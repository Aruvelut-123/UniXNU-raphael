#!/usr/bin/env bash
# Flash the iOS 16.7.16 HFS+ root to the raphael userdata partition.
#
#   flash-root.sh [--parts-dir DIR] [--work-dir DIR] [--dry-run]
#
# Steps: assemble the published parts -> verify sha256 + HFS+ header ->
# split into ABL-safe pieces -> flash them to userdata in DESCENDING order.
#
# The SM8150 ABL has two quirks this script works around:
#   * its sparse chunk header is "u16 type, u16 res, u32 blocks, u32 bytes"
#     (the opposite of the AOSP/libsparse order), and
#   * DONT_CARE is a seek, not a write of zeros.
# See scripts/split_for_abl.py.
set -euo pipefail

REPO="JohnLeeeeeee678/UniXNU-raphael"
TAG="${TAG:-iosroot-16.7.16-20261031-141135}"

PARTS_DIR=""
WORK_DIR="raphael-root"
DRY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --parts-dir) PARTS_DIR="$2"; shift 2 ;;
    --work-dir)  WORK_DIR="$2";  shift 2 ;;
    --dry-run)   DRY=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$(cd "$HERE/.." && pwd)/scripts"
[ -d "$SCRIPTS" ] || SCRIPTS="$HERE"

FASTBOOT="${FASTBOOT:-fastboot}"
command -v "$FASTBOOT" >/dev/null 2>&1 || FASTBOOT="./fastboot.exe"

if [ -z "$PARTS_DIR" ]; then
  PARTS_DIR="$WORK_DIR/parts"
  mkdir -p "$PARTS_DIR"
  echo "== downloading $TAG =="
  for i in 00 01 02 03 04 05 06; do
    f="$PARTS_DIR/root-part.$i"
    if [ ! -s "$f" ]; then
      echo "  root-part.$i"
      gh release download "$TAG" -R "$REPO" -p "root-part.$i" -D "$PARTS_DIR"
    fi
  done
  for extra in root-parts.sha256 ios16-root.simg.sha256; do
    [ -s "$PARTS_DIR/$extra" ] || gh release download "$TAG" -R "$REPO" \
      -p "$extra" -D "$PARTS_DIR"
  done
fi

echo "== assembling =="
python3 "$SCRIPTS/assemble_hfsroot.py" "$PARTS_DIR" -o "$WORK_DIR/ios16-root.simg" \
  --expect-sha "$PARTS_DIR/ios16-root.simg.sha256"

echo "== splitting =="
python3 "$SCRIPTS/split_for_abl.py" "$WORK_DIR/ios16-root.simg" -o "$WORK_DIR/pieces"

echo "== verifying the pieces =="
python3 "$SCRIPTS/verify_pieces.py" "$WORK_DIR/ios16-root.simg" "$WORK_DIR/pieces"

if [ "$DRY" = "1" ]; then
  echo "== dry run: not flashing =="
  cat "$WORK_DIR/pieces/ORDER.txt"
  exit 0
fi

echo "== waiting for the phone in fastboot mode =="
"$FASTBOOT" devices

echo "== flashing userdata (descending order) =="
for p in $(ls "$WORK_DIR"/pieces/p*.simg | sort -r); do
  echo "-- $p"
  "$FASTBOOT" flash userdata "$p"
done

echo "== done: reboot and boot the image =="
"$FASTBOOT" reboot
