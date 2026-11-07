#!/usr/bin/env python3
"""Package the SM8150_EFI.fd as a flashable image for the phone's `esp` GPT partition.

Why this exists
---------------
Project Aloha's build (scripts/build-firmware.py) already produces
uefi/Build/SurfaceDuo1Pkg/{TARGET}_CLANGPDB/FV/SM8150_EFI.fd -- a raw EDK II
firmware volume.  Nothing turns it into an image the user can flash to the
phone's `esp` GPT partition so that the bootloader can actually load it.  This
script wraps the FD into:

  1. a raw esp image (`SM8150_EFI.esp.img`, ≤ 62390272 bytes, padded with
     zeros to the exact esp size so every block the ABL expects is written),
     and
  2. an Android-sparse variant (`SM8150_EFI.esp.simg`) in the layout this
     bootloader expects (chunk header carries block-count then byte-count,
     i.e. what mksimg.py / this toolchain emits), plus a small metadata file
     (size.json) recording the real FD size.

Usage
-----
    scripts/build-efi-image.py \
        --fd uefi/Build/SurfaceDuo1Pkg/RELEASE_CLANGPDB/FV/SM8150_EFI.fd \
        --out out/raphael/efi/SM8150_EFI.esp.img

Without --fd the script searches the standard build tree for the newest
`..._CLANGPDB/FV/SM8150_EFI.fd`.  Pass --no-sparse to skip the sparse variant.

Then flash with fastboot:

    fastboot flash esp out/raphael/efi/SM8150_EFI.esp.img    # raw image
    fastboot flash esp out/raphael/efi/SM8150_EFI.esp.simg   # sparse image

The raw image is padded to the full esp partition size (LBA 62500096..62621951
= 121856 sectors = 62390272 bytes ≈ 59.5 MiB), so the ABL writes every block
it expects even though the FD itself is smaller.

The partition ceiling is enforced: a larger FD is an error, not a silent
truncation.

Partition facts (verified from the GPT dump in GPT-ANALYSIS.md):
  esp  [59]: LBA 62500096..62621951 = 121856 sectors = 62390272 bytes (~59.5 MiB)
"""
import argparse
import json
import os
import struct
import sys
from pathlib import Path

ESP_BYTES = 62390272          # LBA 62500096..62621951 inclusive
ESP_LBA_FIRST = 62500096
ESP_LBA_LAST = 62621951
ESP_SECTORS = ESP_LBA_LAST - ESP_LBA_FIRST + 1

SPARSE_MAGIC = 0xED26FF3A
CHUNK_RAW = 0xCAC1
CHUNK_DONT_CARE = 0xCAC3
FILE_HDR_SZ = 28
CHUNK_HDR_SZ = 12
BS = 4096


def find_fd(default_dirs):
    """Locate the newest SM8150_EFI.fd under the standard build trees."""
    cands = []
    for d in default_dirs:
        p = Path(d)
        if p.is_dir():
            cands.extend(p.rglob("SM8150_EFI.fd"))
    if not cands:
        return None
    return sorted(cands, key=lambda p: p.stat().st_mtime)[-1]


