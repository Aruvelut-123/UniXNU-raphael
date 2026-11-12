#!/bin/bash
# Local build script for UniXNU-raphael
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
UNIXNU_DIR="${UNIXNU_DIR:-$REPO_ROOT/../UniXNU}"
UEFI_DIR="${UEFI_DIR:-$REPO_ROOT/../uefi-raphael}"

echo "=== UniXNU raphael build ==="
echo "Repo: $REPO_ROOT"
echo "UniXNU: $UNIXNU_DIR"
echo "UEFI: $UEFI_DIR"

cd "$UNIXNU_DIR"

echo ">>> defconfig"
./unixnu defconfig raphael_defconfig -D "$REPO_ROOT"

echo ">>> fetch"
./unixnu fetch

echo ">>> status"
./unixnu status --json

echo ">>> kernel"
./unixnu kernel -D "$REPO_ROOT"

echo ">>> package"
./unixnu package -D "$REPO_ROOT"

if [ -d "$UEFI_DIR" ]; then
  echo ">>> firmware"
  ./unixnu build firmware -D "$REPO_ROOT" --uefi "$UEFI_DIR"
fi

echo ">>> bootimg"
./unixnu bootimg -D "$REPO_ROOT"

echo "=== Build complete ==="
find out -name "UniXNU.efi" -o -name "boot.img" -o -name "kernel.macho"
