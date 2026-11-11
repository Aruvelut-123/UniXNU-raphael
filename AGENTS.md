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
