"""Runs without --cooldown are unchanged; --help only gains the --cooldown block.

BEFORE_HELP and every BEFORE_RUNS entry were captured from the command before
--cooldown existed (the unchanged code at git HEAD, run with COLUMNS=80).

The hand file is the 11-bar candle file of test_cli_cooldown.py; c.ini holds
``stop_loss = 10``.

One output could not stay the same: the "ambiguous option" message for a
shortened name that now also fits --cooldown, such as --c. It now lists
--cooldown, and the hidden --co alias, the same way --re already shows up
in the message for --r.
"""

import re

import pytest

from trading_assistant.cli import build_parser, main

HAND = """\
date,open,high,low,close,volume
2026-01-01,10,10.5,9.5,10,1000
2026-01-02,9.2,9.5,8.5,9,1000
2026-01-05,8.3,8.5,7.5,8,1000
2026-01-06,8.8,9.5,8.5,9,1000
2026-01-07,10.8,11.5,10.5,11,1000
2026-01-08,11,12,10.8,12,1000
2026-01-09,11.5,12,9.5,10,1000
2026-01-12,9.8,10.2,9.6,10,1000
2026-01-13,10,11.5,9.9,11,1000
2026-01-14,10.8,12.5,10.5,12,1000
2026-01-15,12,12.4,11.8,12.2,1000
"""
CLOSES_ONLY = "date,close\n2026-01-01,10\n2026-01-02,9\n2026-01-05,8\n2026-01-06,9\n2026-01-07,11\n"
B = ["--backtest", "--cash", "1000", "--short", "1", "--long", "2"]

# Option strings the parser knew before --cooldown (including the hidden exact aliases --t and --re).
BEFORE_OPTIONS = [
    "--atr-mult", "--atr-period", "--atr-stop", "--backtest", "--candles", "--cash", "--chart", "--config",
    "--export", "--fee", "--fee-pct", "--fill", "--help", "--json", "--long", "--min-score", "--param",
    "--position-size", "--re", "--report", "--resample", "--risk-pct", "--rsi-period", "--scan", "--short",
    "--slippage", "--stats", "--stop-loss", "--strategy", "--t", "--take-profit", "--top", "--trailing-stop",
]

