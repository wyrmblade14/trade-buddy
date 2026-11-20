"""The walk-forward engine for any strategy: one value checked on its own, the parameter grid, the grid sweep
and ``walk_forward(..., strategy=, grid=, params=)``.

Hand-worked cases use tests/data/wf.csv, 18 closes (bars 0-17: 10, 11, 12, 11, 10, 9, 10, 11, 12, 13, 12, 11,
10, 11, 13, 14, 15, 14), cash 1000; a signal on bar t fills at the close of bar t + 1, and a BUY while holding
spends the cash that is left.
"""

from pathlib import Path

import pytest

from trading_assistant import backtest as _backtest
from trading_assistant.backtest import run_backtest, run_buy_and_hold
from trading_assistant.cli import load_price_table
from trading_assistant.samples import sideways
from trading_assistant.strategies import STRATEGIES, check_param_value, first_signal_bars
from trading_assistant.sweep import grid_combinations, sweep, sweep_grid
from trading_assistant.walkforward import run_walk_forward, summarize, walk_forward

WF = load_price_table(str(Path(__file__).resolve().parent / "data" / "wf.csv"))[1]
A = pytest.approx


def test_check_param_value_one_value_on_its_own():
    for name, key, value in [
        ("sma_cross", "short", 1), ("sma_cross", "long", 1),  # short < long is not a one-value rule
        ("breakout", "window", 500), ("zscore_reversion", "window", 2), ("rsi_reversion", "oversold", 0),
        ("rsi_reversion", "overbought", 100), ("rsi_reversion", "oversold", 80), ("momentum", "threshold", -3.5),
        ("zscore_reversion", "entry", 1), ("zscore_reversion", "exit", -1.0),
    ]:
        check_param_value(name, key, value)  # no error
    for name, key, value, message in [
        ("breakout", "window", 0, "window must be a whole number of at least 1, got 0"),
        ("hull_trend", "window", 2.0, "window must be a whole number of at least 1, got 2.0"),
        ("rsi_reversion", "period", True, "period must be a whole number of at least 1, got True"),
        ("sma_cross", "short", -5, "short window must be a whole number of at least 1, got -5"),
        ("ema_cross", "long", 0, "long window must be a whole number of at least 1, got 0"),
        ("zscore_reversion", "window", 1, "window must be at least 2 for a z-score, got 1"),
        ("rsi_reversion", "oversold", -0.5, "oversold must be from 0 to 100, got -0.5"),
        ("rsi_reversion", "overbought", 101, "overbought must be from 0 to 100, got 101"),
        ("momentum", "threshold", float("nan"), "threshold must be a finite number, got nan"),
        ("zscore_reversion", "entry", float("-inf"), "entry must be a finite number, got -inf"),
        ("breakout", "period", 5, "unknown parameter 'period' for strategy 'breakout'; choose from: window"),
        ("nope", "window", 5, "unknown strategy 'nope'; choose from: " + ", ".join(STRATEGIES)),
    ]:
        with pytest.raises(ValueError) as info:
            check_param_value(name, key, value)
        assert str(info.value) == message, (name, key, value)


def test_grid_combinations_order_repeats_and_skipped_combinations():
    # Registry order is period, oversold, overbought, whatever the order of the dicts. Values are tried once,
    # smallest first. (40, 35) breaks oversold < overbought and is skipped, as the sweep skips short >= long.
    combos = grid_combinations("rsi_reversion", {"overbought": [70, 35], "oversold": [40, 30, 30]}, {"period": 5})
    assert combos == [
        {"period": 5, "oversold": 30, "overbought": 35},
        {"period": 5, "oversold": 30, "overbought": 70},
        {"period": 5, "oversold": 40, "overbought": 70},
    ]
    assert [list(c) for c in combos] == [["period", "oversold", "overbought"]] * 3
    # No grid: one set, the defaults with the fixed values.
    assert grid_combinations("momentum") == [{"window": 20, "threshold": 0.0}]
    assert grid_combinations("momentum", None, {"threshold": 1.5}) == [{"window": 20, "threshold": 1.5}]
    assert grid_combinations("sma_cross", {"short": [5, 2], "long": [3, 10]}) == [
        {"short": 2, "long": 3}, {"short": 2, "long": 10}, {"short": 5, "long": 10}]


