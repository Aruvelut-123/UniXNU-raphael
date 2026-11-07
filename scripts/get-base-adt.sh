#!/usr/bin/env bash
# Fetch the base Apple Device Tree (ADT) for the CONFIGURED iOS identity.
#
# The SWEET kernel boots an iOS userland whose MobileGestalt identity is taken
# from the real device tree of the iPhone the userland came from (its /product
# node).  That tree is an Apple artifact and is kept out of git; this script
# regenerates it automatically so the whole pipeline is push-button.
#
# Which iPhone -- and therefore which IPSW member -- is not hardcoded here any
# more.  The identity lives in scripts/devices.py's `ios` dict (product type,
# model, chip-id, canvas, ipsw_url, dt_member), and this script reads it from
# there so the IPSW URL and the DeviceTree member name can only be changed in
# one place.  Pass --device to pick a different hardware profile.
#
# Historical note: this script used to be get-base-d22ap.sh and always fetched
# the iPhone X (D22AP / iPhone10,3) tree out of the 16.7.16 IPSW.  The iPhone X
# cannot run iOS 26 (it tops out at 16.7.16), so the identity had to become a
# parameter.  get-base-d22ap.sh is kept as a deprecated wrapper.
#
# The member is an IM4P-wrapped, lzfse-compressed Apple Device Tree.  We fetch
# just that member (HTTP range requests, no full multi-GB download), unwrap the
# IM4P, lzfse-decompress and write the raw ADT that mkadt.py reads.
#
# Output: the profile identity's `base_adt` filename, in scripts/ (consumed by
# scripts/mkadt.py).
#
# Overrides (any one short-circuits the download):
#   BASE_ADT=/path/to/file : use a file you already have
#   BASE_D22AP_ADT=...     : legacy spelling of BASE_ADT
#   BASE_ADT_IPSW_URL=...  : use a different IPSW
#   BASE_D22AP_IPSW_URL=.. : legacy spelling of BASE_ADT_IPSW_URL
#   --ipsw-url / --dt-member / --out / --device
#   drop the output file in scripts/ by hand (the script skips if present)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEVICE="${BASE_ADT_DEVICE:-raphael}"
IPSW_URL_OPT=""
DT_MEMBER_OPT=""
OUT_OPT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --device)    DEVICE="${2:?--device needs a value}"; shift 2 ;;
    --ipsw-url)  IPSW_URL_OPT="${2:?--ipsw-url needs a value}"; shift 2 ;;
    --dt-member) DT_MEMBER_OPT="${2:?--dt-member needs a value}"; shift 2 ;;
    --out)       OUT_OPT="${2:?--out needs a value}"; shift 2 ;;
    -h|--help)   sed -n '2,32p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# --- Resolve the identity from devices.py (single source of truth) ----------
# Import it as a module (not by path surgery) so we get the same values mkadt.py
# uses, including the fallback identity for profiles that carry no `ios` dict.
IDENT_JSON="$(cd "$ROOT/scripts" && python3 - "$DEVICE" <<'PY'
import json, sys
sys.path.insert(0, '.')
import devices
print(json.dumps(devices.default_ios(sys.argv[1])))
PY
)"
read_ident() { python3 -c "import json,sys;print(json.loads(sys.argv[1]).get(sys.argv[2],''))" "$IDENT_JSON" "$1"; }
PRODUCT_TYPE="$(read_ident product_type)"
MODEL="$(read_ident model)"
DT_MEMBER="${DT_MEMBER_OPT:-$(read_ident dt_member)}"
IPSW_URL="${IPSW_URL_OPT:-${BASE_ADT_IPSW_URL:-${BASE_D22AP_IPSW_URL:-$(read_ident ipsw_url)}}}"
UNVERIFIED="$(read_ident unverified)"
# Filename: the profile identity's own name when it is a concrete device,
# otherwise the generic one.  mkadt.py looks for base-<lowercase model>.adt.
DEFAULT_OUT="$ROOT/scripts/base-adt.adt"
if [ -n "$MODEL" ] && [ "${MODEL#<}" = "$MODEL" ]; then
  DEFAULT_OUT="$ROOT/scripts/base-$(printf '%s' "$MODEL" | tr 'A-Z,,' 'a-z--').adt"
fi
DEST="${OUT_OPT:-$DEFAULT_OUT}"
mkdir -p "$(dirname "$DEST")"

if [ -s "$DEST" ]; then
  echo "$(basename "$DEST") already present ($DEST); skipping fetch"
  exit 0
fi

PROVIDED="${BASE_ADT:-${BASE_D22AP_ADT:-}}"
if [ -n "$PROVIDED" ] && [ -s "$PROVIDED" ]; then
  cp "$PROVIDED" "$DEST"
  echo "copied provided base ADT -> $DEST"
  exit 0
