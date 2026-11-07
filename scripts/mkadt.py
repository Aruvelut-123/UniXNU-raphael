#!/usr/bin/env python3
"""Build the minimal Apple Device Tree that the SWEET xnu needs to boot.

Only what the early boot path actually reads (see NOTES.md); every MMIO
address comes from the device's live FDT (see tools/devices.py for the
per-board profile).

The *Apple* identity -- product type, model string, chip-id, presented canvas
and the base ADT its /product node comes from -- is NOT part of the hardware
profile: it is the ``ios`` sub-dict of the device profile in devices.py, so it
can move with the iOS release the port targets without touching this file.
It used to be hardcoded here as the iPhone X (D22AP / iPhone10,3).

Usage:  mkadt.py OUT.adt [--device sweet|guacamole|raphael] [--dump] [--qemu] [--highmem]
                      [--ios-product-type P] [--ios-model M] [--ios-chip-id N]
                      [--ios-canvas WxH] [--base-adt PATH]
"""
import hashlib, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adt      # noqa: E402
import devices  # noqa: E402

# /arm-io children are relative to this; it must not be 0 (serial_init bails)
SOC_BASE = 0x01000000

SWEET_ECID = 0x5357454554000001  # 'SWEET' + 1, synthetic
# QEMU virt (-M virt,gic-version=3 -cpu cortex-a76): GICD/GICR and the generic timer's CNTFRQ
QEMU_GICD, QEMU_GICR, QEMU_TIMEBASE = 0x08000000, 0x080a0000, 62500000
QEMU_VTIMER_INTID = 27

BOOT_MANIFEST_HASH = hashlib.sha384(b'sweet boot manifest').digest()

# The iOS userland is an iPhone IPSW. MobileGestalt derives product type,
# device class, home-button-less UI, artwork etc. from the root identity and
# /product of that device's real device tree. That tree is an Apple artifact
# (kept out of git): scripts/get-base-adt.sh extracts it from the IPSW.
#
# Which device that is comes from the profile's `ios` sub-dict (devices.py).
# The environment variable / --base-adt override below still name the D22AP
# artifact for backwards compatibility with existing callers.
DEFAULT_BASE_ADT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'base-adt.adt')
LEGACY_BASE_ADT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'base-d22ap.adt')
D22AP_ADT = os.environ.get('UNIXNU_D22AP_ADT') or (
    LEGACY_BASE_ADT if os.path.exists(LEGACY_BASE_ADT) else DEFAULT_BASE_ADT)


def base_product(path=None):
    """/product properties of the real base device tree, without the syscfg
    placeholders iBoot would fill in (flag bit set) and the node bookkeeping.

    The tree is the one get-base-adt.sh fetched for the profile's iOS identity
    (D22AP historically, an iOS 26 device now)."""
    path = path or D22AP_ADT
    if not os.path.exists(path):
        print(f'warning: {path} missing, no /product node', file=sys.stderr)
        return None
    root, _ = adt.parse(open(path, 'rb').read())
    for c in root.children:
        if dict((k, v) for k, f, v in c.props).get('name') == b'product\0':
            return [(k, v) for k, f, v in c.props if not f and k not in ('name', 'AAPL,phandle')]
    raise SystemExit(f'{path}: no /product node')


# Backwards-compatible alias: the function used to be named after the device.
d22ap_product = base_product

u32 = lambda *v: struct.pack('<%dI' % len(v), *v)
u64 = lambda *v: struct.pack('<%dQ' % len(v), *v)
cstr = lambda s: s.encode() + b'\0'


def node(name, props=(), children=()):
    n = adt.Node()
    n.props = [('name', 0, cstr(name))] + [(k, 0, v) for k, v in props]
    n.children = list(children)
    return n


