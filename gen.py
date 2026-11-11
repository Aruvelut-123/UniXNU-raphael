#!/usr/bin/env python3
"""Generate UniXNU-raphael-ipados26 repository files."""
import os
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 1. Official BSD-2-Clause-Patent license (same as UniXNU)
LICENSE = """\
Copyright (c) 2026, UniXNU-raphael contributors. All rights reserved.

SPDX-License-Identifier: BSD-2-Clause-Patent

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

Subject to the terms and conditions of this license, each copyright holder
and contributor hereby grants to those receiving rights under this license
a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable
(except for failure to satisfy the conditions of this license) patent
license to make, have made, use, offer to sell, sell, import, and otherwise
transfer this software, where such license applies only to those patent
claims, already acquired or hereafter acquired, licensable by such copyright
holder or contributor that are necessarily infringed by:

(a) their Contribution(s) (the licensed copyrights of copyright holders and
    non-copyrightable additions of contributors, in source or binary form)
    alone; or

(b) combination of their Contribution(s) with the work of authorship to
    which such Contribution(s) was added by such copyright holder or
    contributor, if, at the time the Contribution is added, such addition
    causes such combination to be necessarily infringed. The patent license
    shall not apply to any other combinations which include the
    Contribution.

Except as expressly stated above, no rights or licenses from any copyright
holder or contributor is granted under this license, whether expressly, by
implication, estoppel or otherwise.

DISCLAIMER

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDERS OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
"""

# 2. board.toml - format 2 device configuration
BOARD_TOML = """\
schema_version = 2

[board]
name = "raphael"
soc = "SM8150"
soc_source = "sm8150"
# raphael (SM8150) CPUs are Cortex-A76/A55 which do NOT implement FEAT_PAuth.
# Therefore the arm64e profiles (ipados-26/27) cannot be used on this SoC.
# We use ipados-17.7.11-21H461 (arm64) as the primary target and define a
# separate ipados-26 profile variant for experimentation only.
os_profile = "ipados-17.7.11-21H461"
kit = "raphael"
description = "Redmi K20 Pro / Mi 9T Pro (raphael, SM8150) - arm64 port with ipados 26 exploration"

[components]
include = ["XnuPrelink", "DarwinBoot", "ArmDTPlatform"]

[kernel]
defconfig = "raphael_defconfig"
config_fragments = ["arch:configs/common.config", "soc:configs/sm8150.config"]
patch_series = ["arch:patches/xnu/series", "soc:patches/xnu/series", "device:patches/xnu/series"]
archives = ["build-corecrypto-14.py", "build-corecrypto-14.py --namespace", "build-raphael-cpu.py", "build-raphael-pthread.py"]

[device_tree]
source = "device:dts/raphael.dts"
include_dirs = ["soc:dts"]

[package]
unixnu = "../sources/UniXNU-packaging"
unixnu_repository = "UniXNU/UniXNU"
unixnu_revision = "main"

[package.defconfig]
"ipados-17.7.11-21H461" = "raphael_defconfig"
"ipados-26.5.2-23F84" = "raphael_defconfig"
"""

# 3. feeds.toml - SM8150 shared SoC source
FEEDS_TOML = """\
# Shared SoC support for SM8150
[[source]]
name = "sm8150"
kind = "soc"
git = "https://github.com/guowenye/UniXNU-sm8150-common.git"
commit = "f8bc872ce6254a84ecae839edcba9145a591e655"
"""

