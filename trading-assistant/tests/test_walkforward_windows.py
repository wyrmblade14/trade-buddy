"""Tests for trading_assistant.walkforward.split_window."""

import pytest

from trading_assistant.walkforward import split_window
from trading_assistant import walkforward
from trading_assistant.backtest import run_backtest
from trading_assistant.backtest import run_buy_and_hold
from trading_assistant.samples import sideways
from trading_assistant.sweep import sweep
from trading_assistant.walkforward import walk_forward
from trading_assistant.walkforward import summarize
from trading_assistant.walkforward import format_walk_forward
from trading_assistant.cli import DISCLAIMER
from trading_assistant.sweep import OVERFIT_WARNING


def test_hand_worked_12_bars_train_5_test_3():
    # step defaults to test = 3, so window k is train [3k, 3k+5), test [3k+5, 3k+8).
    # k=0: (0, 5, 5, 8)   kept
    # k=1: (3, 8, 8, 11)  kept
    # k=2: (6, 11, 11, 14) test would end at 14 > 12, dropped
    assert split_window(12, 5, 3) == [(0, 5, 5, 8), (3, 8, 8, 11)]


def test_step_defaults_to_test():
    assert split_window(12, 5, 3) == split_window(12, 5, 3, step=3)
    assert split_window(12, 5, 3, step=None) == split_window(12, 5, 3, step=3)


def test_window_ending_exactly_at_n_is_kept():
    # Second window's test block ends at 11 == n.
    assert split_window(11, 5, 3) == [(0, 5, 5, 8), (3, 8, 8, 11)]
    # One bar short of a third window: it would end at 14.
    assert split_window(13, 5, 3) == [(0, 5, 5, 8), (3, 8, 8, 11)]
    assert split_window(14, 5, 3) == [(0, 5, 5, 8), (3, 8, 8, 11), (6, 11, 11, 14)]


def test_exactly_one_window():
    assert split_window(8, 5, 3) == [(0, 5, 5, 8)]


def test_too_few_bars_gives_no_windows():
    assert split_window(7, 5, 3) == []
    assert split_window(0, 5, 3) == []


def test_step_smaller_than_test_overlaps_test_blocks():
    assert split_window(10, 5, 3, step=1) == [(0, 5, 5, 8), (1, 6, 6, 9), (2, 7, 7, 10)]


def test_step_larger_than_test_leaves_gaps():
    # Starts at 0, 6, 12; the last test block ends at 12 + 8 = 20 == n.
    assert split_window(20, 5, 3, step=6) == [(0, 5, 5, 8), (6, 11, 11, 14), (12, 17, 17, 20)]


def test_smallest_sizes():
    assert split_window(3, 1, 1) == [(0, 1, 1, 2), (1, 2, 2, 3)]


def test_returns_list_of_tuples():
    out = split_window(12, 5, 3)
    assert isinstance(out, list)
    assert all(isinstance(w, tuple) and len(w) == 4 for w in out)


def test_windows_work_as_slices_and_test_never_sees_train():
    bars = list(range(30))
    for train_start, train_end, test_start, test_end in split_window(len(bars), 7, 4, step=3):
        train_bars = bars[train_start:train_end]
        test_bars = bars[test_start:test_end]
        assert len(train_bars) == 7
        assert len(test_bars) == 4
        assert test_start == train_end
        assert max(train_bars) < min(test_bars)
        assert test_end <= len(bars)


@pytest.mark.parametrize(
    "args",
    [
        (-1, 5, 3),
        (12, 0, 3),
        (12, 5, 0),
        (12, -5, 3),
        (12, 5, 3, 0),
        (12, 5, 3, -1),
        (12.0, 5, 3),
        (12, 5.0, 3),
        (12, 5, 3.0),
        (12, 5, 3, 1.5),
        (True, 5, 3),
        (12, True, 3),
        (12, 5, True),
        (12, 5, 3, True),
        ("12", 5, 3),
        (None, 5, 3),
    ],
)
def test_bad_arguments_raise_value_error(args):
    with pytest.raises(ValueError):
        split_window(*args)


# ------------------------------------------------------------ walk_forward()

