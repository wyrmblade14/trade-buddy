#!/usr/bin/env bash
# Create .venv and install the project in editable mode with dev extras.
#
# Usage (from anywhere):
#     scripts/setup_dev.sh                    # uses python3 (or python) from PATH
#     PYTHON=python3.11 scripts/setup_dev.sh  # pick a specific interpreter
#
# Safe to re-run: an existing .venv is reused, packages are upgraded in place.
# Afterwards:
#     scripts/run_tests.sh        # full test suite
#     scripts/demo.sh             # run the CLI on generated sample data
#     scripts/backtest.sh prices.csv  # backtest a price file

set -euo pipefail

# Always work from the project root (one level above scripts/).
cd "$(dirname "${BASH_SOURCE[0]}")/.."

VENV_DIR=".venv"

# Pick an interpreter: $PYTHON if set, else python3, else python.
if [ -n "${PYTHON:-}" ]; then
    PY="$PYTHON"
elif command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "error: no python3/python found on PATH (set PYTHON=/path/to/python)" >&2
    exit 1
fi

if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
    echo "error: $PY is $("$PY" --version 2>&1); this project requires Python >= 3.9" >&2
    exit 1
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "Creating $VENV_DIR with $("$PY" --version 2>&1) ..."
    "$PY" -m venv "$VENV_DIR"
else
    echo "Reusing existing $VENV_DIR ($("$VENV_DIR/bin/python" --version 2>&1))"
fi

VENV_PY="$VENV_DIR/bin/python"

echo "Upgrading pip ..."
"$VENV_PY" -m pip install --quiet --upgrade pip

echo "Installing trading-assistant in editable mode with [dev] extras ..."
"$VENV_PY" -m pip install --quiet --editable ".[dev]"

echo
echo "Done. Installed:"
"$VENV_PY" -m pip list --format=columns 2>/dev/null | grep -i -E '^(Package|trading-assistant|pytest)\b' || true
echo
echo "Next steps:"
echo "    scripts/run_tests.sh                 # run the test suite"
echo "    scripts/demo.sh                      # try the CLI on generated sample data"
echo "    scripts/backtest.sh prices.csv 10000     # backtest a price file"
echo "or activate the venv yourself:  source $VENV_DIR/bin/activate"
