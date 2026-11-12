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

### raphael's measured geometry

Read off the handset (`cat /proc/partitions` + `/dev/block/by-name`), 512 GB
variant with a repartitioned GPT:

| Partition | Device | Start LBA | End LBA | Size |
| --- | --- | --- | --- | --- |
| `userdata` | `sda31` | 4063218 | 231565297 | 108.48 GiB |
| `esp` | `sda32` | 231565298 | 232540145 | 476 MiB |
| `win` | `sda33` | 232540146 | 718487513 | 231.72 GiB |
| **`unixnu`** | `sda34` | **718487514** | **986922969** | **128.00 GiB** |

`board.toml [userdata]` uses the **`unixnu`** entry: 128 GiB of headroom for a
~7.9 GiB root image. `lba_bytes = 512` (raw GPT sectors, which is also what
XNU's UFS driver seeks by).

Root image size, measured from the 21H461 IPSW's ZIP64 directory and UDIF
trailers without downloading the 6.4 GiB archive:

| Window | Raw disk |
| --- | --- |
| `OS` (`044-76040-038.dmg`) | 4.80 GiB |
| `SystemOS` (`044-76034-038.dmg`) | 3.08 GiB |
| `userdata-root.img` | **≈ 7.9 GiB** (1 MiB manifest + 1 MiB-aligned windows) |

So `unixnu` needs ≥ 8 GiB; the 128 GiB it already has is plenty.

## Build

**Build in GitHub Actions: `.github/workflows/build.yml`.** It runs on
`macos-26`, because upstream UniXNU's kernel step only supports the Xcode
toolchain — `scripts/linux/setup-toolchain.py` builds a patched LLVM *from
source*, which does not fit in a hosted Linux runner's time budget.

Manual, on your own machine:

```sh
# macOS with Xcode (the supported path for the kernel step)
git clone --recurse-submodules https://github.com/UniXNU/UniXNU.git
cd UniXNU
./unixnu defconfig raphael_defconfig -D ../UniXNU-raphael-ipados26
./unixnu fetch -D ../UniXNU-raphael-ipados26
./unixnu status --json -D ../UniXNU-raphael-ipados26   # 62 ordered patches
./unixnu build kernel  -D ../UniXNU-raphael-ipados26
./unixnu build package -D ../UniXNU-raphael-ipados26   # -> UniXNU.efi
./unixnu build firmware -D ../UniXNU-raphael-ipados26 --uefi ../uefi-raphael
./unixnu bootimg -D ../UniXNU-raphael-ipados26 --uefi ../uefi-raphael
```

On Linux, run `sudo scripts/linux/setup-toolchain.py` once first (it compiles
clang with the `__builtin_xnu_type_*` patch, cctools-port ld64, mig, iig and
`lzfse` into `/opt/unixnu-linux`) — expect it to take hours.

`scripts/build.sh` runs the same sequence and honours `UNIXNU_DIR` / `UEFI_DIR`.

Firmware and `boot.img` need a `uefi-raphael` Mu-Silicium checkout with UniXNU,
UniXNUDxe, DarwinBoot, UniXNURamDiskDxe, DiskIoDxe and FatPkg in its DSC/FDF —
see [UEFI firmware integration](https://unixnu.com/porting/uefi-firmware).
Without it the kernel and the `UniXNU.efi` package still build; `boot.img`
cannot, since it embeds the firmware volume. Dispatch the workflow with
`uefi_repository=<owner/name>` once such a port exists.

Verify the `unixnu` capacity before any flash, without downloading the IPSW:

```sh
./unixnu build userdata --dry-run -D ../UniXNU-raphael-ipados26
```

That prints the two windows and their sizes; nothing is extracted.

## IPSW → flashable sparse image

```sh
python3 scripts/ipsw_to_sparse.py --raw-image userdata-root.img --output unixnu.sparse
fastboot flash unixnu unixnu.sparse
```

The converter emits libsparse FILL/RAW chunks and self-verifies by expanding the
output and comparing sizes. `--ipsw` picks the largest `.dmg` member (or the one
named by `--member`) and decodes it with UniXNU's own `scripts/unixnu/udif.py`,
which handles raw / zlib / bzip2 / LZFSE; ZLIB-compressed members of the 21H461
IPSW therefore convert on Linux, needing only Apple's reference `lzfse` binary
(`.github/workflows/ipsw-convert.yml` builds it). AEA-encrypted images (iPadOS
27 / iOS 26 restore dmgs) are not UDIF and are rejected rather than half-read.

`--list` prints the IPSW members without touching a byte of them:

```sh
python3 scripts/ipsw_to_sparse.py --ipsw restore.ipsw --list
```

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