# One window: train bars 0-5, test bars 6-11, cash 100, pairs (1, 2) and (1, 3).
# With short 1 the short SMA is the close itself.
#
# Train [10, 9, 10, 12, 14, 14]:
#   (1, 2): bar 2 closes up (10 > 9) after a down bar (9 <= 10): BUY, filled on
#           bar 3 at 12 -> 8 shares for 96, cash 4. No later cross down
#           (bar 5 is flat). 8 * 14 + 4 = 116 -> +16%.
#   (1, 3): first signal bar is 3; the close is already above the 3-bar SMA on
#           bar 2 (10 > 9.67), so there is never a cross up: 0 trades, 0%.
#   Chosen: (1, 2) with a train return of +16%.
# Test [20, 18, 16, 18, 20, 19] with (1, 2) and fresh cash 100:
#   bar 3 closes up (18 > 16) after a down bar: BUY, filled on bar 4 at 20 ->
#   5 shares for 100, cash 0. Bar 5 closes down: SELL signal on the last bar,
#   never filled. Equity 100, 100, 100, 100, 100, 95 -> return -5%,
#   max drawdown -5%, 1 trade.
HAND_TRAIN = [10.0, 9.0, 10.0, 12.0, 14.0, 14.0]
HAND_TEST = [20.0, 18.0, 16.0, 18.0, 20.0, 19.0]


def test_walk_forward_hand_worked():
    out = walk_forward(HAND_TRAIN + HAND_TEST, [1], [2, 3], train=6, test=6, cash=100)
    assert out == [
        {
            "window": 1,
            "train_start": 0,
            "train_end": 6,
            "test_start": 6,
            "test_end": 12,
            "short": 1,
            "long": 2,
            "train_return_pct": pytest.approx(16.0),
            "test_return_pct": pytest.approx(-5.0),
            "test_max_drawdown_pct": pytest.approx(-5.0),
            "test_trades": 1,
            "buy_hold_return_pct": pytest.approx(-5.0),
        }
    ]


def test_walk_forward_keys():
    (row,) = walk_forward(HAND_TRAIN + HAND_TEST, [1], [2, 3], train=6, test=6, cash=100)
    assert list(row) == [
        "window",
        "train_start",
        "train_end",
        "test_start",
        "test_end",
        "short",
        "long",
        "train_return_pct",
        "test_return_pct",
        "test_max_drawdown_pct",
        "test_trades",
        "buy_hold_return_pct",
    ]


def test_walk_forward_matches_sweep_and_backtest_on_each_slice():
    closes = sideways()
    shorts, longs = [2, 3, 5], [5, 10, 20]
    out = walk_forward(closes, shorts, longs, train=40, test=30, step=20, cash=5000, fee=1.0, fee_pct=0.1)
    windows = split_window(len(closes), 40, 30, step=20)
    assert len(out) == len(windows) > 1
    for number, (row, (a, b, c, d)) in enumerate(zip(out, windows), start=1):
        best = sweep(closes[a:b], shorts, longs, cash=5000, fee=1.0, fee_pct=0.1)[0]
        result = run_backtest(closes[c:d], initial_cash=5000, short=best["short"], long=best["long"], fee=1.0, fee_pct=0.1)
        assert row["window"] == number
        assert (row["train_start"], row["train_end"], row["test_start"], row["test_end"]) == (a, b, c, d)
        assert (row["short"], row["long"]) == (best["short"], best["long"])
        assert row["train_return_pct"] == best["return_pct"]
        assert row["test_return_pct"] == result.return_pct
        assert row["test_max_drawdown_pct"] == result.max_drawdown_pct
        assert row["test_trades"] == result.n_trades


