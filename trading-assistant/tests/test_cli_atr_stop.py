"""--atr-stop on the command line, with --atr-mult N and --atr-period N.

Hand case: the 8-bar candle file of test_cli_risk_sizing.py, --cash 1000
--short 1 --long 2 (volume 1000 on every bar):

    bar  date        open  high  low   close
     0   2026-01-01  10    10.5   9.5  10
     1   2026-01-02   9.2   9.5   8.5   9
     2   2026-01-03   8.3   8.5   7.5   8
     3   2026-01-04   8.8   9.5   8.5   9     BUY signal; ATR(3) = 25/18
     4   2026-01-05  10.8  11.5  10.5  11     BUY fills @ 11 (close) or 10.8 (open)
     5   2026-01-06  12.2  13    11.2  12
     6   2026-01-07  11.5  12.5   9.8  10     SELL signal
     7   2026-01-08   8.6   9     7.5   8     SELL fills @ 8 (close) or 8.6 (open)

--atr-stop --atr-mult 2 --atr-period 3: level 11 - 2 * 25/18 = 8.2222. Bar 7 opens
at 8.6 (above it, no gap) and its low 7.5 reaches it: SELL 90 @ 8.22 = 740, cash 750,
reason atr (the signal sell @ 8 would leave 730).
With --risk-pct 2 as well: 7 shares @ 11, sold @ 8.22, cash 980.56.
--atr-mult 1: level 11 - 25/18 = 9.6111; bar 7 opens at 8.6 below it (a gap; the
command always passes the opens with an exit) -> SELL 90 @ 8.60 = 774, cash 784.
--atr-stop alone: default ATR(14) never exists on 8 bars -> the buy is skipped (1 skipped).

Every BEFORE_* text was captured from the command before --atr-stop existed
(COLUMNS=80 for the usage line and help).
"""

import re

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
ATR = ["--atr-stop", "--atr-mult", "2", "--atr-period", "3"]

# Option strings the parser knew before --atr-stop (including the hidden exact aliases --t and --re).
BEFORE_OPTIONS = [
    "--atr-mult", "--atr-period", "--backtest", "--candles", "--cash", "--chart", "--config", "--export", "--fee",
    "--fee-pct", "--fill", "--help", "--json", "--long", "--min-score", "--param", "--position-size", "--re",
    "--report", "--resample", "--risk-pct", "--rsi-period", "--scan", "--short", "--slippage", "--stats",
    "--stop-loss", "--strategy", "--t", "--take-profit", "--top", "--trailing-stop",
]

