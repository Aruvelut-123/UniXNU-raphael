#!/usr/bin/env python3
"""Simulate what the SM8150 ABL does with the flash pieces.

The bootloader is not available on the workstation, but its behaviour is
known from the flashes that already worked on this phone:

  * a sparse chunk header is read as "u16 type, u16 res, u32 blocks,
    u32 bytes" (the opposite of the AOSP/libsparse order),
  * DONT_CARE is a seek, not a write of zeros, and
  * each piece is placed at the absolute block its leading DONT_CARE
    chunk declares.

This replays the pieces into a sparse target and then checks that the
target reproduces the source image block for block.  It catches a wrong
chunk field order, a wrong piece order and an off-by-one in the offset
without touching the phone.

    simulate_flash.py SOURCE.simg PIECE_DIR [--target out.img]
"""
import argparse
import os
import struct
import sys

SPARSE_MAGIC = 0xED26FF3A
CHUNK_RAW, CHUNK_FILL, CHUNK_DONT_CARE = 0xCAC1, 0xCAC2, 0xCAC3
FILE_HDR_SZ, CHUNK_HDR_SZ = 28, 12


def read_chunks(path):
    """Return (block_size, [(type, blocks, bytes, data_offset)])."""
    f = open(path, "rb")
    magic, _maj, _mn, fhs, chs, blk, tot, nch, _ck = struct.unpack(
        "<IHHHHIIII", f.read(FILE_HDR_SZ))
    if magic != SPARSE_MAGIC:
        raise SystemExit("%s: not a sparse image" % path)
    out = []
    pos = FILE_HDR_SZ
    for _ in range(nch):
        f.seek(pos)
        t, _res, a, b = struct.unpack("<HHII", f.read(CHUNK_HDR_SZ))
        # ABL order: blocks first, then bytes.
        if t in (CHUNK_FILL, CHUNK_DONT_CARE):
            blocks, nbytes = a, CHUNK_HDR_SZ
        elif b - CHUNK_HDR_SZ == a * blk:
            blocks, nbytes = a, b
        else:
            raise SystemExit("%s: chunk is neither field order" % path)
        out.append((t, blocks, nbytes, pos + CHUNK_HDR_SZ))
        pos += nbytes
    return blk, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("pieces")
    ap.add_argument("--target")
    a = ap.parse_args()

    names = sorted(p for p in os.listdir(a.pieces) if p.endswith(".simg"))
    print("flashing %d pieces in descending order" % len(names))

    # the device: a sparse map of block -> bytes, only for written blocks
    device = {}
    for name in reversed(names):
        path = os.path.join(a.pieces, name)
        blk, chunks = read_chunks(path)
        cursor = None
        wrote = 0
        for (t, blocks, nbytes, off) in chunks:
            if t == CHUNK_DONT_CARE:
                # the piece's absolute start block, then the seek forward
                if cursor is None:
                    cursor = blocks
                    continue
                cursor += blocks
                continue
            if cursor is None:
                cursor = 0
            f = open(path, "rb")
            f.seek(off)
            data = f.read(nbytes - CHUNK_HDR_SZ)
            f.close()
            for i in range(blocks):
                device[cursor + i] = data[i * blk:(i + 1) * blk]
            wrote += blocks
            cursor += blocks
        print("  %-12s wrote %d blocks" % (name, wrote))

    # compare against the source
    blk, chunks = read_chunks(a.source)
    src = {}
    cursor = 0
    for (t, blocks, nbytes, off) in chunks:
        if t == CHUNK_RAW:
            f = open(a.source, "rb")
            f.seek(off)
            data = f.read(nbytes - CHUNK_HDR_SZ)
            f.close()
            for i in range(blocks):
                src[cursor + i] = data[i * blk:(i + 1) * blk]
        cursor += blocks

    print()
    missing = [b for b in src if b not in device]
    extra = [b for b in device if b not in src]
    diff = [b for b in src if b in device and src[b] != device[b]]
    print("source blocks: %d, device blocks: %d" % (len(src), len(device)))
    print("missing: %d, unexpected: %d, differing: %d"
          % (len(missing), len(extra), len(diff)))
    if missing:
        print("  first missing block %d" % missing[0])
    if diff:
        print("  first differing block %d" % diff[0])
    if missing or extra or diff:
        raise SystemExit("SIMULATION FAILED")
    print("SIMULATION OK: the device would hold exactly the source image")


if __name__ == "__main__":
    main()