def test_walk_forward_passes_only_train_bars_to_sweep_and_only_test_bars_to_backtest(monkeypatch):
    closes = [float(100 + i) for i in range(20)]
    sweep_calls, backtest_calls = [], []
    real_sweep, real_backtest = walkforward._sweep.sweep, walkforward._backtest.run_backtest

    def spy_sweep(prices, *args, **kwargs):
        sweep_calls.append((list(prices), args, kwargs))
        return real_sweep(prices, *args, **kwargs)

    def spy_backtest(prices, **kwargs):
        backtest_calls.append((list(prices), kwargs))
        return real_backtest(prices, **kwargs)

    monkeypatch.setattr(walkforward._sweep, "sweep", spy_sweep)
    monkeypatch.setattr(walkforward._backtest, "run_backtest", spy_backtest)
    out = walk_forward(closes, [1, 2], [3, 4], train=8, test=4, step=5, cash=500, fee=2.0, fee_pct=0.5)

    # Windows: (0, 8, 8, 12), (5, 13, 13, 17); the next would end at 22 > 20.
    assert [(r["train_start"], r["train_end"], r["test_start"], r["test_end"]) for r in out] == [
        (0, 8, 8, 12),
        (5, 13, 13, 17),
    ]
    assert [c[0] for c in sweep_calls] == [closes[0:8], closes[5:13]]
    assert [c[0] for c in backtest_calls] == [closes[8:12], closes[13:17]]
    for _, args, kwargs in sweep_calls:
        assert args == ([1, 2], [3, 4])
        assert kwargs == {"cash": 500, "fee": 2.0, "fee_pct": 0.5}
    for (_, kwargs), row in zip(backtest_calls, out):
        assert kwargs == {"initial_cash": 500, "short": row["short"], "long": row["long"], "fee": 2.0, "fee_pct": 0.5}


def test_walk_forward_choice_never_sees_test_or_later_bars():
    # Changing every bar from the test block on must not change the chosen pair
    # or its train return; only the test numbers may move.
    base = walk_forward(HAND_TRAIN + HAND_TEST, [1], [2, 3], train=6, test=6, cash=100)
    other = walk_forward(HAND_TRAIN + [50.0, 1.0, 50.0, 1.0, 50.0, 1.0], [1], [2, 3], train=6, test=6, cash=100)
    for key in ("short", "long", "train_return_pct"):
        assert other[0][key] == base[0][key]
    assert other[0]["test_return_pct"] != base[0]["test_return_pct"]


def test_walk_forward_step_defaults_to_test():
    closes = sideways()
    assert walk_forward(closes, [2, 3], [5, 10], train=30, test=20) == walk_forward(
        closes, [2, 3], [5, 10], train=30, test=20, step=20
    )


def test_walk_forward_default_cash_is_10000():
    closes = sideways()
    assert walk_forward(closes, [2, 3], [5, 10], train=30, test=20) == walk_forward(
        closes, [2, 3], [5, 10], train=30, test=20, cash=10000
    )


def test_walk_forward_test_block_too_short_to_warm_up_does_not_trade():
    # Long window 3 needs 4 test bars before its first signal and a 5th to fill it.
    out = walk_forward(sideways(), [2], [3], train=20, test=4)
    assert out
    assert all(row["test_trades"] == 0 and row["test_return_pct"] == 0.0 for row in out)


def test_walk_forward_no_windows_raises_one_line_value_error():
    with pytest.raises(ValueError) as info:
        walk_forward(HAND_TRAIN + HAND_TEST, [1], [2, 3], train=8, test=5)
    message = str(info.value)
    assert message == "not enough prices for a walk-forward window: 12 bars, need at least train + test = 13"
    assert "\n" not in message


def test_walk_forward_empty_closes_raises_no_windows_error():
    with pytest.raises(ValueError, match="^not enough prices for a walk-forward window: 0 bars"):
        walk_forward([], [1], [2], train=1, test=1)


def test_walk_forward_bad_window_sizes_raise_split_window_error():
    with pytest.raises(ValueError, match="^train must be a whole number of at least 1, got 0$"):
        walk_forward(HAND_TRAIN + HAND_TEST, [1], [2], train=0, test=3)


def _message(fn, *args, **kwargs):
    with pytest.raises(ValueError) as info:
        fn(*args, **kwargs)
    return str(info.value)


def test_walk_forward_passes_sweep_error_through_unchanged():
    closes = HAND_TRAIN + HAND_TEST
    expected = _message(sweep, closes[0:6], [5], [2])
    assert _message(walk_forward, closes, [5], [2], train=6, test=6) == expected


def test_walk_forward_passes_bad_cash_and_fee_errors_through_unchanged():
    closes = HAND_TRAIN + HAND_TEST
    for kwargs in ({"cash": 0}, {"fee": -1.0}, {"fee_pct": 100.0}):
        expected = _message(sweep, closes[0:6], [1], [2], **kwargs)
        assert _message(walk_forward, closes, [1], [2], train=6, test=6, **kwargs) == expected


