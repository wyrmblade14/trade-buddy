"""--risk-pct PCT, --atr-mult N and --atr-period N on the command line.

Hand case: an 8-bar candle file, --cash 1000 --short 1 --long 2. The opens
are chosen inside each bar's range (low <= open <= high):

    bar  date        open  high  low   close
     0   2026-01-01  10    10.5   9.5  10
     1   2026-01-02   9.2   9.5   8.5   9
     2   2026-01-03   8.3   8.5   7.5   8
     3   2026-01-04   8.8   9.5   8.5   9     BUY signal; ATR(3) = 25/18
     4   2026-01-05  10.8  11.5  10.5  11     BUY fills @ 11 (close) or 10.8 (open)
     5   2026-01-06  12.2  13    11.2  12
     6   2026-01-07  11.5  12.5   9.8  10     SELL signal
     7   2026-01-08   8.6   9     7.5   8     SELL fills @ 8 (close) or 8.6 (open)

--risk-pct 2 --atr-mult 2 --atr-period 3: risk 20, stop 2 * 25/18 = 2.7778,
20 / 2.7778 = 7.2 -> 7 shares. With --atr-period 5 the first ATR is on bar 4,
after the bar 3 signal, so the buy is skipped (1 skipped).

Every OLD_* text was captured from the command before these options existed
(COLUMNS=80 for the usage line).
"""

import csv
import json

import pytest

from trading_assistant.cli import build_parser, main

HAND = """\
date,open,high,low,close,volume
2026-01-01,10,10.5,9.5,10,1000
2026-01-02,9.2,9.5,8.5,9,1000
2026-01-03,8.3,8.5,7.5,8,1000
2026-01-04,8.8,9.5,8.5,9,1000
2026-01-05,10.8,11.5,10.5,11,1000
2026-01-06,12.2,13,11.2,12,1000
2026-01-07,11.5,12.5,9.8,10,1000
2026-01-08,8.6,9,7.5,8,1000
"""
CLOSES_ONLY = "date,close\n" + "".join(f"2026-01-0{i + 1},{c}\n" for i, c in enumerate([10, 9, 8, 9, 11, 12, 10, 8]))
B = ["--backtest", "--cash", "1000", "--short", "1", "--long", "2"]
RISK = ["--risk-pct", "2", "--atr-mult", "2", "--atr-period", "3"]

RISK_LINE = (
    "  Risk sizing: 2.00% of account value at risk per buy, stop distance 2 x ATR(3) "
    "(this only sets the number of shares; no stop is placed)"
)
SKIPPED_LINE = (
    "  Skipped:     1 buy (risk sizing gave 0 shares: no usable ATR on the signal bar, or risk under 1 share)"
)

# Option strings the parser knew before --risk-pct, --atr-mult and --atr-period.
OLD_OPTIONS = ["--backtest", "--candles", "--cash", "--chart", "--config", "--export", "--fee", "--fee-pct", "--fill", "--help", "--json", "--long", "--min-score", "--param", "--position-size", "--report", "--resample", "--rsi-period", "--scan", "--short", "--slippage", "--stats", "--stop-loss", "--strategy", "--take-profit", "--top", "--trailing-stop"]