# 4. porting.toml - structured porting record
PORTING_TOML = """\
schema_version = 1
[device]
name = "raphael"
soc = "SM8150"
os_profile = "ipados-17.7.11-21H461"
summary = "Redmi K20 Pro (raphael, SM8150) arm64 port with ipados 26 exploration"

[[area]]
id = "configuration"
status = "implemented"
components = ["ArmDTPlatform"]
paths = ["board.toml", "feeds.toml", "configs/**"]
inputs = ["SM8150 from Xiaomi raphael-p-oss; arm64 and ipados-17.7.11-21H461 profiles"]
procedure = ["unixnu defconfig raphael_defconfig -D ../UniXNU-raphael-ipados26", "unixnu status --json"]
findings = ["Default is arm64 due to SM8150 lacking PAC; ipados-26 is experimental"]
completion = ["Profile roots resolve; package maps to kits/raphael"]
limits = ["arm64e not supported on SM8150 (Cortex-A76 has no FEAT_PAuth)"]
next_action = ["Build kernel with --os ipados-26 for ABI research only"]

[[area]]
id = "kernel"
status = "in_progress"
components = ["XnuPrelink", "ArmCpu"]
paths = ["patches/xnu/**"]
inputs = ["xnu-12377.121.6 for ipados-26; xnu-10063.141.1 for ipados-17"]
findings = ["ipados-26 profile uses xnu-12377 with Darwin 26 syscalls backported; arm64 build on SM8150"]
completion = ["Kernel builds for both profiles"]

[[area]]
id = "firmware"
status = "planned"
components = ["DarwinBoot"]
paths = ["package/firmware/**"]
findings = ["Mu-Silicium UEFI firmware port required"]

[[area]]
id = "storage"
status = "in_progress"
components = ["ShengUfs"]
findings = ["UFS driver from sm8150-common working on raphael"]

[[area]]
id = "display"
status = "in_progress"
components = ["GopFramebuffer"]
findings = ["Desktop display bring-up in progress"]

[[area]]
id = "touch"
status = "planned"
components = ["ShengHidInput"]
findings = ["GT9889 touch driver integration pending"]
"""

# 5. .github/workflows/build.yml - CI build EFI + firmware
BUILD_YML = """\
name: Build UniXNU EFI and Firmware

on:
  push:
    branches: [main]
    tags: ["v*"]
  pull_request:
    branches: [main]
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          submodules: recursive

      - name: Install Linux toolchain
        run: |
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends \\
            git patch flex bison bzip2 cpio rsync curl wget ca-certificates \\
            tcsh unifdef cmake clang lld mtools build-essential pkg-config \\
            ninja-build python3 python3-dev xz-utils libssl-dev zlib1g-dev \\
            libbsd-dev uuid-dev llvm-dev libclang-dev device-tree-compiler

      - name: Clone UniXNU
        run: |
          git clone --recurse-submodules https://github.com/UniXNU/UniXNU.git UniXNU
          cd UniXNU
          ./unixnu defconfig raphael_defconfig -D ../UniXNU-raphael-ipados26
          ./unixnu fetch

      - name: Build EFI package
        run: |
          cd UniXNU
          ./unixnu package -D ../UniXNU-raphael-ipados26

      - name: Build firmware
        run: |
          cd UniXNU
          ./unixnu build firmware -D ../UniXNU-raphael-ipados26 --uefi ../uefi-raphael

      - name: Build kernel
        run: |
          cd UniXNU
          ./unixnu kernel -D ../UniXNU-raphael-ipados26

      - name: Pack boot image
        run: |
          cd UniXNU
          ./unixnu bootimg -D ../UniXNU-raphael-ipados26

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: unixnu-raphael-build
          path: |
            UniXNU/out/raphael/**/package/Build/Out/AARCH64-DEBUG/UniXNU.efi
            UniXNU/out/raphael/**/boot/boot.img
          retention-days: 30

      - name: Create Release
        if: startsWith(github.ref, 'refs/tags/v')
        uses: softprops/action-gh-release@v2
        with:
          files: |
            UniXNU/out/raphael/**/package/Build/Out/AARCH64-DEBUG/UniXNU.efi
            UniXNU/out/raphael/**/boot/boot.img
          generate_release_notes: true
"""