def test_walk_forward_passes_bad_price_in_train_block_through_unchanged():
    closes = [10.0, 9.0, -1.0] + HAND_TRAIN[3:] + HAND_TEST
    expected = _message(sweep, closes[0:6], [1], [2])
    assert expected == "bar 2: price must be positive, got -1.0"
    assert _message(walk_forward, closes, [1], [2], train=6, test=6) == expected


def test_walk_forward_passes_bad_price_in_test_block_through_unchanged():
    # The bad price is bar 8 of the file but bar 2 of the test block, which is
    # what run_backtest sees and reports.
    closes = HAND_TRAIN + [20.0, 18.0, 0.0, 18.0, 20.0, 19.0]
    expected = _message(run_backtest, closes[6:12], initial_cash=10000, short=1, long=2)
    assert expected == "bar 2: price must be positive, got 0.0"
    assert _message(walk_forward, closes, [1], [2], train=6, test=6) == expected


def test_walk_forward_buy_hold_hand_worked_with_fee():
    # Test block [20, 18, 16, 18, 20, 19], cash 100, fee 5 per trade.
    # Buy on the first test bar at 20: budget 100 - 5 = 95 -> 4 shares for
    # 80 + 5 = 85, cash 15. Held, never sold (no second fee), marked at the
    # last close: 4 * 19 + 15 = 91 -> -9%.
    # (Without the fee: 5 shares for 100, 5 * 19 = 95 -> -5%, as in the
    # hand-worked test above.)
    (row,) = walk_forward(HAND_TRAIN + HAND_TEST, [1], [2, 3], train=6, test=6, cash=100, fee=5.0)
    assert row["buy_hold_return_pct"] == pytest.approx(-9.0)


def test_walk_forward_buy_hold_matches_run_buy_and_hold_on_each_test_slice():
    closes = sideways()
    out = walk_forward(closes, [2, 3, 5], [5, 10, 20], train=40, test=30, step=20, cash=5000, fee=1.0, fee_pct=0.1)
    assert len(out) > 1
    for row in out:
        bench = run_buy_and_hold(closes[row["test_start"] : row["test_end"]], initial_cash=5000, fee=1.0, fee_pct=0.1)
        assert row["buy_hold_return_pct"] == bench.return_pct


def test_walk_forward_train_tie_is_broken_by_sweep_order_not_by_test_return():
    # Train [10, 10, 10, 10] is flat: neither (1, 3) nor (2, 3) ever crosses,
    # so both make 0 trades, 0% return, 0% drawdown. The sweep's tie-break
    # (drawdown, then smaller short) picks (1, 3).
    # Test [10, 10, 10, 10, 11, 10, 14, 16], cash 100:
    #   (1, 3): BUY on bar 4 (11 > 10.33), filled bar 5 at 10 -> 10 shares;
    #           SELL on bar 5 (10 < 10.33), filled bar 6 at 14 -> cash 140;
    #           BUY on bar 6 (14 > 11.67), filled bar 7 at 16 -> 8 shares,
    #           cash 12. 8 * 16 + 12 = 140 -> +40%, 3 trades.
    #   (2, 3): BUY on bar 4 (10.5 > 10.33), filled bar 5 at 10 -> 10 shares,
    #           never crosses back. 10 * 16 = 160 -> +60%.
    # (2, 3) did better on test, but the choice must stay (1, 3): the test
    # block may not influence which pair is picked.
    train = [10.0] * 4
    test = [10.0, 10.0, 10.0, 10.0, 11.0, 10.0, 14.0, 16.0]
    rows = sweep(train, [1, 2], [3], cash=100)
    assert [(r["short"], r["long"], r["return_pct"]) for r in rows] == [(1, 3, 0.0), (2, 3, 0.0)]
    assert run_backtest(test, initial_cash=100, short=2, long=3).return_pct == pytest.approx(60.0)

    (row,) = walk_forward(train + test, [1, 2], [3], train=4, test=8, cash=100)
    assert (row["short"], row["long"]) == (1, 3)
    assert row["train_return_pct"] == 0.0
    assert row["test_return_pct"] == pytest.approx(40.0)
    assert row["test_trades"] == 3


# --------------------------------------------------------------- summarize()


def _window(test_return_pct, buy_hold_return_pct, test_trades, test_start=0, test_end=0):
    return {"test_return_pct": test_return_pct, "buy_hold_return_pct": buy_hold_return_pct, "test_trades": test_trades, "test_start": test_start, "test_end": test_end}


