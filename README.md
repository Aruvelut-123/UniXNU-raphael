# UniXNU-raphael

**Boot Apple's XNU (iOS) on the Redmi K20 Pro / Mi 9T Pro (`raphael`, Snapdragon 855 / SM8150) and reach the iOS SpringBoard desktop — from a stock, unlocked phone, with no macOS, no private source, and no manual kernel work.**

This repository is a *turnkey* device port built on the [UniXNU](https://github.com/UniXNU/UniXNU) framework. It reuses the proven **OnePlus 7 Pro (`guacamole`)** SM8150 bring-up (which already reaches the iOS 16.7.x userland) because `raphael` is the **exact same SM8150 silicon** — only the device tree and the panel resolution (1080×2340) differ. The SM8150 XNU kernel and the Project Aloha UEFI are shared, so there is **no per-device kernel defconfig to obtain**.

> Everything is produced by GitHub Actions. You only need a GitHub account and an unlocked phone.

---

## What you get

A single Android `boot-raphael.img` that you boot temporarily with `fastboot boot` (nothing is written to your device's partitions). The boot chain:

```
fastboot boot boot-raphael.img
   └─ Project Aloha UEFI (SM8150, xiaomi-raphael)  ── SM8150_EFI.fd
        └─ UniXNU boot menu
             └─ GUACESP FAT payload (64 MiB)
                  ├─ kernel.macho        (SM8150 XNU, from guacamole's build)
                  └─ raphael ADT         (iPhone X D22AP identity + raphael panel)
                       └─ DarwinBoot → XNU → UFS root → launchd → SpringBoard
```

---

## One-click build (no understanding required)

1. **Fork** this repository to your own GitHub account.
2. Go to **Actions → “build-raphael”** and click **Run workflow**.
   - The workflow does everything: on a free `macos-14` runner it builds the SM8150 XNU 8796 kernel the same public way `guacamole` does (`dipa-studio/ios-sweet` → `blacktop/darwin-xnu-build`, `MACHINE_CONFIG=SWEET`); then on `ubuntu-latest` it checks out the UniXNU driver and Project Aloha UEFI, fetches the raphael/SM8150 device tree, automatically extracts the iPhone X (`D22AP`) base Apple Device Tree from the public IPSW, builds the UEFI firmware volume, packs the FAT payload, and produces the boot image.
3. When it finishes, download the **`boot-raphael.img`** artifact.

That's it. Every input the build needs is either in this repo or fetched from a **public** source — there is no private kernel defconfig and no manual IPSW work.

---

## Boot it on the phone

Prerequisites (one-time, on your computer): install [Android platform-tools](https://developer.android.com/tools/release-notes-sdk-platform-tools) so you have `adb` and `fastboot`, and **unlock the bootloader** of the phone.

```bash
# phone in bootloader/fastboot mode (power + volume-down, or `adb reboot bootloader`)
fastboot boot boot-raphael.img
```

`fastboot boot` loads the image into RAM only — it does **not** flash or modify any partition, so it is safe and reversible (a normal reboot returns you to Android). Watch the screen for the UniXNU menu, then the iOS desktop.

If your device has **6 GB** of RAM (instead of 8 GB), open `board.toml` and lower `payload.adt.owned_memory_size` (e.g. `0x80000000`) before building.

---

## How it works (for the curious)

| Piece | Source | Why |
|-------|--------|-----|
| SM8150 XNU kernel | `dipa-studio/ios-sweet` → `blacktop/darwin-xnu-build` on `macos-14` (`MACHINE_CONFIG=SWEET`) | The exact public path guacamole uses; identical silicon ⇒ identical kernel. **No private defconfig** — this is the standard XNU 8796 build. |
| Project Aloha UEFI | `Project-Aloha/mu_aloha_platforms` + 3 SM8150 patches | Boots XNU on SM8150; `xiaomi-raphael` device is cloned from `oneplus-guacamole` |
| `raphael.dtb` | Reuses the SM8150 DTB shipped in the Aloha UEFI tree (`get-raphael-dtb.sh`) | Same SoC ⇒ same memory map / MMIO |
| `base-d22ap.adt` | Auto-extracted from the public iPhone X (D22AP) iOS 16.7.16 IPSW (`get-base-d22ap.sh`) | Provides the real `/product` identity MobileGestalt expects |
| `raphael` ADT | `scripts/mkadt.py --device raphael` | D22AP identity + raphael 1080×2340 panel + SM8150 MMIO |

The `scripts/` directory contains the full, self-contained toolchain (`adt.py`, `devices.py`, `mkadt.py`, `build-firmware.py`, `build-payload.py`, `build-bootimg.py`, `get-raphael-dtb.sh`, `get-base-d22ap.sh`). You can reproduce the whole build locally; the only network input is the public IPSW (for the D22AP base tree) and the public git trees.

---

## Repository layout

```
board.toml                 device definition (SoC, firmware, payload, bootimg)
patches/                  the 3 SM8150 patches (unixnu / aloha / darwinboot)
scripts/
  adt.py                  Apple Device Tree parse/serialize
  devices.py              per-board hardware profiles (sweet/guacamole/raphael)
  mkadt.py                builds the minimal ADT XNU needs
  make-raphael-adt.py     ADT step for raphael (D22AP + raphael profile)
  build-firmware.py       builds the UEFI firmware volume (xiaomi-raphael)
  build-payload.py        packs kernel + ADT into the GUACESP FAT payload
  build-bootimg.py        packs the Android boot image
  get-raphael-dtb.sh      fetches the SM8150 device tree
  get-base-d22ap.sh       auto-extracts the iPhone X base ADT from the IPSW
.github/workflows/build-raphael.yml   the turnkey CI
```

---

## Known limitations (inherited from the SM8150 bring-up)

- **No SEP / secure enclave** ⇒ cannot sign in to an Apple ID or use cellular/baseband. The boot is set up as a dev-fused, activated board so the UI still reaches the desktop.
- **Bluetooth / cellular / fingerprint** are not expected to work.
- This is a **temporary boot** (`fastboot boot`); it does not persist across a reboot.
- Userland is **iOS 16.7.x** (iPhone X / D22AP restore build).

---

## Credits

- [UniXNU](https://github.com/UniXNU/UniXNU) — the UEFI/XNU boot framework.
- [Project Aloha](https://github.com/Project-Aloha) — SM8150 UEFI.
- `wochgn/UniXNU-guacamole` — the proven SM8150 (OnePlus 7 Pro) port this device reuses.
- `dipa-studio/ios-sweet` — the XNU 8796 build harness.
- Apple's iPhone X (D22AP) device tree is extracted from a public IPSW for identification only.
