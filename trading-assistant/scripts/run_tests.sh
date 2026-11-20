#!/usr/bin/env bash
# Run the full pytest suite inside .venv (creating it if necessary).
#
# Usage:
#     scripts/run_tests.sh              # quiet summary
#     scripts/run_tests.sh -v           # any extra args go straight to pytest
#     scripts/run_tests.sh tests/test_backtest.py -k hand_worked

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_venv.sh"
cd "$PROJECT_ROOT"

if [ "$#" -eq 0 ]; then
    set -- -q
fi
exec "$VENV_PY" -m pytest -p no:cacheprovider "$@"