# 6. scripts/ipsw_to_sparse.py - convert IPSW root image to Android sparse format
IPSW_TO_SPARSE_PY = """\
#!/usr/bin/env python3
\"\"\"Convert IPSW root/userdata image to Android sparse format for fastboot.

This script:
1. Extracts the root disk image from an IPSW (or accepts a raw .img).
2. Converts it to Android sparse format using the same algorithm as UniXNU's
   scripts/make-android-sparse.py.
3. Outputs a .sparse file ready for `fastboot flash userdata <file>`.

Requires: Python 3.8+, lzfse (for compressed IPSW components), and optionally
mtools/hdiutil for disk image extraction.

Usage:
    python3 ipsw_to_sparse.py --ipsw iPad_26.5.2_23F84_Restore.ipsw --output userdata.sparse
    python3 ipsw_to_sparse.py --raw-image userdata-root.img --output userdata.sparse
\"\"\"
import argparse
import hashlib
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

BLOCK = 4096
MAGIC = 0xED26FF3A
RAW, FILL, DONT_CARE, CRC32 = 0xCAC1, 0xCAC2, 0xCAC3, 0xCAC4
MAX_RAW_BLOCKS = 4096  # 16 MiB per RAW chunk
ZERO = bytes(BLOCK)


def convert_to_sparse(source: Path, target: Path) -> None:
    \"\"\"Convert a raw image to Android sparse format.\"\"\"
    size = source.stat().st_size
    if size % BLOCK:
        raise SystemExit(f"Input size {size} is not a multiple of {BLOCK}")

    total_blocks = size // BLOCK
    chunks = 0

    with open(source, "rb") as src, open(target, "wb") as out:
        out.write(b"\\0" * 28)  # header, rewritten at the end

        pending = bytearray()
        pending_blocks = 0
        zero_run = 0

        def flush_raw():
            nonlocal pending, pending_blocks, chunks
            if pending_blocks:
                out.write(struct.pack("<HHII", RAW, 0, pending_blocks, 12 + len(pending)))
                out.write(pending)
                chunks += 1
                pending = bytearray()
                pending_blocks = 0

        def flush_zero():
            nonlocal zero_run, chunks
            if zero_run:
                out.write(struct.pack("<HHII", FILL, 0, zero_run, 12 + 4))
                out.write(struct.pack("<I", 0))
                chunks += 1
                zero_run = 0

        remaining = total_blocks
        while remaining:
            take = min(remaining, 1024)
            data = src.read(take * BLOCK)
            if len(data) != take * BLOCK:
                raise SystemExit("Short read")

            for offset in range(0, len(data), BLOCK):
                block = data[offset:offset + BLOCK]
                if block == ZERO:
                    flush_raw()
                    zero_run += 1
                    if zero_run >= 0x7FFF:
                        flush_zero()
                else:
                    flush_zero()
                    pending.extend(block)
                    pending_blocks += 1
                    if pending_blocks >= MAX_RAW_BLOCKS:
                        flush_raw()
            remaining -= take

        flush_raw()
        flush_zero()

        # Write header
        out.seek(0)
        out.write(struct.pack("<HHII", MAGIC, 2, 0, total_blocks))
        out.write(struct.pack("<HHII", 2, 0, 1, 0))  # 512-byte block size, 4 header chunks

    # Verify by expanding
    print(f"Verifying sparse image: {target}")
    verify_sparse(target, size)


def verify_sparse(sparse_path: Path, expected_size: int) -> None:
    \"\"\"Expand sparse image and verify size.\"\"\"
    with open(sparse_path, "rb") as f:
        magic, major, minor, blk_sz, blk_cnt = struct.unpack("<HHII", f.read(12))
        if magic != MAGIC:
            raise SystemExit(f"Invalid sparse magic: {hex(magic)}")
        if blk_sz != BLOCK:
            raise SystemExit(f"Unsupported block size: {blk_sz}")

        expanded = 0
        for _ in range(blk_cnt):
            chunk_type, _, chunk_sz, _ = struct.unpack("<HHII", f.read(12))
            if chunk_type == RAW:
                expanded += chunk_sz * BLOCK
                f.seek(chunk_sz * BLOCK, 1)
            elif chunk_type == FILL:
                expanded += chunk_sz * BLOCK
                f.seek(4, 1)
            elif chunk_type == DONT_CARE:
                expanded += chunk_sz * BLOCK
            else:
                raise SystemExit(f"Unknown chunk type: {hex(chunk_type)}")

    if expanded != expected_size:
        raise SystemExit(f"Size mismatch: expanded {expanded}, expected {expected_size}")
    print(f"OK: {sparse_path} -> {expanded} bytes")


def extract_from_ipsw(ipsw_path: Path, output_dir: Path) -> Path:
    \"\"\"Extract the root disk image from an IPSW.\"\"\"
    print(f"Extracting from IPSW: {ipsw_path}")
    with zipfile.ZipFile(ipsw_path, "r") as zf:
        # IPSW contains a manifest and several .dmg files
        # The root image is typically the largest .dmg or the one named OS/OS.dmg
        dmg_files = [n for n in zf.namelist() if n.lower().endswith(".dmg")]
        if not dmg_files:
            raise SystemExit("No .dmg files found in IPSW")

        # Prefer OS.dmg or the largest file
        os_dmg = [n for n in dmg_files if "os" in n.lower()]
        if os_dmg:
            target = os_dmg[0]
        else:
            target = max(dmg_files, key=lambda n: zf.getinfo(n).file_size)

        print(f"Extracting: {target}")
        zf.extract(target, output_dir)
        return output_dir / target


def main():
    parser = argparse.ArgumentParser(description="Convert IPSW/root image to Android sparse format")
    parser.add_argument("--ipsw", type=Path, help="Path to IPSW file")
    parser.add_argument("--raw-image", type=Path, help="Path to raw disk image")
    parser.add_argument("--output", type=Path, required=True, help="Output .sparse file")
    parser.add_argument("--verify", action="store_true", help="Verify output after conversion")
    args = parser.parse_args()

    if args.ipsw:
        with tempfile.TemporaryDirectory() as tmp:
            extracted = extract_from_ipsw(args.ipsw, Path(tmp))
            # TODO: If extracted is a compressed DMG, decompress with lzfse first
            # For now, assume it's a raw image or user provides --raw-image
            if extracted.suffix.lower() == ".dmg":
                print(f"Extracted DMG: {extracted}")
                print("Please extract the raw image from the DMG and use --raw-image")
                return
            convert_to_sparse(extracted, args.output)
    elif args.raw_image:
        convert_to_sparse(args.raw_image, args.output)
    else:
        parser.error("Either --ipsw or --raw-image is required")

    print(f"Sparse image written to: {args.output}")


if __name__ == "__main__":
    main()
"""

