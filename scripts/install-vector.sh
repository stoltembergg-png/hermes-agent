#!/usr/bin/env bash
# Compatibility wrapper. The universal implementation lives in install-vector.py.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/install-vector.py" "$@"
