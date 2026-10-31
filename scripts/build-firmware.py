#!/usr/bin/env python3
"""Build the Aloha NOSB firmware volume with the UniXNU/DarwinBoot INFs for raphael.

raphael reuses guacamole's SM8150 UEFI patch set. The aloha-guacamole.patch
creates the oneplus-guacamole device directory; we clone it to xiaomi-raphael,
rename the DTB/boot-config to raphael, then let the UniXNU firmware driver
build the FV with TARGET_DEVICE=xiaomi-raphael (set in board.toml).
"""
import shutil
import sys
import tomllib
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "unixnu" / "scripts"))

from unixnu import firmware  # noqa: E402

UEFI = ROOT / "uefi"
EDK2 = UEFI / "MU_BASECORE"
TREE = ROOT / "build-tree"
WORK = ROOT / "out" / "raphael"
LOGS = WORK / "logs"
LOGS.mkdir(parents=True, exist_ok=True)

# raphael device directory = clone of guacamole's (same SM8150 silicon).
SRC = UEFI / "Platforms" / "SurfaceDuo1Pkg" / "Device" / "oneplus-guacamole"
DST = UEFI / "Platforms" / "SurfaceDuo1Pkg" / "Device" / "xiaomi-raphael"
if SRC.is_dir() and not DST.is_dir():
    shutil.copytree(SRC, DST)
    for old, new in (("guacamole.dtb", "raphael.dtb"), ("guacamole.toml", "raphael.toml")):
        p = DST / old
        if p.is_file():
            p.rename(DST / new)
    # also mirror the boot config under Resources/Configs
    cfg_src = UEFI / "Resources" / "Configs" / "guacamole.toml"
    if cfg_src.is_file():
        shutil.copy(cfg_src, UEFI / "Resources" / "Configs" / "raphael.toml")
    print(f"firmware: created {DST}")

board = tomllib.loads((ROOT / "board.toml").read_text())
ctx = types.SimpleNamespace(
    board=board,
    tree=TREE,
    work=WORK,
    logs=LOGS,
    jobs=8,
    args=types.SimpleNamespace(skip_preflight=False),
    uefi=UEFI,
)
firmware.build(ctx, None, UEFI, EDK2, "DEBUG")
