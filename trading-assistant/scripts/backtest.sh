#!/usr/bin/env bash
# Backtest the SMA crossover over a whole price file.
#
# Usage:
#     scripts/backtest.sh PRICES.csv [CASH] [extra cli options...]
#
# Examples:
#     scripts/backtest.sh prices.csv                      # 10,000 starting cash, SMA 20/50
#     scripts/backtest.sh prices.csv 5000                 # 5,000 starting cash
#     scripts/backtest.sh prices.csv 10000 --short 5 --long 10
#     scripts/backtest.sh prices.csv 10000 --short 5 --long 10 --fee 1 --fee-pct 0.1
#     scripts/backtest.sh prices.csv 10000 --short 5 --long 10 --export report.csv
#
# Exit code is the CLI's: 0 ok, 1 data problem, 2 usage problem.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_venv.sh"

if [ "$#" -lt 1 ]; then
    echo "usage: scripts/backtest.sh PRICES.csv [CASH] [extra cli options...]" >&2
    exit 2
fi

csv="$1"; shift
args=("$csv" --backtest)

# Optional second positional argument: starting cash (a plain number).
if [ "$#" -ge 1 ] && [[ "$1" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    args+=(--cash "$1"); shift
fi

exec "$VENV_PY" -m trading_assistant.cli "${args[@]}" "$@"
