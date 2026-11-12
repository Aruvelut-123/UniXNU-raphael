#!/usr/bin/env python3
"""Stage the arm64 kernelcache this board prelinks against.

The profile's [ipsw] is the iOS 18.7.12 restore (the payload). iOS 18's lowest
device is the A12 iPhone XS, so its kernelcache is arm64e and cannot run on
SM8150. The arm64 kernelcache therefore comes from the iPadOS 18.7.12 restore of
iPad7,11 (j171ap / A10 / no PAC), the same build and Darwin version.

UniXNU's own ipsw.kernelcache() would write it to out/ipsw/22H390/, which is the
same path the iOS IPSW resolves to -- the two archives would overwrite each
other. This script writes to the dedicated path named by
[kernel.prelink] kernelcache instead.

It reuses UniXNU's own machinery: RangeFile for the HTTP zip, im4p_payload for
the IM4P wrapper, and lzfse() for the LZFSE blob. The result is the raw arm64
kernelcache Mach-O, exactly what the prelinker expects.

Usage:
    python3 scripts/stage-arm64-kernelcache.py --unixnu ../UniXNU
    python3 scripts/stage-arm64-kernelcache.py --unixnu ../UniXNU --ipsw /path/to/ipados18.ipsw
"""
import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The arm64 reference: iPadOS 18.7.12 for iPad 7 (WiFi). Same 22H390 / Darwin
# 24.6.0 as the iOS payload, so the kernel and the root stay build-identical.
IPADOS_IPSW = 'https://updates.cdn-apple.com/2026WinterFCS/97c69315-c496-45a3-9112-dca545d5188f/iPad_10.2_18.7.12_22H390_Restore.ipsw'
IPADOS = {'product': 'iPad7,11', 'version': '18.7.12', 'build': '22H390',
          'device_class': 'j171ap', 'chip_id': 32784, 'board_id': 28}
# kernelcache.release.ipad7c -- the arm64 kernelcache, not the arm64e one.
MEMBER = 'kernelcache.release.ipad7c'


def load_unixnu(unixnu):
    """Import UniXNU's ipsw/util modules from the checkout, not from this repository."""
    sys.path.insert(0, str(unixnu / 'scripts'))
    from unixnu import ipsw as ipsw_module          # noqa: E402
    from unixnu.util import Error, log, lzfse       # noqa: E402
    return ipsw_module, Error, log, lzfse


def decoder(lzfse):
    """The LZFSE decoder: macOS /usr/bin/compression_tool, else Apple's reference lzfse tool."""
    if sys.platform == 'darwin':
        return ['/usr/bin/compression_tool', '-decode', '-a', 'lzfse']
    return [lzfse(), '-decode']


def decompress(ipsw_module, Error, log, lzfse, spec, destination, record_path):
    """Fetch the IM4P, strip the wrapper, decode the LZFSE blob, keep the arm64 slice."""
    config = dict(IPADOS, url=spec, fetch=['KernelCache'])

    class FakeCtx:
        pass

    ctx = FakeCtx()
    ctx.board = {'ipsw': config}
    ctx.out_root = destination.parent.parent.parent   # out/<device>/../.. ; only used for caching

    source = ipsw_module.Ipsw(ctx, spec)
    payload = ipsw_module.im4p_payload(source.read('KernelCache'))
    log(f'kernelcache: {MEMBER}, {len(payload) >> 20} MiB IM4P payload')
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.kc-') as work:
        workdir = Path(work)
        packed = workdir / 'kernelcache.lzfse'
        raw = workdir / 'kernelcache.fat'
        packed.write_bytes(payload)
        tool = decoder(lzfse)
        result = subprocess.run([*tool, '-i', str(packed), '-o', str(raw)], capture_output=True, text=True)
        if result.returncode:
            raise Error(f'{Path(tool[0]).name} failed: {result.stderr.strip()[-300:]}')
        fat = raw.read_bytes()
    if fat[:4] == b'\xca\xfe\xba\xbe':
        count = struct.unpack('>I', fat[4:8])[0]
        slices = [struct.unpack('>5I', fat[8 + 20 * i:28 + 20 * i]) for i in range(count)]
        arm64 = [s for s in slices if s[0] == 0x0100000c]
        if len(arm64) != 1:
            raise Error(f'expected exactly one arm64 slice in {MEMBER}, found {len(arm64)}')
        _, _, offset, size, _ = arm64[0]
        fat = fat[offset:offset + size]
    if fat[:4] != b'\xcf\xfa\xed\xfe':
        raise Error(f'{MEMBER} is not a 64-bit Mach-O after decode')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(fat)
    digest = hashlib.sha256(fat).hexdigest()
    record_path.write_text(json.dumps({'member': MEMBER, 'source': spec, 'bytes': len(fat),
                                       'sha256': digest}, indent=2) + '\n')
    log(f'kernelcache: {destination} sha256 {digest}')
    return digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unixnu', required=True, type=Path)
    parser.add_argument('--ipsw', default=IPADOS_IPSW,
                        help='iPadOS 18.7.12 IPSW (URL or local path) that carries the arm64 kernelcache')
    parser.add_argument('--force', action='store_true', help='rebuild even when the staged file is present')
    args = parser.parse_args()
    unixnu = args.unixnu.resolve()
    profile_path = unixnu / 'profiles/os' / tomllib.loads((ROOT / 'board.toml').read_text())['board']['os_profile'] / 'profile.toml'
    profile = tomllib.loads(profile_path.read_text())
    spec = profile['kernel']['prelink']
    relative = spec['kernelcache']
    # The prelinker resolves a relative kernelcache against the working directory of
    # the step, which is the UniXNU checkout.
    destination = (unixnu / relative).resolve()
    record = destination.with_suffix(destination.suffix + '.json')
    if not args.force and destination.is_file() and record.is_file():
        print(json.dumps({'present': True, 'kernelcache': str(destination),
                          'sha256': json.loads(record.read_text()).get('sha256')}, indent=2))
        return 0
    ipsw_module, Error, log, lzfse = load_unixnu(unixnu)
    digest = decompress(ipsw_module, Error, log, lzfse, args.ipsw, destination, record)
    print(json.dumps({'staged': True, 'kernelcache': str(destination), 'sha256': digest}, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())