def test_summarize_hand_worked_three_windows():
    # Test returns 10%, -5%, 20%; buy-and-hold 4%, -8%, 20%; every window traded.
    # Compound test:      1.10 * 0.95 = 1.045;   1.045 * 1.20 = 1.254   -> +25.4%
    # Compound buy-hold:  1.04 * 0.92 = 0.9568;  0.9568 * 1.20 = 1.14816 -> +14.816%
    # Beating buy-hold:   10 > 4 yes, -5 > -8 yes, 20 > 20 no (tie)     -> 2
    # Mean test return:   (10 - 5 + 20) / 3 = 25 / 3                    -> 8.333...%
    out = summarize([_window(10.0, 4.0, 2), _window(-5.0, -8.0, 1), _window(20.0, 20.0, 1)])
    assert out == {
        "windows": 3,
        "compound_test_return_pct": pytest.approx(25.4),
        "compound_buy_hold_return_pct": pytest.approx(14.816),
        "windows_beating_buy_hold": 2,
        "mean_test_return_pct": pytest.approx(25.0 / 3.0),
        "windows_without_trades": 0,
        "test_blocks_contiguous": True,
    }


def test_summarize_keys():
    assert list(summarize([_window(1.0, 0.0, 1)])) == [
        "windows",
        "compound_test_return_pct",
        "compound_buy_hold_return_pct",
        "windows_beating_buy_hold",
        "mean_test_return_pct",
        "windows_without_trades",
        "test_blocks_contiguous",
    ]


def test_summarize_counts_windows_without_trades():
    # A window with no test trades stays at 0%; buy-and-hold of 3% beats it.
    # Compound test: 1.10 * 1.00 * 1.00 = 1.10 -> +10%. Mean (10 + 0 + 0) / 3.
    out = summarize([_window(10.0, 5.0, 2), _window(0.0, 3.0, 0), _window(0.0, -2.0, 0)])
    assert out["windows_without_trades"] == 2
    assert out["windows_beating_buy_hold"] == 2
    assert out["compound_test_return_pct"] == pytest.approx(10.0)
    assert out["mean_test_return_pct"] == pytest.approx(10.0 / 3.0)


def test_summarize_single_window_compound_is_its_own_return():
    out = summarize([_window(-7.5, 12.0, 3)])
    assert out["windows"] == 1
    assert out["compound_test_return_pct"] == pytest.approx(-7.5)
    assert out["compound_buy_hold_return_pct"] == pytest.approx(12.0)
    assert out["mean_test_return_pct"] == pytest.approx(-7.5)
    assert out["windows_beating_buy_hold"] == 0


def test_summarize_compound_differs_from_sum():
    # +50% then -50%: 1.5 * 0.5 = 0.75 -> -25%, while the mean is 0%.
    out = summarize([_window(50.0, 0.0, 1), _window(-50.0, 0.0, 1)])
    assert out["compound_test_return_pct"] == pytest.approx(-25.0)
    assert out["mean_test_return_pct"] == pytest.approx(0.0)


def test_summarize_walk_forward_output():
    rows = walk_forward(sideways(), [2, 3, 5], [5, 10, 20], train=40, test=30, cash=5000, fee=1.0, fee_pct=0.1)
    out = summarize(rows)
    growth = 1.0
    for r in rows:
        growth *= 1 + r["test_return_pct"] / 100
    assert out["windows"] == len(rows) > 1
    assert out["compound_test_return_pct"] == pytest.approx((growth - 1) * 100)
    assert out["mean_test_return_pct"] == pytest.approx(sum(r["test_return_pct"] for r in rows) / len(rows))
    assert out["windows_without_trades"] == sum(1 for r in rows if r["test_trades"] == 0)


def test_summarize_does_not_change_its_input():
    rows = [_window(10.0, 4.0, 2), _window(-5.0, -8.0, 1)]
    copy = [dict(r) for r in rows]
    summarize(rows)
    assert rows == copy


def test_summarize_empty_list_raises_value_error():
    with pytest.raises(ValueError, match="^no walk-forward windows to summarize$"):
        summarize([])


# ------------------------------------------------- summarize(): contiguous blocks


