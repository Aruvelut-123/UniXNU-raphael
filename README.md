# UniXNU-raphael-ipados26

**Redmi K20 Pro / Mi 9T Pro (raphael, SM8150) — UniXNU device port**

Target profile: `ipados-17.7.11-21H461` (arm64, XNU 10063.141.1)

[![Build](https://github.com/Aruvelut-123/UniXNU-raphael-ipados26/actions/workflows/build.yml/badge.svg)](../../actions/workflows/build.yml)
[![License](https://img.shields.io/badge/license-BSD--2--Clause--Patent-blue)](LICENSE)

## Why not iPadOS 26

iPadOS 26 and 27 ship **arm64e only** — no arm64 slice. arm64e requires ARMv8.3
`FEAT_PAuth` (pointer authentication) in hardware. The SM8150 CPUs (Cortex-A76 /
A55) do not implement it, so the arm64e kernel cannot program the PAC key
registers and PAC instructions fault.

`ipados-17.7.11-21H461` is arm64 and is the newest profile this SoC can run.
See [UniXNU arm64e profiles](https://unixnu.com/porting/arm64e).

## Products

Two independent artifacts are published per build:

| Artifact | What it is | How to use |
| --- | --- | --- |
| `boot.img` | Android boot image: BootShim + UEFI firmware volume + payload FAT ramdisk + DTB | `fastboot boot boot.img`, or `fastboot flash boot boot.img` |
| `UniXNU.efi` | UEFI boot manager / loader package (AARCH64) | Place at `\EFI\UniXNU\UniXNU.efi` on an ESP, or embed in a firmware build |

`kernel.macho` (the prelinked XNU kernel) is published alongside them for
inspection and manual payload assembly.

Tag `v*` publishes all three to a GitHub Release; every other push uploads them
as workflow artifacts (`unixnu-efi`, `unixnu-bootimg`, `unixnu-kernel`).

## Root partition: unixnu first, userdata as fallback

UniXNU selects the root volume by **APFS Volume UUID written into the ADT**, not
by partition label. A boot-time "try A then B" search is not implemented
upstream, so the preference is applied at **flash time**:

```sh
# Builds the root image and prints the target it would use.
scripts/build-root.sh --ipsw restore.ipsw --dry-run

# Builds and flashes to `unixnu` if that partition exists, else `userdata`.
scripts/build-root.sh --ipsw restore.ipsw --flash
```

Detection order: `/dev/disk/by-partlabel/{unixnu,userdata}` then
`/dev/block/by-name/{unixnu,userdata}`. Details and the limitation of doing this
at boot time are in [docs/root-partition.md](docs/root-partition.md).

## Build

Host: Ubuntu 22.04+ (glibc). macOS works for the kernel step but the scripts
here assume Linux.

```sh
# One-time: build the clang/ld64/lzfse toolchain into /opt/unixnu-linux
git clone --recurse-submodules https://github.com/UniXNU/UniXNU.git
cd UniXNU
sudo scripts/linux/setup-toolchain.py

# Select the device and fetch sources
./unixnu defconfig raphael_defconfig -D ../UniXNU-raphael-ipados26
./unixnu fetch
./unixnu status --json

# Build
./unixnu kernel  -D ../UniXNU-raphael-ipados26
./unixnu package -D ../UniXNU-raphael-ipados26
./unixnu build firmware -D ../UniXNU-raphael-ipados26 --uefi ../uefi-raphael
./unixnu bootimg -D ../UniXNU-raphael-ipados26
```

`scripts/build.sh` runs the same sequence and honours `UNIXNU_DIR` / `UEFI_DIR`.

Firmware needs a `uefi-raphael` Mu-Silicium checkout with UniXNU, UniXNUDxe,
DarwinBoot, UniXNURamDiskDxe, DiskIoDxe and FatPkg in its DSC/FDF — see
[UEfI firmware integration](https://unixnu.com/porting/uefi-firmware). Without
it the kernel, EFI package and boot image still build.

## IPSW → flashable sparse image

```sh
python3 scripts/ipsw_to_sparse.py --raw-image userdata-root.img --output unixnu.sparse
fastboot flash unixnu unixnu.sparse
```

The converter emits libsparse FILL/RAW chunks and self-verifies by expanding the
output and comparing sizes. `--ipsw` extracts a disk image from an IPSW archive,
but AEA-encrypted images (iPadOS 27) and UDIF-compressed `.dmg` payloads still
need macOS `aea` / `ipsw` or `hdiutil` — the script reports that and stops
rather than producing a bad image.

## Porting status

| Area | State | Note |
| --- | --- | --- |
| Configuration | done | `board.toml`, `feeds.toml`, `porting.toml` resolve |
| Kernel (arm64) | in progress | builds against `xnu-10063.141.1` |
| Kernel (arm64e) | not possible | SM8150 has no `FEAT_PAuth` |
| EFI package | in progress | `UniXNU.efi` from CI |
| Firmware | blocked | needs `uefi-raphael` Mu-Silicium port |
| Boot image | in progress | `boot.img` packs |
| UFS storage | in progress | via `UniXNU-sm8150-common` |
| Display | in progress | desktop bring-up |
| Touch | not started | GT9889 driver |
| IPSW conversion | done | `scripts/ipsw_to_sparse.py` |
| CI | done | build / release / porting-record / ipsw-convert |

`porting.toml` is the authoritative record and is validated in CI by
`scripts/porting-record.py`.

## Layout

```
board.toml                     device configuration (format 2)
feeds.toml                     SM8150 shared source pin
porting.toml                   structured porting record
configs/raphael_defconfig      kernel defconfig
dts/raphael.dts                device tree
patches/xnu/series             XNU patch series (empty for now)
scripts/build.sh               full build sequence
scripts/build-root.sh          root image build + partition preference + flash
scripts/ipsw_to_sparse.py      IPSW/raw image -> Android sparse
docs/root-partition.md         unixnu-vs-userdata reasoning
.github/workflows/             build, release, porting-record, ipsw-convert
package/firmware/              UEFI firmware package (not yet implemented)
```

## License

BSD-2-Clause-Patent, matching upstream UniXNU. See [LICENSE](LICENSE).

## References

- [UniXNU documentation](https://unixnu.com)
- [UniXNU repository](https://github.com/UniXNU/UniXNU)
- [UniXNU-sm8150-common](https://github.com/guowenye/UniXNU-sm8150-common)
- [arm64e profiles](https://unixnu.com/porting/arm64e)

Independent community port. Not affiliated with Apple, Xiaomi or Qualcomm.
iOS and iPadOS are trademarks of Apple Inc.