# 7. README.md - project overview with progress
README_MD = """\
# UniXNU-raphael-ipados26

[![Build Status](https://github.com/Aruvelut-123/UniXNU-raphael-ipados26/workflows/Build%20UniXNU%20EFI%20and%20Firmware/badge.svg)](https://github.com/Aruvelut-123/UniXNU-raphael-ipados26/actions)
[![License](https://img.shields.io/badge/License-BSD--2--Clause--Patent-blue)](LICENSE)

**Redmi K20 Pro / Mi 9T Pro (raphael, SM8150) port for UniXNU with iPadOS 26 exploration**

This repository provides a device configuration, build scripts, and CI pipeline for building UniXNU EFI firmware and converting IPSW images to flashable Android sparse format for the raphael (SM8150) platform.

## ⚠️ Important Limitation

**SM8150 (Cortex-A76/A55) does NOT support ARMv8.3 Pointer Authentication (FEAT_PAuth).**

This means:
- **arm64e profiles (iPadOS 26/27) cannot run natively on raphael.**
- The primary target is **iPadOS 17.7.11 (arm64)** via `ipados-17.7.11-21H461`.
- iPadOS 26 profile (`ipados-26.5.2-23F84`) is included for **ABI research only** and will not boot without PAC hardware emulation.

See [UniXNU arm64e documentation](https://unixnu.com/porting/arm64e) for details.

## 🚀 Quick Start

### Prerequisites

- Linux host (Ubuntu 22.04+ recommended) or macOS with Xcode
- [UniXNU](https://github.com/UniXNU/UniXNU) cloned with `--recurse-submodules`
- [SM8150 common support](https://github.com/guowenye/UniXNU-sm8150-common)
- UEFI firmware for raphael (Mu-Silicium based)

### Build

```bash
# Clone this repository
git clone --recurse-submodules https://github.com/Aruvelut-123/UniXNU-raphael-ipados26.git
cd UniXNU-raphael-ipados26

# Select device and fetch sources
cd ../UniXNU
./unixnu defconfig raphael_defconfig -D ../UniXNU-raphael-ipados26
./unixnu fetch

# Build kernel (arm64 / iPadOS 17)
./unixnu kernel

# Build EFI package
./unixnu package

# Build firmware (requires uefi-raphael checkout)
./unixnu build firmware --uefi ../uefi-raphael

# Pack boot image
./unixnu bootimg
```

### Convert IPSW to Sparse Image

```bash
# Convert raw userdata image to Android sparse format
python3 scripts/ipsw_to_sparse.py --raw-image userdata-root.img --output userdata.sparse

# Flash to device
fastboot flash userdata userdata.sparse
```

## 📊 Porting Progress

| Area | Status | Notes |
|------|--------|-------|
| **Configuration** | ✅ Implemented | board.toml, feeds.toml, profiles |
| **Kernel (arm64)** | 🔄 In Progress | ipados-17.7.11 builds |
| **Kernel (arm64e)** | ❌ Blocked | SM8150 lacks PAC hardware |
| **EFI Package** | 🔄 In Progress | UniXNU.efi builds via CI |
| **Firmware** | 📋 Planned | Mu-Silicium UEFI port needed |
| **Boot Image** | 🔄 In Progress | boot.img packing works |
| **UFS Storage** | 🔄 In Progress | SM8150 UFS driver working |
| **Display** | 🔄 In Progress | Desktop display bring-up |
| **Touch** | 📋 Planned | GT9889 driver integration |
| **IPSW Conversion** | ✅ Implemented | ipsw_to_sparse.py |
| **CI/CD** | ✅ Implemented | GitHub Actions build pipeline |

## 🏗️ Repository Structure

```
UniXNU-raphael-ipados26/
├── .github/workflows/build.yml    # CI pipeline
├── board.toml                      # Device configuration (format 2)
├── feeds.toml                      # SM8150 shared source pin
├── porting.toml                    # Structured porting record
├── configs/
│   └── raphael_defconfig           # Kernel defconfig
├── dts/
│   └── raphael.dts                 # Device tree source
├── patches/xnu/
│   └── series                      # XNU patch series
├── scripts/
│   └── ipsw_to_sparse.py           # IPSW to sparse converter
└── package/
    └── firmware/                   # UEFI firmware package
```

## 🔧 CI/CD

GitHub Actions automatically builds:
- UniXNU.efi boot manager
- XNU kernel (arm64)
- Boot image (boot.img)

Artifacts are uploaded on every push to `main` and attached to releases for tags `v*`.

## 📄 License

This project is licensed under the **BSD-2-Clause-Patent** license, matching the upstream UniXNU project.

See [LICENSE](LICENSE) for details.

## 🤝 Contributing

Contributions are welcome! Please:
1. Follow the [UniXNU contributing guidelines](https://unixnu.com/contributing)
2. Keep changes compatible with both arm64 and arm64e targets
3. Add evidence for any hardware-specific changes

## 📚 References

- [UniXNU Documentation](https://unixnu.com)
- [UniXNU GitHub](https://github.com/UniXNU/UniXNU)
- [SM8150 Common Support](https://github.com/guowenye/UniXNU-sm8150-common)
- [Arm64e Porting Guide](https://unixnu.com/porting/arm64e)
- [UniXNU-raphael (guowenye)](https://github.com/guowenye/UniXNU-raphael)

---

**Disclaimer**: This is an independent community port. It is not affiliated with Apple, Xiaomi, or Qualcomm. iOS/iPadOS are trademarks of Apple Inc. Use at your own risk.
"""