OLD_USAGE = (
    "usage: trading_assistant.cli [-h] [--short SHORT] [--long LONG]\n"
    "                             [--rsi-period RSI_PERIOD] [--backtest]\n"
    "                             [--cash AMOUNT] [--fee AMOUNT] [--fee-pct PCT]\n"
    "                             [--slippage PCT] [--position-size FRACTION]\n"
    "                             [--stop-loss PCT] [--take-profit PCT]\n"
    "                             [--export FILE] [--fill {close,open}]\n"
    "                             [--resample {weekly,monthly}]\n"
    "                             [--strategy {sma_cross,rsi_reversion,breakout,ema_cross,momentum,zscore_reversion,hull_trend}]\n"
    "                             [--param KEY=VALUE] [--stats] [--config FILE]\n"
    "                             [--json] [--chart] [--candles] [--scan FOLDER]\n"
    "                             [--min-score N] [--top N] [--report FILE]\n"
    "                             csv_path\n"
)
OLD_HELP = (
    "usage: trading_assistant.cli [-h] [--short SHORT] [--long LONG]\n"
    "                             [--rsi-period RSI_PERIOD] [--backtest]\n"
    "                             [--cash AMOUNT] [--fee AMOUNT] [--fee-pct PCT]\n"
    "                             [--slippage PCT] [--position-size FRACTION]\n"
    "                             [--stop-loss PCT] [--take-profit PCT]\n"
    "                             [--export FILE] [--fill {close,open}]\n"
    "                             [--resample {weekly,monthly}]\n"
    "                             [--strategy {sma_cross,rsi_reversion,breakout,ema_cross,momentum,zscore_reversion,hull_trend}]\n"
    "                             [--param KEY=VALUE] [--stats] [--config FILE]\n"
    "                             [--json] [--chart] [--candles] [--scan FOLDER]\n"
    "                             [--min-score N] [--top N] [--report FILE]\n"
    "                             csv_path\n"
    "\n"
    "Suggest BUY/SELL/HOLD from closing prices.\n"
    "\n"
    "positional arguments:\n"
    "  csv_path              CSV file with a 'close' column\n"
    "\n"
    "options:\n"
    "  -h, --help            show this help message and exit\n"
    "  --short SHORT         short SMA window (default: 20)\n"
    "  --long LONG           long SMA window (default: 50)\n"
    "  --rsi-period RSI_PERIOD\n"
    "                        RSI lookback (default: 14)\n"
    "  --backtest            also simulate trading the crossover signal over the\n"
    "                        whole file\n"
    "  --cash AMOUNT         starting cash for --backtest (default: 10,000)\n"
    "  --fee AMOUNT          fixed cost charged on every buy and every sell in\n"
    "                        --backtest (default: 0)\n"
    "  --fee-pct PCT         percentage of traded value charged on every buy and\n"
    "                        sell in --backtest, e.g. 0.1 for 0.1% (default: 0)\n"
    "  --slippage PCT        with --backtest, buys fill this percentage above and\n"
    "                        sells this percentage below the fill price, before\n"
    "                        fees, e.g. 0.1 for 0.1% (default: 0)\n"
    "  --position-size FRACTION\n"
    "                        with --backtest, each buy spends at most this fraction\n"
    "                        of the account value (above 0, at most 1), costs and\n"
    "                        slippage included (default: all the cash)\n"
    "  --stop-loss PCT       with --backtest, sell when a bar's low reaches the\n"
    "                        entry price less PCT% (reads a candle file; cannot be\n"
    "                        combined with --resample yet)\n"
    "  --take-profit PCT     with --backtest, sell when a bar's high reaches the\n"
    "                        entry price plus PCT% (reads a candle file; cannot be\n"
    "                        combined with --resample yet); if a bar touches both\n"
    "                        levels the stop wins\n"
    "  --trailing-stop PCT   with --backtest, sell when a bar's low reaches the\n"
    "                        highest high since entry less PCT% (the bar's own high\n"
    "                        is not used; reads a candle file; cannot be combined\n"
    "                        with --resample yet); works next to --stop-loss and\n"
    "                        --take-profit: the higher of the stop and trail levels\n"
    "                        is used, and it wins over the target if a bar touches\n"
    "                        both\n"
    "  --export FILE         with --backtest, write one CSV row per bar (account\n"
    "                        value, signal, fills) to FILE\n"
    "  --fill {close,open}   with --backtest, the price of the next bar a signal is\n"
    "                        filled at (default: close); open reads the file as a\n"
    "                        candle file and cannot be combined with --resample yet\n"
    "  --resample {weekly,monthly}\n"
    "                        reduce daily bars to weekly or monthly bars before\n"
    "                        analysing (needs a 'date' column)\n"
    "  --strategy {sma_cross,rsi_reversion,breakout,ema_cross,momentum,zscore_reversion,hull_trend}\n"
    "                        rule traded by --backtest (default: sma_cross); does\n"
    "                        not change the Signal line\n"
    "  --param KEY=VALUE     override a strategy parameter in --backtest, e.g.\n"
    "                        window=10 (repeatable)\n"
    "  --stats               with --backtest, also print the risk and return\n"
    "                        statistics block\n"
    "  --config FILE         read defaults from an INI file; flags win over the\n"
    "                        file (no file is read unless this is given or\n"
    "                        $TRADING_ASSISTANT_CONFIG is set)\n"
    "  --json                print the report as one JSON object on stdout instead\n"
    "                        of text (cannot be combined with --chart)\n"
    "  --chart               print a text chart of the closes after the report\n"
    "                        (fills marked B and S with --backtest)\n"
    "  --candles             read the file as a candle file (date, open, high, low,\n"
    "                        close, volume) and analyse its closes; cannot be\n"
    "                        combined with --resample yet\n"
    "  --scan FOLDER         instead of one price file, give the combined score of\n"
    "                        every .csv file directly inside FOLDER (cannot be\n"
    "                        combined with a price file or backtest options)\n"
    "  --min-score N         with --scan, keep only the files scoring N or more\n"
    "  --top N               with --scan, show only the first N rows (after --min-\n"
    "                        score)\n"
    "  --report FILE         with --scan, also write a Markdown report to FILE (the\n"
    "                        screen output does not change)\n"
    "\n"
    "Research aid only. Not financial advice.\n"
)
OLD_PLAIN_REPORT = (
    "Bars:    8\n"
    "Last:    8.00\n"
    "Signal:  HOLD\n"
    "RSI:     n/a\n"
    "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n"
    "  Start cash:  1,000.00\n"
    "  Trades:      2 (1 buy, 1 sell)\n"
    "  Fills (bar index is 0-based):\n"
    "    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00\n"
    "    #2   bar 7     SELL       90 @       8.00  value       720.00  cost     0.00  cash       730.00\n"
    "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n"
    "  Round trips: 1 completed, 0 made money (0%)\n"
    "  Comparison              Strategy    Buy & hold\n"
    "    End equity              730.00        800.00\n"
    "    Return                 -27.00%       -20.00%\n"
    "    Max drawdown           -33.03%       -33.33%\n"
    "    Trades                       2             1\n"
    "    Costs paid                0.00          0.00\n"
    "  End cash:    730.00\n"
    "  End shares:  0 @ 8.00\n"
    "  End equity:  730.00\n"
    "  Return:      -27.00%\n"
    "Research aid only. Not financial advice.\n"
)
OLD_EXITS_REPORT = (
    "Bars:    8\n"
    "Last:    8.00\n"
    "Signal:  HOLD\n"
    "RSI:     n/a\n"
    "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n"
    "  Start cash:  1,000.00\n"
    "  Trades:      2 (1 buy, 1 sell)\n"
    "  Fills (bar index is 0-based):\n"
    "    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal\n"
    "    #2   bar 6     SELL       90 @      11.50  value     1,035.00  cost     0.00  cash     1,045.00  trail\n"
    "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n"
    "  Exits:       stop 5.00% below entry, trail 8.00% below the highest high since entry, target 20.00% above entry (the higher of stop and trail is used; it wins if a bar also touches the target)\n"
    "  Round trips: 1 completed, 1 made money (100%)\n"
    "  Comparison              Strategy    Buy & hold\n"
    "    End equity            1,045.00        800.00\n"
    "    Return                  +4.50%       -20.00%\n"
    "    Max drawdown            -4.13%       -33.33%\n"
    "    Trades                       2             1\n"
    "    Costs paid                0.00          0.00\n"
    "  End cash:    1,045.00\n"
    "  End shares:  0 @ 8.00\n"
    "  End equity:  1,045.00\n"
    "  Return:      +4.50%\n"
    "  Exported:    8 rows to E.csv\n"
    "Research aid only. Not financial advice.\n"
)
OLD_EXITS_EXPORT = (
    "bar,date,close,signal,action,shares,price,value,cost,cash,position,equity,drawdown_pct,buy_hold_equity,reason\n"
    "0,2026-01-01,10.00,HOLD,,,,,,1000.00,0,1000.00,0.00,1000.00,\n"
    "1,2026-01-02,9.00,HOLD,,,,,,1000.00,0,1000.00,0.00,900.00,\n"
    "2,2026-01-03,8.00,HOLD,,,,,,1000.00,0,1000.00,0.00,800.00,\n"
    "3,2026-01-04,9.00,BUY,,,,,,1000.00,0,1000.00,0.00,900.00,\n"
    "4,2026-01-05,11.00,HOLD,BUY,90,11.00,990.00,0.00,10.00,90,1000.00,0.00,1100.00,signal\n"
    "5,2026-01-06,12.00,HOLD,,,,,,10.00,90,1090.00,0.00,1200.00,\n"
    "6,2026-01-07,10.00,SELL,SELL,90,11.50,1035.00,0.00,1045.00,0,1045.00,-4.13,1000.00,trail\n"
    "7,2026-01-08,8.00,HOLD,,,,,,1045.00,0,1045.00,-4.13,800.00,\n"
)
OLD_JSON = (
    "{\n"
    "  \"bars\": 8,\n"
    "  \"last_close\": 8.0,\n"
    "  \"signal\": \"HOLD\",\n"
    "  \"rsi\": null,\n"
    "  \"rsi_label\": null,\n"
    "  \"backtest\": {\n"
    "    \"strategy\": \"sma_cross\",\n"
    "    \"params\": {\n"
    "      \"short\": 1,\n"
    "      \"long\": 2\n"
    "    },\n"
    "    \"fill\": \"close\",\n"
    "    \"start_cash\": 1000.0,\n"
    "    \"fee\": 0.0,\n"
    "    \"fee_pct\": 0.0,\n"
    "    \"slippage_pct\": 0.0,\n"
    "    \"position_size\": null,\n"
    "    \"stop_loss_pct\": null,\n"
    "    \"take_profit_pct\": null,\n"
    "    \"trades\": 2,\n"
    "    \"buys\": 1,\n"
    "    \"sells\": 1,\n"
    "    \"fills\": [\n"
    "      {\n"
    "        \"bar\": 4,\n"
    "        \"side\": \"BUY\",\n"
    "        \"shares\": 90,\n"
    "        \"price\": 11.0,\n"
    "        \"value\": 990.0,\n"
    "        \"cost\": 0.0,\n"
    "        \"cash_after\": 10.0,\n"
    "        \"reason\": \"signal\"\n"
    "      },\n"
    "      {\n"
    "        \"bar\": 7,\n"
    "        \"side\": \"SELL\",\n"
    "        \"shares\": 90,\n"
    "        \"price\": 8.0,\n"
    "        \"value\": 720.0,\n"
    "        \"cost\": 0.0,\n"
    "        \"cash_after\": 730.0,\n"
    "        \"reason\": \"signal\"\n"
    "      }\n"
    "    ],\n"
    "    \"total_costs\": 0.0,\n"
    "    \"round_trips\": 1,\n"
    "    \"winning_round_trips\": 0,\n"
    "    \"final_cash\": 730.0,\n"
    "    \"final_position\": 0,\n"
    "    \"final_price\": 8.0,\n"
    "    \"final_equity\": 730.0,\n"
    "    \"return_pct\": -27.0,\n"
    "    \"max_drawdown_pct\": -33.02752293577982,\n"
    "    \"benchmark\": {\n"
    "      \"shares\": 100,\n"
    "      \"final_cash\": 0.0,\n"
    "      \"final_equity\": 800.0,\n"
    "      \"return_pct\": -20.0,\n"
    "      \"max_drawdown_pct\": -33.33333333333333,\n"
    "      \"trades\": 1,\n"
    "      \"total_costs\": 0.0\n"
    "    },\n"
    "    \"export\": {\n"
    "      \"path\": \"E.csv\",\n"
    "      \"rows\": 8\n"
    "    },\n"
    "    \"stats\": {\n"
    "      \"total_return_pct\": -27.0,\n"
    "      \"cagr_pct\": -99.99879877886636,\n"
    "      \"annualized_volatility_pct\": 163.76388748865816,\n"
    "      \"sharpe_ratio\": -5.999999999999997,\n"
    "      \"sortino_ratio\": -6.355456041144764,\n"
    "      \"exposure_pct\": 37.5,\n"
    "      \"profit_factor\": 0.0,\n"
    "      \"average_win\": null,\n"
    "      \"average_loss\": -270.0,\n"
    "      \"longest_drawdown_bars\": 2\n"
    "    }\n"
    "  },\n"
    "  \"disclaimer\": \"Research aid only. Not financial advice.\"\n"
    "}\n"
)
OLD_NEEDS_BACKTEST_STDERR = (
    "usage: trading_assistant.cli [-h] [--short SHORT] [--long LONG]\n"
    "                             [--rsi-period RSI_PERIOD] [--backtest]\n"
    "                             [--cash AMOUNT] [--fee AMOUNT] [--fee-pct PCT]\n"
    "                             [--slippage PCT] [--position-size FRACTION]\n"
    "                             [--stop-loss PCT] [--take-profit PCT]\n"
    "                             [--export FILE] [--fill {close,open}]\n"
    "                             [--resample {weekly,monthly}]\n"
    "                             [--strategy {sma_cross,rsi_reversion,breakout,ema_cross,momentum,zscore_reversion,hull_trend}]\n"
    "                             [--param KEY=VALUE] [--stats] [--config FILE]\n"
    "                             [--json] [--chart] [--candles] [--scan FOLDER]\n"
    "                             [--min-score N] [--top N] [--report FILE]\n"
    "                             csv_path\n"
    "trading_assistant.cli: error: --stop-loss only makes sense together with --backtest\n"
)


