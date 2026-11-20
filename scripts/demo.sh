#!/usr/bin/env bash
# Run the CLI over generated sample data and a few broken files, showing each
# exit code. Handy for eyeballing that good input, bad input and --backtest
# all behave. Everything is written to a temporary folder that is removed at
# the end.
#
# Usage:
#     scripts/demo.sh

set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_venv.sh"
cd "$PROJECT_ROOT"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

run() {
    echo "\$ python -m trading_assistant.cli $*"
    "$VENV_PY" -m trading_assistant.cli "$@"
    echo "[exit $?]"
    echo
}

"$VENV_PY" -m trading_assistant.samples uptrend "$WORK/prices.csv"
printf 'date,price\n2026-01-02,101.50\n2026-01-05,102.10\n' > "$WORK/nocolumn.csv"
printf 'date,close\n2026-01-02,101.50\n2026-01-05,102.10\n2026-01-06,abc\n' > "$WORK/badvalue.csv"
PRICES="$WORK/prices.csv"

echo "### Good file (seeded up trend), default windows (20/50)"
run "$PRICES"

echo "### Backtest with default 10,000 cash"
run "$PRICES" --backtest

echo "### Backtest with shorter windows, trading costs (1.00 per trade + 0.1% of value) and a CSV export"
run "$PRICES" --backtest --short 5 --long 10 --fee 1 --fee-pct 0.1 --export "$WORK/report.csv"
echo "--- first and last lines of the export:"
head -3 "$WORK/report.csv"; echo "..."; tail -2 "$WORK/report.csv"; echo

echo "### Other strategies, with risk and return statistics"
run "$PRICES" --backtest --strategy breakout --param window=10 --stats
run "$PRICES" --backtest --strategy rsi_reversion --stats

echo "### Built-in sample series (same data the web page uses), written as CSV and run on the CLI"
"$VENV_PY" -m trading_assistant.samples --list
"$VENV_PY" -m trading_assistant.samples sideways "$WORK/sideways.csv"
run "$WORK/sideways.csv" --backtest --short 5 --long 20 --fee 1 --fee-pct 0.1
echo "(start the page with scripts/web.sh and pick 'Choppy sideways', SMA 5/20, fee 1, 0.1% to see the same numbers)"
echo

echo "### Bad input: no 'close' column  (expect one-line error, exit 1)"
run "$WORK/nocolumn.csv"

echo "### Bad input: non-numeric close  (expect one-line error, exit 1)"
run "$WORK/badvalue.csv"

echo "### Bad usage: --short not smaller than --long  (expect usage error, exit 2)"
run "$PRICES" --short 50 --long 20

echo "### Bad usage: --cash without --backtest  (expect usage error, exit 2)"
run "$PRICES" --cash 5000

echo "### Bad usage: negative --fee  (expect usage error, exit 2)"
run "$PRICES" --backtest --fee -1

echo "### Bad input: --export into a directory that does not exist  (expect one-line error, exit 1)"
run "$PRICES" --backtest --export /no/such/dir/report.csv