BEFORE_HELP = (
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
    "  --risk-pct PCT        with --backtest, size each buy by risk: PCT% of the\n"
    "                        account value (above 0, at most 100) divided by a stop\n"
    "                        distance of --atr-mult times the ATR (--atr-period\n"
    "                        bars) on the bar the buy signal came on, rounded down\n"
    "                        to whole shares; with --position-size the smaller size\n"
    "                        wins. A buy that gets 0 shares this way (no ATR yet,\n"
    "                        or under one share) is skipped and counted in the\n"
    "                        report. This only sets the number of shares: no stop\n"
    "                        is placed, so a loss is not limited to PCT%. Works\n"
    "                        next to --stop-loss, --take-profit and --trailing-\n"
    "                        stop, which are the exits (reads a candle file; cannot\n"
    "                        be combined with --resample yet)\n"
    "  --atr-mult N          with --risk-pct, the stop distance used for sizing is\n"
    "                        N times the ATR (above 0; default: 2); it only sets\n"
    "                        the number of shares, no stop is placed\n"
    "  --atr-period N        with --risk-pct, the number of bars in the ATR (a\n"
    "                        whole number of at least 1; default: 14)\n"
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
# (argv, exit code, stdout, stderr, export file or None); "*B" stands for the backtest base flags.
BEFORE_RUNS = [
    (
        ["hand.csv", "*B", "--risk-pct", "2", "--atr-mult", "2", "--atr-period", "3", "--stop-loss", "5", "--trailing-stop", "8", "--fill", "open", "--export", "E.csv"],
        0,
        (
            "Bars:    8\n"
            "Last:    8.00\n"
            "Signal:  HOLD\n"
            "RSI:     n/a\n"
            "Backtest: SMA 1/2 crossover, next-bar open fills, whole shares, no shorting\n"
            "  Start cash:  1,000.00\n"
            "  Trades:      2 (1 buy, 1 sell)\n"
            "  Fills (bar index is 0-based):\n"
            "    #1   bar 4     BUY         7 @      10.80  value        75.60  cost     0.00  cash       924.40  signal\n"
            "    #2   bar 6     SELL        7 @      11.50  value        80.50  cost     0.00  cash     1,004.90  trail\n"
            "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n"
            "  Risk sizing: 2.00% of account value at risk per buy, stop distance 2 x ATR(3) (this only sets the number of shares; no stop is placed)\n"
            "  Exits:       stop 5.00% below entry, trail 8.00% below the highest high since entry (the higher of stop and trail is used)\n"
            "  Round trips: 1 completed, 1 made money (100%)\n"
            "  Comparison              Strategy    Buy & hold\n"
            "    End equity            1,004.90        800.00\n"
            "    Return                  +0.49%       -20.00%\n"
            "    Max drawdown            -0.35%       -33.33%\n"
            "    Trades                       2             1\n"
            "    Costs paid                0.00          0.00\n"
            "  End cash:    1,004.90\n"
            "  End shares:  0 @ 8.00\n"
            "  End equity:  1,004.90\n"
            "  Return:      +0.49%\n"
            "  Exported:    8 rows to E.csv\n"
            "Research aid only. Not financial advice.\n"
        ),
        "",
        (
            "bar,date,close,signal,action,shares,price,value,cost,cash,position,equity,drawdown_pct,buy_hold_equity,reason\n"
            "0,2026-01-01,10.00,HOLD,,,,,,1000.00,0,1000.00,0.00,1000.00,\n"
            "1,2026-01-02,9.00,HOLD,,,,,,1000.00,0,1000.00,0.00,900.00,\n"
            "2,2026-01-03,8.00,HOLD,,,,,,1000.00,0,1000.00,0.00,800.00,\n"
            "3,2026-01-04,9.00,BUY,,,,,,1000.00,0,1000.00,0.00,900.00,\n"
            "4,2026-01-05,11.00,HOLD,BUY,7,10.80,75.60,0.00,924.40,7,1001.40,0.00,1100.00,signal\n"
            "5,2026-01-06,12.00,HOLD,,,,,,924.40,7,1008.40,0.00,1200.00,\n"
            "6,2026-01-07,10.00,SELL,SELL,7,11.50,80.50,0.00,1004.90,0,1004.90,-0.35,1000.00,trail\n"
            "7,2026-01-08,8.00,HOLD,,,,,,1004.90,0,1004.90,-0.35,800.00,\n"
        ),
    ),
    (
        ["hand.csv", "*B", "--risk", "2", "--atr-m", "1.5", "--atr-p", "3", "--stop", "10", "--trail", "8", "--take", "20"],
        0,
        (
            "Bars:    8\n"
            "Last:    8.00\n"
            "Signal:  HOLD\n"
            "RSI:     n/a\n"
            "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n"
            "  Start cash:  1,000.00\n"
            "  Trades:      2 (1 buy, 1 sell)\n"
            "  Fills (bar index is 0-based):\n"
            "    #1   bar 4     BUY         9 @      11.00  value        99.00  cost     0.00  cash       901.00  signal\n"
            "    #2   bar 6     SELL        9 @      11.50  value       103.50  cost     0.00  cash     1,004.50  trail\n"
            "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n"
            "  Risk sizing: 2.00% of account value at risk per buy, stop distance 1.5 x ATR(3) (this only sets the number of shares; no stop is placed)\n"
            "  Exits:       stop 10.00% below entry, trail 8.00% below the highest high since entry, target 20.00% above entry (the higher of stop and trail is used; it wins if a bar also touches the target)\n"
            "  Round trips: 1 completed, 1 made money (100%)\n"
            "  Comparison              Strategy    Buy & hold\n"
            "    End equity            1,004.50        800.00\n"
            "    Return                  +0.45%       -20.00%\n"
            "    Max drawdown            -0.45%       -33.33%\n"
            "    Trades                       2             1\n"
            "    Costs paid                0.00          0.00\n"
            "  End cash:    1,004.50\n"
            "  End shares:  0 @ 8.00\n"
            "  End equity:  1,004.50\n"
            "  Return:      +0.45%\n"
            "Research aid only. Not financial advice.\n"
        ),
        "",
        None,
    ),
    (
        ["hand.csv", "*B", "--risk-pct", "2", "--atr-period", "3", "--json", "--stats"],
        0,
        (
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
            "    \"risk_pct\": 2.0,\n"
            "    \"atr_mult\": 2.0,\n"
            "    \"atr_period\": 3,\n"
            "    \"stop_loss_pct\": null,\n"
            "    \"take_profit_pct\": null,\n"
            "    \"trades\": 2,\n"
            "    \"buys\": 1,\n"
            "    \"sells\": 1,\n"
            "    \"risk_skipped_buys\": 0,\n"
            "    \"fills\": [\n"
            "      {\n"
            "        \"bar\": 4,\n"
            "        \"side\": \"BUY\",\n"
            "        \"shares\": 7,\n"
            "        \"price\": 11.0,\n"
            "        \"value\": 77.0,\n"
            "        \"cost\": 0.0,\n"
            "        \"cash_after\": 923.0,\n"
            "        \"reason\": \"signal\"\n"
            "      },\n"
            "      {\n"
            "        \"bar\": 7,\n"
            "        \"side\": \"SELL\",\n"
            "        \"shares\": 7,\n"
            "        \"price\": 8.0,\n"
            "        \"value\": 56.0,\n"
            "        \"cost\": 0.0,\n"
            "        \"cash_after\": 979.0,\n"
            "        \"reason\": \"signal\"\n"
            "      }\n"
            "    ],\n"
            "    \"total_costs\": 0.0,\n"
            "    \"round_trips\": 1,\n"
            "    \"winning_round_trips\": 0,\n"
            "    \"final_cash\": 979.0,\n"
            "    \"final_position\": 0,\n"
            "    \"final_price\": 8.0,\n"
            "    \"final_equity\": 979.0,\n"
            "    \"return_pct\": -2.1,\n"
            "    \"max_drawdown_pct\": -2.780536246276067,\n"
            "    \"benchmark\": {\n"
            "      \"shares\": 100,\n"
            "      \"final_cash\": 0.0,\n"
            "      \"final_equity\": 800.0,\n"
            "      \"return_pct\": -20.0,\n"
            "      \"max_drawdown_pct\": -33.33333333333333,\n"
            "      \"trades\": 1,\n"
            "      \"total_costs\": 0.0\n"
            "    },\n"
            "    \"stats\": {\n"
            "      \"total_return_pct\": -2.100000000000002,\n"
            "      \"cagr_pct\": -53.42242166509541,\n"
            "      \"annualized_volatility_pct\": 12.600823240338743,\n"
            "      \"sharpe_ratio\": -6.000000000000048,\n"
            "      \"sortino_ratio\": -6.363909061513708,\n"
            "      \"exposure_pct\": 37.5,\n"
            "      \"profit_factor\": 0.0,\n"
            "      \"average_win\": null,\n"
            "      \"average_loss\": -21.0,\n"
            "      \"longest_drawdown_bars\": 2\n"
            "    }\n"
            "  },\n"
            "  \"disclaimer\": \"Research aid only. Not financial advice.\"\n"
            "}\n"
        ),
        "",
        None,
    ),
    (
        ["hand.csv", "*B", "--stop-loss", "5", "--take-profit", "20", "--stats", "--chart"],
        0,
        (
            "Bars:    8\n"
            "Last:    8.00\n"
            "Signal:  HOLD\n"
            "RSI:     n/a\n"
            "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n"
            "  Start cash:  1,000.00\n"
            "  Trades:      2 (1 buy, 1 sell)\n"
            "  Fills (bar index is 0-based):\n"
            "    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal\n"
            "    #2   bar 6     SELL       90 @      10.45  value       940.50  cost     0.00  cash       950.50  stop\n"
            "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n"
            "  Exits:       stop 5.00% below entry, target 20.00% above entry (stop wins if a bar touches both)\n"
            "  Round trips: 1 completed, 0 made money (0%)\n"
            "  Comparison              Strategy    Buy & hold\n"
            "    End equity              950.50        800.00\n"
            "    Return                  -4.95%       -20.00%\n"
            "    Max drawdown           -12.80%       -33.33%\n"
            "    Trades                       2             1\n"
            "    Costs paid                0.00          0.00\n"
            "  End cash:    950.50\n"
            "  End shares:  0 @ 8.00\n"
            "  End equity:  950.50\n"
            "  Return:      -4.95%\n"
            "Risk and return\n"
            "  Total return:       -4.95%\n"
            "  CAGR:               -83.92%\n"
            "  Volatility (ann.):  100.97%\n"
            "  Sharpe ratio:       -1.35\n"
            "  Sortino ratio:      -1.78\n"
            "  Exposure:           25.00%\n"
            "  Profit factor:      0.00\n"
            "  Average win:        n/a\n"
            "  Average loss:       -49.50\n"
            "  Longest drawdown:   2 bars\n"
            "Chart:   close, 8 bars, B = buy, S = sell\n"
            "12.00 |     *\n"
            "      |\n"
            "      |\n"
            "      |    B\n"
            "      |\n"
            "      |*     S\n"
            "      |\n"
            "      |\n"
            "      | * *\n"
            "      |\n"
            "      |\n"
            " 8.00 |  *    *\n"
            "      +--------\n"
            "Research aid only. Not financial advice.\n"
        ),
        "",
        None,
    ),
    (
        ["hand.csv", "--risk-pct", "2"],
        2,
        "",
        (
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
            "trading_assistant.cli: error: --risk-pct only makes sense together with --backtest\n"
        ),
        None,
    ),
    (
        ["hand.csv", "*B", "--risk-pct", "2", "--atr-mult", "0"],
        2,
        "",
        (
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
            "trading_assistant.cli: error: --atr-mult must be above 0, got 0\n"
        ),
        None,
    ),
    (
        ["hand.csv", "*B", "--trailing-stop", "8", "--resample", "weekly"],
        2,
        "",
        (
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
            "trading_assistant.cli: error: --trailing-stop cannot be combined with --resample yet\n"
        ),
        None,
    ),
    (
        ["--scan", "scan", "--atr-period", "3"],
        2,
        "",
        (
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
            "                             [csv_path]\n"
            "trading_assistant.cli: error: --atr-period cannot be combined with --scan\n"
        ),
        None,
    ),
    (
        ["closes.csv", "*B", "--risk-pct", "2"],
        1,
        "",
        (
            "Error: closes.csv has no 'open', 'high', 'low', 'volume' columns (found columns: 'date', 'close'); expected a header row like 'date,open,high,low,close,volume' followed by rows like '2026-01-02,100.5,103.0,99.5,101.5,12000'\n"
        ),
        None,
    ),
    (
        ["hand.csv", "*B", "--risk-pct", "2", "--atr-period", "5"],
        0,
        (
            "Bars:    8\n"
            "Last:    8.00\n"
            "Signal:  HOLD\n"
            "RSI:     n/a\n"
            "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n"
            "  Start cash:  1,000.00\n"
            "  Trades:      0 (0 buy, 0 sell)\n"
            "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n"
            "  Risk sizing: 2.00% of account value at risk per buy, stop distance 2 x ATR(5) (this only sets the number of shares; no stop is placed)\n"
            "  Skipped:     1 buy (risk sizing gave 0 shares: no usable ATR on the signal bar, or risk under 1 share)\n"
            "  Round trips: 0 completed\n"
            "  Comparison              Strategy    Buy & hold\n"
            "    End equity            1,000.00        800.00\n"
            "    Return                  +0.00%       -20.00%\n"
            "    Max drawdown             0.00%       -33.33%\n"
            "    Trades                       0             1\n"
            "    Costs paid                0.00          0.00\n"
            "  End cash:    1,000.00\n"
            "  End shares:  0 @ 8.00\n"
            "  End equity:  1,000.00\n"
            "  Return:      +0.00%\n"
            "Research aid only. Not financial advice.\n"
        ),
        "",
        None,
    ),
]

BEFORE_USAGE = BEFORE_HELP[: BEFORE_HELP.index("csv_path\n") + len("csv_path\n")]

FILL_LINES_HAND = [
    "    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal",
    "    #2   bar 7     SELL       90 @       8.22  value       740.00  cost     0.00  cash       750.00  atr",
]


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
    assert err == BEFORE_USAGE + f"trading_assistant.cli: error: {message}\n"


def fill_lines(out):
    return [line for line in out.splitlines() if line.startswith("    #")]


# --------------------------------------------------------------------------- the hand case


def test_hand_case_report(folder, capsys):
    code, out, err = run(["hand.csv", *B, *ATR], capsys)
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
        "    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal\n"
        "    #2   bar 7     SELL       90 @       8.22  value       740.00  cost     0.00  cash       750.00  atr\n"
        "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n"
        "  Exits:       atr 2 x ATR(3) below entry\n"
        "  Round trips: 1 completed, 0 made money (0%)\n"
        "  Comparison              Strategy    Buy & hold\n"
        "    End equity              750.00        800.00\n"
        "    Return                 -25.00%       -20.00%\n"
        "    Max drawdown           -31.19%       -33.33%\n"
        "    Trades                       2             1\n"
        "    Costs paid                0.00          0.00\n"
        "  End cash:    750.00\n"
        "  End shares:  0 @ 8.00\n"
        "  End equity:  750.00\n"
        "  Return:      -25.00%\n"
        "Research aid only. Not financial advice.\n"
    )


