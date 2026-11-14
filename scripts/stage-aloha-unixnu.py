#!/usr/bin/env python3
"""Compile the UniXNU boot chain into a Project Aloha UEFI platform.

Aloha's platform package describes only Windows-capable firmware. This script
adds the UniXNU boot chain -- the boot menu application, the boot option
registration driver, the initrd block device and the DarwinBoot kernel loader
-- to the DSC/FDF of a given platform, and teaches the platform build script to
find the UniXNU packages through an environment variable.

Design notes (learned from the Mu-Silicium raphael platform, which never
booted on hardware):

* Both device variants must be patched. build_uefi.py runs PlatformBuild.py for
  the Secure Boot build and PlatformBuildNoSb.py for the plain one, and the two
  read different DSC files (SurfaceDuo1.dsc / SurfaceDuo1NoSb.dsc), which both
  include the same Device/<device>/*.inc fragments.
* The disk stack is *already* in the platform. Device/<device>/APRIORI.inc
  embeds prebuilt DiskIoDxe and PartitionDxe images under fixed FILE GUIDs and
  the main FDF already contains FatPkg's Fat.inf. Adding the dispatchable INFs
  again would collide on those GUIDs, so this script does not add them at all;
  it only checks that they are present and warns when they are not.
* Library mappings belong to [LibraryClasses], components to [Components].
  Mixing them up is a hard EDK II parse error, so each include carries its own
  section context.
* The switch value travels through ALOHA_EXTRA_DEFINES as a "; "-separated
  NAME=VALUE list. build_uefi.py cannot forward -D to EDK II, so this script
  writes the requested value straight into the DSC [Defines] block, which is
  exactly what a -D would override.

Every edit is guarded by a marker so the script is idempotent. A plain Aloha
build (BUILD_UNIXNU=0) stays byte-for-byte unaffected.
"""
import argparse
import os
import pathlib
import sys

COMPONENTS = [
    "UniXNUPkg/Application/UniXNU/UniXNU.inf",
    "UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf",
    "UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf",
    "DarwinBootPkg/Driver/DarwinBoot.inf",
]

LIBRARIES = [
    "UniXNULib|UniXNUPkg/Library/UniXNULib/UniXNULib.inf",
]

# Prerequisites the platform is expected to provide already. The script only
# verifies them: Aloha embeds the prebuilt disk drivers as fixed-GUID FILE
# entries in Device/<device>/APRIORI.inc and lists FatPkg in the FDF, so adding
# the INFs again would duplicate those GUIDs.
PREREQUISITES = [
    ("DiskIoDxe", "Binaries/MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.efi"),
    ("PartitionDxe", "Binaries/MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe.efi"),
]

# Library mappings the UniXNU modules need. FdtLib is mapped by Andromeda.dsc.inc
# already, so only UniXNULib itself has to be declared here.
MARKER = "# --- UniXNU (added by stage-aloha-unixnu.py) ---"
MARKER_DEFINES = MARKER + " defines"
MARKER_COMPONENTS = MARKER + " components"
MARKER_LIBRARIES = MARKER + " libraries"
MARKER_FDF = MARKER + " fvmain"
MARKER_BUILD = MARKER + " packagespath"
MARKER_BLOCK = MARKER + " firmwarevolume"