BEFORE_HELP = (
    'usage: trading_assistant.cli [-h] [--short SHORT] [--long LONG]\n'
    '                             [--rsi-period RSI_PERIOD] [--backtest]\n'
    '                             [--cash AMOUNT] [--fee AMOUNT] [--fee-pct PCT]\n'
    '                             [--slippage PCT] [--position-size FRACTION]\n'
    '                             [--stop-loss PCT] [--take-profit PCT]\n'
    '                             [--export FILE] [--fill {close,open}]\n'
    '                             [--resample {weekly,monthly}]\n'
    '                             [--strategy {sma_cross,rsi_reversion,breakout,ema_cross,momentum,zscore_reversion,hull_trend}]\n'
    '                             [--param KEY=VALUE] [--stats] [--config FILE]\n'
    '                             [--json] [--chart] [--candles] [--scan FOLDER]\n'
    '                             [--min-score N] [--top N] [--report FILE]\n'
    '                             csv_path\n'
    '\n'
    'Suggest BUY/SELL/HOLD from closing prices.\n'
    '\n'
    'positional arguments:\n'
    "  csv_path              CSV file with a 'close' column\n"
    '\n'
    'options:\n'
    '  -h, --help            show this help message and exit\n'
    '  --short SHORT         short SMA window (default: 20)\n'
    '  --long LONG           long SMA window (default: 50)\n'
    '  --rsi-period RSI_PERIOD\n'
    '                        RSI lookback (default: 14)\n'
    '  --backtest            also simulate trading the crossover signal over the\n'
    '                        whole file\n'
    '  --cash AMOUNT         starting cash for --backtest (default: 10,000)\n'
    '  --fee AMOUNT          fixed cost charged on every buy and every sell in\n'
    '                        --backtest (default: 0)\n'
    '  --fee-pct PCT         percentage of traded value charged on every buy and\n'
    '                        sell in --backtest, e.g. 0.1 for 0.1% (default: 0)\n'
    '  --slippage PCT        with --backtest, buys fill this percentage above and\n'
    '                        sells this percentage below the fill price, before\n'
    '                        fees, e.g. 0.1 for 0.1% (default: 0)\n'
    '  --position-size FRACTION\n'
    '                        with --backtest, each buy spends at most this fraction\n'
    '                        of the account value (above 0, at most 1), costs and\n'
    '                        slippage included (default: all the cash)\n'
    "  --stop-loss PCT       with --backtest, sell when a bar's low reaches the\n"
    '                        entry price less PCT% (reads a candle file; cannot be\n'
    '                        combined with --resample yet)\n'
    "  --take-profit PCT     with --backtest, sell when a bar's high reaches the\n"
    '                        entry price plus PCT% (reads a candle file; cannot be\n'
    '                        combined with --resample yet); if a bar touches both\n'
    '                        levels the stop wins\n'
    "  --trailing-stop PCT   with --backtest, sell when a bar's low reaches the\n"
    "                        highest high since entry less PCT% (the bar's own high\n"
    '                        is not used; reads a candle file; cannot be combined\n'
    '                        with --resample yet); works next to --stop-loss and\n'
    '                        --take-profit: the higher of the stop and trail levels\n'
    '                        is used, and it wins over the target if a bar touches\n'
    '                        both\n'
    '  --risk-pct PCT        with --backtest, size each buy by risk: PCT% of the\n'
    '                        account value (above 0, at most 100) divided by a stop\n'
    '                        distance of --atr-mult times the ATR (--atr-period\n'
    '                        bars) on the bar the buy signal came on, rounded down\n'
    '                        to whole shares; with --position-size the smaller size\n'
    '                        wins. A buy that gets 0 shares this way (no ATR yet,\n'
    '                        or under one share) is skipped and counted in the\n'
    '                        report. This only sets the number of shares: no stop\n'
    '                        is placed, so a loss is not limited to PCT% (--atr-\n'
    '                        stop adds a stop at the distance of the buy that\n'
    '                        opened the position; even then a gap, slippage, fees\n'
    '                        or a later buy into the position can lose more). Works\n'
    '                        next to --stop-loss, --take-profit and --trailing-\n'
    '                        stop, and next to --atr-stop (reads a candle file;\n'
    '                        cannot be combined with --resample yet)\n'
    '  --atr-mult N          with --risk-pct, the stop distance used for sizing is\n'
    '                        N times the ATR (above 0; default: 2); without --atr-\n'
    '                        stop it only sets the number of shares, no stop is\n'
    '                        placed. With --atr-stop (with or without --risk-pct)\n'
    '                        it is the distance of the ATR stop, taken on the buy\n'
    '                        that opened the position\n'
    '  --atr-period N        with --risk-pct, the number of bars in the ATR (a\n'
    '                        whole number of at least 1; default: 14); --atr-stop\n'
    '                        uses the same ATR\n'
    "  --atr-stop            with --backtest, sell when a bar's low reaches the\n"
    '                        entry price less --atr-mult times the ATR (--atr-\n'
    '                        period bars) on the bar the buy signal came on; that\n'
    '                        distance is fixed when the position opens, and a later\n'
    '                        buy moves the level with the average entry price only.\n'
    '                        A buy signal with no ATR yet (or an ATR of 0) is\n'
    '                        skipped and counted in the report. Works next to\n'
    '                        --stop-loss, --trailing-stop and --take-profit: the\n'
    '                        highest stop level is used (on a tie the stop, then\n'
    '                        the trail, then atr) and it wins over the target if a\n'
    '                        bar touches both; its fills say atr. With --risk-pct a\n'
    "                        position's first buy is sized on the same distance the\n"
    '                        stop uses; a gap, slippage, fees or a later buy (sized\n'
    "                        on its own signal bar's ATR) can still lose more than\n"
    '                        the risk (reads a candle file; cannot be combined with\n'
    '                        --resample yet)\n'
    '  --export FILE         with --backtest, write one CSV row per bar (account\n'
    '                        value, signal, fills) to FILE\n'
    '  --fill {close,open}   with --backtest, the price of the next bar a signal is\n'
    '                        filled at (default: close); open reads the file as a\n'
    '                        candle file and cannot be combined with --resample yet\n'
    '  --resample {weekly,monthly}\n'
    '                        reduce daily bars to weekly or monthly bars before\n'
    "                        analysing (needs a 'date' column)\n"
    '  --strategy {sma_cross,rsi_reversion,breakout,ema_cross,momentum,zscore_reversion,hull_trend}\n'
    '                        rule traded by --backtest (default: sma_cross); does\n'
    '                        not change the Signal line\n'
    '  --param KEY=VALUE     override a strategy parameter in --backtest, e.g.\n'
    '                        window=10 (repeatable)\n'
    '  --stats               with --backtest, also print the risk and return\n'
    '                        statistics block\n'
    '  --config FILE         read defaults from an INI file; flags win over the\n'
    '                        file (no file is read unless this is given or\n'
    '                        $TRADING_ASSISTANT_CONFIG is set)\n'
    '  --json                print the report as one JSON object on stdout instead\n'
    '                        of text (cannot be combined with --chart)\n'
    '  --chart               print a text chart of the closes after the report\n'
    '                        (fills marked B and S with --backtest)\n'
    '  --candles             read the file as a candle file (date, open, high, low,\n'
    '                        close, volume) and analyse its closes; cannot be\n'
    '                        combined with --resample yet\n'
    '  --scan FOLDER         instead of one price file, give the combined score of\n'
    '                        every .csv file directly inside FOLDER (cannot be\n'
    '                        combined with a price file or backtest options)\n'
    '  --min-score N         with --scan, keep only the files scoring N or more\n'
    '  --top N               with --scan, show only the first N rows (after --min-\n'
    '                        score)\n'
    '  --report FILE         with --scan, also write a Markdown report to FILE (the\n'
    '                        screen output does not change)\n'
    '\n'
    'Research aid only. Not financial advice.\n'
)