def test_hand_case_with_risk_pct(folder, capsys):
    code, out, err = run(["hand.csv", *B, "--risk-pct", "2", *ATR], capsys)
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
        "    #1   bar 4     BUY         7 @      11.00  value        77.00  cost     0.00  cash       923.00  signal\n"
        "    #2   bar 7     SELL        7 @       8.22  value        57.56  cost     0.00  cash       980.56  atr\n"
        "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n"
        "  Risk sizing: 2.00% of account value at risk per buy, stop distance 2 x ATR(3) "
        "(the ATR stop sells at this distance, as of the buy that opened the position, below the average entry price; a gap, slippage, fees or a later buy can lose more)\n"
        "  Exits:       atr 2 x ATR(3) below entry\n"
        "  Round trips: 1 completed, 0 made money (0%)\n"
        "  Comparison              Strategy    Buy & hold\n"
        "    End equity              980.56        800.00\n"
        "    Return                  -1.94%       -20.00%\n"
        "    Max drawdown            -2.63%       -33.33%\n"
        "    Trades                       2             1\n"
        "    Costs paid                0.00          0.00\n"
        "  End cash:    980.56\n"
        "  End shares:  0 @ 8.00\n"
        "  End equity:  980.56\n"
        "  Return:      -1.94%\n"
        "Research aid only. Not financial advice.\n"
    )