@pytest.fixture
def folder(tmp_path, monkeypatch):
    """A working folder with the hand candle file; the usage line is wrapped at 80 columns."""
    (tmp_path / "hand.csv").write_text(HAND)
    (tmp_path / "closes.csv").write_text(CLOSES_ONLY)
    (tmp_path / "scan").mkdir()
    (tmp_path / "scan" / "a.csv").write_text(CLOSES_ONLY)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    return tmp_path


def run(argv, capsys):
    try:
        code = main(argv)
    except SystemExit as exc:
        code = exc.code
    out, err = capsys.readouterr()
    return code, out, err


def usage_error(argv, capsys, message):
    code, out, err = run(argv, capsys)
    assert (code, out) == (2, "")
    assert err == OLD_USAGE + f"trading_assistant.cli: error: {message}\n"


# --------------------------------------------------------------------------- the hand case


def test_hand_case_report(folder, capsys):
    code, out, err = run(["hand.csv", *B, *RISK], capsys)
    assert (code, err) == (0, "")
    assert out == (
        "Bars:    8\n"
        "Last:    8.00\n"
        "Signal:  HOLD\n"
        "RSI:     n/a\n"
        "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n"
        "  Start cash:  1,000.00\n"
        "  Trades:      2 (1 buy, 1 sell)\n"
        "  Fills (bar index is 0-based):\n"
        "    #1   bar 4     BUY         7 @      11.00  value        77.00  cost     0.00  cash       923.00\n"
        "    #2   bar 7     SELL        7 @       8.00  value        56.00  cost     0.00  cash       979.00\n"
        "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n"
        + RISK_LINE + "\n"
        "  Round trips: 1 completed, 0 made money (0%)\n"
        "  Comparison              Strategy    Buy & hold\n"
        "    End equity              979.00        800.00\n"
        "    Return                  -2.10%       -20.00%\n"
        "    Max drawdown            -2.78%       -33.33%\n"
        "    Trades                       2             1\n"
        "    Costs paid                0.00          0.00\n"
        "  End cash:    979.00\n"
        "  End shares:  0 @ 8.00\n"
        "  End equity:  979.00\n"
        "  Return:      -2.10%\n"
        "Research aid only. Not financial advice.\n"
    )