BEFORE_RUNS = [
    (
        ['hand.csv', '--backtest', '--cash', '1000', '--short', '1', '--long', '2'],
        0,
        (
            'Bars:    11\n'
            'Last:    12.20\n'
            'Signal:  HOLD\n'
            'RSI:     n/a\n'
            'Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n'
            '  Start cash:  1,000.00\n'
            '  Trades:      3 (2 buy, 1 sell)\n'
            '  Fills (bar index is 0-based):\n'
            '    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00\n'
            '    #2   bar 7     SELL       90 @      10.00  value       900.00  cost     0.00  cash       910.00\n'
            '    #3   bar 9     BUY        75 @      12.00  value       900.00  cost     0.00  cash        10.00\n'
            '  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n'
            '  Round trips: 1 completed, 0 made money (0%)\n'
            '  Comparison              Strategy    Buy & hold\n'
            '    End equity              925.00      1,220.00\n'
            '    Return                  -7.50%       +22.00%\n'
            '    Max drawdown           -16.51%       -20.00%\n'
            '    Trades                       3             1\n'
            '    Costs paid                0.00          0.00\n'
            '  End cash:    10.00\n'
            '  End shares:  75 @ 12.20\n'
            '  End equity:  925.00\n'
            '  Return:      -7.50%\n'
            'Research aid only. Not financial advice.\n'
        ),
        "",
        None,
    ),
    (
        ['hand.csv', '--backtest', '--cash', '1000', '--short', '1', '--long', '2', '--stop-loss', '10'],
        0,
        (
            'Bars:    11\n'
            'Last:    12.20\n'
            'Signal:  HOLD\n'
            'RSI:     n/a\n'
            'Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n'
            '  Start cash:  1,000.00\n'
            '  Trades:      3 (2 buy, 1 sell)\n'
            '  Fills (bar index is 0-based):\n'
            '    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal\n'
            '    #2   bar 6     SELL       90 @       9.90  value       891.00  cost     0.00  cash       901.00  stop\n'
            '    #3   bar 9     BUY        75 @      12.00  value       900.00  cost     0.00  cash         1.00  signal\n'
            '  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n'
            '  Exits:       stop 10.00% below entry\n'
            '  Round trips: 1 completed, 0 made money (0%)\n'
            '  Comparison              Strategy    Buy & hold\n'
            '    End equity              916.00      1,220.00\n'
            '    Return                  -8.40%       +22.00%\n'
            '    Max drawdown           -17.34%       -20.00%\n'
            '    Trades                       3             1\n'
            '    Costs paid                0.00          0.00\n'
            '  End cash:    1.00\n'
            '  End shares:  75 @ 12.20\n'
            '  End equity:  916.00\n'
            '  Return:      -8.40%\n'
            'Research aid only. Not financial advice.\n'
        ),
        "",
        None,
    ),
    (
        ['hand.csv', '--backtest', '--cash', '1000', '--short', '1', '--long', '2', '--stop-loss', '10', '--trailing-stop', '8', '--take-profit', '20', '--fill', 'open', '--export', 'E.csv'],
        0,
        (
            'Bars:    11\n'
            'Last:    12.20\n'
            'Signal:  HOLD\n'
            'RSI:     n/a\n'
            'Backtest: SMA 1/2 crossover, next-bar open fills, whole shares, no shorting\n'
            '  Start cash:  1,000.00\n'
            '  Trades:      3 (2 buy, 1 sell)\n'
            '  Fills (bar index is 0-based):\n'
            '    #1   bar 4     BUY        92 @      10.80  value       993.60  cost     0.00  cash         6.40  signal\n'
            '    #2   bar 6     SELL       92 @      11.04  value     1,015.68  cost     0.00  cash     1,022.08  trail\n'
            '    #3   bar 9     BUY        94 @      10.80  value     1,015.20  cost     0.00  cash         6.88  signal\n'
            '  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n'
            '  Exits:       stop 10.00% below entry, trail 8.00% below the highest high since entry, target 20.00% above entry (the higher of stop and trail is used; it wins if a bar also touches the target)\n'
            '  Round trips: 1 completed, 1 made money (100%)\n'
            '  Comparison              Strategy    Buy & hold\n'
            '    End equity            1,153.68      1,220.00\n'
            '    Return                 +15.37%       +22.00%\n'
            '    Max drawdown            -7.95%       -20.00%\n'
            '    Trades                       3             1\n'
            '    Costs paid                0.00          0.00\n'
            '  End cash:    6.88\n'
            '  End shares:  94 @ 12.20\n'
            '  End equity:  1,153.68\n'
            '  Return:      +15.37%\n'
            '  Exported:    11 rows to E.csv\n'
            'Research aid only. Not financial advice.\n'
        ),
        "",
        (
            'bar,date,close,signal,action,shares,price,value,cost,cash,position,equity,drawdown_pct,buy_hold_equity,reason\n'
            '0,2026-01-01,10.00,HOLD,,,,,,1000.00,0,1000.00,0.00,1000.00,\n'
            '1,2026-01-02,9.00,HOLD,,,,,,1000.00,0,1000.00,0.00,900.00,\n'
            '2,2026-01-05,8.00,HOLD,,,,,,1000.00,0,1000.00,0.00,800.00,\n'
            '3,2026-01-06,9.00,BUY,,,,,,1000.00,0,1000.00,0.00,900.00,\n'
            '4,2026-01-07,11.00,HOLD,BUY,92,10.80,993.60,0.00,6.40,92,1018.40,0.00,1100.00,signal\n'
            '5,2026-01-08,12.00,HOLD,,,,,,6.40,92,1110.40,0.00,1200.00,\n'
            '6,2026-01-09,10.00,SELL,SELL,92,11.04,1015.68,0.00,1022.08,0,1022.08,-7.95,1000.00,trail\n'
            '7,2026-01-12,10.00,HOLD,,,,,,1022.08,0,1022.08,-7.95,1000.00,\n'
            '8,2026-01-13,11.00,BUY,,,,,,1022.08,0,1022.08,-7.95,1100.00,\n'
            '9,2026-01-14,12.00,HOLD,BUY,94,10.80,1015.20,0.00,6.88,94,1134.88,0.00,1200.00,signal\n'
            '10,2026-01-15,12.20,HOLD,,,,,,6.88,94,1153.68,0.00,1220.00,\n'
        ),
    ),
    (
        ['hand.csv', '--backtest', '--cash', '1000', '--short', '1', '--long', '2', '--atr-stop', '--atr-mult', '1', '--atr-period', '1', '--risk-pct', '1', '--stats'],
        0,
        (
            'Bars:    11\n'
            'Last:    12.20\n'
            'Signal:  HOLD\n'
            'RSI:     n/a\n'
            'Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n'
            '  Start cash:  1,000.00\n'
            '  Trades:      3 (2 buy, 1 sell)\n'
            '  Fills (bar index is 0-based):\n'
            '    #1   bar 4     BUY         6 @      11.00  value        66.00  cost     0.00  cash       934.00  signal\n'
            '    #2   bar 6     SELL        6 @       9.50  value        57.00  cost     0.00  cash       991.00  atr\n'
            '    #3   bar 9     BUY         6 @      12.00  value        72.00  cost     0.00  cash       919.00  signal\n'
            '  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n'
            '  Risk sizing: 1.00% of account value at risk per buy, stop distance 1 x ATR(1) (the ATR stop sells at this distance, as of the buy that opened the position, below the average entry price; a gap, slippage, fees or a later buy can lose more)\n'
            '  Exits:       atr 1 x ATR(1) below entry\n'
            '  Round trips: 1 completed, 0 made money (0%)\n'
            '  Comparison              Strategy    Buy & hold\n'
            '    End equity              992.20      1,220.00\n'
            '    Return                  -0.78%       +22.00%\n'
            '    Max drawdown            -1.49%       -20.00%\n'
            '    Trades                       3             1\n'
            '    Costs paid                0.00          0.00\n'
            '  End cash:    919.00\n'
            '  End shares:  6 @ 12.20\n'
            '  End equity:  992.20\n'
            '  Return:      -0.78%\n'
            'Risk and return\n'
            '  Total return:       -0.78%\n'
            '  CAGR:               -17.91%\n'
            '  Volatility (ann.):  8.43%\n'
            '  Sharpe ratio:       -2.30\n'
            '  Sortino ratio:      -2.59\n'
            '  Exposure:           36.36%\n'
            '  Profit factor:      0.00\n'
            '  Average win:        n/a\n'
            '  Average loss:       -9.00\n'
            '  Longest drawdown:   5 bars\n'
            'Research aid only. Not financial advice.\n'
        ),
        "",
        None,
    ),
    (
        ['hand.csv', '--backtest', '--cash', '1000', '--short', '1', '--long', '2', '--stop-loss', '10', '--json'],
        0,
        (
            '{\n'
            '  "bars": 11,\n'
            '  "last_close": 12.2,\n'
            '  "signal": "HOLD",\n'
            '  "rsi": null,\n'
            '  "rsi_label": null,\n'
            '  "backtest": {\n'
            '    "strategy": "sma_cross",\n'
            '    "params": {\n'
            '      "short": 1,\n'
            '      "long": 2\n'
            '    },\n'
            '    "fill": "close",\n'
            '    "start_cash": 1000.0,\n'
            '    "fee": 0.0,\n'
            '    "fee_pct": 0.0,\n'
            '    "slippage_pct": 0.0,\n'
            '    "position_size": null,\n'
            '    "stop_loss_pct": 10.0,\n'
            '    "take_profit_pct": null,\n'
            '    "trades": 3,\n'
            '    "buys": 2,\n'
            '    "sells": 1,\n'
            '    "fills": [\n'
            '      {\n'
            '        "bar": 4,\n'
            '        "side": "BUY",\n'
            '        "shares": 90,\n'
            '        "price": 11.0,\n'
            '        "value": 990.0,\n'
            '        "cost": 0.0,\n'
            '        "cash_after": 10.0,\n'
            '        "reason": "signal"\n'
            '      },\n'
            '      {\n'
            '        "bar": 6,\n'
            '        "side": "SELL",\n'
            '        "shares": 90,\n'
            '        "price": 9.9,\n'
            '        "value": 891.0,\n'
            '        "cost": 0.0,\n'
            '        "cash_after": 901.0,\n'
            '        "reason": "stop"\n'
            '      },\n'
            '      {\n'
            '        "bar": 9,\n'
            '        "side": "BUY",\n'
            '        "shares": 75,\n'
            '        "price": 12.0,\n'
            '        "value": 900.0,\n'
            '        "cost": 0.0,\n'
            '        "cash_after": 1.0,\n'
            '        "reason": "signal"\n'
            '      }\n'
            '    ],\n'
            '    "total_costs": 0.0,\n'
            '    "round_trips": 1,\n'
            '    "winning_round_trips": 0,\n'
            '    "final_cash": 1.0,\n'
            '    "final_position": 75,\n'
            '    "final_price": 12.2,\n'
            '    "final_equity": 916.0,\n'
            '    "return_pct": -8.4,\n'
            '    "max_drawdown_pct": -17.339449541284406,\n'
            '    "benchmark": {\n'
            '      "shares": 100,\n'
            '      "final_cash": 0.0,\n'
            '      "final_equity": 1220.0,\n'
            '      "return_pct": 22.0,\n'
            '      "max_drawdown_pct": -20.0,\n'
            '      "trades": 1,\n'
            '      "total_costs": 0.0\n'
            '    }\n'
            '  },\n'
            '  "disclaimer": "Research aid only. Not financial advice."\n'
            '}\n'
        ),
        "",
        None,
    ),
    (
        ['hand.csv', '--backtest', '--cash', '1000', '--short', '1', '--long', '2', '--co', 'c.ini'],
        0,
        (
            'Bars:    11\n'
            'Last:    12.20\n'
            'Signal:  HOLD\n'
            'RSI:     n/a\n'
            'Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n'
            '  Start cash:  1,000.00\n'
            '  Trades:      3 (2 buy, 1 sell)\n'
            '  Fills (bar index is 0-based):\n'
            '    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal\n'
            '    #2   bar 6     SELL       90 @       9.90  value       891.00  cost     0.00  cash       901.00  stop\n'
            '    #3   bar 9     BUY        75 @      12.00  value       900.00  cost     0.00  cash         1.00  signal\n'
            '  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n'
            '  Exits:       stop 10.00% below entry\n'
            '  Round trips: 1 completed, 0 made money (0%)\n'
            '  Comparison              Strategy    Buy & hold\n'
            '    End equity              916.00      1,220.00\n'
            '    Return                  -8.40%       +22.00%\n'
            '    Max drawdown           -17.34%       -20.00%\n'
            '    Trades                       3             1\n'
            '    Costs paid                0.00          0.00\n'
            '  End cash:    1.00\n'
            '  End shares:  75 @ 12.20\n'
            '  End equity:  916.00\n'
            '  Return:      -8.40%\n'
            'Research aid only. Not financial advice.\n'
        ),
        "",
        None,
    ),
    (
        ['hand.csv', '--stop-loss', '10'],
        2,
        "",
        (
            'usage: trading_assistant.cli [-h] [--short SHORT] [--long LONG]\n'
            '                             [--rsi-period RSI_PERIOD] [--backtest]\n'
            '                             [--cash AMOUNT] [--fee AMOUNT] [--fee-pct PCT]\n'
            '                             [--slippage PCT] [--position-size FRACTION]\n'
            '                             [--stop-loss PCT] [--take-profit PCT]\n'
            '                             [--export FILE] [--fill {close,open}]\n'
            '                             [--resample {weekly,monthly}]\n'
            '                             [--strategy {sma_cross,rsi_reversion,breakout,ema_cross,momentum,zscore_reversion,hull_trend}]\n'
            '                             [--param KEY=VALUE] [--stats] [--config FILE]\n'
            '                             [--json] [--chart] [--candles] [--scan FOLDER]\n'
            '                             [--min-score N] [--top N] [--report FILE]\n'
            '                             csv_path\n'
            'trading_assistant.cli: error: --stop-loss only makes sense together with --backtest\n'
        ),
        None,
    ),
    (
        ['hand.csv', '--backtest', '--cash', '1000', '--short', '1', '--long', '2', '--atr-mult', '3'],
        2,
        "",
        (
            'usage: trading_assistant.cli [-h] [--short SHORT] [--long LONG]\n'
            '                             [--rsi-period RSI_PERIOD] [--backtest]\n'
            '                             [--cash AMOUNT] [--fee AMOUNT] [--fee-pct PCT]\n'
            '                             [--slippage PCT] [--position-size FRACTION]\n'
            '                             [--stop-loss PCT] [--take-profit PCT]\n'
            '                             [--export FILE] [--fill {close,open}]\n'
            '                             [--resample {weekly,monthly}]\n'
            '                             [--strategy {sma_cross,rsi_reversion,breakout,ema_cross,momentum,zscore_reversion,hull_trend}]\n'
            '                             [--param KEY=VALUE] [--stats] [--config FILE]\n'
            '                             [--json] [--chart] [--candles] [--scan FOLDER]\n'
            '                             [--min-score N] [--top N] [--report FILE]\n'
            '                             csv_path\n'
            'trading_assistant.cli: error: --atr-mult only makes sense together with --risk-pct or --atr-stop\n'
        ),
        None,
    ),
    (
        ['hand.csv', '--backtest', '--cash', '1000', '--short', '1', '--long', '2', '--stop-loss', '10', '--resample', 'weekly'],
        2,
        "",
        (
            'usage: trading_assistant.cli [-h] [--short SHORT] [--long LONG]\n'
            '                             [--rsi-period RSI_PERIOD] [--backtest]\n'
            '                             [--cash AMOUNT] [--fee AMOUNT] [--fee-pct PCT]\n'
            '                             [--slippage PCT] [--position-size FRACTION]\n'
            '                             [--stop-loss PCT] [--take-profit PCT]\n'
            '                             [--export FILE] [--fill {close,open}]\n'
            '                             [--resample {weekly,monthly}]\n'
            '                             [--strategy {sma_cross,rsi_reversion,breakout,ema_cross,momentum,zscore_reversion,hull_trend}]\n'
            '                             [--param KEY=VALUE] [--stats] [--config FILE]\n'
            '                             [--json] [--chart] [--candles] [--scan FOLDER]\n'
            '                             [--min-score N] [--top N] [--report FILE]\n'
            '                             csv_path\n'
            'trading_assistant.cli: error: --stop-loss cannot be combined with --resample yet\n'
        ),
        None,
    ),
    (
        ['--scan', 'scan', '--stop-loss', '5'],
        2,
        "",
        (
            'usage: trading_assistant.cli [-h] [--short SHORT] [--long LONG]\n'
            '                             [--rsi-period RSI_PERIOD] [--backtest]\n'
            '                             [--cash AMOUNT] [--fee AMOUNT] [--fee-pct PCT]\n'
            '                             [--slippage PCT] [--position-size FRACTION]\n'
            '                             [--stop-loss PCT] [--take-profit PCT]\n'
            '                             [--export FILE] [--fill {close,open}]\n'
            '                             [--resample {weekly,monthly}]\n'
            '                             [--strategy {sma_cross,rsi_reversion,breakout,ema_cross,momentum,zscore_reversion,hull_trend}]\n'
            '                             [--param KEY=VALUE] [--stats] [--config FILE]\n'
            '                             [--json] [--chart] [--candles] [--scan FOLDER]\n'
            '                             [--min-score N] [--top N] [--report FILE]\n'
            '                             [csv_path]\n'
            'trading_assistant.cli: error: --stop-loss cannot be combined with --scan\n'
        ),
        None,
    ),
    (
        ['closes.csv', '--backtest', '--cash', '1000', '--short', '1', '--long', '2', '--stop-loss', '10'],
        1,
        "",
        (
            "Error: closes.csv has no 'open', 'high', 'low', 'volume' columns (found columns: 'date', 'close'); expected a header row like 'date,open,high,low,close,volume' followed by rows like '2026-01-02,100.5,103.0,99.5,101.5,12000'\n"
        ),
        None,
    ),
]

