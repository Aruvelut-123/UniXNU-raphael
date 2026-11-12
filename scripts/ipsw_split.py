#!/usr/bin/env python3
"""Split a large image into release-sized parts, and rejoin them.

GitHub Releases reject any single asset of 2 GiB or more:

    Validation Failed: {"resource":"ReleaseAsset","field":"size",
    "message":"size must be less than 2147483648"}

The raphael root images are 7.85 GiB, so a Release can only carry them as
parts. Artifacts (actions/upload-artifact) have a higher ceiling and are
uploaded whole as well, but they need a GitHub account to fetch; the parts are
what makes the image anonymously downloadable.

Splitting is byte-exact and order-sensitive: `join` concatenates the parts in
the order the manifest lists them, nothing more. The first line of the manifest
is the sha256 of the whole image, so a damaged or reordered download is caught
before it reaches fastboot.

    split:  ipsw_split.py split --input IMG --output-dir DIR [--part-size BYTES]
    join:   ipsw_split.py join  --manifest DIR/IMG.parts.json --output IMG

--part-size defaults to 1900 MiB, below the 2 GiB limit with room for the
multipart wrapper's own bytes. GitHub's documented cap is "less than 2147483648"
(2 GiB) for release assets; 1900 MiB leaves 148 MiB of headroom.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

MIB = 1 << 20
DEFAULT_PART_SIZE = 1900 * MIB
CHUNK = 8 * MIB


def sha256_file(path, limit=None):
    digest = hashlib.sha256()
    done = 0
    with open(path, 'rb') as handle:
        while True:
            want = CHUNK if limit is None else min(CHUNK, limit - done)
            if want <= 0:
                break
            data = handle.read(want)
            if not data:
                break
            digest.update(data)
            done += len(data)
    return digest.hexdigest()


def split(input_path, output_dir, part_size):
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    if not input_path.is_file():
        raise SystemExit(f'no such file: {input_path}')
    total = input_path.stat().st_size
    if part_size <= 0:
        raise SystemExit('--part-size must be positive')
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = input_path.name
    # 3 digits fit 100-999 parts; a 7.85 GiB image at 1900 MiB is 5 parts.
    parts = []
    written = 0
    # The image's own digest first, so the manifest states what the parts rebuild.
    print(f'image : {input_path} ({total} bytes)')
    print(f'image sha256: {sha256_file(input_path)}')

    with input_path.open('rb') as src:
        index = 1
        while written < total:
            remaining = total - written
            take = min(part_size, remaining)
            name = f'{stem}.part{index:03d}'
            target = output_dir / name
            digest = hashlib.sha256()
            produced = 0
            with target.open('wb') as dst:
                while produced < take:
                    data = src.read(min(CHUNK, take - produced))
                    if not data:
                        raise SystemExit(f'short read from {input_path} at {written + produced}')
                    dst.write(data)
                    digest.update(data)
                    produced += len(data)
            parts.append({'name': name, 'bytes': produced, 'sha256': digest.hexdigest()})
            print(f'  {name}  {produced} bytes  sha256 {digest.hexdigest()}')
            written += produced
            index += 1

    if written != total:
        raise SystemExit(f'wrote {written} bytes, expected {total}')

    manifest = {
        'file': stem,
        'bytes': total,
        'sha256': sha256_file(input_path),
        'part_size': part_size,
        'parts': parts,
        'join_command': f'cat {" ".join(p["name"] for p in parts)} > {stem}',
        'verify_command': f'sha256sum {stem}   # must print the sha256 above',
    }
    manifest_path = output_dir / f'{stem}.parts.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'manifest: {manifest_path}')
    print(f'{len(parts)} parts, largest {max(p["bytes"] for p in parts)} bytes '
          f'(must stay under 2147483648)')
    if max(p['bytes'] for p in parts) >= 2147483648:
        raise SystemExit('a part is at or over the 2 GiB release-asset limit')
    return 0


def join(manifest_path, output):
    manifest_path = Path(manifest_path)
    if not manifest_path.is_file():
        raise SystemExit(f'no such manifest: {manifest_path}')
    manifest = json.loads(manifest_path.read_text())
    base = manifest_path.parent
    output = Path(output)
    digest = hashlib.sha256()
    written = 0
    with output.open('wb') as dst:
        for part in manifest['parts']:
            path = base / part['name']
            if not path.is_file():
                raise SystemExit(f'missing part: {path}')
            if path.stat().st_size != part['bytes']:
                raise SystemExit(f'{path}: size {path.stat().st_size}, manifest says {part["bytes"]}')
            part_digest = hashlib.sha256()
            with path.open('rb') as src:
                while True:
                    data = src.read(CHUNK)
                    if not data:
                        break
                    dst.write(data)
                    digest.update(data)
                    part_digest.update(data)
                    written += len(data)
            if part_digest.hexdigest() != part['sha256']:
                raise SystemExit(f'{path}: sha256 does not match the manifest')
    if written != manifest['bytes']:
        raise SystemExit(f'wrote {written} bytes, manifest says {manifest["bytes"]}')
    if digest.hexdigest() != manifest['sha256']:
        raise SystemExit('the joined image does not match sha256 of the original')
    print(f'{output}: {written} bytes, sha256 matches the manifest')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)
    s = sub.add_parser('split', help='split an image into release-sized parts')
    s.add_argument('--input', type=Path, required=True)
    s.add_argument('--output-dir', type=Path, required=True)
    s.add_argument('--part-size', type=int, default=DEFAULT_PART_SIZE)
    j = sub.add_parser('join', help='rejoin the parts listed in a manifest')
    j.add_argument('--manifest', type=Path, required=True)
    j.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'split':
        return split(args.input, args.output_dir, args.part_size)
    return join(args.manifest, args.output)


if __name__ == '__main__':
    sys.exit(main())
