"""Idempotently inject the UniXNU build hooks into a Project Aloha tree.

`patches/aloha-guacamole.patch` carries two hunks whose context moved between
Aloha releases (the marker comment changed from "## aloha patch" to
"## woa-msmnile patch", and SurfaceDuo1NoSb.dsc lost the CranePkg lines that
anchored the UniXNULib hunk). Without them git apply aborts the whole patch and
the build never starts. Those two edits are pure *additions* though, so they
can be re-done here without depending on any context.

usage: python3 fix_aloha_tree.py <uefi_tree_root>
"""
import re
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "uefi")


def report(path, changed, what):
    print(("  patched  " if changed else "  ok       ") + what + "  [" + str(path) + "]")


# --------------------------------------------------------------------------
# 1. PlatformBuildNoSb.py - add the UniXNU / DarwinBoot package search paths
# --------------------------------------------------------------------------
py = root / "Platforms/SurfaceDuo1Pkg/PlatformBuildNoSb.py"
if py.exists():
    text = py.read_text(encoding="utf-8")
    need = ["../build-tree/package", "../build-tree/drivers/DarwinBoot"]
    missing = [n for n in need if n not in text]
    if missing:
        # Anchor on the Silicon/QC entry, which every revision has.
        m = re.search(r'^[ \t]*"Silicon/QC/"\s*\+\s*SiliconName[ \t]*,?[ \t]*$',
                      text, re.M)
        if m is None:
            sys.exit("FATAL: cannot find the Silicon/QC entry in %s" % py)
        indent = re.match(r"^[ \t]*", m.group(0)).group(0)
        line = m.group(0).rstrip()
        if not line.endswith(","):
            line += ","
        add = "\n".join(indent + '"%s",' % n for n in missing)
        text = text[:m.start()] + line + "\n" + add + text[m.end():]
        py.write_text(text, encoding="utf-8")
    report(py, bool(missing), "package search paths " + ",".join(need))
else:
    print("  skip      PlatformBuildNoSb.py not present")

# --------------------------------------------------------------------------
# 1c. LibUfdt - vendor the copy that compiles with a modern clang
# --------------------------------------------------------------------------
# QcomModulePkg/Library/LibUfdt/sysdeps/libufdt_sysdeps_vendor.c calls
# AllocatePool/FreePool/strtoul without the headers (and without the local
# strtoul fallback) that newer revisions added. clang treats an implicit
# declaration as an error, so the DXE build dies on this one file. The fixed
# upstream copy is vendored here and installed only when needed.
ufdt = root / "Platforms/QcomModulePkg/Library/LibUfdt/sysdeps/libufdt_sysdeps_vendor.c"
fixed = Path(__file__).resolve().parent / "fixes/libufdt_sysdeps_vendor.c"
if ufdt.is_file() and fixed.is_file():
    text = ufdt.read_text(encoding="utf-8")
    if "MemoryAllocationLib.h" not in text or "strtoul (" not in text:
        ufdt.write_text(fixed.read_text(encoding="utf-8"), encoding="utf-8")
        print("  patched  LibUfdt sysdeps (clang-safe copy installed)")
    else:
        print("  ok       LibUfdt sysdeps already clang-safe")
else:
    print("  skip     LibUfdt sysdeps not present")

# --------------------------------------------------------------------------
# 2. SurfaceDuo1NoSb.dsc - add the FdtLib / UniXNULib library class mappings
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# 1b. board.toml - make sure the Mu package trees are on the packages path
# --------------------------------------------------------------------------
# board.toml's [firmware] packages list was written for a revision where
# ArmPkg still lived inside mu_basecore. Newer Mu trees moved it (and more)
# into the mu_tiano_plus / mu_silicon_arm_tiano submodules, so the DSC fails
# with "ArmPkg/Drivers/ArmGic/ArmGicDxe.inf is not found in packages path".
board = Path("board.toml")
if board.is_file():
    text = board.read_text(encoding="utf-8")
    m = re.search(r"^packages\s*=\s*\[(.*?)^\]", text, re.S | re.M)
    if m:
        have = re.findall(r'"([^"]+)"', m.group(1))
        add = ['{uefi}/%s' % p for p in ("Common/MU_TIANO", "Silicon/Arm/MU_TIANO")
               if (root / p).is_dir() and "{uefi}/%s" % p not in have]
        if add:
            body = "\n".join('  "%s",' % e for e in have + add)
            text = text[:m.start()] + "packages = [\n" + body + "\n]" + text[m.end():]
            board.write_text(text, encoding="utf-8")
        print("  added to packages: %s" % (", ".join(add) or "(nothing)"))

dsc = root / "Platforms/SurfaceDuo1Pkg/SurfaceDuo1NoSb.dsc"
if dsc.exists():
    text = dsc.read_text(encoding="utf-8")
    libs = [
        ("FdtLib", "MdePkg/Library/BaseFdtLib/BaseFdtLib.inf"),
        ("UniXNULib", "UniXNUPkg/Library/UniXNULib/UniXNULib.inf"),
    ]
    missing = [(k, v) for k, v in libs if (k + "|") not in text]
    if missing:
        m = re.search(r"^\[LibraryClasses\.common\][ \t]*$", text, re.M)
        if m is None:
            sys.exit("FATAL: cannot find [LibraryClasses.common] in %s" % dsc)
        add = "\n".join("  %s|%s" % (k, v) for k, v in missing)
        text = text[:m.end()] + "\n" + add + text[m.end():]
        dsc.write_text(text, encoding="utf-8")
    report(dsc, bool(missing), "library mappings " + ",".join(k for k, _ in missing))
else:
    print("  skip      SurfaceDuo1NoSb.dsc not present")