def test_grid_combinations_errors():
    for args, message in [
        (("nope", {"window": [5]}), "unknown strategy 'nope'; choose from: " + ", ".join(STRATEGIES)),
        (("breakout", {"period": [5]}), "unknown parameter 'period' for strategy 'breakout'; choose from: window"),
        (("breakout", None, {"size": 5}), "unknown parameter 'size' for strategy 'breakout'; choose from: window"),
        (("breakout", {"window": [5]}, {"window": 6}), "window is both in the grid and a fixed parameter; give only one"),
        (("breakout", {"window": []}), "the grid for window needs at least one value"),
        # one bad value in a list is enough, even when the others are fine
        (("breakout", {"window": [10, 0, 20]}), "window must be a whole number of at least 1, got 0"),
        (("momentum", None, {"window": 0}), "window must be a whole number of at least 1, got 0"),
        (("sma_cross", {"short": [50, 60], "long": [20, 50]}),
         "no parameter combination for sma_cross passes its checks: short window must be smaller than long window"),
        (("zscore_reversion", {"entry": [0.5, 1]}, {"exit": 0.5}),
         "no parameter combination for zscore_reversion passes its checks:"
         " entry must be smaller than exit, got entry=0.5, exit=0.5"),
    ]:
        with pytest.raises(ValueError) as info:
            grid_combinations(*args)
        assert str(info.value) == message, args


def test_sweep_grid_breakout_hand_worked_with_a_tie():
    # Train bars 0-11. window 3: bar 7 (11) is above 10, 9, 10: BUY, 83 @ 12 on bar 8, 4 cash left; held to the
    # end at 11: 917, -8.30%, peak 83 * 13 + 4 = 1,083 on bar 9, drawdown -15.33%.
    # window 4: bar 8 (12) is above 10, 9, 10, 11: 76 @ 13 on bar 9 (12 left); bar 9 (13) again: 1 @ 12 on bar 10;
    # 77 * 11 = 847, -15.30%, and the peak is the starting 1,000, so the drawdown is -15.30% too.
    # window 5: bar 7's 11 is below bar 2's 12; bar 8's 12 is the first close above the previous five (11, 10, 9,
    # 10, 11), so it trades exactly as window 4: the same -15.30% and -15.30%, a tie broken by the smaller window.
    # Windows 1 (-16.60%) and 2 (-24.80%) come last (the engine's figures, not worked by hand).
    rows = sweep_grid(WF[:12], "breakout", {"window": [5, 2, 4, 1, 3, 4]}, cash=1000)
    assert [r["params"] for r in rows] == [{"window": w} for w in (3, 4, 5, 1, 2)]
    assert [round(r["return_pct"], 2) for r in rows] == [-8.3, -15.3, -15.3, -16.6, -24.8]
    assert rows[0]["max_drawdown_pct"] == A((917 - 1083) / 1083 * 100)
    assert (rows[1]["return_pct"], rows[1]["max_drawdown_pct"]) == (rows[2]["return_pct"], rows[2]["max_drawdown_pct"])
    assert [(r["trades"], r["round_trips"], r["win_rate_pct"]) for r in rows] == [
        (1, 0, None), (2, 0, None), (2, 0, None), (4, 2, 0.0), (3, 1, 0.0)]
    assert list(rows[0]) == ["params", "return_pct", "max_drawdown_pct", "trades", "round_trips", "win_rate_pct"]


def test_sweep_grid_for_sma_cross_is_the_sweep():
    closes = sideways()
    for kwargs in ({}, {"cash": 5000, "fee": 1.0, "fee_pct": 0.1}):
        old = sweep(closes, [2, 3, 5], [5, 10, 20], **kwargs)
        new = sweep_grid(closes, "sma_cross", {"short": [2, 3, 5], "long": [5, 10, 20]}, **kwargs)
        assert len(new) == len(old) == 8
        assert new == [{"params": {"short": r["short"], "long": r["long"]},
                        **{k: v for k, v in r.items() if k not in ("short", "long")}} for r in old]