def test_order_of_the_options_does_not_matter(folder, capsys):
    a = run(["hand.csv", *B, *ATR], capsys)
    b = run(["hand.csv", "--atr-period", "3", "--atr-stop", *B, "--atr-mult", "2"], capsys)
    assert a == b


def test_defaults_are_atr_mult_2_and_atr_period_14(folder, capsys):
    # ATR(14) never exists on 8 bars, so the only buy is skipped and counted.
    code, out, err = run(["hand.csv", *B, "--atr-stop"], capsys)
    assert (code, err) == (0, "")
    lines = out.splitlines()
    i = lines.index("  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)")
    assert lines[i + 1 : i + 3] == [
        "  Skipped:     1 buy (ATR stop: no usable ATR on the signal bar)",
        "  Exits:       atr 2 x ATR(14) below entry",
    ]
    assert "  Trades:      0 (0 buy, 0 sell)" in lines and "  End cash:    1,000.00" in lines


def test_atr_period_5_skips_the_buy_and_counts_it_once_with_risk_pct(folder, capsys):
    for extra in ([], ["--risk-pct", "2"]):
        code, out, _ = run(["hand.csv", *B, *extra, "--atr-stop", "--atr-period", "5"], capsys)
        assert code == 0
        skipped = [line for line in out.splitlines() if line.startswith("  Skipped:")]
        assert len(skipped) == 1 and skipped[0].startswith("  Skipped:     1 buy ")
        assert "  Trades:      0 (0 buy, 0 sell)" in out.splitlines()


