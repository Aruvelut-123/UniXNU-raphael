#!/usr/bin/env python3
"""Per-device hardware profiles for the SWEET XNU port.

One entry per phone: everything that changes when the same kernel/shim is
brought up on a different Qualcomm board. The values are the ones the early
boot path reads (see NOTES.md); they come from the live FDT / stock DTB of
the device (reserved-memory, /memory, /soc MMIO nodes) unless noted.

`guacamole` is the OnePlus 7 Pro (SM8150) port and `raphael` is the Redmi K20
Pro / Mi 9T Pro (SM8150) -- the SAME silicon. They share GIC/UFS/CPU MMIO
ranges; they differ in the board compatible string and the panel resolution
(raphael's panel is 1080x2340). `sweet` is the original SM7150 bring-up and is
kept for reference.

Each profile also carries an ``ios`` sub-dict: the *Apple* identity the kernel
presents to the iOS userland (product type / model / chip-id / canvas / the
base-ADT source). It is deliberately separate from the hardware keys above,
because the two are unrelated: the SM8150 board is fixed, while the iOS
identity is whatever iPhone the running userland came from.

The identity used to be hardcoded in mkadt.py and get-base-d22ap.sh (iPhone X,
D22AP / iPhone10,3, A11 chip-id 0x8015, 1125x2436 canvas). The iPhone X cannot
run iOS 26 -- it tops out at iOS 16.7.16 -- so the identity is now a per-device
value that moves with the iOS release the port targets. Change it in ONE place:
the ``ios`` dict below.

`default_ios(device)` returns that dict; `get(name)` returns the whole profile.

Used by tools/mkadt.py (ADT) and mirrored by shim/boards/*.h (framebuffer,
GIC, probe addresses). Keep the two in sync when changing a value.
"""