def test_summarize_test_blocks_contiguous_hand_built():
    # Test blocks 30-39, 40-49, 50-59: each starts where the last one ended.
    assert summarize([_window(1.0, 0.0, 1, 30, 40), _window(1.0, 0.0, 1, 40, 50), _window(1.0, 0.0, 1, 50, 60)])[
        "test_blocks_contiguous"
    ] is True
    # 35 < 40: the second block overlaps the first.
    assert summarize([_window(1.0, 0.0, 1, 30, 40), _window(1.0, 0.0, 1, 35, 45)])["test_blocks_contiguous"] is False
    # 41 > 40: bar 40 is in no test block.
    assert summarize([_window(1.0, 0.0, 1, 30, 40), _window(1.0, 0.0, 1, 41, 51)])["test_blocks_contiguous"] is False
    # Only the last join is broken.
    assert summarize(
        [_window(1.0, 0.0, 1, 30, 40), _window(1.0, 0.0, 1, 40, 50), _window(1.0, 0.0, 1, 55, 65)]
    )["test_blocks_contiguous"] is False


def test_summarize_single_window_is_contiguous():
    assert summarize([_window(1.0, 0.0, 1, 30, 40)])["test_blocks_contiguous"] is True


def test_summarize_contiguous_follows_walk_forward_step():
    closes = sideways()
    args = ([2, 3], [5, 10])
    assert summarize(walk_forward(closes, *args, train=30, test=20))["test_blocks_contiguous"] is True
    assert summarize(walk_forward(closes, *args, train=30, test=20, step=20))["test_blocks_contiguous"] is True
    assert summarize(walk_forward(closes, *args, train=30, test=20, step=10))["test_blocks_contiguous"] is False
    assert summarize(walk_forward(closes, *args, train=30, test=20, step=25))["test_blocks_contiguous"] is False


# ---------------------------------------------------------- format_walk_forward()


def _full_window(number, train, test, pair, train_return, test_return, buy_hold, trades):
    return {
        "window": number,
        "train_start": train[0],
        "train_end": train[1],
        "test_start": test[0],
        "test_end": test[1],
        "short": pair[0],
        "long": pair[1],
        "train_return_pct": train_return,
        "test_return_pct": test_return,
        "test_max_drawdown_pct": 0.0,
        "test_trades": trades,
        "buy_hold_return_pct": buy_hold,
    }


# The three-window example: train 30 bars, test 10 bars, step 10 (contiguous).
THREE_WINDOWS = [
    _full_window(1, (0, 30), (30, 40), (5, 20), 12.5, 10.0, 4.0, 2),
    _full_window(2, (10, 40), (40, 50), (10, 30), 8.0, -5.0, -8.0, 1),
    _full_window(3, (20, 50), (50, 60), (5, 20), -3.0, 20.0, 20.0, 1),
]

# Compound test 1.10 * 0.95 * 1.20 = 1.254 -> +25.40%; buy & hold
# 1.04 * 0.92 * 1.20 = 1.14816 -> +14.82%; mean 25 / 3 -> +8.33%;
# beating buy & hold: 10 > 4, -5 > -8, 20 = 20 -> 2 of 3. Bar ranges show both
# ends: train_start 0, train_end 30 is "0-29".
THREE_WINDOWS_TEXT = """\
Walk-forward: 3 windows; each SMA crossover pair was chosen on its train bars only, then run on the test bars after them
Window  Train bars   Test bars    Pair     Train      Test  Buy&Hold Trades
     1        0-29       30-39    5/20   +12.50%   +10.00%    +4.00%      2
     2       10-39       40-49   10/30    +8.00%    -5.00%    -8.00%      1
     3       20-49       50-59    5/20    -3.00%   +20.00%   +20.00%      1
Test return, compounded over the windows: +25.40%
Buy & hold, compounded over the windows:  +14.82%
Mean test return per window: +8.33%
Windows beating buy & hold: 2 of 3
Windows without test trades: 0 of 3
Best in-sample parameters overfit; check them on data they were not chosen on.
Research aid only. Not financial advice."""

GAP_NOTE = (
    "Note: the test blocks overlap or leave gaps (step is not equal to test), so the compounded"
    " figures do not describe one continuous stretch of prices."
)


def _no_trade_note(k, n):
    return (
        f"Note: {k} of {n} windows made no trades in the test block (no crossover,"
        " or fewer than long + 2 test bars to warm up); their 0.00% says nothing about the pair."
    )


