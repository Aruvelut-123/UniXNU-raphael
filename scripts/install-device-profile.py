#!/usr/bin/env python3
"""Install this repository's OS profile into a UniXNU checkout.

UniXNU resolves board.os_profile as a directory under its own profiles/os/.
Upstream has no 18.x profile, so this board carries one at
os-profiles/<profile>/ and this script copies it in before resolving.

The step is idempotent: an identical file is left alone, a differing one stops
the run (so a profile edited in the checkout is never silently overwritten).

Usage:
    python3 scripts/install-device-profile.py --unixnu ../UniXNU
"""
import argparse
import json
import shutil
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def install_profile(unixnu, profile):
    source = ROOT / 'os-profiles' / profile
    if not source.is_dir():
        raise SystemExit(f'{source} missing: board.os_profile names a profile this repository must carry')
    target = unixnu / 'profiles/os' / profile
    copied = []
    for path in sorted(source.rglob('*')):
        if not path.is_file():
            continue
        destination = target / path.relative_to(source)
        if destination.exists() and destination.read_bytes() != path.read_bytes():
            raise SystemExit(f'{destination} differs from {path}; keep the profile in one place')
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            copied.append(str(destination.relative_to(unixnu)))
    return target, copied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unixnu', required=True, type=Path,
                        help='path to a UniXNU checkout (default: ../UniXNU)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    unixnu = args.unixnu.resolve()
    if not (unixnu / 'profiles/os').is_dir():
        raise SystemExit(f'{unixnu}/profiles/os missing: not a UniXNU checkout')
    board = tomllib.loads((ROOT / 'board.toml').read_text())
    profile = board['board']['os_profile']
    if args.dry_run:
        print(json.dumps({'profile': profile, 'would_install_at': str(unixnu / 'profiles/os' / profile)}, indent=2))
        return 0
    target, copied = install_profile(unixnu, profile)
    print(json.dumps({'profile': profile, 'installed_at': str(target),
                      'copied': copied or 'already present'}, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
