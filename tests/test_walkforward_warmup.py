"""Tests for the walk-forward warm-up (``walk_forward(..., warmup=True)``, ``run_backtest(..., warmup_closes=...)``).

Data: tests/data/wf.csv, 18 closes (bar: close):

     0:10  1:11  2:12  3:11  4:10  5:9  6:10  7:11  8:12  9:13  10:12  11:11
    12:10 13:11 14:13 15:14 16:15 17:14

tests/data/wf_before_warmup.json holds the rows ``walk_forward`` returned for these cases before the
option existed; without warm-up the rows must still be exactly those.

Case 1: short 1, long 3, train 12, test 6 (or 4), cash 1000. One window: train 0-11, test 12-17 (12-15).
    Train (same with or without warm-up): BUY signal bar 6, fills bar 7 @ 11; SELL signal bar 10,
    fills bar 11 @ 11: +0.00%. Pair 1/3.
    Without warm-up the first signal needs long + 1 = 4 test bars, so it comes on bar 15 at the earliest:
        bar 15 and 16 HOLD, bar 17 SELL (flat, last bar). 0 trades, +0.00%. With test 4 the only signal
        is on bar 15, the last bar. Buy & hold: 100 @ 10, ends at 14: +40.00% (both).
    With warm-up (bars 9-11 = 13, 12, 11 feed the SMA 3):
        bar 12: close 10 < SMA3 (12 + 11 + 10) / 3 = 11       below
        bar 13: close 11 > SMA3 (11 + 10 + 11) / 3 = 10.67    BUY signal
        bar 14: BUY fills @ 13: int(1000 / 13) = 76 shares = 988, cash 12
        equity 1000, 1000, 1000, 12 + 76 * 14 = 1076, 12 + 76 * 15 = 1152, 1076 (bars 12-17)
        test 6: +7.60%, max drawdown (1076 - 1152) / 1152 = -6.60% (bar 17's SELL signal cannot fill).
        test 4: ends on bar 15 at 1076: +7.60%, max drawdown 0.00% (the 1152 peak is on bar 16,
        outside the block).

Case 2: short 2, long 3, train 6, test 6, cash 1000, fee 1. Two windows: train 0-5 / test 6-11,
    train 6-11 / test 12-17. Pair 2/3 both times, train +0.00% (no fill on the train blocks).
    Without warm-up: 0 trades in both test blocks. Buy & hold: int(999 / 10) = 99 @ 10 = 990 + 1 fee,
    cash 9; window 1 ends 9 + 99 * 11 = 1098 (+9.80%), window 2 ends 9 + 99 * 14 = 1395 (+39.50%).
    With warm-up:
      window 1 (warm-up bars 3-5 = 11, 10, 9): bar 7 SMA2 10.5 > SMA3 10 (bar 6: 9.5 < 9.67) -> BUY signal;
        bar 8 fills @ 12: int(999 / 12) = 83 = 996 + 1 fee, cash 3. Equity 1000, 1000, 999, 1082, 999,
        3 + 83 * 11 = 916: -8.40%, drawdown (916 - 1082) / 1082 = -15.34%. Bar 11's SELL signal is the
        last bar: 83 shares still held at the end.
      window 2 (warm-up bars 9-11 = 13, 12, 11): bar 14 SMA2 12 > SMA3 11.33 (bar 13: 10.5 < 10.67) -> BUY
        signal; bar 15 fills @ 14: int(999 / 14) = 71 = 994 + 1 fee, cash 5. Equity 1000, 1000, 1000, 999,
        1070, 999: -0.10%, drawdown (999 - 1070) / 1070 = -6.64%. 71 shares still held at the end.

Case 3 (fallback): short 1, long 5, train 3, test 7, cash 1000. Two windows: train 0-2 / test 3-9,
    train 7-9 / test 10-16. Pair 1/5 both times (no fill on 3 train bars).
    Window 1 wants 5 warm-up bars but only bars 0-2 (10, 11, 12) come before bar 3: those 3 are used.
        bar 7: close 11 > SMA5 of bars 3-7 (11 + 10 + 9 + 10 + 11) / 5 = 10.2, bar 6: 10 < SMA5 of bars 2-6
        (12 + 11 + 10 + 9 + 10) / 5 = 10.4 -> BUY signal. It needs bar 2, a warm-up bar: without warm-up the
        first signal comes on test bar 5 (bar 8). Bar 8 fills @ 12: int(1000 / 12) = 83 = 996, cash 4; ends
        on bar 9 at 4 + 83 * 13 = 1083: +8.30%, 1 trade (0 trades, +0.00% without warm-up).
    Window 2 has its full 5 warm-up bars (5-9 = 9, 10, 11, 12, 13): bar 14: 13 > SMA5 of bars 10-14
        (12 + 11 + 10 + 11 + 13) / 5 = 11.4, bar 13: 11 < SMA5 of bars 9-13 (13 + 12 + 11 + 10 + 11) / 5 = 11.4
        -> BUY signal; bar 15 fills @ 14: int(1000 / 14) = 71 = 994, cash 6; ends on bar 16 at
        6 + 71 * 15 = 1071: +7.10%, 1 trade (0 trades without warm-up).

A crossing on the last warm-up bar is not acted on: with 2/3, bar 7 is a BUY crossing; a test block
starting at bar 8 with bars 4-7 as warm-up (long + 1 = 4 bars, enough to see that crossing) must not buy
on bar 8 (and has no other BUY up to bar 13). ``walk_forward`` itself passes only ``long`` warm-up bars,
one too few to see a crossing on the last of them, so this is checked on ``run_backtest`` directly.
"""