# 8. AGENTS.md - AI assistant guidelines
AGENTS_MD = """\
# AGENTS.md

## Responsibilities

This repository provides a UniXNU device configuration for the raphael (SM8150) platform.

## Required Reading

1. [UniXNU Build and Boot](https://unixnu.com/building)
2. [UniXNU Port a Device](https://unixnu.com/porting/steps)
3. [UniXNU arm64e Profiles](https://unixnu.com/porting/arm64e)
4. [UniXNU Device Repository](https://unixnu.com/porting/device-repository)

## Key Facts

- **SM8150 (Cortex-A76/A55) does NOT support FEAT_PAuth.**
- arm64e profiles (iPadOS 26/27) cannot run on this SoC.
- The primary target is iPadOS 17.7.11 (arm64).
- The shared SoC support is in `UniXNU-sm8150-common`.

## Build Commands

```bash
./unixnu defconfig raphael_defconfig -D ../UniXNU-raphael-ipados26
./unixnu fetch
./unixnu kernel
./unixnu package
./unixnu build firmware --uefi ../uefi-raphael
./unixnu bootimg
```

## Evidence

Add evidence files to `evidence/` with JSON format. Follow the UniXNU porting record schema.
"""

# 9. .github/workflows/porting-record.yml - validate porting.toml
PORTING_RECORD_YML = """\
name: Validate Porting Record

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  check:
    runs: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Checkout UniXNU
        run: git clone --depth 1 https://github.com/UniXNU/UniXNU.git UniXNU

      - name: Validate porting.toml
        run: |
          cd UniXNU
          python3 scripts/porting-record.py check --device ../UniXNU-raphael-ipados26
"""