BEFORE_USAGE = BEFORE_HELP[: BEFORE_HELP.index("csv_path\n") + len("csv_path\n")]


@pytest.fixture
def folder(tmp_path, monkeypatch):
    """A working folder with the hand candle file; the usage line is wrapped at 80 columns."""
    (tmp_path / "hand.csv").write_text(HAND)
    (tmp_path / "closes.csv").write_text(CLOSES_ONLY)
    (tmp_path / "scan").mkdir()
    (tmp_path / "scan" / "a.csv").write_text(CLOSES_ONLY)
    (tmp_path / "c.ini").write_text("[cli]\nstop_loss = 10\n")
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


# --------------------------------------------------------------------------- commands that worked before: unchanged


@pytest.mark.parametrize("argv, code, out, err, export", BEFORE_RUNS, ids=[" ".join(r[0]) for r in BEFORE_RUNS])
def test_old_commands_print_exactly_the_same(folder, capsys, argv, code, out, err, export):
    assert run(argv, capsys) == (code, out, err)
    if export is None:
        assert not (folder / "E.csv").exists()
    else:
        assert (folder / "E.csv").read_text() == export


def test_no_cooldown_line_without_the_option(folder, capsys):
    for argv, *_ in BEFORE_RUNS:
        _, out, _ = run(argv, capsys)
        assert "Cooldown" not in out and "cooldown" not in out, argv


