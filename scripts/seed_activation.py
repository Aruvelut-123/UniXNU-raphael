#!/usr/bin/env python3
"""Seed the activation state into an assembled iOS root.

The upstream bring-up tweaks skip this: Apple's OS.dmg ships no
mobileactivationd system container, so there is nothing for them to find and
they print "skipped data ark".  Without it mobileactivationd starts out
unactivated and the system can block on the activation check.

This creates the container the upstream bring-up image was seeded with by
hand and writes the same data_ark.plist into it.

    seed_activation.py /mnt/iosroot [--product-version 26.x] [--build-version 20Hxxx]

The ProductVersion / BuildVersion written into data_ark.plist default to the
iOS 26 values (the iOS release the port targets).  Pass --product-version /
--build-version to match a different release -- they must match what
scripts/verify_root.py compares against.
"""
import os
import plistlib
import sys

# The container the upstream bring-up image used.
CONTAINER_ID = "D90C94C4-F94E-4FCF-8A28-A93BE3846D8E"
MOBILE_UID = 501
MOBILE_GID = 501

# iOS 26 defaults: ProductVersion 26.0 / BuildVersion 23A341, the first iOS 26
# release for iPhone 11 (N104AP / iPhone12,1). Verified by the lead via the
# ipsw.me API (research-ios26.md).  Pass --product-version / --build-version to
# match a different release.
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
    if len(rest) != 1 or not os.path.isdir(rest[0]):
        raise SystemExit(__doc__)
    root = rest[0]

    idir = os.path.join(root, "private/var/containers/Data/System",
                        CONTAINER_ID, "Library/internal")
    os.makedirs(idir, exist_ok=True)
    os.chown(idir, MOBILE_UID, MOBILE_GID)
    os.chmod(idir, 0o755)

    path = os.path.join(idir, "data_ark.plist")
    with open(path, "wb") as f:
        plistlib.dump(ark(product_version, build_version), f, fmt=plistlib.FMT_XML)
    os.chown(path, MOBILE_UID, MOBILE_GID)
    os.chmod(path, 0o600)
    print("data ark seeded in", idir)


if __name__ == "__main__":
    main()