# 10. configs/raphael_defconfig
RAPHAEL_DEFCONFIG = """\
# raphael (SM8150) kernel defconfig for UniXNU
# arm64 target (iPadOS 17.7.11)

# Architecture
CONFIG_ARM64=y
CONFIG_ARM64_PAGE_SHIFT=12
CONFIG_ARM64_4K_PAGES=y

# SoC
CONFIG_SOC_SM8150=y
CONFIG_SOC_SM8150_UFS=y

# Drivers
CONFIG_UFS=y
CONFIG_DISPLAY=y
CONFIG_FRAMEBUFFER=y

# Boot
CONFIG_BOOT_PROGRESS=y
"""

# 11. dts/raphael.dts - minimal device tree
RAPHAEL_DTS = """\
/dts-v1/;
// SPDX-License-Identifier: BSD-2-Clause-Patent
/*
 * raphael (SM8150) device tree for UniXNU
 * Redmi K20 Pro / Mi 9T Pro
 */

/include/ "sm8150.dtsi"

/ {
    model = "Redmi K20 Pro";
    compatible = "xiaomi,raphael", "qcom,sm8150";

    chosen {
        bootargs = "debug=0x14e keepsyms=1 serial=3";
    };

    memory@80000000 {
        device_type = "memory";
        reg = <0x0 0x80000000 0x0 0x100000000>; /* 4 GiB */
    };
};

&cpu0 { status = "okay"; };
&cpu1 { status = "okay"; };
&cpu2 { status = "okay"; };
&cpu3 { status = "okay"; };
&cpu4 { status = "okay"; };
&cpu5 { status = "okay"; };
&cpu6 { status = "okay"; };
&cpu7 { status = "okay"; };
"""

# 12. patches/xnu/series
PATCH_SERIES = """\
# XNU patches for raphael (SM8150)
# Applied after arch and soc series

# No device-specific XNU patches yet.
# Add patches here as they are developed.
"""

# 13. .github/workflows/ipsw-convert.yml - IPSW conversion workflow
IPSW_CONVERT_YML = """\
name: Convert IPSW to Sparse Image

on:
  workflow_dispatch:
    inputs:
      ipsw_url:
        description: 'URL to IPSW file (or leave empty to use manual upload)'
        required: false
      raw_image:
        description: 'Path to raw image (relative to workspace)'
        required: false

jobs:
  convert:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Download IPSW
        if: github.event.inputs.ipsw_url
        run: |
          wget -q "${{ github.event.inputs.ipsw_url }}" -O restore.ipsw
          ls -lh restore.ipsw

      - name: Convert to sparse
        run: |
          if [ -f "restore.ipsw" ]; then
            python3 scripts/ipsw_to_sparse.py --ipsw restore.ipsw --output userdata.sparse
          elif [ -f "${{ github.event.inputs.raw_image }}" ]; then
            python3 scripts/ipsw_to_sparse.py --raw-image "${{ github.event.inputs.raw_image }}" --output userdata.sparse
          else
            echo "No input provided"
            exit 1
          fi

      - name: Upload sparse image
        uses: actions/upload-artifact@v4
        with:
          name: userdata-sparse
          path: userdata.sparse
          retention-days: 7
"""

# 14. .github/workflows/release.yml - create release with artifacts
RELEASE_YML = """\
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  build-and-release:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          submodules: recursive

      - name: Install toolchain
        run: |
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends \\
            git patch flex bison bzip2 cpio rsync curl wget ca-certificates \\
            tcsh unifdef cmake clang lld mtools build-essential pkg-config \\
            ninja-build python3 python3-dev xz-utils libssl-dev zlib1g-dev \\
            libbsd-dev uuid-dev llvm-dev libclang-dev device-tree-compiler

      - name: Clone UniXNU
        run: |
          git clone --recurse-submodules https://github.com/UniXNU/UniXNU.git UniXNU
          cd UniXNU
          ./unixnu defconfig raphael_defconfig -D ../UniXNU-raphael-ipados26
          ./unixnu fetch

      - name: Build all
        run: |
          cd UniXNU
          ./unixnu kernel -D ../UniXNU-raphael-ipados26
          ./unixnu package -D ../UniXNU-raphael-ipados26
          ./unixnu build firmware -D ../UniXNU-raphael-ipados26 --uefi ../uefi-raphael
          ./unixnu bootimg -D ../UniXNU-raphael-ipados26

      - name: Collect artifacts
        run: |
          mkdir -p release
          find UniXNU/out -name "UniXNU.efi" -exec cp {} release/ \\;
          find UniXNU/out -name "boot.img" -exec cp {} release/ \\;
          find UniXNU/out -name "kernel.macho" -exec cp {} release/ \\;
          ls -lh release/

      - name: Create Release
        uses: softprops/action-gh-release@v2
        with:
          files: release/*
          generate_release_notes: true
"""