def test_period_5_skips_the_buy(folder, capsys):
    code, out, err = run(["hand.csv", *B, "--risk-pct", "2", "--atr-mult", "2", "--atr-period", "5"], capsys)
    assert (code, err) == (0, "")
    assert "  Trades:      0 (0 buy, 0 sell)\n" in out
    assert "stop distance 2 x ATR(5)" in out
    assert SKIPPED_LINE + "\n" in out
    assert "  End cash:    1,000.00\n" in out


def test_defaults_are_atr_mult_2_and_atr_period_14(folder, capsys):
    # 8 bars: ATR(14) never exists, so the one buy is skipped.
    code, out, _ = run(["hand.csv", *B, "--risk-pct", "2"], capsys)
    assert code == 0
    assert "  Risk sizing: 2.00% of account value at risk per buy, stop distance 2 x ATR(14) " in out
    assert SKIPPED_LINE in out


def test_risk_pct_100_is_allowed(folder, capsys):
    code, out, _ = run(["hand.csv", *B, "--risk-pct", "100", "--atr-period", "3"], capsys)
    assert code == 0
    assert "BUY        90 @      11.00" in out  # 1000 / 2.7778 = 360 wanted, the cash buys 90


def test_export_follows_the_risk_sized_fills(folder, capsys):
    code, out, _ = run(["hand.csv", *B, *RISK, "--export", "E.csv"], capsys)
    assert code == 0 and "  Exported:    8 rows to E.csv" in out
    rows = list(csv.DictReader(open(folder / "E.csv")))
    assert (rows[4]["action"], rows[4]["shares"]) == ("BUY", "7")
    assert (rows[7]["action"], rows[7]["shares"]) == ("SELL", "7")


