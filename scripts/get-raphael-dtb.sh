#!/usr/bin/env bash
# Fetch the SM8150 device tree for raphael.
#
# raphael is the SAME SM8150 SoC as guacamole (OnePlus 7 Pro) and nabu (Xiaomi
# Pad 5). For the first bring-up we reuse the SM8150 DTB that already ships in
# the Project Aloha UEFI tree (oneplus-guacamole/guacamole.dtb) -- the SoC is
# identical, so the memory map / MMIO ranges match. A raphael-specific DTB
# (extracted from the phone via TWRP, or from a LineageOS raphael boot.img)
# can later be dropped at inputs/uefi-prebuilt/raphael.dtb to override.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/inputs/uefi-prebuilt/raphael.dtb"
mkdir -p "$(dirname "$DEST")"

if [ -f "$DEST" ]; then echo "raphael.dtb already present"; exit 0; fi

# 1) Preferred: the SM8150 DTB shipped in the Project Aloha UEFI tree.
SRC="$ROOT/uefi/Platforms/SurfaceDuo1Pkg/Device/oneplus-guacamole/guacamole.dtb"
if [ -f "$SRC" ]; then
  cp "$SRC" "$DEST"
  echo "copied SM8150 DTB from Aloha UEFI tree -> $DEST"
  echo "(override later with a raphael-specific DTB extracted from the phone)"
  exit 0
fi

# 2) Fallback: extract from a LineageOS raphael boot.img if provided.
if [ -n "${RAPHAEL_BOOTIMG:-}" ] && [ -f "$RAPHAEL_BOOTIMG" ]; then
  pip install --quiet extract-dtb 2>/dev/null || true
  python3 - "$RAPHAEL_BOOTIMG" "$DEST" <<'PY'
import sys, os
try:
    from extract_dtb import extract_dtbs
except Exception as e:
    sys.exit("extract-dtb unavailable: " + str(e))
src, dst = sys.argv[1], sys.argv[2]
out = extract_dtbs(src)
best = max(out, key=lambda p: os.path.getsize(p))
os.replace(best, dst)
print("extracted", best, "->", dst)
PY
  exit 0
fi

echo "ERROR: could not locate a SM8150 DTB." >&2
echo "Options:" >&2
echo "  - let the workflow use the Aloha UEFI tree DTB (default), or" >&2
echo "  - set RAPHAEL_BOOTIMG=/path/to/lineage-raphael-boot.img, or" >&2
echo "  - drop a raphael DTB at $DEST" >&2
exit 1