def test_atr_mult_and_atr_period_work_with_atr_stop_alone(folder, capsys):
    # --atr-mult 1: level 9.6111; bar 7 opens at 8.6 below it, so it sells at the open.
    code, out, err = run(["hand.csv", *B, "--atr-stop", "--atr-mult", "1", "--atr-period", "3"], capsys)
    assert (code, err) == (0, "")
    assert fill_lines(out)[1].split() == [
        "#2", "bar", "7", "SELL", "90", "@", "8.60", "value", "774.00", "cost", "0.00", "cash", "784.00", "atr"
    ]
    assert "  Exits:       atr 1 x ATR(3) below entry" in out.splitlines()


def test_works_next_to_stop_loss_take_profit_and_trailing_stop(folder, capsys):
    # stop 20 % -> 8.80, trail 30 % -> 13 * 0.7 = 9.10, atr -> 8.22: the trail is highest.
    # Bar 7 opens at 8.6, below 9.10 -> trail at the open.
    code, out, err = run(
        ["hand.csv", *B, *ATR, "--stop-loss", "20", "--trailing-stop", "30", "--take-profit", "25"], capsys
    )
    assert (code, err) == (0, "")
    assert fill_lines(out)[1].split()[-3:] == ["cash", "784.00", "trail"]
    assert (
        "  Exits:       stop 20.00% below entry, trail 30.00% below the highest high since entry, "
        "atr 2 x ATR(3) below entry, target 25.00% above entry (the highest of stop, trail and atr is used, "
        "in that order on a tie; it wins if a bar also touches the target)"
    ) in out.splitlines()
    # Without the other exits the atr level sells, as in the hand case.
    assert fill_lines(run(["hand.csv", *B, *ATR, "--take-profit", "25"], capsys)[1]) == FILL_LINES_HAND


