#!/usr/bin/env python3
"""Compile the UniXNU boot chain into a Project Aloha UEFI platform.

Aloha's platform package describes only Windows-capable firmware. This script
adds the UniXNU boot chain -- the boot menu application, the boot option
registration driver, the initrd block device and the DarwinBoot kernel loader
-- to the DSC/FDF of a given platform, and teaches the platform build script to
find the UniXNU packages through an environment variable.

Every edit is guarded by a marker so the script is idempotent, and the DSC/FDF
changes sit behind a BUILD_UNIXNU switch whose default is 0, so a plain Aloha
build is byte-for-byte unaffected.
"""

import argparse
import pathlib
import sys

COMPONENTS = [
    "UniXNUPkg/Application/UniXNU/UniXNU.inf",
    "UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf",
    "UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf",
    "DarwinBootPkg/Driver/DarwinBoot.inf",
]

# Boot option registration needs to enumerate and read partitions. Aloha's
# device DXE list does carry the disk stack for some boards, so these are only
# listed in the UniXNU include file and EDK II tolerates the duplicate when the
# platform already builds them.
# Aloha builds the SCSI stack and, for boards that need it, a RAM partition
# driver, but its device DXE list carries neither DiskIoDxe nor PartitionDxe and
# no FAT driver. The UniXNU boot option registration walks partitions to find
# EFI/UniXNU, and DarwinBoot reads the payload off FAT, so both are required.
DISK_STACK = [
    "MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf",
    "MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe.inf",
    "FatPkg/EnhancedFatDxe/Fat.inf",
]

LIBRARIES = [
    "UniXNULib|UniXNUPkg/Library/UniXNULib/UniXNULib.inf",
]

MARKER = "# --- UniXNU (added by stage-aloha-unixnu.py) ---"
MARKER_DEFINES = MARKER + " defines"
MARKER_COMPONENTS = MARKER + " components"
MARKER_FDF = MARKER + " fvmain"
MARKER_BUILD = MARKER + " packagespath"