def spy_backtests(monkeypatch):
    calls = []
    real = _backtest.run_backtest

    def spy(prices, **kwargs):
        calls.append(kwargs)
        return real(prices, **kwargs)

    monkeypatch.setattr(_backtest, "run_backtest", spy)
    return calls


def test_walk_forward_breakout_hand_worked_cold_and_warm(monkeypatch):
    # One window, train 0-11, test 12-17 (10, 11, 13, 14, 15, 14). Window 3 is chosen on the train bars (above).
    # Cold: bar 15 (14) is above 10, 11, 13: 66 @ 15 on bar 16 (10 left); bar 16's BUY gets 0 shares at 14.
    # 66 * 14 + 10 = 934: -6.60%, also the drawdown. Warm: first_signal_bars(breakout, 3) - 1 = 3 bars, 9-11
    # (13, 12, 11). Bar 14 (13) is above 11, 10, 11: 71 @ 14 on bar 15 (6 left), worth 1,071 on bar 16 and
    # 1,000 on bar 17: +0.00%, drawdown (1000 - 1071) / 1071.
    calls = spy_backtests(monkeypatch)
    args = (WF, None, None, 12, 6)
    (cold,) = walk_forward(*args, cash=1000, strategy="breakout", grid={"window": [2, 3, 4]})
    (warm,) = walk_forward(*args, cash=1000, strategy="breakout", grid={"window": [2, 3, 4]}, warmup=True)
    assert list(cold) == ["window", "train_start", "train_end", "test_start", "test_end", "params",
                          "train_return_pct", "test_return_pct", "test_max_drawdown_pct", "test_trades",
                          "buy_hold_return_pct"]
    assert cold == {"window": 1, "train_start": 0, "train_end": 12, "test_start": 12, "test_end": 18,
                    "params": {"window": 3}, "train_return_pct": A(-8.3), "test_return_pct": A(-6.6),
                    "test_max_drawdown_pct": A(-6.6), "test_trades": 1, "buy_hold_return_pct": A(40.0)}
    assert warm == {**cold, "test_return_pct": A(0.0), "test_max_drawdown_pct": A((1000 - 1071) / 1071 * 100)}
    # Only the test runs go through backtest.run_backtest (the sweep holds its own reference).
    assert [c.get("warmup_closes") for c in calls] == [None, [13.0, 12.0, 11.0]]
    assert [c["strategy_params"] for c in calls] == [{"window": 3}] * 2


def test_walk_forward_every_strategy_matches_sweep_grid_and_backtest_on_each_slice(monkeypatch):
    closes = sideways()
    grids = {
        "sma_cross": ({"short": [2, 3], "long": [5, 10]}, None),
        "rsi_reversion": ({"period": [3, 5], "oversold": [30, 40]}, {"overbought": 60}),
        "breakout": ({"window": [3, 8]}, None),
        "ema_cross": ({"short": [2, 3]}, {"long": 8}),
        "momentum": ({"window": [3, 6], "threshold": [0, 1.5]}, None),
        "zscore_reversion": ({"window": [5, 10], "entry": [-1.5, -1.0]}, None),
        "hull_trend": ({"window": [4, 9]}, None),
    }
    for name, (grid, params) in grids.items():
        for warmup in (False, True):
            calls = spy_backtests(monkeypatch)
            kwargs = dict(step=15, cash=5000, fee=1.0, fee_pct=0.1, warmup=warmup)
            rows = walk_forward(closes, None, None, 40, 20, strategy=name, grid=grid, params=params, **kwargs)
            assert len(rows) == 7, name  # starts 0, 15, ..., 90: the last test block ends at bar 149
            assert len(calls) == len(rows), name  # only the test runs: the sweep holds its own run_backtest
            for row, call in zip(rows, calls):
                a, b, c, d = row["train_start"], row["train_end"], row["test_start"], row["test_end"]
                best = sweep_grid(closes[a:b], name, grid, params, cash=5000, fee=1.0, fee_pct=0.1)[0]
                assert (row["params"], row["train_return_pct"]) == (best["params"], best["return_pct"]), name
                warm = closes[max(0, c - first_signal_bars(name, best["params"]) + 1) : c] if warmup else None
                assert call.get("warmup_closes") == warm, name
                result = run_backtest(closes[c:d], initial_cash=5000, fee=1.0, fee_pct=0.1, strategy=name,
                                      strategy_params=best["params"], warmup_closes=warm)
                assert (row["test_return_pct"], row["test_max_drawdown_pct"], row["test_trades"]) == (
                    result.return_pct, result.max_drawdown_pct, result.n_trades), name
                bench = run_buy_and_hold(closes[c:d], initial_cash=5000, fee=1.0, fee_pct=0.1).return_pct
                assert row["buy_hold_return_pct"] == bench
            # The choice never sees a test bar: change every bar from window 1's test block on.
            changed = closes[:40] + [x * 1.5 for x in closes[40:]]
            (first, *_) = walk_forward(changed, None, None, 40, 20, strategy=name, grid=grid, params=params, **kwargs)
            assert (first["params"], first["train_return_pct"]) == (rows[0]["params"], rows[0]["train_return_pct"])
            monkeypatch.undo()


