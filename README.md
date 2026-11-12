# UniXNU-raphael

**Redmi K20 Pro / Mi 9T Pro (raphael, SM8150) — UniXNU device port**

This board targets **iOS / iPadOS 18.7.12 (build 22H390, Darwin 24.6.0)** with a
single build on both sides of the boot chain:

- the **root image** is the iOS 18.7.12 restore of iPhone11,2 (iPhone XS);
- the **kernelcache used for prelinking** is the arm64 one from the iPadOS
  18.7.12 restore of iPad7,11 (iPad 7, A10, no PAC).

The two are the same build, so the APFS volume UUID and trust cache the kernel
signs match the root it mounts. See
[Two archives, one build](#two-archives-one-build).

[![Build](https://github.com/Aruvelut-123/UniXNU-raphael/actions/workflows/build.yml/badge.svg)](../../actions/workflows/build.yml)
[![License](https://img.shields.io/badge/license-BSD--2--Clause--Patent-blue)](LICENSE)

## Why not an arm64e-only profile

- **arm64e requires ARMv8.3 `FEAT_PAuth`** (pointer authentication) in hardware.
  The SM8150 CPUs (Cortex-A76 / A55) do not implement it, so the arm64e-only
  iPadOS 26/27 profiles cannot run here.
- iPadOS 18 still ships an **arm64 kernelcache**: the 2019 iPad 7
  (`iPad7,11` / `j171ap` / A10, also no PAC) runs 18.7.12. That archive is the
  arm64 reference the XNU tree is built against.
- **The kernel and the root must be the same build.** XNU matches the root by the
  APFS volume UUID and trust cache signed at build time; mixing builds (or
  Darwin versions) leaves the kernel unable to find/verify its root volume.
  Both archives below are `22H390` / Darwin `24.6.0` / xnu `11417.140.69`.

## Two archives, one build

UniXNU reads exactly one IPSW per run (`board.toml [ipsw]`), and `userdata`
takes the root disk images from it. This board pins that one to the **iOS**
payload, and prelink takes its kernelcache from a **separately staged iPadOS**
archive:

| | `[ipsw]` — payload | `[kernel.prelink]` — kernelcache reference |
| --- | --- | --- |
| Restore | iOS 18.7.12 for `iPhone11,2` (iPhone XS, `d321ap`, A12) | iPadOS 18.7.12 for `iPad7,11` (iPad 7, `j171ap`, A10) |
| Used for | `OS` / `Cryptex1,SystemOS` dmgs → root image | arm64 kernelcache Mach-O → prelink |
| Build | `22H390` | `22H390` |
| Why this one | phone-shaped userland | A10 has no PAC, so its kernelcache is arm64, not arm64e |

iOS 18's lowest device is the A12 iPhone XS, whose kernelcache is arm64e and
would not run on SM8150 — hence the iPadOS arm64 kernelcache even though the
root is iOS. `scripts/stage-arm64-kernelcache.py` extracts and decodes it into
`out/raphael/arm64-kernelcache.decompressed` (a dedicated path, because both
archives share the build ID and would otherwise overwrite each other in
`out/ipsw/22H390/`). Its sha256 is pinned in
`os-profiles/ipados-18.7.12-22H390/profile.toml`.

Upstream UniXNU has no 18.x profile, so this repository carries one under
`os-profiles/`; `scripts/install-device-profile.py` copies it into the UniXNU
checkout before resolving. `board.toml [board] os_profile` selects it.

Both 22H390 restores ship their dmgs as `.dmg.aea`. UniXNU decrypts AEA with
macOS `/usr/bin/aea` and `ipsw fw aea --key`, so **building the root image is a
macOS step**. The Linux host can resolve and `--dry-run` it, but not decrypt.
`[root] os_volume_uuid` is deliberately empty until that dmg is decrypted and
its APFS volume UUID can be read; an empty value makes the kernel build skip the
UUID variable rather than burn a wrong one in.

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

## Root image: build it, then flash it yourself

The root image is the **raw `SHNGROOT` image** UniXNU writes into the `unixnu`
partition. Two things produce it:

| Where | What it does |
| --- | --- |
| `.github/workflows/root-image.yml` | macOS runner. Builds `userdata-root.img`, converts it to `unixnu.sparse`, uploads both as artifacts, and publishes them as **Release assets on tag pushes** (no GitHub login needed to download) |
| `scripts/build-root.sh` locally | Same image on your own machine, plus `--flash` to write it to `unixnu` (falling back to `userdata`) |

```sh
# Locally: build and print the target, then build and flash.
scripts/build-root.sh --dry-run
scripts/build-root.sh --flash

# On the handset, from a downloaded release asset:
fastboot flash unixnu unixnu.sparse
```

Both run `./unixnu build userdata` on **macOS**, because the 22H390 payload dmgs
are AEA encrypted (`/usr/bin/aea` + `ipsw fw aea --key`). On Linux only the
`--dry-run` works; `scripts/ipsw_to_sparse.py` cannot decrypt AEA and says so
instead of emitting a broken image.

The build prints the exact image size and refuses to write when the image would
not fit the `[userdata]` geometry, so a wrong partition plan fails loudly
instead of overwriting a neighbour.

### Payload size

Run `./unixnu build userdata --dry-run` (see below) — it reads the IPSW's
central directory over HTTPS and prints the windows and their sizes without
downloading the archive. The target partition must hold at least that many bytes;
`./unixnu build userdata` refuses to build otherwise, so a wrong `[userdata]`
geometry fails loudly instead of corrupting another partition.

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
# Upstream has no 18.x profile; install this board's copy and the arm64 kernelcache.
python3 ../UniXNU-raphael/scripts/install-device-profile.py --unixnu .
python3 ../UniXNU-raphael/scripts/stage-arm64-kernelcache.py --unixnu .
./unixnu defconfig raphael_defconfig -D ../UniXNU-raphael
./unixnu fetch -D ../UniXNU-raphael
./unixnu status --json -D ../UniXNU-raphael   # ordered patches for the board's OS profile
./unixnu build kernel  -D ../UniXNU-raphael
./unixnu build package -D ../UniXNU-raphael   # -> UniXNU.efi
./unixnu build firmware -D ../UniXNU-raphael --uefi ../uefi-raphael
./unixnu bootimg -D ../UniXNU-raphael --uefi ../uefi-raphael
```

On Linux, run `sudo scripts/linux/setup-toolchain.py` once first (it compiles
clang with the `__builtin_xnu_type_*` patch, cctools-port ld64, mig, iig and
`lzfse` into `/opt/unixnu-linux`) — expect it to take hours. The staging script
needs the `lzfse` decoder on Linux and macOS `/usr/bin/compression_tool` on
macOS; CI installs both prerequisites.

`scripts/build.sh` runs the same sequence and honours `UNIXNU_DIR` / `UEFI_DIR`.

Firmware and `boot.img` need a `uefi-raphael` Mu-Silicium checkout with UniXNU,
UniXNUDxe, DarwinBoot, UniXNURamDiskDxe, DiskIoDxe and FatPkg in its DSC/FDF —
see [UEFI firmware integration](https://unixnu.com/porting/uefi-firmware).
Without it the kernel and the `UniXNU.efi` package still build; `boot.img`
cannot, since it embeds the firmware volume. Dispatch the workflow with
`uefi_repository=<owner/name>` once such a port exists.

Verify the target partition's capacity before any flash, without downloading the
IPSW:

```sh
./unixnu build userdata --dry-run -D ../UniXNU-raphael
```

That prints the windows and their sizes; nothing is extracted. Build the root
image itself (and flash it to the preferred partition) with:

```sh
scripts/build-root.sh --ipsw restore.ipsw --dry-run   # print target + size
scripts/build-root.sh --ipsw restore.ipsw --flash     # build + flash
```

## IPSW → flashable sparse image

```sh
python3 scripts/ipsw_to_sparse.py --raw-image userdata-root.img --output unixnu.sparse
fastboot flash unixnu unixnu.sparse
```

The converter emits libsparse FILL/RAW chunks and self-verifies by expanding the
output and comparing sizes. `--ipsw` picks the largest `.dmg` member (or the one
named by `--member`) and decodes it with UniXNU's own `scripts/unixnu/udif.py`,
which handles raw / zlib / bzip2 / LZFSE, so ZLIB-compressed members convert on
Linux with only Apple's reference `lzfse` binary (`.github/workflows/ipsw-convert.yml`
builds it). AEA-encrypted images are not UDIF and are rejected rather than
half-read. The 18.7.12 restores this board selects use AEA dmgs, so
`ipsw_to_sparse.py` cannot convert them directly: use UniXNU's `build userdata`
on macOS, which decrypts them with `/usr/bin/aea` (see
[Two archives, one build](#two-archives-one-build)).

`--list` prints the IPSW members without touching a byte of them:

```sh
python3 scripts/ipsw_to_sparse.py --ipsw restore.ipsw --list
```

## Porting status

| Area | State | Note |
| --- | --- | --- |
| Configuration | done | `board.toml`, `feeds.toml`, `porting.toml` resolve |
| Kernel (arm64) | in progress | builds against the profile's XNU |
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

The payload IPSW is pinned by the OS profile (`os-profiles/<profile>/profile.toml`
`[ipsw]`), selected by `board.toml [board] os_profile`. Its build and Darwin
version must stay in sync with the staged arm64 kernelcache — see
[Two archives, one build](#two-archives-one-build).

## Layout

```
board.toml                     device configuration (format 2)
feeds.toml                     SM8150 shared source pin
porting.toml                   structured porting record
os-profiles/ipados-18.7.12-22H390/profile.toml   board-carried OS profile
configs/raphael_defconfig      kernel defconfig
dts/raphael.dts                device tree
patches/xnu/series             XNU patch series (empty for now)
scripts/install-device-profile.py   copy the OS profile into the UniXNU checkout
scripts/stage-arm64-kernelcache.py  stage the iPadOS 18 arm64 kernelcache
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