def build(seed=None, qemu=False, highmem=False, device='sweet', dram_size=None, owned_memory_size=None,
          ios=None, base_adt=None):
    """qemu=True: same tree, but with QEMU virt's GIC addresses and CNTFRQ (tools/qemu-sweet.py).
    dram_size overrides the profile's kernel RAM size (e.g. 0x180000000 on an 8 GB guacamole).
    owned_memory_size emits /chosen/darwinboot-memory-size for the contiguous kernel window.
    ios overrides keys of the profile's `ios` identity dict (devices.py).
    base_adt overrides the path of the fetched base device tree (default: the
    profile identity's artifact)."""
    if owned_memory_size is not None and (
            not 0x10000000 <= owned_memory_size <= 0x200000000 or owned_memory_size & 0x1FFFFF):
        raise SystemExit('owned-memory-size must be 256 MiB..8 GiB in 2 MiB steps')
    dev = devices.get(device)
    ident = devices.default_ios(device)
    ident.update(ios or {})
    product_type = ident['product_type']
    model = ident['model']
    target_type = ident.get('target_type') or product_type.rstrip('AP')
    chip_id = ident['chip_id']
    canvas_w, canvas_h = ident['canvas_width'], ident['canvas_height']
    display_scale = ident.get('display_scale', 3)
    if base_adt:
        globals()['D22AP_ADT'] = base_adt
    phys_base, mem_size = (dev['high_phys_base'], dev['high_mem_size']) if highmem else (dev['phys_base'], dev['mem_size'])
    if dram_size is not None:
        mem_size = dram_size
    gicd, gicr, timebase = (QEMU_GICD, QEMU_GICR, QEMU_TIMEBASE) if qemu else (dev['gicd'], dev['gicr'], dev['timebase'])
    fb, fb_size = dev['fb'], dev['fb_size']
    gicd_size, gicr_size = dev['gicd_size'], dev['gicr_size']
    ufs, ufs_size = dev['ufs'], dev['ufs_size']
    vtimer_intid = QEMU_VTIMER_INTID if qemu else dev['vtimer_intid']
    seed = seed if seed is not None else os.urandom(64)
    phandle = iter(range(1, 1000))
    ph = lambda: ('AAPL,phandle', u32(next(phandle)))

    chosen = node('chosen', [
        ph(),
        ('dram-base', u64(phys_base)),
        ('dram-size', u64(mem_size)),
        *([('darwinboot-memory-size', u64(owned_memory_size))] if owned_memory_size else []),
        ('random-seed', seed),
        ('debug-enabled', u32(1)),
        ('firmware-version', cstr('sweet-shim')),
        ('system-firmware-version', cstr('sweet-shim')),
        # iBoot's SHA-384 of the boot manifest; /sbin/mount -P 1 exits unless
        # it exists (bind mounts /private/preboot/<hex>/usr/standalone/firmware,
        # tolerating a missing directory). Fixed stand-in value.
        ('boot-manifest-hash', BOOT_MANIFEST_HASH),
        # libimg4 (cryptexd) aborts "failed to get crypto algorithm" without
        # it; real A11+ device trees say sha2-384.
        ('crypto-hash-method', cstr('sha2-384')),
        # MobileGestalt's screen class: display-scale (u32) comes from /chosen,
        # the pixel size from IOMobileFramebuffer. Scale 0 makes SpringBoard's
        # FBSDisplayMode "infxinf@0x" invalid. 1080x2400 @3x = 360x800 points
        # (like iPhone X class devices); the value is the profile identity's.
        ('display-scale', u32(display_scale)),
        # XNU derives IOPlatformUUID (gethostuuid) from these on arm; without
        # them CFPreferences cannot use kCFPreferencesCurrentHost (no ByHost
        # files), so e.g. DataMigration never records LastSystemVersion and
        # migrates on every boot. Synthetic ECID (not the phone's); chip-id is
        # the AES id of the iOS device whose userland runs here, from the
        # profile identity (A11 / iPhone X = 0x8015 historically).
        ('unique-chip-id', struct.pack('<Q', SWEET_ECID)),
        ('chip-id', u32(chip_id)),
        # Security status as on a dev-fused, undemoted board (tuple 0,0,1,1):
        # MobileGestalt reads these from /chosen, and mobileactivationd's
        # DeviceType then takes its native "Hactivation" branch (state
        # Activated without an activation record; no SEP, no baseband here).
        ('certificate-production-status', u32(0)),
        ('effective-production-status-ap', u32(0)),
        ('certificate-security-mode', u32(1)),
        ('effective-security-mode-sep', u32(1)),
    ], [node('memory-map', [ph()]),
        # Local boot policy (kern_csr.c): SIP relaxed like `csrutil disable`
        # (lp-sip0: untrusted kexts, unrestricted FS, task_for_pid, kernel
        # debugger, dtrace, nvram), lp-sip1: unauthenticated (unsealed) root.
        node('asmb', [ph(), ('lp-sip0', u64(0x6f)), ('lp-sip1', u32(1))])])

    # SWEET SMP: all cores in physical-core order as one homogeneous cluster
    # (sweet: 0-5 A55 + 6-7 A76; guacamole/raphael: 0-3 A55 + 4-7 A76). The
    # kernel defaults to one and uses cpus=N to select an initial prefix.
    cpu_nodes = []
    for core in range(1 if qemu else dev['cpus']):
        cpu_nodes.append(node(f'cpu{core}', [
            ph(),
            ('device_type', cstr('cpu')),
            ('compatible', cstr(dev['cpu_compat']) + cstr('ARM,v8')),
            ('reg', u32(dev['cpu_regs'][core])),  # actual MPIDR Aff1:Aff0, NOT logical ID
            ('cpu-id', u32(core)),   # descriptive: XNU assigns IDs by DT order
            ('cluster-id', u32(0)),  # descriptive; see ml_parse_cpu_topology
            ('cluster-type', u32(0)),  # homogeneous CLUSTER_TYPE_SMP, not AMP
            ('die-cluster-id', u32(0)),
            ('cluster-core-id', u32(core)),
            ('l2-cache-id', u32(core)),  # distinct per-core L2 nodes in live FDT
            ('l3-cache-id', u32(0)),     # shared L3
            ('state', cstr('running' if core == 0 else 'stopped')),
            ('timebase-frequency', u32(timebase)),
            ('clock-frequency', u32(dev['cpu_clocks'][core])),
            ('bus-frequency', u32(dev['bus_frequency'])),
            ('memory-frequency', u32(dev['memory_frequency'])),
            ('peripheral-frequency', u32(timebase)),
            ('fixed-frequency', u32(timebase)),
        ]))
    cpus = node('cpus', [ph(), ('#address-cells', u32(1)),
                         ('#size-cells', u32(0))], cpu_nodes)

    gic = node('gic', [
        ph(),
        ('compatible', cstr('arm,gic-v3')),
        ('interrupt-controller', b''),
        ('virtual-timer-intid', u32(vtimer_intid)),
        ('reg', u64(gicd - SOC_BASE, gicd_size, gicr - SOC_BASE, gicr_size)),
    ])
    arm_io = node('arm-io', [
        ph(),
        ('device_type', cstr('sweet-io')),
        ('compatible', cstr('sweet-io') + cstr('arm-io')),
        ('#address-cells', u32(2)),
        ('#size-cells', u32(2)),
        ('ranges', u64(0, SOC_BASE, 0x100000000 - SOC_BASE)),
    ], [gic,
        # No hardware: watchdogd checks IODeviceTree:/arm-io/wdt for no-pmu and
        # otherwise crashes trying to set the PMU boot stage (customer builds
        # ignore the -wdt_no_pmu boot-arg).
        node('wdt', [ph(), ('no-pmu', u32(1))]),
        # Main display: IOMobileFramebuffer.framework counts /arm-io children
        # with this device_type and reads the canvas size from the node
        # (the presented iPhone X size, see SweetFramebuffer.cpp);
        # the kernel's AppleCLCD matches the compatible string.
        node('disp0', [
            ph(),
            ('device_type', cstr('display-subsystem')),
            ('compatible', cstr('sweet,display')),
            ('canvas-width', u32(canvas_w)),
            ('canvas-height', u32(canvas_h)),
        ])])

    fbcon = node('sweet-fbcon', [
        ph(),
        ('reg', u64(fb, fb_size)),
        ('width', u32(dev['fb_w'])),
        ('height', u32(dev['fb_h'])),
        ('stride', u32(dev['fb_stride'])),
    ])

    # bsd/dev/sweet_ufs.c: the UFS host ABL leaves running (absolute physical reg).
    ufs = node('sweet-ufs', [
        ph(),
        ('compatible', cstr('qcom,ufshc')),
        ('reg', u64(ufs, ufs_size)),
    ])

    # pmap_compute_max_asids requires the node even when no overrides are set.
    defaults = node('defaults', [ph(), ('no-effaceable-storage', u32(1))])

    # MobileGestalt HomeButtonType = IODeviceTree:/buttons home-button-type
    # (iPhone X / D22AP: 2, no Home button; absent = 0 = Home-button device).
    buttons = node('buttons', [
        ph(),
        ('button-names', cstr('volup') + cstr('voldown') + cstr('hold')),
        ('home-button-type', u32(2)),
        ('opposed-power-vol-buttons', u32(1)),
    ])

    product_props = base_product(base_adt or D22AP_ADT)
    product = [node('product', [ph()] + product_props)] if product_props else []

    # Identity of the iOS device whose userland runs here: compatible[0] is
    # hw.model/hw.target (the product type, e.g. D22AP), model is
    # hw.machine/hw.product (e.g. iPhone10,3). Both come from devices.py's
    # `ios` dict, so moving to an iOS 26-capable device is a one-line change.
    #
    # The built-in SweetPlatformExpert personality is IONameMatch 'xiaomi,sweet'
    # and IODTCompareNubName compares that key against the root's
    # name/compatible/device_type/model, so every board built from the SWEET
    # machine config must carry that exact string in /compatible - otherwise no
    # IOPlatformExpert matches and IOPanicPlatform panics with "Unable to find
    # driver for this platform". `platform_match` in devices.py supplies it;
    # board/soc strings follow for identification and live-FDT audits.
    platform_match = dev.get('platform_match', 'xiaomi,sweet')
    return node('device-tree', [
        ph(),
        ('compatible', cstr(product_type) + cstr(model) + cstr(platform_match) + cstr(dev['board_compat']) + cstr(dev['soc_compat']) + cstr('AppleARM')),
        ('model', cstr(model)),
        ('target-type', cstr(target_type)),
        ('target-sub-type', cstr(product_type)),
        ('manufacturer', cstr('Apple Inc.')),
        ('#address-cells', u32(2)),
        ('#size-cells', u32(2)),
    ], [chosen, defaults, cpus, arm_io, fbcon, buttons] + product + ([] if qemu else [ufs]))


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('out')
    ap.add_argument('--device', default='sweet', choices=sorted(devices.DEVICES),
                    help='hardware profile (tools/devices.py)')
    ap.add_argument('--qemu', action='store_true', help='QEMU virt GIC/CNTFRQ instead of the board')
    ap.add_argument('--highmem', action='store_true', help='kernel RAM from the upper DDR bank (phone default)')
    ap.add_argument('--dram-size', type=lambda s: int(s, 0), default=None,
                    help='override the kernel RAM size, e.g. 0x180000000 for an 8 GB guacamole')
    ap.add_argument('--owned-memory-size', type=lambda s: int(s, 0), default=None,
                    help='DarwinBoot contiguous window in bytes (256 MiB..8 GiB, 2 MiB steps)')
    ap.add_argument('--ios-product-type', default=None,
                    help='override the profile identity product type, e.g. D321AP')
    ap.add_argument('--ios-model', default=None,
                    help='override the profile identity model string, e.g. iPhone11,2')
    ap.add_argument('--ios-target-type', default=None,
                    help='override the target-type (default: product type without the AP suffix)')
    ap.add_argument('--ios-chip-id', type=lambda s: int(s, 0), default=None,
                    help='override the AES chip-id, e.g. 0x8020 for A12')
    ap.add_argument('--ios-canvas', default=None, metavar='WxH',
                    help='override the presented canvas, e.g. 828x1792')
    ap.add_argument('--ios-display-scale', type=int, default=None,
                    help='override /chosen display-scale (1|2|3)')
    ap.add_argument('--base-adt', default=None,
                    help='path to the fetched base device tree (default: the identity artifact)')
    ap.add_argument('--print-identity', action='store_true',
                    help='print the resolved iOS identity as JSON and exit')
    ap.add_argument('--dump', action='store_true')
    args = ap.parse_args()
    ios = {}
    for key, value in (('product_type', args.ios_product_type), ('model', args.ios_model),
                       ('target_type', args.ios_target_type), ('chip_id', args.ios_chip_id),
                       ('display_scale', args.ios_display_scale)):
        if value is not None:
            ios[key] = value
    if args.ios_canvas is not None:
        try:
            ios['canvas_width'], ios['canvas_height'] = (int(v, 0) for v in args.ios_canvas.lower().split('x'))
        except ValueError:
            raise SystemExit('--ios-canvas expects WxH, e.g. 828x1792')
    if args.print_identity:
        import json
        ident = devices.default_ios(args.device)
        ident.update(ios)
        print(json.dumps(ident, indent=2, sort_keys=True))
        sys.exit(0)
    if args.dump and os.path.exists(args.out):
        blob = open(args.out, 'rb').read()
        adt.dump(adt.parse(blob)[0])
        print(f'{args.out}: {len(blob)} bytes (existing file, not rebuilt)', file=sys.stderr)
        sys.exit(0)
    root = build(qemu=args.qemu, highmem=args.highmem, device=args.device,
                 dram_size=args.dram_size, owned_memory_size=args.owned_memory_size,
                 ios=ios, base_adt=args.base_adt)
    blob = adt.serialize(root)
    open(args.out, 'wb').write(blob)
    if args.dump:
        adt.dump(adt.parse(blob)[0])
    ident = devices.default_ios(args.device)
    ident.update(ios)
    print(f'{args.out}: {len(blob)} bytes ({args.device}, {ident["product_type"]}/{ident["model"]})',
          file=sys.stderr)
