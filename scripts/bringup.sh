#!/usr/bin/env bash
# Flash the iOS root and boot it, in one go.
#
#   bringup.sh [--image TEST_Y.img] [--work-dir DIR] [--no-flash]
#
# The phone must already be in fastboot mode (Power + Volume Down).
#
# Why the pieces: Google's fastboot.exe for Windows is 32-bit and mmaps the
# whole file, so a 12 GiB image dies with std::bad_alloc.  The pieces are
# each under 1.5 GiB and carry a leading DONT_CARE chunk that states the
# absolute block they belong at, so the bootloader places them correctly.
# They are flashed in DESCENDING order, which is also the only order that
# stays correct if a bootloader ever materialised DONT_CARE as zeros.
#
# The HFS+ volume goes to the very start of the userdata partition: the
# kernel mounts the partition itself as the root filesystem, and the
# persistent console log lives in the last 4 MiB of the same partition.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

IMAGE="${IMAGE:-D:/raphael-ios/boot/TEST_Y.img}"
WORK_DIR="${WORK_DIR:-D:/raphael-ios/out}"
FLASH=1

while [ $# -gt 0 ]; do
  case "$1" in
    --image)    IMAGE="$2"; shift 2 ;;
    --work-dir) WORK_DIR="$2"; shift 2 ;;
    --no-flash) FLASH=0; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

FASTBOOT="${FASTBOOT:-}"
if [ -z "$FASTBOOT" ]; then
  for c in fastboot ./fastboot.exe ../tools/platform-tools/fastboot.exe; do
    if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then FASTBOOT="$c"; break; fi
  done
fi
[ -n "$FASTBOOT" ] || { echo "fastboot not found; set FASTBOOT=" >&2; exit 1; }

echo "== fastboot: $FASTBOOT"
DEVS="$("$FASTBOOT" devices 2>&1)"
echo "$DEVS"
if [ -z "$DEVS" ]; then
  echo
  echo "!! No device in fastboot mode." >&2
  echo "!! Hold Power + Volume Down on the phone, then release Power." >&2
  exit 1
fi
echo
echo "== image: $IMAGE"
echo "== work dir: $WORK_DIR"
echo

if [ "$FLASH" = "1" ]; then
  echo "== verifying the pieces =="
  python3 "$ROOT/scripts/verify_pieces.py" "$WORK_DIR/ios16-root.simg" "$WORK_DIR/pieces"

  echo
  echo "== flashing userdata, descending =="
  for p in $(ls "$WORK_DIR"/pieces/p*.simg | sort -r); do
    echo "-- $p"
    "$FASTBOOT" flash userdata "$p"
  done
  echo
  echo "== userdata done =="
else
  echo "== skipping the flash (--no-flash) =="
fi

echo
echo "== booting $IMAGE =="
"$FASTBOOT" boot "$IMAGE"
echo
echo "== watch the screen =="
echo "   === SWEET t=Ns exec=N crash=N sb=N/N fb=N sw=N dn=N m=N ==="
echo "   sw= is the number of frames that actually reached the panel."
echo "   A non-zero sw= means the GUI owns the screen and the panel stops"
echo "   painting, so the console text disappears on its own."