def test_with_fill_open_the_signal_sell_at_the_open_comes_first(folder, capsys):
    code, out, err = run(["hand.csv", *B, *ATR, "--fill", "open"], capsys)
    assert (code, err) == (0, "")
    assert [line.split()[-1] for line in fill_lines(out)] == ["signal", "signal"]
    assert fill_lines(out)[0].split()[4:7] == ["92", "@", "10.80"]
    assert fill_lines(out)[1].split()[4:7] == ["92", "@", "8.60"]


def test_export_says_atr(folder, capsys):
    code, out, err = run(["hand.csv", *B, *ATR, "--export", "E.csv"], capsys)
    assert (code, err) == (0, "")
    assert "  Exported:    8 rows to E.csv" in out.splitlines()
    assert (folder / "E.csv").read_text() == (
        "bar,date,close,signal,action,shares,price,value,cost,cash,position,equity,drawdown_pct,buy_hold_equity,reason\n"
        "0,2026-01-01,10.00,HOLD,,,,,,1000.00,0,1000.00,0.00,1000.00,\n"
        "1,2026-01-02,9.00,HOLD,,,,,,1000.00,0,1000.00,0.00,900.00,\n"
        "2,2026-01-03,8.00,HOLD,,,,,,1000.00,0,1000.00,0.00,800.00,\n"
        "3,2026-01-04,9.00,BUY,,,,,,1000.00,0,1000.00,0.00,900.00,\n"
        "4,2026-01-05,11.00,HOLD,BUY,90,11.00,990.00,0.00,10.00,90,1000.00,0.00,1100.00,signal\n"
        "5,2026-01-06,12.00,HOLD,,,,,,10.00,90,1090.00,0.00,1200.00,\n"
        "6,2026-01-07,10.00,SELL,,,,,,10.00,90,910.00,-16.51,1000.00,\n"
        "7,2026-01-08,8.00,HOLD,SELL,90,8.22,740.00,0.00,750.00,0,750.00,-31.19,800.00,atr\n"
    )


def test_chart_marks_the_atr_sell(folder, capsys):
    code, out, _ = run(["hand.csv", *B, *ATR, "--chart"], capsys)
    assert code == 0 and "Chart:   close, 8 bars, B = buy, S = sell" in out.splitlines()


# --------------------------------------------------------------------------- usage errors (exit 2)


@pytest.mark.parametrize("option, value", [("--atr-mult", "3"), ("--atr-period", "5")])
def test_atr_options_need_risk_pct_or_atr_stop(folder, capsys, option, value):
    message = f"{option} only makes sense together with --risk-pct or --atr-stop"
    usage_error(["hand.csv", *B, option, value], capsys, message)
    usage_error(["hand.csv", option, value], capsys, message)  # without --backtest too
    for extra in (["--risk-pct", "2"], ["--atr-stop"], ["--risk-pct", "2", "--atr-stop"]):
        code, _, err = run(["hand.csv", *B, *extra, option, value], capsys)
        assert (code, err) == (0, ""), extra


