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
# The build prints "== userdata: <path>" as its last word on the image; capture
# it instead of guessing the path. ctx.work is out/<board>/<os profile>/<config>
# (config.py:146-164), and <config> comes from the selected defconfig, so the
# path cannot be reconstructed from board.toml alone.
BUILD_LOG="$(mktemp)"
build_status=0
( cd "$UNIXNU_DIR" && ./unixnu build userdata -D "$REPO_ROOT" ${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"} ) > "$BUILD_LOG" 2>&1 \
  || build_status=$?

if [ "$build_status" -ne 0 ]; then
  cat "$BUILD_LOG" >&2
  echo "error: unixnu build userdata failed with status $build_status" >&2
  rm -f "$BUILD_LOG"
  exit 1
fi
cat "$BUILD_LOG"

if [ "$DRY_RUN" -eq 1 ]; then
  rm -f "$BUILD_LOG"
  echo "dry run complete; no image written"
  exit 0
fi

# Resolve the image path from the build's own report, never by guessing.
# ctx.work = out/<board>/<os profile>/<config> (config.py:146-164), where
# <config> is the selected defconfig minus its suffix, so the path cannot be
# reconstructed from board.toml.
# util.log() prefixes every line with "== ".
IMAGE="$(sed -n 's/^== userdata: \(.*userdata-root\.img\)$/\1/p' "$BUILD_LOG" | tail -1)"
REPORT="$(dirname "${IMAGE:-.}")/userdata-root.json"

if [ -z "$IMAGE" ] || [ ! -f "$IMAGE" ]; then
  # Second source: the flash command the build prints for the user.
  IMAGE="$(sed -n 's/^== flash it yourself with: fastboot flash userdata \(.*\)$/\1/p' "$BUILD_LOG" | tail -1)"
fi

if [ -z "$IMAGE" ] || [ ! -f "$IMAGE" ]; then
  # Last resort, in case the log wording changes.
  IMAGE="$(find "$UNIXNU_DIR/out" -name 'userdata-root.img' -newer "$REPO_ROOT/board.toml" 2>/dev/null | head -1)"
fi

if [ -z "$IMAGE" ] || [ ! -f "$IMAGE" ]; then
  echo "error: could not locate the built userdata-root.img" >&2
  echo "--- build log tail ---" >&2
  tail -40 "$BUILD_LOG" >&2
  rm -f "$BUILD_LOG"
  exit 1
fi

rm -f "$BUILD_LOG"

IMAGE="$(cd "$(dirname "$IMAGE")" && pwd)/$(basename "$IMAGE")"
echo "image: $IMAGE"
ls -lh "$IMAGE"
[ -n "$REPORT" ] && [ -f "$REPORT" ] && echo "report: $REPORT"

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