def test_json_uses_the_risk_sized_fills(folder, capsys):
    # --json itself is not changed; its fills simply come from the risk-sized backtest.
    code, out, _ = run(["hand.csv", *B, *RISK, "--json"], capsys)
    assert code == 0
    assert [f["shares"] for f in json.loads(out)["backtest"]["fills"]] == [7, 7]


# --------------------------------------------------------------------------- next to the other settings


def test_smaller_of_position_size_and_risk_size_wins(folder, capsys):
    _, out, _ = run(["hand.csv", *B, *RISK, "--position-size", "0.5"], capsys)  # cap 45 shares: risk's 7 wins
    assert "BUY         7 @      11.00" in out
    _, out, _ = run(["hand.csv", *B, *RISK, "--position-size", "0.05"], capsys)  # cap 50 / 11 = 4 shares
    assert "BUY         4 @      11.00" in out
    assert "  Sizing:      each buy at most 5% of account value (costs and slippage included)\n" + RISK_LINE in out


def test_works_next_to_stop_loss_take_profit_and_trailing_stop(folder, capsys):
    # 7 shares are bought; the trailing stop (13 * 0.92 = 11.96) sells them at bar 6's open 11.50.
    code, out, _ = run(
        ["hand.csv", *B, *RISK, "--stop-loss", "5", "--take-profit", "20", "--trailing-stop", "8"], capsys
    )
    assert code == 0
    assert "    #1   bar 4     BUY         7 @      11.00" in out and out.count("  signal\n") == 1
    assert "    #2   bar 6     SELL        7 @      11.50" in out and "  trail\n" in out
    assert RISK_LINE + "\n  Exits:       stop 5.00% below entry" in out


