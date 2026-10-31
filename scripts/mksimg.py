#!/usr/bin/env python3
"""Convert a raw image to an Android sparse image.

Why: `fastboot -S <n> flash` loads the WHOLE raw image into RAM to sparsify it,
which dies with std::bad_alloc on an 8 GB image. Feeding fastboot an
already-sparse file lets it stream chunk by chunk instead.

Android sparse format (little endian):

  file header (28 bytes)
    u32 magic        0xED26FF3A
    u16 major_ver    1
    u16 minor_ver    0
    u16 file_hdr_sz  28
    u16 chunk_hdr_sz 12
    u32 blk_sz       block size in bytes
    u32 total_blks   blocks in the ORIGINAL image
    u32 total_chunks number of chunks that follow
    u32 image_crc    0 (unused)

  chunk header (12 bytes)
    u16 chunk_type   0xCAC1 raw / 0xCAC2 fill / 0xCAC3 don't care
    u16 reserved
    u32 chunk_sz     blocks covered by this chunk
    u32 total_sz     bytes of this chunk including its header
"""
import argparse
import struct
from pathlib import Path

MAGIC = 0xED26FF3A
CHUNK_RAW = 0xCAC1
CHUNK_DONT_CARE = 0xCAC3
FILE_HDR_SZ = 28
CHUNK_HDR_SZ = 12


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--block-size", type=int, default=4096)
    ap.add_argument("--max-chunk-blocks", type=int, default=16384,
                    help="cap raw chunks (16384 x 4096 = 64 MiB)")
    args = ap.parse_args()

    bs = args.block_size
    src = Path(args.raw)
    size = src.stat().st_size
    total_blks = (size + bs - 1) // bs

    chunks = []
    data_run = []        # list of block-sized bytes
    zero_run = 0

    def flush_data():
        nonlocal data_run
        if not data_run:
            return
        blob = b"".join(data_run)
        data_run = []
        off = 0
        while off < len(blob):
            take = min(len(blob) - off, args.max_chunk_blocks * bs)
            chunks.append((CHUNK_RAW, take // bs, blob[off:off + take]))
            off += take

    def flush_zeros():
        nonlocal zero_run
        if zero_run:
            chunks.append((CHUNK_DONT_CARE, zero_run, None))
            zero_run = 0

    f = open(src, "rb")
    for idx in range(total_blks):
        blkdata = f.read(bs)
        if len(blkdata) < bs:                 # final partial block
            blkdata = blkdata + b"\0" * (bs - len(blkdata))
        if blkdata.count(0) == bs:            # all-zero block
            flush_data()
            zero_run += 1
        else:
            flush_zeros()
            data_run.append(blkdata)
        if idx % 200000 == 0:
            print("  scanning block %d / %d" % (idx, total_blks), flush=True)
    f.close()
    flush_data()
    flush_zeros()

    covered = sum(n for _t, n, _p in chunks)
    assert covered == total_blks, "chunk coverage %d != total blocks %d" % (covered, total_blks)

    with open(args.output, "wb") as out:
        out.write(struct.pack("<IHHHHIIII", MAGIC, 1, 0, FILE_HDR_SZ, CHUNK_HDR_SZ,
                              bs, total_blks, len(chunks), 0))
        for ctype, nblk, payload in chunks:
            if ctype == CHUNK_RAW:
                out.write(struct.pack("<HHII", ctype, 0, nblk, CHUNK_HDR_SZ + len(payload)))
                out.write(payload)
            else:
                out.write(struct.pack("<HHII", ctype, 0, nblk, CHUNK_HDR_SZ))

    raw_bytes = sum(len(p) for t, _n, p in chunks if t == CHUNK_RAW)
    out_size = Path(args.output).stat().st_size
    print("sparse image: %s" % args.output)
    print("  original   : %d bytes (%.3f GB), %d blocks" % (size, size / 1024 ** 3, total_blks))
    print("  chunks     : %d (%d raw, %d don't-care)"
          % (len(chunks), sum(1 for t, _, _ in chunks if t == CHUNK_RAW),
             sum(1 for t, _, _ in chunks if t == CHUNK_DONT_CARE)))
    print("  data bytes : %d (%.3f GB)" % (raw_bytes, raw_bytes / 1024 ** 3))
    print("  output size: %d bytes (%.3f GB)" % (out_size, out_size / 1024 ** 3))


if __name__ == "__main__":
    main()