DEVICES = {
    'sweet': {
        # Redmi Note 10 Pro (SM7150 / Snapdragon 732G)
        'name': 'Redmi Note 10 Pro (sweet, SM7150)',
        'board_compat': 'xiaomi,sweet',
        'soc_compat': 'qcom,sm7150',
        'phys_base': 0xb0000000,
        'mem_size': 0x4d000000,
        'high_phys_base': 0x100000000,
        'high_mem_size': 0xfcc00000,
        'gicd': 0x17a00000,
        'gicd_size': 0x10000,
        'gicr': 0x17a60000,
        'gicr_size': 0x100000,
        'timebase': 19200000,
        'vtimer_intid': 19,
        'fb': 0x9c000000,
        'fb_size': 0x1700000,
        'fb_w': 1080,
        'fb_h': 2400,
        'fb_stride': 1080 * 4,
        'ufs': 0x01d84000,
        'ufs_size': 0x3000,
        'cpu_compat': 'qcom,kryo470',
        'cpus': 8,
        'cpu_regs': [0, 0x100, 0x200, 0x300, 0x400, 0x500, 0x600, 0x700],
        'cpu_clocks': [1804800000] * 6 + [2304000000] * 2,
        'memory_frequency': 1866000000,
        'bus_frequency': 100000000,
    },
    'guacamole': {
        # OnePlus 7 Pro (guacamole, SM8150). Board facts from the LineageOS
        # oneplus_sm8150 DTS and the mainline sm8150-oneplus-guacamole.dts;
        # audited against the GM1910's own live FDT.
        'name': 'OnePlus 7 Pro (guacamole, SM8150)',
        'board_compat': 'oneplus,guacamole',
        'soc_compat': 'qcom,sm8150',
        'phys_base': 0xc0000000,
        'mem_size': 0xc0000000,
        'high_phys_base': 0x180000000,
        'high_mem_size': 0x100000000,
        'gicd': 0x17a00000,          # confirmed on the live FDT
        'gicd_size': 0x10000,
        'gicr': 0x17a60000,          # confirmed
        'gicr_size': 0x100000,
        'timebase': 19200000,        # confirmed (clock-frequency)
        'vtimer_intid': 19,          # confirmed (GIC_PPI 3 numbering)
        # reserved-memory cont_splash_region: 0x9C000000, 0x02400000 (36 MiB).
        'fb': 0x9c000000,
        'fb_size': 0x2400000,
        'fb_w': 1440,
        'fb_h': 3120,
        'fb_stride': 1440 * 4,
        'ufs': 0x01d84000,           # confirmed (ICE at 0x1d90000 too)
        'ufs_size': 0x3000,
        'cpu_compat': 'qcom,kryo485',
        'cpus': 8,
        'cpu_regs': [0, 0x100, 0x200, 0x300, 0x400, 0x500, 0x600, 0x700],
        'cpu_clocks': [1785600000] * 4 + [2419200000] * 3 + [2841600000],
        'memory_frequency': 2133000000,
        'bus_frequency': 100000000,
    },
    'raphael': {
        # Redmi K20 Pro / Mi 9T Pro (raphael, SM8150) -- SAME SoC as guacamole.
        # Board facts from the LineageOS xiaomi_sm8150 DTS (device_xiaomi_raphael)
        # and the previous live-FDT audit (adb feac7571). The SM8150 MMIO ranges
        # (GIC/UFS/timer) are identical to guacamole; only the panel resolution
        # (1080x2340) and the board compatible differ.
        'name': 'Redmi K20 Pro / Mi 9T Pro (raphael, SM8150)',
        'board_compat': 'xiaomi,raphael',
        # The kernel is built with MACHINE_CONFIG=SWEET, whose built-in
        # platform expert only matches IONameMatch 'xiaomi,sweet'. The tree has
        # to carry that string or the platform expert never binds.
        'platform_match': 'xiaomi,sweet',
        'soc_compat': 'qcom,sm8150',
        # SM8150 DDR (audited on the raphael live FDT): reuse the documented
        # 3 GiB mid bank (carve-out free) so QEMU/lowmem runs have a valid window.
        'phys_base': 0xc0000000,
        'mem_size': 0xc0000000,
        'high_phys_base': 0x180000000,
        'high_mem_size': 0x100000000,
        'gicd': 0x17a00000,          # confirmed on the live FDT
        'gicd_size': 0x10000,
        'gicr': 0x17a60000,          # confirmed
        'gicr_size': 0x100000,
        'timebase': 19200000,        # confirmed (clock-frequency)
        'vtimer_intid': 19,          # confirmed (GIC_PPI 3 numbering)
        # reserved-memory cont_splash_region: 0x9C000000, 0x02400000 (36 MiB);
        # large enough for the 1080x2340x4 framebuffer and matches the SoC range.
        'fb': 0x9c000000,
        'fb_size': 0x2400000,
        'fb_w': 1080,
        'fb_h': 2340,
        'fb_stride': 1080 * 4,
        'ufs': 0x01d84000,           # confirmed (ICE at 0x1d90000 too)
        'ufs_size': 0x3000,
        # Kryo 485: 4x A55 (silver) + 3x A76 (gold) + 1x A76 (prime) -- same as guacamole.
        'cpu_compat': 'qcom,kryo485',
        'cpus': 8,
        'cpu_regs': [0, 0x100, 0x200, 0x300, 0x400, 0x500, 0x600, 0x700],
        'cpu_clocks': [1785600000] * 4 + [2419200000] * 3 + [2841600000],
        'memory_frequency': 2133000000,
        'bus_frequency': 100000000,

        # --- Apple identity presented to the iOS userland -------------------
        # Everything below is read back by scripts/mkadt.py and
        # scripts/build-efi-image.py.  Values marked [UNVERIFIED] are the
        # best-known candidates; see the note above PLACEHOLDER_* at the
        # bottom of this file.
        'ios': {
            # Base-ADT source: the DeviceTree member of the restore IPSW whose
            # /product node the ADT carries.
            # [VERIFIED] iPhone 11 (N104AP / iPhone12,1) is the first
            # generation that runs iOS 26; iPhone XS (D321AP / iPhone11,2) tops
            # out at 18.7.11. Source: research-ios26.md / ipsw.me API.
            'product_type': 'N104AP',
            'model': 'iPhone12,1',
            'target_type': 'N104',
            # [VERIFIED] A13 (t8030) cpid 32816 = 0x8030.
            'chip_id': 0x8030,
            # Canvas of the *presented* device, not of the panel: the iPhone 11
            # is 828x1792 @2x, while raphael's own panel is 1080x2340.
            'canvas_width': 828,
            'canvas_height': 1792,
            'display_scale': 2,
            # [VERIFIED] iPhone 12,1 iOS 26.0 (23A341) restore IPSW, sha256
            # 65da7bf14d281fba63a11c61e09d4a3a4b865d49f7e628d97295633758a347bb.
            'ipsw_url': ('https://updates.cdn-apple.com/2025FallFCS/fullrestores/093-40149/'
                         'C2DDBCFD-327C-417B-A463-8F7820561E80/'
                         'iPhone12,1_26.0_23A341_Restore.ipsw'),
            # [UNVERIFIED] the obvious pattern from the d22ap build
            # (Firmware/all_flash/DeviceTree.d22ap.im4p), but not confirmed
            # against this IPSW. Confirm with:
            #   unzip -l iPhone12,1_26.0_23A341_Restore.ipsw | grep DeviceTree
            'dt_member': 'Firmware/all_flash/DeviceTree.n104ap.im4p',
            # True while the three values above are still unverified guesses.
            'unverified': True,
        },
    },
}


def get(name):
    try:
        return DEVICES[name]
    except KeyError:
        raise SystemExit(f'unknown device "{name}"; known: {", ".join(sorted(DEVICES))}')


# The iOS identity of the reference device (the SM7150 sweet bring-up). Every
# board that has no `ios` dict of its own presents this one, so mkadt.py has a
# single well-defined fallback instead of a second hardcoded copy.
PLACEHOLDER_REFERENCE_IOS = {
    'product_type': 'D22AP',
    'model': 'iPhone10,3',
    'target_type': 'D22',
    # A11 (iPhone X): 0x8015 is what the shipped iPhone X userland expects.
    'chip_id': 0x8015,
    # Canvas of the *presented* device, not of the panel: the iPhone X is
    # 1125x2436, while raphael's own panel is 1080x2340.
    'canvas_width': 1125,
    'canvas_height': 2436,
    'display_scale': 3,
    # Verified-available iPhone X (D22AP) iOS 16.7.16 restore IPSW; the iPhone
    # X never got an iOS 26 restore, so this is the LAST iOS this identity can
    # source a base ADT from.
    'ipsw_url': ('https://updates.cdn-apple.com/2025FallFCS/fullrestores/122-77006/'
                 '1158E502-D76D-4226-AA06-ED5E30CD1111/'
                 'iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw'),
    'dt_member': 'Firmware/all_flash/DeviceTree.d22ap.im4p',
    'unverified': False,
}


def default_ios(device='sweet'):
    """The `ios` identity dict for `device`, falling back to the reference one.

    Returns a copy so a caller can override single keys without mutating the
    profile.
    """
    prof = get(device)
    ident = prof.get('ios') or PLACEHOLDER_REFERENCE_IOS
    return dict(ident)
