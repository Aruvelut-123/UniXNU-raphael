# Root partition preference for raphael

UniXNU selects the root volume by **APFS Volume UUID** (`[payload.adt]
root_match_volume_uuid`), not by partition label. The root image is built by
`./unixnu build userdata` from `board.toml`'s `[userdata]` geometry and flashed
to exactly one partition.

To prefer a dedicated `unixnu` partition and fall back to `userdata`, the
choice is made **when flashing**, not when booting:

```
                  ┌─────────────────────────┐
                  │ scripts/build-root.sh   │
                  └───────────┬─────────────┘
                              │
              ┌───────────────┴────────────────┐
              ▼                                ▼
    unixnu partition present?          no unixnu partition
              │                                │
              ▼                                ▼
   flash to /dev/block/by-name/unixnu   flash to /dev/block/by-name/userdata
              │                                │
              └───────────────┬────────────────┘
                              ▼
              board.toml [userdata] geometry + ADT UUID
```

## Why not at boot time

XNU matches `IOMedia` by the root volume UUID written into the ADT. A boot-time
"try partition A, then B" search would need either

- two payload variants (one ADT per root UUID) plus a firmware-side selector, or
- a custom native block driver that enumerates both candidates and picks the
  first with a matching volume.

Neither exists yet, so the selection lives in the flash step.

## Filling in `[userdata]`

`board.toml [userdata]` holds **one device's** GPT geometry and is what
`./unixnu build userdata` uses to locate the window on disk. Partition layouts
differ per handset — a repartitioned disk, a 256 GB model and a stock 512 GB
model all disagree — so re-read it for your own phone instead of trusting the
committed numbers:

```sh
# On the phone, as root (sysfs is readable only with root):
adb shell su -c "cat /sys/block/sda/sda34/start /sys/block/sda/sda34/size"
```

`start` and `size` are in **512-byte sectors**, so
`last_lba = start + size - 1`, and `lba_bytes = 512`.

Do not use `sgdisk -p` on MIUI: the `sgdisk` there is toybox's stub and rejects
`-p`. Read `/proc/partitions` for sizes and `/dev/block/by-name` for the
label → node mapping instead, or dump the raw GPT header from the disk.

The committed values describe the maintainer's own repartitioned 512 GB handset
(`unixnu` = sda34, 128 GiB). Use them only as a sanity check that your `unixnu`
is big enough; a wrong `first_lba` makes the image land on the wrong sectors.

## The root image must match the kernel's OS profile

The root image is not interchangeable between OS versions. XNU matches the root
volume by the APFS volume UUID baked into the ADT at build time, and the
`SystemVolume` root hash plus `StaticTrustCache` come from the same IPSW the
kernel was built against. Building a kernel from one OS profile and flashing a
root image from another OS version leaves the kernel unable to find or verify
its root volume.

So `board.toml [board] os_profile` selects **both** the kernel inputs and the
IPSW whose disk images go into `[userdata]` windows. Changing one without the
other is not a supported configuration.

## Verification

`scripts/build-root.sh --dry-run` prints the chosen target and the image size
without writing anything. `userdata-root.json` records the window offsets,
capacity and the exact `fastboot flash` command that was used.