def test_atr_stop_needs_backtest(folder, capsys):
    usage_error(["hand.csv", "--atr-stop"], capsys, "--atr-stop only makes sense together with --backtest")
    usage_error(["hand.csv", "--atr-stop", "--atr-mult", "3"], capsys, "--atr-stop only makes sense together with --backtest")


def test_atr_stop_with_resample(folder, capsys):
    usage_error(["closes.csv", *B, "--atr-stop", "--resample", "weekly"], capsys, "--atr-stop cannot be combined with --resample yet")


def test_atr_stop_not_with_scan(folder, capsys):
    code, out, err = run(["--scan", "scan", "--atr-stop"], capsys)
    assert (code, out) == (2, "")
    assert err.endswith("trading_assistant.cli: error: --atr-stop cannot be combined with --scan\n")


def test_atr_stop_takes_no_value(folder, capsys):
    usage_error(["hand.csv", *B, "--atr-stop=1"], capsys, "argument --atr-stop: ignored explicit argument '1'")


@pytest.mark.parametrize(
    "extra, message",
    [
        (["--atr-mult", "0"], "--atr-mult must be above 0, got 0"),
        (["--atr-mult", "-2"], "--atr-mult must be above 0, got -2"),
        (["--atr-mult", "nan"], "--atr-mult must be above 0, got nan"),
        (["--atr-period", "0"], "--atr-period must be a whole number of at least 1, got 0"),
        (["--atr-period", "1.5"], "argument --atr-period: invalid int value: '1.5'"),
    ],
)
def test_atr_settings_are_range_checked_with_atr_stop_alone(folder, capsys, extra, message):
    usage_error(["hand.csv", *B, "--atr-stop", *extra], capsys, message)


# --------------------------------------------------------------------------- data errors (exit 1)


def test_atr_stop_needs_a_candle_file_like_stop_loss(folder, capsys):
    code, out, err = run(["closes.csv", *B, "--atr-stop"], capsys)
    assert (code, out) == (1, "")
    assert err.startswith("Error: closes.csv has no 'open', 'high', 'low', 'volume' columns")
    assert (code, out, err) == run(["closes.csv", *B, "--stop-loss", "5"], capsys)


# --------------------------------------------------------------------------- help and usage


def _option_blocks(help_text):
    """{first option string: its help block, whitespace collapsed} for the options section."""
    section = help_text.split("\noptions:\n", 1)[1].split("\n\n", 1)[0]
    blocks = re.split(r"\n(?=  -)", section)
    return {block.split()[0].rstrip(","): " ".join(block.split()) for block in blocks}


def test_help_lists_atr_stop_between_atr_period_and_export(folder, capsys):
    _, out, _ = run(["--help"], capsys)
    starts = [line.split()[0] for line in out.splitlines() if line.startswith("  --")]
    i = starts.index("--atr-stop")
    assert starts[i - 1 : i + 3] == ["--atr-period", "--atr-stop", "--cooldown", "--min-hold"]


def test_help_describes_the_option(folder, capsys):
    _, out, _ = run(["--help"], capsys)
    text = _option_blocks(out)["--atr-stop"]
    assert text.startswith("--atr-stop with --backtest, sell when a bar's low reaches the entry price less --atr-mult")
    assert "A buy signal with no ATR yet (or an ATR of 0) is skipped and counted in the report" in text
    assert "(on a tie the stop, then the trail, then atr)" in text and "its fills say atr" in text
    assert "(with or without --risk-pct) it is the distance of the ATR stop" in _option_blocks(out)["--atr-mult"]
    assert _option_blocks(out)["--atr-period"].endswith("uses the same ATR")


def test_usage_line_is_unchanged(folder, capsys):
    _, out, _ = run(["--help"], capsys)
    assert out.startswith(BEFORE_USAGE)
    assert "--atr-stop" not in BEFORE_USAGE


