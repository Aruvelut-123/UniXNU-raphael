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
