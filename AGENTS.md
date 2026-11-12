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
- arm64e-only Apple OS profiles (iPadOS 26/27) cannot run on this SoC.
  iPadOS 18 does ship an arm64 kernelcache (the no-PAC A10 iPad 7 runs 18.7.12),
  which is what this port is built against.
- Target build: `ipados-18.7.12-22H390` (Darwin 24.6.0, xnu 11417.140.69),
  selected by `board.toml [board] os_profile`. Upstream UniXNU has no 18.x
  profile, so this repository carries one under `os-profiles/`; run
  `scripts/install-device-profile.py --unixnu <UniXNU checkout>` before resolving.
- **Two archives, one build.** `os-profiles/<profile>/profile.toml [ipsw]` is the
  iOS 18.7.12 restore of iPhone11,2 (the root image). The arm64e iOS kernelcache
  cannot run here, so `[kernel.prelink] kernelcache` points to the separately
  staged iPadOS 18.7.12 / iPad7,11 arm64 kernelcache, produced by
  `scripts/stage-arm64-kernelcache.py`. Both are build 22H390.
- **Kernel and root must be the same build.** XNU matches the root by the APFS
  volume UUID / trust cache signed at build time. Never mix builds or Darwin
  versions. `[root] os_volume_uuid` stays empty until the AEA OS dmg is
  decrypted on macOS and its UUID can be read.
- Both 22H390 restores ship `.dmg.aea` images; decrypting them needs macOS
  `/usr/bin/aea`, so the root image is a macOS-only build step.
- The shared SoC support is in `UniXNU-sm8150-common`.

## Build Commands

```bash
python3 scripts/install-device-profile.py --unixnu ../UniXNU
python3 scripts/stage-arm64-kernelcache.py --unixnu ../UniXNU
cd ../UniXNU
./unixnu defconfig raphael_defconfig -D ../UniXNU-raphael
./unixnu fetch -D ../UniXNU-raphael
./unixnu build kernel -D ../UniXNU-raphael
./unixnu build package -D ../UniXNU-raphael
./unixnu build firmware -D ../UniXNU-raphael --uefi ../uefi-raphael
./unixnu bootimg -D ../UniXNU-raphael --uefi ../uefi-raphael
```

## Evidence

Add evidence files to `evidence/` with JSON format. Follow the UniXNU porting record schema.