def write_if_changed(path, text):
    if path.exists() and path.read_text() == text:
        print(f"unchanged {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print(f"wrote {path}")


def patch_once(path, anchor, addition, label, marker=MARKER, after=True):
    """Insert `addition` next to `anchor` unless `marker` is already present."""
    text = path.read_text()
    if marker in text:
        print(f"already patched {path} ({label})")
        return False
    if anchor not in text:
        sys.exit(f"anchor not found in {path} ({label}): {anchor!r}")
    if after:
        text = text.replace(anchor, anchor + addition, 1)
    else:
        text = text.replace(anchor, addition + anchor, 1)
    path.write_text(text)
    print(f"patched {path} ({label})")
    return True


def lines_of(entries, prefix=""):
    # Two spaces of indent are required: EDK II treats an unindented token in
    # [Components] as the start of a new section header.
    return "".join("  " + prefix + entry + "\n" for entry in entries)


def parse_extra_defines(spec):
    """Turn 'BUILD_UNIXNU=1; FOO=bar' into {'BUILD_UNIXNU': '1', 'FOO': 'bar'}."""
    result = {}
    for chunk in (spec or "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            sys.exit(f"malformed ALOHA_EXTRA_DEFINES entry: {chunk!r}")
        key, _, value = chunk.partition("=")
        result[key.strip()] = value.strip()
    return result


def set_dsc_define(dsc, name, value):
    """Force `NAME = value` inside the [Defines] block, idempotently."""
    text = dsc.read_text()
    existing = f"  {name}                   = "
    if existing in text:
        # Rewrite the current default in place so a rerun with a different
        # value still lands.
        out = []
        for line in text.splitlines(True):
            if line.startswith(existing):
                padding = " " * max(1, 31 - len(name))
                line = f"  {name}{padding}= {value}\n"
            out.append(line)
        new = "".join(out)
        if new != text:
            dsc.write_text(new)
            print(f"set {name}={value} in {dsc}")
        else:
            print(f"{name}={value} already current in {dsc}")
        return
    anchor = "[Defines]"
    if anchor not in text:
        sys.exit(f"[Defines] not found in {dsc}")
    head, _, tail = text.partition(anchor)
    line_end = tail.index("\n") + 1
    padding = " " * max(1, 31 - len(name))
    text = (
        head
        + anchor
        + tail[:line_end]
        + f"  {MARKER_DEFINES}\n"
        + f"  {name}{padding}= {value}\n"
        + tail[line_end:]
    )
    dsc.write_text(text)
    print(f"added {name}={value} to {dsc}")


def patch_dsc(dsc, platform, device_rel):
    text = dsc.read_text()
    components_anchor = f"!include {platform}Pkg/Device/$(TARGET_DEVICE)/DXE.dsc.inc"
    if components_anchor not in text:
        sys.exit(f"device DXE include not found in {dsc}")
    patch_once(
        dsc,
        components_anchor,
        "\n"
        + MARKER_COMPONENTS
        + "\n!if $(BUILD_UNIXNU) == 1\n"
        + f"  !include {platform}Pkg/Include/UniXNU.dsc.inc\n"
        + "!endif\n",
        "components",
        marker=MARKER_COMPONENTS,
    )
    # Library mappings must live in a [LibraryClasses] section. The first
    # LibraryClasses header after the device DXE include is the right home.
    lib_anchor = "[LibraryClasses.common]"
    if lib_anchor not in dsc.read_text():
        sys.exit(f"[LibraryClasses.common] not found in {dsc}")
    patch_once(
        dsc,
        lib_anchor,
        "\n"
        + MARKER_LIBRARIES
        + "\n!if $(BUILD_UNIXNU) == 1\n"
        + f"  !include {platform}Pkg/Include/UniXNULLib.dsc.inc\n"
        + "!endif\n",
        "libraries",
        marker=MARKER_LIBRARIES,
    )


def patch_fdf(fdf, platform):
    anchor = f"  !include {platform}Pkg/Device/$(TARGET_DEVICE)/DXE.inc"
    if anchor not in fdf.read_text():
        sys.exit(f"device DXE include not found in {fdf}")
    patch_once(
        fdf,
        anchor,
        "\n"
        + MARKER_FDF
        + "\n!if $(BUILD_UNIXNU) == 1\n"
        + f"  !include {platform}Pkg/Include/UniXNU.fdf.inc\n"
        + "!endif\n",
        "FV.FvMain",
        marker=MARKER_FDF,
    )


def patch_build_py(build_py):
    text = build_py.read_text()
    needle = (
        "        for a in CommonPlatform.PackagesPath:\n"
        "            result.append(a)\n"
        "        return result"
    )
    target = (
        "        for a in CommonPlatform.PackagesPath:\n"
        "            result.append(a)\n"
        f"        {MARKER_BUILD}\n"
        "        # Skip entries that are not directories: Edk2Path aborts the whole\n"
        "        # build with NotADirectoryError instead of warning, and a baseline\n"
        "        # run has no UniXNU checkout for the variable to point at.\n"
        "        result.extend(\n"
        "            p for p in os.environ.get('ALOHA_EXTRA_PACKAGES', '').split(os.pathsep)\n"
        "            if p and os.path.isdir(p)\n"
        "        )\n"
        "        return result"
    )
    if target in text:
        print(f"already patched {build_py} (PackagesPath)")
        return
    if needle not in text:
        sys.exit(f"PackagesPath loop not found in {build_py}")
    build_py.write_text(text.replace(needle, target))
    print(f"patched {build_py} (PackagesPath)")


def check_prerequisites(device):
    missing = []
    for name, rel in PREREQUISITES:
        if not (device / rel).is_file():
            missing.append(f"{name} ({rel})")
    return missing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--aloha", required=True, type=pathlib.Path)
    parser.add_argument("--unixnu", required=True, type=pathlib.Path)
    parser.add_argument("--platform", default="SurfaceDuo1")
    parser.add_argument("--device", default="xiaomi-raphael")
    parser.add_argument(
        "--defines",
        default=os.environ.get("ALOHA_EXTRA_DEFINES", ""),
        help="'; '-separated NAME=VALUE list, usually $ALOHA_EXTRA_DEFINES",
    )
    args = parser.parse_args()

    # The switch decides how much validation applies below, so parse it first.
    defines = parse_extra_defines(args.defines)
    build_unixnu = defines.get("BUILD_UNIXNU", "0")
    print(f"BUILD_UNIXNU = {build_unixnu}")

    aloha = args.aloha.resolve()
    unixnu = args.unixnu.resolve()
    package = aloha / "Platforms" / f"{args.platform}Pkg"
    if not package.is_dir():
        sys.exit(f"platform package not found: {package}")

    # The UniXNU packages only have to exist when the boot chain is compiled in.
    # A baseline run (BUILD_UNIXNU=0) does not check UniXNU out at all, and the
    # includes stay behind the switch, so a missing checkout is not an error.
    unixnu_packages = [unixnu / "package", unixnu / "drivers" / "DarwinBoot"]
    if build_unixnu == "1":
        if not (unixnu / "package" / "UniXNUPkg" / "UniXNUPkg.dec").is_file():
            sys.exit(
                "BUILD_UNIXNU=1 needs a full UniXNU checkout, but "
                f"{unixnu / 'package' / 'UniXNUPkg' / 'UniXNUPkg.dec'} is missing"
            )
        for candidate in unixnu_packages:
            if not candidate.is_dir():
                sys.exit(f"expected UniXNU package directory missing: {candidate}")
    else:
        print(f"BUILD_UNIXNU=0: no UniXNU checkout required under {unixnu}")

    device = package / "Device" / args.device
    if not device.is_dir():
        sys.exit(f"device directory not found: {device}")

    includes = package / "Include"
    write_if_changed(
        includes / "UniXNU.dsc.inc",
        MARKER + "\n" + lines_of(COMPONENTS),
    )
    write_if_changed(
        includes / "UniXNU.fdf.inc",
        MARKER + "\n" + lines_of(COMPONENTS, prefix="INF "),
    )
    write_if_changed(
        includes / "UniXNULLib.dsc.inc",
        MARKER + "\n" + lines_of(LIBRARIES),
    )

    # Both DSC files share the switch, so patch every one that exists.
    dscs = sorted(package.glob(f"{args.platform}*.dsc"))
    if not dscs:
        sys.exit(f"no DSC found under {package}")
    for dsc in dscs:
        set_dsc_define(dsc, "BUILD_UNIXNU", build_unixnu)
        patch_dsc(dsc, args.platform, args.device)
        print(f"  {dsc.name}: done")

    # PlatformBuild.py and PlatformBuildNoSb.py are separate files; build_uefi.py
    # drives each of them in turn, so both must learn about ALOHA_EXTRA_PACKAGES.
    build_pys = sorted(package.glob("PlatformBuild*.py"))
    if not build_pys:
        sys.exit(f"no PlatformBuild*.py found under {package}")
    for build_py in build_pys:
        patch_build_py(build_py)

    # The FDF is shared by both variants (both DSCs point at SurfaceDuo1.fdf).
    fdf = package / f"{args.platform}.fdf"
    if not fdf.is_file():
        sys.exit(f"FDF not found: {fdf}")
    patch_fdf(fdf, args.platform)

    missing = check_prerequisites(device)
    print()
    if missing:
        print("WARNING: the platform does not appear to carry these disk drivers:")
        for item in missing:
            print(f"  - {item}")
        print("  UniXNUDxe needs DiskIo/Partition to enumerate volumes, and")
        print("  DarwinBoot needs FAT to read the payload. Add them to the")
        print("  device APRIORI.inc/FDF or the boot menu will come up empty.")
    else:
        print("disk prerequisites: present (embedded in device APRIORI.inc)")

    print()
    print("PACKAGES_PATH additions (export ALOHA_EXTRA_PACKAGES):")
    for candidate in unixnu_packages:
        print(f"  {candidate}")
    print()
    print("build:")
    print("  cd <aloha> && python3 build_uefi.py -d " + args.device)


if __name__ == "__main__":
    main()