import json
from pathlib import Path

import pytest

from trading_assistant import backtest as _backtest
from trading_assistant.cli import load_price_table
from trading_assistant.walkforward import walk_forward

DATA = Path(__file__).resolve().parent / "data"
A = pytest.approx
_, CLOSES = load_price_table(DATA / "wf.csv")
BEFORE = json.loads((DATA / "wf_before_warmup.json").read_text())
CHOICE = ("window", "train_start", "train_end", "test_start", "test_end", "short", "long", "train_return_pct")


def spy_backtests(monkeypatch):
    """Record every ``run_backtest`` call ``walk_forward`` makes: (warmup_closes, result)."""
    calls = []
    real = _backtest.run_backtest

    def spy(*args, **kwargs):
        result = real(*args, **kwargs)
        calls.append((kwargs.get("warmup_closes"), result))
        return result

    monkeypatch.setattr(_backtest, "run_backtest", spy)
    return calls


def fills(result, test_start):
    """Fills as (bar in CLOSES, side, shares, price, cash after)."""
    return [(test_start + t.bar, t.side, t.shares, A(t.price), A(t.cash_after)) for t in result.trades]


@pytest.mark.parametrize("test, drawdown", [(6, -6.60), (4, 0.00)])
def test_short_1_long_3_one_window(monkeypatch, test, drawdown):
    args = (CLOSES, [1], [3], 12, test)
    plain = walk_forward(*args, cash=1000)
    assert plain == walk_forward(*args, cash=1000, warmup=False) == BEFORE[f"user_test_{test}"]
    (row,) = plain
    assert (row["short"], row["long"], row["test_trades"]) == (1, 3, 0)
    assert row["test_return_pct"] == 0.0 and row["buy_hold_return_pct"] == A(40.0)

    calls = spy_backtests(monkeypatch)
    (warm,) = walk_forward(*args, cash=1000, warmup=True)
    (warmup_closes, result), = calls
    assert warmup_closes == [13.0, 12.0, 11.0]  # bars 9-11
    assert {k: warm[k] for k in CHOICE} == {k: row[k] for k in CHOICE}  # same pair, chosen on train bars
    assert warm["test_trades"] == 1
    assert fills(result, 12) == [(14, "BUY", 76, 13.0, 12.0)]
    assert result.final_equity == A(1076.0)
    assert round(warm["test_return_pct"], 2) == 7.60
    assert round(warm["test_max_drawdown_pct"], 2) == drawdown
    assert warm["buy_hold_return_pct"] == row["buy_hold_return_pct"]


