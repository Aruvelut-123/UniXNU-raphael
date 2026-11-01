# Flashing the iOS root (HFS+) to raphael

## Why HFS+ and not the SHNGROOT/APFS image

The kernel this port boots is the **SWEET** platform XNU (XNU 8796) built by
`dipa-studio/ios-sweet`. It does **not** use UniXNU's native userdata path:

| | UniXNU native (upstream docs) | This port (SWEET kernel) |
| --- | --- | --- |
| userdata layout | `SHNGROOT` manifest + disk-image windows | nothing; the partition *is* the filesystem |
| root filesystem | APFS volume inside the `OS` window | **HFS+ volume at the start of the partition** |
| how the root is found | `/chosen/root-matching` UUID in the ADT | GPT partition named `userdata` (boot-arg `ufsroot=`) |
| kernel support | native APFS driver | `bsd/dev/sweet_ufs.c` (patch 0028) + built-in Apple OSS `hfs-627` (patch 0026) |

The kernel binary settles it: `SWEET HFS`, `sweet_ufs`, `sweet_ufs_rootdev`
and `ufsroot0` are all present, while **`SHNGROOT` appears zero times**.

`bsd/dev/sweet_ufs.c` finds one GPT partition by name on the internal UFS
(`ufsroot=`, default `userdata`), exposes it as the BSD disk `ufsroot0` with
512-byte logical sectors over 4 KiB device blocks, and the built-in HFS+ driver
mounts it at `/`. The root volume therefore has to be an **HFS+ volume placed
at the very beginning of the `userdata` partition**.

Consequence: an image built as "SHNGROOT manifest + APFS `OS`/`SystemOS`
windows" (what `unixnu build userdata` produces) is **unreadable** by this
kernel. `scripts/../work/mkuserdata.py` on the workstation was a dead end.

The same is true for the official `wochgn/UniXNU-guacamole` device repository
(oneplus 7 Pro, same SM8150 silicon, already reached the iOS userland): its
`board.toml` has **no `[userdata]` section** and its ADT has **no
`root-matching`** node either. It boots the HFS+ iOS root that was already on
the phone's UFS.

## Where the image comes from

The `ios-root-hfs` workflow (`.github/workflows/ios-root-hfs.yml`) builds it
on `ubuntu-24.04`:

1. download the public iPhone X 16.7.16 IPSW,
2. read `OS.dmg`, `Cryptex1,SystemOS` and `Cryptex1,AppOS` with `apfs-fuse`
   (the IPSW images are APFS with LZBITMAP-compressed files),
3. assemble them into **one 16 GiB case-sensitive journaled HFS+ volume**
   (`iOSRoot`) with `mkfs.hfsplus` and `rsync -aH` (owners, modes, symlinks
   and hard links preserved),
4. apply the upstream bring-up tweaks (`tools/sweet-root-tweaks.py`):
   - `launchd.plist`: `_PanicOnCrash` → `_PanicOnCrasX` (a crashing daemon
     must not panic the system) and the CommCenter jobs removed (no baseband:
     it crash-loops and Setup blocks on its CoreTelephony XPC),
   - `/private/var/containers/{Bundle,Data/System,Shared/SystemGroup,Temp}`,
   - `com.apple.migration`: `LastSystemVersion` so DataMigration does not run
     for an hour on every boot,
   - `com.apple.springboard`: `BKNoWatchdogs` (no scene-create watchdog kills),
   - `com.apple.purplebuddy`: Setup skipped (`SetupDone`, `SetupFinishedAllSteps`,
     `SetupVersion` 11),
   - `VirtualAudio.plugin` disabled and `StartRecorderServer=false`
     (mediaserverd crash loop),
5. seed the activation state (`scripts/seed_activation.py`),
6. `fsck.hfsplus`, convert to Android sparse, publish in 1.9 GB parts.

The published release is `iosroot-16.7.16-<timestamp>` with the parts
`root-part.00` … `root-part.06`.