def test_with_fill_open(folder, capsys):
    code, out, _ = run(["hand.csv", *B, *RISK, "--fill", "open"], capsys)
    assert code == 0
    assert "    #1   bar 4     BUY         7 @      10.80" in out
    assert "    #2   bar 7     SELL        7 @       8.60" in out


# --------------------------------------------------------------------------- usage errors (exit 2)


def test_risk_pct_needs_backtest(folder, capsys):
    usage_error(["hand.csv", "--risk-pct", "2"], capsys, "--risk-pct only makes sense together with --backtest")


@pytest.mark.parametrize("value", ["0", "-1", "100.5", "nan"])
def test_risk_pct_out_of_range(folder, capsys, value):
    shown = format(float(value), "g")
    usage_error(["hand.csv", *B, "--risk-pct", value], capsys, f"--risk-pct must be above 0 and at most 100, got {shown}")


def test_risk_pct_not_a_number(folder, capsys):
    usage_error(["hand.csv", *B, "--risk-pct", "abc"], capsys, "argument --risk-pct: invalid float value: 'abc'")


def test_risk_pct_with_resample(folder, capsys):
    usage_error(
        ["closes.csv", *B, "--risk-pct", "2", "--resample", "weekly"], capsys,
        "--risk-pct cannot be combined with --resample yet",
    )