def write_if_changed(path, text):
    if path.exists() and path.read_text() == text:
        print(f"unchanged {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print(f"wrote {path}")


def patch_once(path, anchor, addition, label, marker=MARKER):
    """Insert `addition` after `anchor` unless `marker` is already present."""
    text = path.read_text()
    if marker in text:
        print(f"already patched {path}")
        return
    if anchor not in text:
        sys.exit(f"anchor not found in {path} ({label}): {anchor!r}")
    text = text.replace(anchor, anchor + addition, 1)
    path.write_text(text)
    print(f"patched {path} ({label})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--aloha", required=True, type=pathlib.Path)
    parser.add_argument("--unixnu", required=True, type=pathlib.Path)
    parser.add_argument("--platform", default="SurfaceDuo1")
    args = parser.parse_args()

    aloha = args.aloha.resolve()
    unixnu = args.unixnu.resolve()
    package = aloha / "Platforms" / f"{args.platform}Pkg"
    if not package.is_dir():
        sys.exit(f"platform package not found: {package}")

    unixnu_packages = [unixnu / "package", unixnu / "drivers" / "DarwinBoot"]
    for candidate in unixnu_packages:
        if not candidate.is_dir():
            sys.exit(f"expected UniXNU package directory missing: {candidate}")

    device = package / "Device" / "xiaomi-raphael"

    # 1. Include files the platform DSC/FDF pull in.
    includes = package / "Include"
    def lines_of(entries, prefix=""):
        # Two spaces of indent are required: EDK II treats an unindented token in
        # [Components] as the start of a new section header.
        return "".join("  " + prefix + entry + "\n" for entry in entries)

    write_if_changed(
        includes / "UniXNU.dsc.inc",
        MARKER + "\n" + lines_of(COMPONENTS + DISK_STACK),
    )
    write_if_changed(
        includes / "UniXNU.fdf.inc",
        MARKER + "\n" + lines_of(COMPONENTS, prefix="INF "),
    )
    write_if_changed(
        includes / "UniXNULLib.dsc.inc",
        MARKER + "\n" + lines_of(LIBRARIES),
    )

    # 2. Declare the switch. DSC defaults are the place EDK II reads a -D value
    #    from when the command line does not pass one.
    dsc = package / f"{args.platform}.dsc"
    dtext = dsc.read_text()
    if MARKER_DEFINES not in dtext:
        defines_anchor = "[Defines]"
        if defines_anchor not in dtext:
            sys.exit(f"[Defines] not found in {dsc}")
        head, _, tail = dtext.partition(defines_anchor)
        line_end = tail.index("\n") + 1
        dtext = (
            head
            + defines_anchor
            + tail[:line_end]
            + f"  {MARKER_DEFINES}\n  BUILD_UNIXNU                   = 0\n"
            + tail[line_end:]
        )
        dsc.write_text(dtext)
        print(f"patched {dsc} (BUILD_UNIXNU default)")

    # 3. Append the components and the library mapping behind the switch.
    components_anchor = f"!include {args.platform}Pkg/Device/$(TARGET_DEVICE)/DXE.dsc.inc"
    patch_once(
        dsc,
        components_anchor,
        "\n"
        + MARKER_COMPONENTS
        + "\n!if $(BUILD_UNIXNU) == 1\n"
        + f"  !include {args.platform}Pkg/Include/UniXNULLib.dsc.inc\n"
        + f"  !include {args.platform}Pkg/Include/UniXNU.dsc.inc\n"
        + "!endif\n",
        "components",
        marker=MARKER_COMPONENTS,
    )

    # 4. Add the modules to the main firmware volume.
    fdf = package / f"{args.platform}.fdf"
    # [FV.FvMain] starts with the volume attributes and only then lists modules.
    # The device DXE.inc line is the first module statement, so the include goes
    # right after it, next to the other module lists.
    fdf_anchor = f"  !include {args.platform}Pkg/Device/$(TARGET_DEVICE)/DXE.inc"
    patch_once(
        fdf,
        fdf_anchor,
        "\n" + MARKER_FDF + "\n" + "!if $(BUILD_UNIXNU) == 1\n"
        + f"  !include {args.platform}Pkg/Include/UniXNU.fdf.inc\n"
        + "!endif\n",
        "FV.FvMain",
        marker=MARKER_FDF,
    )

    # 5. Let the platform build script find the UniXNU packages. Its
    #    PackagesPath is a hard-coded tuple, so append whatever the caller puts
    #    in ALOHA_EXTRA_PACKAGES instead of editing the tuple in place.
    build_py = package / "PlatformBuild.py"
    btext = build_py.read_text()
    if MARKER_BUILD not in btext:
        anchor = "    def GetPackagesPath(self):"
        if anchor not in btext:
            sys.exit(f"GetPackagesPath not found in {build_py}")
        # There are two definitions (BuildSettingsManager and PrEval); patch both
        # by replacing every occurrence of the returned list construction.
        needle = "        for a in CommonPlatform.PackagesPath:\n            result.append(a)\n        return result"
        if needle not in btext:
            sys.exit(f"PackagesPath loop not found in {build_py}")
        replacement = (
            "        for a in CommonPlatform.PackagesPath:\n"
            "            result.append(a)\n"
            f"        {MARKER_BUILD}\n"
            "        result.extend(\n"
            "            p for p in os.environ.get('ALOHA_EXTRA_PACKAGES', '').split(os.pathsep) if p\n"
            "        )\n"
            "        return result"
        )
        btext = btext.replace(needle, replacement)
        build_py.write_text(btext)
        print(f"patched {build_py} (PackagesPath)")

    # 6. Report what the caller must export.
    print()
    print("PACKAGES_PATH additions:")
    for candidate in unixnu_packages:
        print(f"  {candidate}")


if __name__ == "__main__":
    main()