## Flash it

```bash
# 1. download the parts
gh release download iosroot-16.7.16-20261031-141135 \
    -R JohnLeeeeeee678/UniXNU-raphael -p 'root-part.*' -D hfsroot/

# 2. concatenate and verify
python3 scripts/assemble_hfsroot.py hfsroot/ -o ios16-root.simg

# 3. split it: the Google fastboot.exe for Windows is 32-bit and mmaps the
#    whole file, so anything above ~2 GB dies with std::bad_alloc
python3 scripts/split_for_abl.py ios16-root.simg -o pieces/

# 3b. prove the pieces reproduce the image byte for byte before flashing
python3 scripts/verify_pieces.py ios16-root.simg pieces/

# 4. phone into the bootloader, then flash in DESCENDING order
for p in $(ls pieces/p*.simg | sort -r); do fastboot flash userdata "$p"; done
```

Descending order is deliberate: each piece carries a leading `DONT_CARE`
chunk that covers every block before its own range, and the SM8150 ABL
**seeks** over `DONT_CARE` instead of writing zeros. If a bootloader ever
materialised `DONT_CARE` as zeros, descending order would only damage blocks
that have not been written yet.

**This overwrites `userdata`.** Everything on that partition is lost.

## Boot

```bash
fastboot boot boot-raphael.img
```

Watch the screen. The kernel panel prints a digest every 20 s:

```
=== SWEET t=60s exec=42 crash=3 sb=1/1 fb=9 sw=16 dn=0 m=1 ===
```

- `sw=` — number of framebuffer presents that actually reached the panel. If
  it is non-zero the GUI owns the screen and the panel stops painting
  (`m=1` means the console is muted).
- `sb=x/y` — SpringBoard execs / SpringBoard crashes.
- `crash=` — crashing processes, listed underneath.

If `sw=` stays 0 the userland never presented a frame; the panel keeps
painting the digest every 20 s so the numbers stay readable.

## Kernel boot arguments

From `board.toml` `[payload] kernel_args`:

| Argument | Meaning |
| --- | --- |
| `rd=ufsroot0` | mount the root from `ufsroot0` (the `userdata` GPT partition) |
| `ufsroot=userdata` | optional: which GPT partition to use (default `userdata`) |
| `sweetfb_noconsole=1` | mute the console once the GUI presents (see the note below) |
| `sweetfb_hz=30` | framebuffer present rate |
| `sweetusb=2` | expose the kernel console over USB CDC-ACM |
| `ignition_level=1` | look for the shared cache in the cryptexes |

## Note on `sweetfb_noconsole`

`sweetfb_noconsole=1` makes the kernel mute the console on the **first** swap
(patch 0067). That is what upstream uses, and it hides the kernel text once
the GUI takes the screen.

It also means that if the userland never gets far enough to present a frame
while the console was already muted, the screen stays blank with no
diagnostics on it -- and this port cannot pull the persistent log, because
that needs a recovery, which is out of scope here.

The kernel's panel thread (patch 0103 onwards, enabled by default) solves this
better: it keeps painting a digest every 20 s, and as soon as it sees a
**real** framebuffer present it draws one last digest and then stops painting
so the GUI shows through. So for bring-up, boot **without** `sweetfb_noconsole`:

```
python3 scripts/mkboot.py TEST_X.img TEST_Y.img --del sweetfb_noconsole
```

`TEST_Y.img` in this repository is exactly that: the same kernel, the same
ADT and the same UEFI as `TEST_X.img`, with that one boot argument removed.

## Still open

- **Touch**: not wired up yet on raphael.
- **SEP**: absent, so no secure enclave operations.
- **Apple ID**: the root is seeded as Activated
  (`scripts/seed_activation.py` creates the mobileactivationd container the
  upstream bring-up image used and writes `data_ark.plist` into it), but
  without a SEP the device still cannot sign in to an Apple ID.
