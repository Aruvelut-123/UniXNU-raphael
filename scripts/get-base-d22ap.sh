#!/usr/bin/env bash
# DEPRECATED: thin wrapper kept so existing workflow lines and local habits
# keep working.  The real script is scripts/get-base-adt.sh, which fetches the
# base ADT for whatever iOS identity scripts/devices.py configures (it used to
# be hardwired to the iPhone X / D22AP here).
#
# All arguments and environment variables are forwarded, including the legacy
# BASE_D22AP_ADT / BASE_D22AP_IPSW_URL spellings.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "note: get-base-d22ap.sh is deprecated; use get-base-adt.sh (forwarding)" >&2
exec bash "$HERE/get-base-adt.sh" "$@"
