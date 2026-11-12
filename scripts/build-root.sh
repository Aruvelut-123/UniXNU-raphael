#!/bin/bash
# Build the root (userdata) image and flash it to the preferred partition.
#
# Preference: dedicated `unixnu` partition, falling back to `userdata`.
# UniXNU itself selects root by APFS Volume UUID, so the choice is made here,
# at flash time. See docs/root-partition.md.
#
# Usage:
#   scripts/build-root.sh --ipsw restore.ipsw --dry-run
#   scripts/build-root.sh --ipsw restore.ipsw --flash
#
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
UNIXNU_DIR="${UNIXNU_DIR:-$REPO_ROOT/../UniXNU}"

IPSW=""
DO_FLASH=0
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --ipsw)     IPSW="$2"; shift 2 ;;
    --flash)    DO_FLASH=1; shift ;;
    --dry-run)  DRY_RUN=1; shift ;;
    -h|--help)
      sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ ! -d "$UNIXNU_DIR" ]; then
  echo "UniXNU checkout not found at $UNIXNU_DIR (set UNIXNU_DIR)" >&2
  exit 1
fi

# --- pick the target partition ------------------------------------------------
TARGET_LABEL=""
TARGET_DEV=""

for candidate in unixnu userdata; do
  for link in "/dev/disk/by-partlabel/$candidate" "/dev/block/by-name/$candidate"; do
    if [ -e "$link" ]; then
      TARGET_LABEL="$candidate"
      TARGET_DEV="$(readlink -f "$link" 2>/dev/null || printf '%s' "$link")"
      break 2
    fi
  done
done

if [ -z "$TARGET_LABEL" ]; then
  echo "warning: neither 'unixnu' nor 'userdata' partition found on this host." >&2
  echo "         Expected when building on a PC rather than on the phone." >&2
  TARGET_LABEL="userdata"
  TARGET_DEV="<device-not-present>"
else
  echo "root target: $TARGET_LABEL ($TARGET_DEV)"
fi

# --- build the root image -----------------------------------------------------
BUILD_ARGS=()
[ -n "$IPSW" ] && BUILD_ARGS+=(--ipsw "$IPSW")
[ "$DRY_RUN" -eq 1 ] && BUILD_ARGS+=(--dry-run)

echo ">>> unixnu build userdata ${BUILD_ARGS[*]:-}"
( cd "$UNIXNU_DIR" && ./unixnu build userdata -D "$REPO_ROOT" "${BUILD_ARGS[@]:-}" )

# ctx.work is out/<board name> (config.py:146), and userdata.py:paths() puts the
# image under <work>/userdata. The OS profile does not appear in the path.
BOARD_NAME=$(sed -n 's/^[[:space:]]*name[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$REPO_ROOT/board.toml" | head -1)
if [ -z "$BOARD_NAME" ]; then
  echo "error: no [board] name in $REPO_ROOT/board.toml" >&2
  exit 1
fi
REPORT="$UNIXNU_DIR/out/$BOARD_NAME/userdata/userdata-root.json"
IMAGE="$UNIXNU_DIR/out/$BOARD_NAME/userdata/userdata-root.img"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry run complete; no image written"
  exit 0
fi

if [ ! -f "$IMAGE" ]; then
  echo "error: expected image at $IMAGE" >&2
  exit 1
fi

ls -lh "$IMAGE"
[ -f "$REPORT" ] && echo "report: $REPORT"

# --- optionally flash ---------------------------------------------------------
if [ "$DO_FLASH" -eq 1 ]; then
  if [ "$TARGET_DEV" = "<device-not-present>" ]; then
    echo "error: --flash requested but no target partition is visible" >&2
    exit 1
  fi
  echo ">>> fastboot flash $TARGET_LABEL $IMAGE"
  fastboot flash "$TARGET_LABEL" "$IMAGE"
  fastboot reboot bootloader
else
  echo
  echo "not flashing. To flash manually:"
  echo "  fastboot flash $TARGET_LABEL $IMAGE"
fi