# --------------------------------------------------------------------------- help and usage


def _option_blocks(help_text):
    """{first option string: its help block, whitespace collapsed} for the options section."""
    section = help_text.split("\noptions:\n", 1)[1].split("\n\n", 1)[0]
    blocks = re.split(r"\n(?=  -)", section)
    return {block.split()[0].rstrip(","): " ".join(block.split()) for block in blocks}


def test_usage_line_is_unchanged(folder, capsys):
    _, out, _ = run(["--help"], capsys)
    assert out.startswith(BEFORE_USAGE)
    assert "--cooldown" not in BEFORE_USAGE


def test_help_only_adds_the_cooldown_block_after_atr_stop(folder, capsys):
    code, out, _ = run(["--help"], capsys)
    assert code == 0
    lines = out.splitlines(keepends=True)
    start = lines.index(next(line for line in lines if line.startswith("  --cooldown N")))
    end = lines.index(next(line for line in lines if line.startswith("  --export FILE")))
    t_start = lines.index(next(line for line in lines if line.startswith("  --trade-list ")))  # added later, after --stats
    t_end = lines.index(next(line for line in lines if line.startswith("  --config FILE")))
    e_start = lines.index(next(line for line in lines if line.startswith("  --explain ")))  # added later, after --chart
    e_end = lines.index(next(line for line in lines if line.startswith("  --candles")))
    assert lines[start - 1].strip() != "" and "".join(
        lines[:start] + lines[end:t_start] + lines[t_end:e_start] + lines[e_end:]
    ) == BEFORE_HELP
    starts = [line.split()[0] for line in lines if line.startswith("  --")]
    i = starts.index("--cooldown")
    assert starts[i - 1 : i + 2] == ["--atr-stop", "--cooldown", "--min-hold"]