def test_walk_forward_sma_cross_through_the_grid_gives_the_old_numbers():
    closes = sideways()
    for warmup in (False, True):
        for kwargs in ({}, {"step": 10, "cash": 5000, "fee": 1.0, "fee_pct": 0.1}):
            old = walk_forward(closes, [2, 3, 5], [5, 10, 20], 40, 20, warmup=warmup, **kwargs)
            new = walk_forward(closes, None, None, 40, 20, warmup=warmup, strategy="sma_cross",
                               grid={"short": [2, 3, 5], "long": [5, 10, 20]}, **kwargs)
            assert new == [{k: ({"short": r["short"], "long": r["long"]} if k == "params" else r[k]) for k in n}
                           for r, n in zip(old, new)]
            assert summarize(new) == summarize(old)


def test_walk_forward_strategy_argument_errors():
    def message(*args, **kwargs):
        with pytest.raises(ValueError) as info:
            walk_forward(*args, **kwargs)
        return str(info.value)

    only = "shorts and longs only apply without a strategy; give its parameters in grid or params"
    assert message(WF, [1], [3], 12, 6, strategy="sma_cross") == only
    assert message(WF, None, [3], 12, 6, strategy="breakout") == only
    assert message(WF, [1], [3], 12, 6, grid={"short": [1]}) == "grid and params need a strategy"
    assert message(WF, [1], [3], 12, 6, params={"short": 1}) == "grid and params need a strategy"
    # The grid is checked before the windows: a bad grid is reported even with too few bars.
    assert message(WF, None, None, 30, 6, strategy="breakout", grid={"window": [0]}) == (
        "window must be a whole number of at least 1, got 0")
    assert message(WF, None, None, 30, 6, strategy="breakout") == (
        "not enough prices for a walk-forward window: 18 bars, need at least train + test = 36")
    assert message(WF, None, None, 12, 6, strategy="breakout", warmup=1) == "warmup must be True or False, got 1"


def test_run_walk_forward_passes_the_strategy_on():
    closes = sideways()
    rows, summary = run_walk_forward(closes, None, None, 40, 20, warmup=True, strategy="momentum",
                                     grid={"window": [3, 6]}, params={"threshold": 0.5})
    assert rows == walk_forward(closes, None, None, 40, 20, warmup=True, strategy="momentum",
                                grid={"window": [3, 6]}, params={"threshold": 0.5})
    assert summary == summarize(rows)
    # As without a strategy, every bar is checked first: a bad bar no window uses is still an error.
    with pytest.raises(ValueError) as info:
        run_walk_forward(closes[:145] + [0.0] + closes[146:], None, None, 40, 20, strategy="breakout")
    assert str(info.value) == "bar 145: price must be positive, got 0.0"
