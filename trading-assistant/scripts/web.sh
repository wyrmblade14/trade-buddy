#!/usr/bin/env bash
# Start the local backtest page (creates .venv first if needed).
#
# Usage:
#     scripts/web.sh                 # http://localhost:8765/ (or the next free port)
#     scripts/web.sh --port 9000     # any trading_assistant.web option is passed through
#     scripts/web.sh --verbose
#
# Stop it with Ctrl+C.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_venv.sh"
cd "$PROJECT_ROOT"
exec "$VENV_PY" -m trading_assistant.web "$@"
