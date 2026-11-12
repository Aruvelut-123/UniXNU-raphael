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

## Adding a `unixnu` partition

The partition must be declared in the device GPT before it can be used. Add it
from a Linux host with `sgdisk` / `parted` while the phone is in a fastboot
DSU or a booted-recovery shell, then read back its geometry:

```sh
# On the phone (root shell), read the new entry's LBAs
sgdisk -i <n> /dev/block/sda

# Copy first_lba / last_lba / lba_bytes into board.toml
```

`board.toml` describes the **`unixnu`** entry (sda34, 128.00 GiB). Measured on
the handset; see the table in the README. Do not use `sgdisk -p` on MIUI: the
`sgdisk` shipped there is toybox's and rejects `-p`.

If you ever re-read the geometry, the sysfs files need root:

```sh
adb shell su -c "cat /sys/block/sda/sda34/start /sys/block/sda/sda34/size"
```

`start` and `size` are in **512-byte sectors**, so
`last_lba = start + size - 1`.

## Verification

`scripts/build-root.sh --dry-run` prints the chosen target and the image size
without writing anything. `userdata-root.json` records the window offsets,
capacity and the exact `fastboot flash` command that was used.