@pytest.mark.parametrize(
    "option, value", [("--risk-pct", "2"), ("--atr-mult", "2"), ("--atr-period", "3")]
)
def test_not_with_scan(folder, capsys, option, value):
    code, out, err = run(["--scan", "scan", option, value], capsys)
    assert (code, out) == (2, "")
    assert err.endswith(f"trading_assistant.cli: error: {option} cannot be combined with --scan\n")


@pytest.mark.parametrize("option, value", [("--atr-mult", "3"), ("--atr-period", "5")])
def test_atr_options_need_risk_pct(folder, capsys, option, value):
    usage_error(["hand.csv", *B, option, value], capsys, f"{option} only makes sense together with --risk-pct or --atr-stop")


@pytest.mark.parametrize("option, value", [("--atr-mult", "3"), ("--atr-period", "5")])
def test_atr_options_without_backtest_also_name_risk_pct(folder, capsys, option, value):
    usage_error(["hand.csv", option, value], capsys, f"{option} only makes sense together with --risk-pct or --atr-stop")


@pytest.mark.parametrize("value, shown", [("0", "0"), ("-2", "-2"), ("nan", "nan")])
def test_atr_mult_must_be_above_0(folder, capsys, value, shown):
    usage_error(["hand.csv", *B, "--risk-pct", "2", "--atr-mult", value], capsys, f"--atr-mult must be above 0, got {shown}")


@pytest.mark.parametrize("value", ["0", "-3"])
def test_atr_period_must_be_at_least_1(folder, capsys, value):
    usage_error(
        ["hand.csv", *B, "--risk-pct", "2", "--atr-period", value], capsys,
        f"--atr-period must be a whole number of at least 1, got {value}",
    )


def test_atr_period_must_be_whole(folder, capsys):
    usage_error(
        ["hand.csv", *B, "--risk-pct", "2", "--atr-period", "1.5"], capsys,
        "argument --atr-period: invalid int value: '1.5'",
    )


# --------------------------------------------------------------------------- data errors (exit 1)


def test_risk_pct_needs_a_candle_file_like_stop_loss(folder, capsys):
    code, out, err = run(["closes.csv", *B, "--risk-pct", "2"], capsys)
    stop = run(["closes.csv", *B, "--stop-loss", "5"], capsys)
    assert (code, out) == (1, "")
    assert err.startswith("Error: closes.csv has no 'open', 'high', 'low', 'volume' columns")
    assert (code, out, err) == stop