def test_help_describes_the_option(folder, capsys):
    _, out, _ = run(["--help"], capsys)
    text = _option_blocks(out)["--cooldown"]
    assert text.startswith("--cooldown N with --backtest and one of --stop-loss, --trailing- stop or --atr-stop")
    assert "no buy can fill for the next N bars (a whole number of at least 1)" in text
    assert "A buy due then is dropped, not delayed, and counted in the report" in text
    assert text.endswith("A --take-profit or signal sell starts no cooldown")


def test_usage_errors_still_print_the_old_usage_line(folder, capsys):
    code, out, err = run(["hand.csv", *B, "--cooldown", "0"], capsys)
    assert (code, out) == (2, "")
    assert err == BEFORE_USAGE + (
        "trading_assistant.cli: error: --cooldown only makes sense together with --stop-loss, "
        "--trailing-stop or --atr-stop\n"
    )


# --------------------------------------------------------------------------- shortened option names


def _value_for(action):
    if action.nargs == 0:
        return []
    if action.choices:
        return [sorted(action.choices)[0]]
    if action.dest == "param":
        return ["a=1"]
    return ["5"]


def _before_meaning(prefix):
    """The option ``prefix`` meant before --cooldown: itself if exact, the one option it started, else None."""
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
            assert args.cooldown is None, prefix
            checked += 1
    assert checked > 100