def write_sparse(raw_path, out_path):
    """Convert a raw image to an Android sparse image in ABL block-count order."""
    size = raw_path.stat().st_size
    total_blks = (size + BS - 1) // BS
    cap_blocks = 16384  # 64 MiB raw runs

    n_raw = n_dc = 0
    raw_bytes = 0
    zero_run = 0
    buf = bytearray()

    f = open(raw_path, "rb", buffering=0)
    out = open(out_path, "wb")

    def write_raw():
        nonlocal buf, n_raw, raw_bytes
        if not buf:
            return
        out.write(struct.pack("<HHII", CHUNK_RAW, 0, len(buf) // BS,
                              CHUNK_HDR_SZ + len(buf)))
        out.write(bytes(buf))
        n_raw += 1
        raw_bytes += len(buf)
        buf = bytearray()

    def write_dontcare():
        nonlocal zero_run, n_dc
        if not zero_run:
            return
        out.write(struct.pack("<HHII", CHUNK_DONT_CARE, 0, zero_run,
                              CHUNK_HDR_SZ))
        n_dc += 1
        zero_run = 0

    out.write(b"\0" * FILE_HDR_SZ)  # placeholder, patched below

    slab = 1 << 20
    idx = 0
    while True:
        chunk = f.read(slab)
        if not chunk:
            break
        pad = (-len(chunk)) % BS
        if pad:
            chunk = chunk + b"\0" * pad
        for off in range(0, len(chunk), BS):
            blk = chunk[off:off + BS]
            if blk.count(0) == BS:
                write_raw()
                zero_run += 1
            else:
                write_dontcare()
                buf += blk
                if len(buf) >= cap_blocks * BS:
                    write_raw()
            idx += 1
    f.close()

    if idx > total_blks:
        over = idx - total_blks
        if over * BS <= len(buf):
            buf = buf[:len(buf) - over * BS]
        idx = total_blks
    write_raw()
    write_dontcare()

    total_chunks = n_raw + n_dc
    covered = raw_bytes // BS
    dc_blocks = total_blks - covered
    if dc_blocks < 0:
        sys.exit("error: raw blocks exceed image blocks")

    out.seek(0)
    out.write(struct.pack("<IHHHHIIII", SPARSE_MAGIC, 1, 0, FILE_HDR_SZ,
                          CHUNK_HDR_SZ, BS, total_blks, total_chunks, 0))
    out.close()
    return os.path.getsize(out_path), total_chunks


def main():
    ap = argparse.ArgumentParser(description="Build a flashable esp image from SM8150_EFI.fd")
    ap.add_argument("--fd", default=None,
                    help="path to SM8150_EFI.fd (default: newest in the build tree)")
    ap.add_argument("--out", default=None,
                    help="output raw image path (default: <fd dir>/SM8150_EFI.esp.img)")
    ap.add_argument("--no-sparse", action="store_true",
                    help="skip the Android-sparse variant")
    ap.add_argument("--esp-size", type=int, default=ESP_BYTES,
                    help=f"esp size in bytes (default {ESP_BYTES})")
    args = ap.parse_args()

    default_dirs = [
        "uefi/Build/SurfaceDuo1Pkg",
        str(Path("out") / "raphael"),
    ]
    fd = Path(args.fd) if args.fd else find_fd(default_dirs)
    if fd is None:
        sys.exit("error: no SM8150_EFI.fd found (pass --fd or run build-firmware.py first)")
    if not fd.is_file():
        sys.exit("error: %s: not a file" % fd)

    fd_size = fd.stat().st_size
    print(f"fd         : {fd}")
    print(f"fd size    : {fd_size} bytes ({fd_size / 1024 ** 2:.3f} MiB)")
    print(f"esp size   : {args.esp_size} bytes ({args.esp_size / 1024 ** 2:.3f} MiB, "
          f"LBA {ESP_LBA_FIRST}..{ESP_LBA_LAST})")

    if fd_size > args.esp_size:
        sys.exit(f"error: SM8150_EFI.fd ({fd_size} bytes) does not fit esp "
                 f"({args.esp_size} bytes); cannot build a flashable image")

    out = Path(args.out) if args.out else (fd.parent / "SM8150_EFI.esp.img")
    out.parent.mkdir(parents=True, exist_ok=True)

    # Raw image: FD at the start, then zeros padding to the full esp size so
    # every block of the partition gets written (ABL seeks don't write zeros).
    buf = fd.read_bytes() + b"\0" * (args.esp_size - fd_size)
    out.write_bytes(buf)
    print(f"raw image  : {out} ({args.esp_size} bytes)")

    meta = {
        "fd": str(fd),
        "fd_size": fd_size,
        "esp_size": args.esp_size,
        "esp_lba_first": ESP_LBA_FIRST,
        "esp_lba_last": ESP_LBA_LAST,
        "lba_size": 512,
        "flash": f"fastboot flash esp {out}",
    }
    meta_path = out.with_suffix(".size.json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    if not args.no_sparse:
        simg = out.with_suffix(".simg")
        total_size, total_chunks = write_sparse(out, simg)
        print(f"sparse image: {simg} ({total_size} bytes, {total_chunks} chunks)")
        print(f"flash sparse: fastboot flash esp {simg}")

    print()
    print("OK: flashable esp image ready")
    print(f"  fastboot flash esp {out}")


if __name__ == "__main__":
    main()
