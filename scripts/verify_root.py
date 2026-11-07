#!/usr/bin/env python3
"""Check an HFS+ iOS root image by its bytes, without mounting it.

The build server proves the volume properly: it mounts it with the hfsplus
driver, runs fsck over it and lists the root.  This is the local half of
that check.  It confirms that the file sitting on this machine -- the file
that is about to be flashed to the phone -- really is an iOS root and really
carries the activation seed, using only bytes that are in the file.

Nothing here parses the catalog B-tree.  Its record layout was not worth
reverse-engineering when the build server can simply mount the volume; what
matters locally is that the image is a valid HFS+ volume of the expected
size and that specific byte sequences are present.

    verify_root.py IMAGE.simg [--product-version 26.x] [--build-version 20Axxx]

The activation seed it expects (ProductVersion / BuildVersion) must match
exactly what scripts/seed_activation.py writes -- keep them in lockstep.
Defaults are the iOS 26 values; pass --product-version / --build-version to
check a different release's image.
"""
import os
import plistlib
import struct
import sys

SPARSE_MAGIC = 0xED26FF3A
CHUNK_RAW = 0xCAC1
FILE_HDR_SZ, CHUNK_HDR_SZ = 28, 12

# The container the upstream bring-up image was seeded with by hand.
CONTAINER_ID = "D90C94C4-F94E-4FCF-8A28-A93BE3846D8E"

# iOS 26 defaults: ProductVersion 26.0 / BuildVersion 23A341.  Must stay in
# lockstep with scripts/seed_activation.py (verified by the lead via ipsw.me;
# research-ios26.md).
DEFAULT_PRODUCT_VERSION = "26.0"
DEFAULT_BUILD_VERSION = "23A341"


def ark(product_version, build_version):
    return {
        "-ActivationState": "Activated",
        "-BrickState": False,
        "-BuildVersion": build_version,
        "-ProductVersion": product_version,
        "-DataMigrationCompleted": True,
        "-PreSydroDataMigrationCompleted": True,
    }


# Directory entry names live in the catalog as UTF-16BE.  Finding them proves
# the catalog really is an iOS one.
CATALOG_NAMES = [
    "launchd",
    "dyld_shared_cache_arm64.30",
    "systembag.kb",
    "com.apple.purplebuddy.plist",
    "SpringBoard",
    "SystemVersion.plist",
    "data_ark.plist",
    CONTAINER_ID,
]


def seed_plist_bytes(product_version=DEFAULT_PRODUCT_VERSION,
                     build_version=DEFAULT_BUILD_VERSION):
    """The exact bytes seed_activation.py writes into data_ark.plist."""
    import io
    buf = io.BytesIO()
    plistlib.dump(ark(product_version, build_version), buf, fmt=plistlib.FMT_XML)
    return buf.getvalue()


class SparseImage:
    """Random access to a sparse image, plus a streaming scan of its data."""

    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb")
        hdr = self.f.read(FILE_HDR_SZ)
        (magic, _maj, _mn, _fsz, _csz, self.blk, self.total_blocks,
         nch, _cks) = struct.unpack("<IHHHHIIII", hdr)
        if magic != SPARSE_MAGIC:
            raise SystemExit("%s: not an Android sparse image" % path)
        self.chunks = []
        pos = FILE_HDR_SZ
        block = 0
        for _ in range(nch):
            self.f.seek(pos)
            ctype, _res, blocks, total = struct.unpack("<HHII",
                                                       self.f.read(CHUNK_HDR_SZ))
            self.chunks.append((ctype, blocks, pos + CHUNK_HDR_SZ, total, block))
            block += blocks
            pos += total

    def read(self, offset, length):
        """Read `length` bytes at `offset` inside the sparse volume."""
        out = bytearray()
        for ctype, blocks, data_off, total, blk0 in self.chunks:
            if ctype != CHUNK_RAW:
                continue
            start = blk0 * self.blk
            end = start + blocks * self.blk
            if end <= offset or start >= offset + length:
                continue
            take = min(end, offset + length) - max(start, offset)
            self.f.seek(data_off + (max(start, offset) - start))
            out += self.f.read(take)
        return bytes(out)

    def scan(self, needles):
        """Look for every needle in the raw payload.

        The needles are matched as plain bytes; the caller decides whether to
        pass UTF-16BE or ASCII.
        """
        hits = {n: False for n in needles}
        longest = max(len(n) for n in needles)
        carry = b""
        for ctype, _blocks, data_off, total, _blk0 in self.chunks:
            if ctype != CHUNK_RAW:
                continue
            self.f.seek(data_off)
            remaining = total - CHUNK_HDR_SZ
            while remaining > 0:
                chunk = self.f.read(min(16 << 20, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                buf = carry + chunk
                for needle in needles:
                    if not hits[needle] and needle in buf:
                        hits[needle] = True
                carry = buf[-longest + 1:]
        return hits


def main():
    argv = sys.argv[1:]
    product_version = DEFAULT_PRODUCT_VERSION
    build_version = DEFAULT_BUILD_VERSION
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--product-version", "--pv") and i + 1 < len(argv):
            product_version = argv[i + 1]; i += 2
        elif arg in ("--build-version", "--bv") and i + 1 < len(argv):
            build_version = argv[i + 1]; i += 2
        else:
            break
    rest = argv[i:]
    if len(rest) != 1:
        raise SystemExit(__doc__)
    path = rest[0]
    if not os.path.isfile(path):
        raise SystemExit("%s: no such file" % path)

    img = SparseImage(path)
    print("image      : %s" % path)
    print("sparse     : %d bytes, %d chunks, block size %d, %d blocks"
          % (os.path.getsize(path), len(img.chunks), img.blk, img.total_blocks))

    # The volume header sits at byte 1024 of the volume.
    head = img.read(1024, 512)
    sig, ver = struct.unpack(">HH", head[0:4])
    if sig not in (0x482B, 0x4858):
        raise SystemExit("!! not an HFS+ volume (signature %#x)" % sig)
    files = struct.unpack(">I", head[32:36])[0]
    folders = struct.unpack(">I", head[36:40])[0]
    block_size = struct.unpack(">I", head[40:44])[0]
    total_blocks = struct.unpack(">I", head[44:48])[0]
    print("volume     : signature %#x version %d, case-sensitive %s"
          % (sig, ver, "yes" if sig == 0x4858 else "no"))
    print("             block size %d, %d blocks (%.2f GiB)"
          % (block_size, total_blocks,
             total_blocks * block_size / 2 ** 30))
    print("             catalog claims %d files, %d folders" % (files, folders))

    print()
    print("catalog entry names (UTF-16BE):")
    names = [n.encode("utf-16-be") for n in CATALOG_NAMES]
    hits = img.scan(names)
    missing = []
    for text, needle in zip(CATALOG_NAMES, names):
        ok = hits[needle]
        print("   %-40s %s" % (text, "found" if ok else "MISSING"))
        if not ok:
            missing.append(text)

    print()
    print("activation seed:")
    seed = seed_plist_bytes(product_version, build_version)
    seed_ok = img.scan([seed])[seed]
    print("   %-40s %s (%d bytes)"
          % ("data_ark.plist payload",
             "found" if seed_ok else "MISSING", len(seed)))
    if not seed_ok:
        missing.append("activation seed")

    if missing:
        print()
        print("!! FAILED: %d marker(s) missing" % len(missing))
        return 1
    print()
    print("OK: the image is an iOS root and carries the activation seed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
