#!/usr/bin/env python3
"""Convert an IPSW disk image, or any raw image, into an Android sparse image.

The sparse writer follows UniXNU's `scripts/make-android-sparse.py`: every
all-zero 4096-byte block becomes a FILL chunk with value 0 (never DONT_CARE),
everything else becomes RAW chunks, and the expanded result is verified to be
byte-identical in size.

UDIF-compressed `.dmg` payloads are read with UniXNU's own reader
(`scripts/unixnu/udif.py`, which handles raw/zlib/bzip2/LZFSE and needs the
`lzfse` tool from the Linux toolchain). That reader is imported from a UniXNU
checkout, so the two implementations cannot drift.

Usage:
    # From a DMG extracted out of an IPSW
    python3 scripts/ipsw_to_sparse.py --dmg OS.dmg --output unixnu.sparse

    # From an IPSW: extract the requested member, then convert it
    python3 scripts/ipsw_to_sparse.py --ipsw restore.ipsw --member 038-XXXXX.dmg \
        --output unixnu.sparse

    # From a raw image that is already a full disk image
    python3 scripts/ipsw_to_sparse.py --raw-image userdata-root.img \
        --output unixnu.sparse

The UniXNU checkout is found at $UNIXNU_DIR, then ../UniXNU beside this
repository.
"""
import argparse
import os
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

BLOCK = 4096
MAGIC = 0xED26FF3A
RAW, FILL, DONT_CARE = 0xCAC1, 0xCAC2, 0xCAC3
MAX_RAW_BLOCKS = 4096  # 16 MiB per RAW chunk
ZERO = bytes(BLOCK)