def test_co_still_means_config(folder, capsys):
    # "--co" was a working short name of --config before --cooldown; the hidden exact alias keeps it.
    args = build_parser().parse_args(["x.csv", "--co", "c.ini"])
    assert (args.config, args.cooldown) == ("c.ini", None)
    with_co = run(["hand.csv", *B, "--co", "c.ini"], capsys)
    assert with_co == run(["hand.csv", *B, "--config", "c.ini"], capsys)
    assert with_co[0] == 0 and "  Exits:       stop 10.00% below entry" in with_co[1].splitlines()
    # Its errors still name --config.
    code, out, err = run(["hand.csv", *B, "--co"], capsys)
    assert (code, out) == (2, "")
    assert err.endswith("trading_assistant.cli: error: argument --config: expected one argument\n")


@pytest.mark.parametrize("prefix", ["--coo", "--cool", "--coold", "--cooldo", "--cooldow", "--cooldown"])
def test_new_shortened_names_mean_cooldown(prefix):
    args, extra = build_parser().parse_known_args(["x.csv", prefix, "3"])
    assert extra == [] and args.cooldown == 3 and args.config is None, prefix


def test_single_dash_coo_is_still_unrecognised(folder, capsys):
    code, out, err = run(["hand.csv", *B, "--stop-loss", "10", "-coo", "3"], capsys)
    assert (code, out) == (2, "")
    assert err.endswith("trading_assistant.cli: error: unrecognized arguments: -coo 3\n")


def test_shortened_names_that_were_ambiguous_before_are_still_errors(folder, capsys):
    prefixes = sorted({o[:n] for o in BEFORE_OPTIONS for n in range(3, len(o)) if _before_meaning(o[:n]) is None})
    assert "--c" in prefixes
    for prefix in prefixes:
        code, out, err = run(["hand.csv", "--backtest", prefix, "5"], capsys)
        assert (code, out) == (2, ""), prefix
        assert "ambiguous option" in err.splitlines()[-1], prefix


def test_the_c_message_now_also_lists_cooldown(folder, capsys):
    # The one message that changes: before it read "--c could match --cash, --config, --chart, --candles".
    code, out, err = run(["hand.csv", *B, "--c", "1"], capsys)
    assert (code, out) == (2, "")
    assert err == BEFORE_USAGE + (
        "trading_assistant.cli: error: ambiguous option: --c could match --cash, --cooldown, --config, --co, "
        "--chart, --candles\n"
    )
