#!/usr/bin/env python3
"""UniXNU ADT step for raphael (Redmi K20 Pro / Mi 9T Pro, SM8150).

raphael is the same SM8150 silicon as guacamole (OnePlus 7 Pro); only the
board compatible string and the panel resolution differ (1080x2340). The
UniXNU payload driver passes the generic ADT flags (chip-id, owned-memory-size,
root-match UUID, CPU registers, PSCI method, trust cache, ...). The raphael
hardware profile in mkadt.py owns those values; accept the flags and generate
the D22AP/raphael tree with the requested DRAM size.

The *iOS identity* the tree carries (product type / model / chip-id / canvas /
base ADT) is parameterised in scripts/devices.py's `ios` dict and exposed here
through mkadt.py's --ios-* flags, so moving to an iOS 26-capable device does
not require touching this file. The legacy --base-d22ap flag still works for
the iPhone X artifact; it is now an alias of --base-adt.
"""
import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output", required=True)
    parser.add_argument("--dram-size", default="0xc0000000")
    parser.add_argument("--owned-memory-size", type=lambda value: int(value, 0))
    parser.add_argument("--base-d22ap", default=None,
                        help="path to base-d22ap.adt (iPhone X artifact, alias of --base-adt)")
    parser.add_argument("--base-adt", default=None,
                        help="path to the fetched base device tree (default: the identity artifact)")
    parser.add_argument("--device", default="raphael",
                        help="hardware profile (default: raphael)")
    parser.add_argument("--ios-product-type", default=None,
                        help="override profile identity product type, e.g. D321AP")
    parser.add_argument("--ios-model", default=None,
                        help="override profile identity model, e.g. iPhone11,2")
    parser.add_argument("--ios-target-type", default=None,
                        help="override target-type (default: product type without AP suffix)")
    parser.add_argument("--ios-chip-id", type=lambda value: int(value, 0), default=None,
                        help="override AES chip-id, e.g. 0x8020 for A12")
    parser.add_argument("--ios-canvas", default=None, metavar="WxH",
                        help="override presented canvas, e.g. 828x1792")
    parser.add_argument("--ios-display-scale", type=int, default=None,
                        help="override /chosen display-scale (1|2|3)")
    known, _unknown = parser.parse_known_args()
    tool = Path(__file__).resolve().parent / "mkadt.py"
    command = [sys.executable, str(tool), known.output, "--device", known.device,
               "--dram-size", known.dram_size]
    if known.owned_memory_size is not None:
        command += ["--owned-memory-size", str(known.owned_memory_size)]
    if known.base_adt is not None:
        command += ["--base-adt", known.base_adt]
    if known.base_d22ap is not None:
        command += ["--base-adt", known.base_d22ap]
    if known.ios_product_type is not None:
        command += ["--ios-product-type", known.ios_product_type]
    if known.ios_model is not None:
        command += ["--ios-model", known.ios_model]
    if known.ios_target_type is not None:
        command += ["--ios-target-type", known.ios_target_type]
    if known.ios_chip_id is not None:
        command += ["--ios-chip-id", str(known.ios_chip_id)]
    if known.ios_canvas is not None:
        command += ["--ios-canvas", known.ios_canvas]
    if known.ios_display_scale is not None:
        command += ["--ios-display-scale", str(known.ios_display_scale)]
    import os
    env = dict(os.environ)
    subprocess.run(command, check=True, env=env)


if __name__ == "__main__":
    main()