fi

for v in "$PRODUCT_TYPE" "$MODEL" "$DT_MEMBER" "$IPSW_URL"; do
  case "$v" in
    ''|'<'*)
      echo "ERROR: the '$DEVICE' identity is not configured (got '$v')." >&2
      echo "Set the 'ios' dict in scripts/devices.py (or pass --ipsw-url/--dt-member)." >&2
      exit 1
      ;;
  esac
done
if [ "$UNVERIFIED" = "True" ] || [ "$UNVERIFIED" = "true" ]; then
  echo "WARNING: the '$DEVICE' iOS identity is marked unverified in scripts/devices.py;" >&2
  echo "         product=$PRODUCT_TYPE model=$MODEL member=$DT_MEMBER" >&2
fi

echo "Fetching base ADT for $PRODUCT_TYPE ($MODEL) from IPSW (single member):"
echo "  $IPSW_URL"
echo "  member: $DT_MEMBER"
echo "  output: $DEST"

# Make sure the pure-Python deps are present (idempotent; CI starts clean).
python3 -m pip install --quiet --disable-pip-version-check remotezip lzfse 2>/dev/null \
  || pip install --quiet --disable-pip-version-check remotezip lzfse 2>/dev/null \
  || true

# --- Primary path: pure-Python (remotezip + lzfse). No external binary, works
#     identically on macOS / Linux / Windows CI runners. ---
python3 - "$IPSW_URL" "$DT_MEMBER" "$DEST" <<'PY'
import sys, struct, os

url, member, dest = sys.argv[1], sys.argv[2], sys.argv[3]

# Decompress lzfse if available; otherwise fall back to the `ipsw` CLI below.
try:
    import lzfse  # noqa
except Exception:
    sys.exit(10)  # signal: lzfse missing, let the shell fall back to `ipsw`

try:
    from remotezip import RemoteZip
except Exception as e:
    sys.exit("remotezip unavailable: %s" % e)

def der(buf, off):
    tag = buf[off]; ln = buf[off + 1]; off += 2
    if ln & 0x80:
        n = ln & 0x7f
        ln = int.from_bytes(buf[off:off + n], 'big'); off += n
    return tag, off, off + ln

def im4p_payload(buf):
    tag, s, e = der(buf, 0)
    assert tag == 0x30, 'not a DER sequence (not IM4P)'
    items, off = [], s
    while off < e:
        t, vs, ve = der(buf, off); items.append(buf[vs:ve]); off = ve
    assert items[0] == b'IM4P', 'missing IM4P marker'
    return items[3]

with RemoteZip(url) as rz:
    data = rz.read(member)

payload = im4p_payload(data)
if payload[:4] == b'bvx2':
    payload = lzfse.decompress(payload)

# Sanity: ADT starts with little-endian {u32 nprops, u32 nchildren}.
nprops, nchildren = struct.unpack_from('<II', payload, 0)
assert 0 < nprops < 2000 and 0 <= nchildren < 2000, 'unexpected ADT header'

with open(dest, 'wb') as f:
    f.write(payload)
print("wrote %s (%d bytes, nprops=%d nchildren=%d)" % (dest, len(payload), nprops, nchildren))
PY
rc=$?
if [ "$rc" -eq 0 ]; then
  echo "DONE: $DEST"
  exit 0
fi
if [ "$rc" -ne 10 ]; then
  echo "python fetch failed (rc=$rc); falling back to ipsw CLI" >&2
fi

# --- Fallback path: the `ipsw` CLI (blacktop/ipsw) if present. ---
if command -v ipsw >/dev/null 2>&1; then
  echo "using ipsw CLI fallback"
  TMP="$(mktemp -d)"
  python3 - "$IPSW_URL" "$DT_MEMBER" "$TMP" <<'PY'
import sys, os
from remotezip import RemoteZip
url, member, d = sys.argv[1], sys.argv[2], sys.argv[3]
with RemoteZip(url) as rz:
    data = rz.read(member)
open(os.path.join(d, os.path.basename(member)), "wb").write(data)
PY
  BLOB="$TMP/$(basename "$DT_MEMBER")"
  if ! ipsw img4 im4p extract "$BLOB" -o "$DEST"; then
    echo "ipsw im4p extract failed; retrying with the generic img4 extract" >&2
    ipsw img4 extract "$BLOB" -o "$DEST"
  fi
  rm -rf "$TMP"
  echo "DONE (ipsw): $DEST"
  exit 0
fi

echo "ERROR: could not fetch $(basename "$DEST")." >&2
echo "Install deps with:  pip install remotezip lzfse" >&2
echo "or provide one:     BASE_ADT=/path/to/base.adt bash scripts/get-base-adt.sh" >&2
exit 1