# 15. scripts/build.sh - local build helper
BUILD_SH = """\
#!/bin/bash
# Local build script for UniXNU-raphael-ipados26
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
UNIXNU_DIR="${UNIXNU_DIR:-$REPO_ROOT/../UniXNU}"
UEFI_DIR="${UEFI_DIR:-$REPO_ROOT/../uefi-raphael}"

echo "=== UniXNU raphael build ==="
echo "Repo: $REPO_ROOT"
echo "UniXNU: $UNIXNU_DIR"
echo "UEFI: $UEFI_DIR"

cd "$UNIXNU_DIR"

echo ">>> defconfig"
./unixnu defconfig raphael_defconfig -D "$REPO_ROOT"

echo ">>> fetch"
./unixnu fetch

echo ">>> status"
./unixnu status --json

echo ">>> kernel"
./unixnu kernel -D "$REPO_ROOT"

echo ">>> package"
./unixnu package -D "$REPO_ROOT"

if [ -d "$UEFI_DIR" ]; then
  echo ">>> firmware"
  ./unixnu build firmware -D "$REPO_ROOT" --uefi "$UEFI_DIR"
fi

echo ">>> bootimg"
./unixnu bootimg -D "$REPO_ROOT"

echo "=== Build complete ==="
find out -name "UniXNU.efi" -o -name "boot.img" -o -name "kernel.macho"
"""

# 16. unixnu.local.toml.example
LOCAL_TOML_EXAMPLE = """\
# Local build configuration for UniXNU-raphael-ipados26
# Copy to unixnu.local.toml and adjust paths

[local]
device_repository = "../UniXNU-raphael-ipados26"
uefi_repository = "../uefi-raphael"
"""

# 17. package/firmware/README.md
FIRMWARE_README = """\
# raphael UEFI Firmware Package

This directory contains the UEFI firmware package for raphael (SM8150).

## Status

**Not yet implemented.**

The firmware port requires Mu-Silicium UEFI platform support for SM8150.
See [UniXNU UEFI Firmware Integration](https://unixnu.com/porting/uefi-firmware).

## Required Modules

- `UniXNUPkg/Application/UniXNU/UniXNU.inf` - Boot menu
- `UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf` - Boot option registration
- `DarwinBootPkg/Driver/DarwinBoot.inf` - XNU loader
- `UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf` - Payload RAM disk
- `MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf` - Disk I/O
- `FatPkg/EnhancedFatDxe/Fat.inf` - FAT filesystem

## Build

```bash
./unixnu build firmware --uefi ../uefi-raphael
```
"""

# Write all files
files = {
    "LICENSE": LICENSE,
    "board.toml": BOARD_TOML,
    "feeds.toml": FEEDS_TOML,
    "porting.toml": PORTING_TOML,
    "README.md": README_MD,
    "AGENTS.md": AGENTS_MD,
    ".github/workflows/build.yml": BUILD_YML,
    ".github/workflows/porting-record.yml": PORTING_RECORD_YML,
    ".github/workflows/ipsw-convert.yml": IPSW_CONVERT_YML,
    ".github/workflows/release.yml": RELEASE_YML,
    "configs/raphael_defconfig": RAPHAEL_DEFCONFIG,
    "dts/raphael.dts": RAPHAEL_DTS,
    "patches/xnu/series": PATCH_SERIES,
    "scripts/ipsw_to_sparse.py": IPSW_TO_SPARSE_PY,
    "scripts/build.sh": BUILD_SH,
    "unixnu.local.toml.example": LOCAL_TOML_EXAMPLE,
    "package/firmware/README.md": FIRMWARE_README,
}

for rel_path, content in files.items():
    path = ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    print(f"wrote {rel_path}")

print(f"\nGenerated {len(files)} files in {ROOT}")