# Window 2 of THREE_WINDOWS moved to test bars 35-44: it overlaps window 1.
OVERLAPPING = [THREE_WINDOWS[0], dict(THREE_WINDOWS[1], test_start=35, test_end=45), THREE_WINDOWS[2]]
# Window 2 of THREE_WINDOWS with no test trades and a 0% test return.
NO_TRADES = [THREE_WINDOWS[0], dict(THREE_WINDOWS[1], test_return_pct=0.0, test_trades=0), THREE_WINDOWS[2]]
# Both at once.
BOTH = [
    THREE_WINDOWS[0],
    dict(THREE_WINDOWS[1], test_start=35, test_end=45, test_return_pct=0.0, test_trades=0),
    THREE_WINDOWS[2],
]


def _text(windows):
    return format_walk_forward(windows, summarize(windows))


def test_format_three_windows_hand_worked():
    assert _text(THREE_WINDOWS) == THREE_WINDOWS_TEXT


def test_format_one_row_per_window_in_order():
    lines = _text(THREE_WINDOWS).splitlines()
    rows = lines[2:5]
    assert [row.split()[0] for row in rows] == ["1", "2", "3"]
    assert rows[1].split() == ["2", "10-39", "40-49", "10/30", "+8.00%", "-5.00%", "-8.00%", "1"]
    assert lines[5].startswith("Test return, compounded")


def test_format_rows_follow_walk_forward_output():
    rows = walk_forward(sideways(), [2, 3, 5], [5, 10, 20], train=40, test=30)
    lines = format_walk_forward(rows, summarize(rows)).splitlines()
    body = lines[2 : 2 + len(rows)]
    for line, row in zip(body, rows):
        parts = line.split()
        assert parts[0] == str(row["window"])
        assert parts[1] == f"{row['train_start']}-{row['train_end'] - 1}"
        assert parts[2] == f"{row['test_start']}-{row['test_end'] - 1}"
        assert parts[3] == f"{row['short']}/{row['long']}"
        assert parts[7] == str(row["test_trades"])
    assert lines[2 + len(rows)].startswith("Test return, compounded")


def test_format_no_notes_when_contiguous_and_every_window_traded():
    text = _text(THREE_WINDOWS)
    assert GAP_NOTE not in text
    assert "Note:" not in text


def test_format_gap_note_only_when_blocks_not_contiguous():
    lines = _text(OVERLAPPING).splitlines()
    assert GAP_NOTE in lines
    assert [line for line in lines if line.startswith("Note:")] == [GAP_NOTE]


def test_format_no_trade_note_only_when_a_window_made_no_trades():
    lines = _text(NO_TRADES).splitlines()
    assert "Windows without test trades: 1 of 3" in lines
    assert [line for line in lines if line.startswith("Note:")] == [_no_trade_note(1, 3)]


def test_format_both_notes_gap_first():
    lines = _text(BOTH).splitlines()
    assert [line for line in lines if line.startswith("Note:")] == [GAP_NOTE, _no_trade_note(1, 3)]


@pytest.mark.parametrize("windows", [THREE_WINDOWS, OVERLAPPING, NO_TRADES, BOTH, THREE_WINDOWS[:1]])
def test_format_always_ends_with_overfit_warning_and_disclaimer(windows):
    text = _text(windows)
    assert text.splitlines()[-2:] == [OVERFIT_WARNING, DISCLAIMER]
    assert text.count(OVERFIT_WARNING) == 1
    assert text.count(DISCLAIMER) == 1


def test_format_reuses_sweep_and_cli_lines():
    assert walkforward.OVERFIT_WARNING is OVERFIT_WARNING
    assert walkforward.DISCLAIMER is DISCLAIMER


def test_format_returns_text_without_trailing_newline():
    text = _text(THREE_WINDOWS)
    assert isinstance(text, str)
    assert not text.endswith("\n")


def test_format_prints_the_shared_lines_not_copies(monkeypatch):
    # If format_walk_forward typed its own copy of either line, swapping the
    # shared names would not change its output.
    monkeypatch.setattr(walkforward, "OVERFIT_WARNING", "overfit line under test")
    monkeypatch.setattr(walkforward, "DISCLAIMER", "disclaimer under test")
    assert _text(THREE_WINDOWS).splitlines()[-2:] == ["overfit line under test", "disclaimer under test"]