# --------------------------------------------------------------------------- help


def test_help_describes_the_options(folder, capsys):
    code, out, _ = run(["--help"], capsys)
    assert code == 0
    text = " ".join(out.split())
    assert "--risk-pct PCT with --backtest, size each buy by risk: PCT% of the account value" in text
    assert "with --position-size the smaller size wins" in text
    assert "This only sets the number of shares: no stop is placed, so a loss is not limited to PCT%" in text
    assert "Works next to --stop-loss, --take-profit and --trailing- stop" in text  # argparse hyphen wrap
    assert "--atr-mult N with --risk-pct, the stop distance used for sizing is N times the ATR" in text
    assert "it only sets the number of shares, no stop is placed" in text
    assert "--atr-period N with --risk-pct, the number of bars in the ATR" in text


def test_help_only_adds_the_new_options(folder, capsys):
    _, out, _ = run(["--help"], capsys)
    new = out.splitlines()
    start = new.index(next(line for line in new if line.startswith("  --risk-pct PCT")))
    end = new.index(next(line for line in new if line.startswith("  --export FILE")))
    t_start = new.index(next(line for line in new if line.startswith("  --trade-list ")))  # added later, after --stats
    t_end = new.index(next(line for line in new if line.startswith("  --config FILE")))
    e_start = new.index(next(line for line in new if line.startswith("  --explain ")))  # added later, after --chart
    e_end = new.index(next(line for line in new if line.startswith("  --candles")))
    assert "\n".join(new[:start] + new[end:t_start] + new[t_end:e_start] + new[e_end:]) + "\n" == OLD_HELP


def test_usage_line_does_not_list_the_new_options(folder, capsys):
    _, out, _ = run(["--help"], capsys)
    assert out.startswith(OLD_USAGE)
    for option in ("--risk-pct", "--atr-mult", "--atr-period"):
        assert option not in OLD_USAGE


# --------------------------------------------------------------------------- without the new options: unchanged


def test_old_commands_print_exactly_the_same(folder, capsys):
    assert run(["hand.csv", *B], capsys) == (0, OLD_PLAIN_REPORT, "")

    code, out, err = run(
        ["hand.csv", *B, "--stop-loss", "5", "--take-profit", "20", "--trailing-stop", "8", "--export", "E.csv"], capsys
    )
    assert (code, out, err) == (0, OLD_EXITS_REPORT, "")
    assert (folder / "E.csv").read_text() == OLD_EXITS_EXPORT

    assert run(["hand.csv", *B, "--json", "--stats", "--export", "E.csv"], capsys) == (0, OLD_JSON, "")
    assert run(["hand.csv", "--stop-loss", "5"], capsys) == (2, "", OLD_NEEDS_BACKTEST_STDERR)


def _value_for(action):
    if action.nargs == 0:
        return []
    if action.choices:
        return [sorted(action.choices)[0]]
    if action.dest == "param":
        return ["a=1"]
    return ["5"]


def test_every_shortened_name_that_worked_before_still_means_the_same_option():
    parser = build_parser()
    actions = {s: a for a in parser._actions for s in a.option_strings}
    checked = 0
    for option in OLD_OPTIONS:
        if option == "--help":
            continue
        action = actions[option]
        for n in range(3, len(option) + 1):
            prefix = option[:n]
            if prefix != option and (prefix in OLD_OPTIONS or sum(o.startswith(prefix) for o in OLD_OPTIONS) > 1):
                continue  # an exact old option, or ambiguous before: not a working short name of this one
            args, extra = build_parser().parse_known_args(["x.csv", prefix, *_value_for(action)])
            assert extra == [], prefix
            assert getattr(args, action.dest) != parser.get_default(action.dest), (prefix, option)
            checked += 1
    assert checked > 100