def test_help_only_changes_the_atr_options(folder, capsys):
    # Every other option's help is word for word as before and --atr-stop is new. --atr-period only
    # gains a sentence at the end. --risk-pct and --atr-mult now say what changes with --atr-stop
    # (so that each sentence is true with neither, either or both options); the sentences the
    # risk sizing tests pin are still there word for word.
    _, out, _ = run(["--help"], capsys)
    before, now = _option_blocks(BEFORE_HELP), _option_blocks(out)
    expected = [*list(before)[: list(before).index("--export")], "--atr-stop", "--cooldown", "--min-hold", "--max-hold", "--max-drawdown", "--breakeven", "--max-losses", "--scale-out", "--add-on", "--max-adds", *list(before)[list(before).index("--export") :]]
    expected = [*expected[: expected.index("--stats") + 1], "--trade-list", *expected[expected.index("--stats") + 1 :]]
    assert list(now) == [*expected[: expected.index("--chart") + 1], "--explain", *expected[expected.index("--chart") + 1 :]]
    for option, text in before.items():
        if option == "--atr-period":
            assert now[option].startswith(text) and now[option] != text, option
        elif option not in ("--risk-pct", "--atr-mult"):
            assert now[option] == text, option
    assert "This only sets the number of shares: no stop is placed, so a loss is not limited to PCT% (--atr- stop adds a stop" in now["--risk-pct"]
    assert "even then a gap, slippage, fees or a later buy into the position can lose more" in now["--risk-pct"]
    assert "without --atr- stop it only sets the number of shares, no stop is placed" in now["--atr-mult"]
    assert out.split("\noptions:\n")[0] == BEFORE_HELP.split("\noptions:\n")[0]
    assert out.split("\n\n")[-1] == BEFORE_HELP.split("\n\n")[-1]  # the disclaimer epilog


# --------------------------------------------------------------------------- commands that worked before: unchanged


@pytest.mark.parametrize("argv, code, out, err, export", BEFORE_RUNS, ids=[" ".join(r[0]) for r in BEFORE_RUNS])
def test_old_commands_print_exactly_the_same(folder, capsys, argv, code, out, err, export):
    argv = [arg for item in argv for arg in (B if item == "*B" else [item])]
    assert run(argv, capsys) == (code, out, err)
    if export is None:
        assert not (folder / "E.csv").exists()
    else:
        assert (folder / "E.csv").read_text() == export


def _value_for(action):
    if action.nargs == 0:
        return []
    if action.choices:
        return [sorted(action.choices)[0]]
    if action.dest == "param":
        return ["a=1"]
    return ["5"]


def _before_meaning(prefix):
    """The option ``prefix`` meant before --atr-stop: itself if exact, the one option it started, else None."""
    if prefix in BEFORE_OPTIONS:
        return prefix
    matches = [o for o in BEFORE_OPTIONS if o.startswith(prefix)]
    return matches[0] if len(matches) == 1 else None


def test_every_shortened_name_that_worked_before_still_means_the_same_option():
    parser = build_parser()
    checked = 0
    for option in BEFORE_OPTIONS:
        if option == "--help":
            continue
        action = parser._option_string_actions[option]
        for n in range(3, len(option) + 1):
            prefix = option[:n]
            if _before_meaning(prefix) != option:
                continue  # ambiguous before, or an exact old option of its own
            args, extra = build_parser().parse_known_args(["x.csv", prefix, *_value_for(action)])
            assert extra == [], prefix
            assert getattr(args, action.dest) != parser.get_default(action.dest), (prefix, option)
            assert args.atr_stop is None, prefix
            checked += 1
    assert checked > 100


def test_shortened_names_that_were_ambiguous_before_are_still_errors(folder, capsys):
    prefixes = sorted({o[:n] for o in BEFORE_OPTIONS for n in range(3, len(o)) if _before_meaning(o[:n]) is None})
    assert {"--atr", "--atr-", "--st", "--r"} <= set(prefixes)
    for prefix in prefixes:
        code, out, err = run(["hand.csv", "--backtest", prefix, "5"], capsys)
        assert (code, out) == (2, ""), prefix
        assert "ambiguous option" in err.splitlines()[-1], prefix


def test_new_shortened_names_mean_atr_stop():
    for prefix in ("--atr-s", "--atr-st", "--atr-sto", "--atr-stop"):
        args, extra = build_parser().parse_known_args(["x.csv", prefix])
        assert extra == [] and args.atr_stop is True, prefix