def test_short_2_long_3_two_windows_with_fee(monkeypatch):
    args = (CLOSES, [2], [3], 6, 6)
    plain = walk_forward(*args, cash=1000, fee=1)
    assert plain == walk_forward(*args, cash=1000, fee=1, warmup=False) == BEFORE["own_2_windows_fee"]
    assert [r["test_trades"] for r in plain] == [0, 0]
    assert [r["buy_hold_return_pct"] for r in plain] == [A(9.8), A(39.5)]

    calls = spy_backtests(monkeypatch)
    warm = walk_forward(*args, cash=1000, fee=1, warmup=True)
    assert [{k: w[k] for k in CHOICE} for w in warm] == [{k: p[k] for k in CHOICE} for p in plain]
    assert [c[0] for c in calls] == [[11.0, 10.0, 9.0], [13.0, 12.0, 11.0]]
    (_, r1), (_, r2) = calls
    assert fills(r1, 6) == [(8, "BUY", 83, 12.0, 3.0)]
    assert fills(r2, 12) == [(15, "BUY", 71, 14.0, 5.0)]
    assert [d.equity for d in r1.daily] == A([1000, 1000, 999, 1082, 999, 916])
    assert [d.equity for d in r2.daily] == A([1000, 1000, 1000, 999, 1070, 999])
    assert (r1.final_position, r2.final_position) == (83, 71)  # still held at the end, marked at the last close
    assert [round(w["test_return_pct"], 2) for w in warm] == [-8.40, -0.10]
    assert [round(w["test_max_drawdown_pct"], 2) for w in warm] == [-15.34, -6.64]
    assert [w["test_trades"] for w in warm] == [1, 1]
    assert [w["buy_hold_return_pct"] for w in warm] == [p["buy_hold_return_pct"] for p in plain]

    # Bar 7 is a BUY crossing (SMA2 10.5 > SMA3 10, bar 6: 9.5 < 9.67), visible from the 4 warm-up bars 4-7.
    # As the last warm-up bar of a block starting at bar 8 it is not acted on: no buy on bar 8, and no
    # other BUY up to bar 13.
    edge = _backtest.run_backtest(CLOSES[8:14], initial_cash=1000, short=2, long=3, warmup_closes=CLOSES[4:8])
    assert edge.trades == [] and edge.final_equity == A(1000.0)


def test_bad_warmup_inputs():
    with pytest.raises(ValueError, match="warmup must be True or False"):
        walk_forward(CLOSES, [1], [3], 12, 6, warmup=1)
    with pytest.raises(ValueError, match="warm-up bar 1: price must be positive"):
        _backtest.run_backtest(CLOSES[12:], short=1, long=3, warmup_closes=[11.0, 0.0, 12.0])


def test_fallback_to_the_bars_back_to_bar_0(monkeypatch):
    args = (CLOSES, [1], [5], 3, 7)
    plain = walk_forward(*args, cash=1000)
    assert [(r["test_start"], r["test_trades"], r["test_return_pct"]) for r in plain] == [(3, 0, 0.0), (10, 0, 0.0)]

    calls = spy_backtests(monkeypatch)
    warm = walk_forward(*args, cash=1000, warmup=True)
    assert [{k: w[k] for k in CHOICE} for w in warm] == [{k: p[k] for k in CHOICE} for p in plain]
    # Window 1: only bars 0-2 exist before bar 3, not the 5 that long = 5 asks for; window 2 gets its full 5.
    assert [c[0] for c in calls] == [CLOSES[0:3], CLOSES[5:10]] == [[10.0, 11.0, 12.0], [9.0, 10.0, 11.0, 12.0, 13.0]]
    (_, r1), (_, r2) = calls
    assert fills(r1, 3) == [(8, "BUY", 83, 12.0, 4.0)]
    assert fills(r2, 10) == [(15, "BUY", 71, 14.0, 6.0)]
    assert [round(w["test_return_pct"], 2) for w in warm] == [8.30, 7.10]
    assert [w["test_trades"] for w in warm] == [1, 1]
    assert [w["buy_hold_return_pct"] for w in warm] == [p["buy_hold_return_pct"] for p in plain]