# --------------------------------------------------------------------- UniXNU
def find_unixnu() -> Path | None:
    """Locate a UniXNU checkout that has the udif reader."""
    here = Path(__file__).resolve().parent.parent
    candidates = [
        os.environ.get('UNIXNU_DIR'),
        here.parent / 'UniXNU',
        Path('/home/unixnu-work/UniXNU'),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if (path / 'scripts' / 'unixnu' / 'udif.py').is_file():
            return path
    return None


def load_udif():
    """Import scripts/unixnu/udif.py from a UniXNU checkout."""
    unixnu = find_unixnu()
    if unixnu is None:
        raise SystemExit(
            'UniXNU checkout not found. Set UNIXNU_DIR to a checkout that '
            'contains scripts/unixnu/udif.py, or pass --raw-image instead.'
        )
    sys.path.insert(0, str(unixnu / 'scripts'))
    from unixnu.udif import Image  # noqa: E402
    return Image


# --------------------------------------------------------------------- sparse
def write_sparse(source: Path, target: Path) -> int:
    """Convert a raw image to Android sparse format. Returns the block count."""
    size = source.stat().st_size
    if size % BLOCK:
        raise SystemExit(f'input size {size} is not a multiple of {BLOCK}')
    total_blocks = size // BLOCK

    with open(source, 'rb') as src, open(target, 'wb') as out:
        out.write(b'\0' * 28)  # header placeholder, rewritten below

        pending = bytearray()
        pending_blocks = 0
        zero_run = 0
        chunks = 0

        def flush_raw():
            nonlocal pending, pending_blocks, chunks
            if pending_blocks:
                out.write(struct.pack('<HHII', RAW, 0, pending_blocks,
                                      12 + len(pending)))
                out.write(pending)
                chunks += 1
                pending = bytearray()
                pending_blocks = 0

        def flush_zero():
            nonlocal zero_run, chunks
            if zero_run:
                out.write(struct.pack('<HHII', FILL, 0, zero_run, 12 + 4))
                out.write(struct.pack('<I', 0))
                chunks += 1
                zero_run = 0

        remaining = total_blocks
        while remaining:
            take = min(remaining, 1024)
            data = src.read(take * BLOCK)
            if len(data) != take * BLOCK:
                raise SystemExit('short read from source image')
            for offset in range(0, len(data), BLOCK):
                block = data[offset:offset + BLOCK]
                if block == ZERO:
                    flush_raw()
                    zero_run += 1
                    if zero_run >= 0x7FFF:
                        flush_zero()
                else:
                    flush_zero()
                    pending.extend(block)
                    pending_blocks += 1
                    if pending_blocks >= MAX_RAW_BLOCKS:
                        flush_raw()
            remaining -= take

        flush_raw()
        flush_zero()

        out.seek(0)
        # struct sparse_header: u32 magic, u16 major, u16 minor,
        # u16 file_hdr_sz, u16 chunk_hdr_sz, u32 blk_sz, u32 total_blks,
        # u32 total_chunks, u32 image_checksum  (28 bytes)
        out.write(struct.pack('<IHHHHIIII', MAGIC, 1, 0, 28, 12,
                              BLOCK, total_blocks, chunks, 0))
    return total_blocks


def verify_sparse(sparse_path: Path, expected_size: int) -> None:
    """Expand the sparse image in memory-free fashion and check the byte size."""
    with open(sparse_path, 'rb') as f:
        magic, major, minor, file_hdr_sz, chunk_hdr_sz = struct.unpack(
            '<IHHHH', f.read(12))
        if magic != MAGIC:
            raise SystemExit(f'invalid sparse magic: {hex(magic)}')
        blk_sz, total_blks, total_chunks, _ = struct.unpack('<IIII', f.read(16))
        if blk_sz != BLOCK:
            raise SystemExit(f'unsupported sparse block size: {blk_sz}')
        f.seek(file_hdr_sz)

        expanded = 0
        for _ in range(total_chunks):
            chunk_type, _, chunk_sz, total_sz = struct.unpack('<HHII', f.read(12))
            payload = total_sz - chunk_hdr_sz
            if chunk_type == RAW:
                expanded += chunk_sz * BLOCK
            elif chunk_type == FILL:
                expanded += chunk_sz * BLOCK
            elif chunk_type == DONT_CARE:
                expanded += chunk_sz * BLOCK
            else:
                raise SystemExit(f'unknown chunk type: {hex(chunk_type)}')
            f.seek(payload, 1)

    if expanded != expected_size:
        raise SystemExit(
            f'sparse expansion mismatch: got {expanded}, expected {expected_size}')
    if expanded != total_blks * BLOCK:
        raise SystemExit('sparse chunk sizes disagree with the block count')
    print(f'verified: {sparse_path} expands to {expanded} bytes '
          f'({total_chunks} chunks)')


# ------------------------------------------------------------------ extraction
def extract_ipsw_member(ipsw: Path, member: str | None, output_dir: Path) -> Path:
    """Extract one member of an IPSW, or pick the largest .dmg by default."""
    with zipfile.ZipFile(ipsw) as zf:
        names = zf.namelist()
        if member:
            if member not in names:
                raise SystemExit(f'{member} is not in {ipsw}')
            chosen = member
        else:
            dmgs = [n for n in names if n.lower().endswith('.dmg')]
            if not dmgs:
                raise SystemExit(
                    f'{ipsw} contains no .dmg members; list them with '
                    f'--list and pass --member')
            chosen = max(dmgs, key=lambda n: zf.getinfo(n).file_size)
            print(f'note: no --member given, using the largest .dmg: {chosen}')
        print(f'extracting {chosen}')
        zf.extract(chosen, output_dir)
        return output_dir / chosen


def dmg_to_raw(dmg: Path, raw: Path) -> int:
    """Materialize a disk image (UDIF or raw) as raw bytes. Returns byte size."""
    Image = load_udif()
    image = Image(str(dmg))
    total = 0
    with open(raw, 'wb') as out:
        for chunk in image.blocks():
            out.write(chunk)
            total += len(chunk)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Convert an IPSW disk image or raw image to Android sparse format')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--ipsw', type=Path, help='IPSW archive')
    source.add_argument('--dmg', type=Path, help='disk image (.dmg or raw)')
    source.add_argument('--raw-image', type=Path, help='raw image, already a full disk')
    parser.add_argument('--member', help='IPSW member to extract (default: largest .dmg)')
    parser.add_argument('--list', action='store_true',
                        help='list IPSW members and exit')
    parser.add_argument('--output', type=Path, help='output .sparse file')
    parser.add_argument('--keep-raw', type=Path,
                        help='also keep the materialized raw image at this path')
    args = parser.parse_args()

    if args.list:
        if not args.ipsw:
            parser.error('--list needs --ipsw')
        with zipfile.ZipFile(args.ipsw) as zf:
            for info in sorted(zf.infolist(), key=lambda i: -i.file_size):
                print(f'{info.file_size:>13}  {info.filename}')
        return 0

    if not args.output:
        parser.error('--output is required unless --list is given')

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        if args.raw_image:
            raw = args.raw_image
            if not raw.is_file():
                raise SystemExit(f'no such file: {raw}')
            size = raw.stat().st_size
            print(f'raw input: {raw} ({size} bytes)')

        elif args.dmg:
            if not args.dmg.is_file():
                raise SystemExit(f'no such file: {args.dmg}')
            if args.keep_raw:
                raw = args.keep_raw
            else:
                raw = tmpdir / 'disk.raw'
            size = dmg_to_raw(args.dmg, raw)
            print(f'materialized {args.dmg} -> {size} bytes')

        else:  # --ipsw
            if not args.ipsw.is_file():
                raise SystemExit(f'no such file: {args.ipsw}')
            member = extract_ipsw_member(args.ipsw, args.member, tmpdir)
            if args.keep_raw:
                raw = args.keep_raw
            else:
                raw = tmpdir / 'disk.raw'
            size = dmg_to_raw(member, raw)
            print(f'materialized {member.name} -> {size} bytes')

        print(f'writing sparse image: {args.output}')
        blocks = write_sparse(raw, args.output)
        if blocks * BLOCK != size:
            raise SystemExit('block count does not match the input size')
        verify_sparse(args.output, size)

    print(f'done: {args.output}')
    print(f'flash with: fastboot flash <partition> {args.output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())