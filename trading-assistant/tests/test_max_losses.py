"""Losing-streak halt in the engine and the text report (``run_backtest(..., max_losses=N)``).

After N completed round trips in a row that lost money (profit after costs below 0), no buy can fill for the
rest of the run; each buy due then is dropped and counted in ``loss_skipped_buys``. Any other round trip (a win,
or exactly 0.00) resets the streak. Nothing is held when the streak completes, so nothing is sold because of it.

Every number is worked out by hand in the comments. SMA 1/2 means: BUY when a close rises after one that did not,
SELL when a close falls after one that did not; a signal fills at the next bar's close.
"""

import functools
import json
from pathlib import Path

import pytest

from trading_assistant.backtest import export_columns, export_rows, format_result, format_stats, run_backtest
from trading_assistant.data import load_candles

DATA = Path(__file__).parent / "data"
HAND = dict(initial_cash=1000, short=1, long=2)

#        bar:  0  1  2  3   4   5   6  7  8  9  10  11  12 13  14  15  16
LOSSES = [10, 9, 8, 9, 11, 12, 10, 9, 8, 9, 10, 11, 10, 9, 10, 12, 13]
# Signals: BUY on bars 3, 9, 14; SELL on bars 6, 12. Without the option:
#   bar 4  BUY 90 @ 11 (cash 1000 - 990 = 10)
#   bar 7  SELL 90 @ 9 (cash 10 + 810 = 820)        round trip 810 - 990 = -180: loss 1
#   bar 10 BUY 82 @ 10 (cash 0)
#   bar 13 SELL 82 @ 9 (cash 738)                    round trip 738 - 820 = -82: loss 2
#   bar 15 BUY 61 @ 12 (cash 738 - 732 = 6)          end 6 + 61 x 13 = 799

# Loss, win, loss, loss:
#        bar:  0  1   2   3  4  5  6   7  8   9  10  11  12  13  14 15 16  17  18
RESET = [10, 9, 10, 10, 9, 8, 9, 10, 9, 12, 12, 11, 10, 11, 10, 8, 9, 10, 11]
# Signals: BUY on bars 2, 6, 9, 13, 16; SELL on bars 4, 8, 11, 14 (bars 3 and 10 are flat: HOLD).
#   bar 3  BUY 100 @ 10 (cash 0)     bar 5  SELL 100 @ 8  (cash 800)   800 - 1000 = -200  loss: streak 1
#   bar 7  BUY  80 @ 10 (cash 0)     bar 9  SELL  80 @ 12 (cash 960)   960 -  800 = +160  win:  streak 0
#   bar 10 BUY  80 @ 12 (cash 0)     bar 12 SELL  80 @ 10 (cash 800)   800 -  960 = -160  loss: streak 1
#   bar 14 BUY  80 @ 10 (cash 0)     bar 15 SELL  80 @ 8  (cash 640)   640 -  800 = -160  loss: streak 2
#   bar 17 BUY  64 @ 10 (cash 0)     end 64 x 11 = 704

# Loss, exactly 0.00, loss: RESET with bars 9 and 10 at 10.
#        bar:  0  1   2   3  4  5  6   7  8   9  10 11 12 13  14  15
ZERO = [10, 9, 10, 10, 9, 8, 9, 10, 9, 10, 10, 9, 8, 9, 10, 11]
#   bar 3  BUY 100 @ 10, bar 5  SELL 100 @ 8 (cash 800)    -200  loss: streak 1
#   bar 7  BUY  80 @ 10, bar 9  SELL  80 @ 10 (cash 800)      0  not a loss: streak 0
#   bar 10 BUY  80 @ 10, bar 12 SELL  80 @ 8 (cash 640)    -160  loss: streak 1
#   bar 14 BUY  64 @ 10 (cash 0)                           end 64 x 11 = 704


@functools.lru_cache(maxsize=None)
def candles():
    """tests/data/c.csv (candles11.csv of docs/cli.md) as run_backtest keywords."""
    rows = load_candles(str(DATA / "c.csv"))
    return {
        "closes": [c.close for c in rows],
        "opens": [c.open for c in rows],
        "highs": [c.high for c in rows],
        "lows": [c.low for c in rows],
    }


def fills(result):
    return [(t.bar, t.side, t.shares, t.price, t.reason) for t in result.trades]


def losses_line(result):
    return [line for line in format_result(result, 1, 2) if line.startswith("  Max losses:")]


# ----------------------------------------------------------------- the given case


def test_without_the_option_two_losing_round_trips_end_at_799():
    result = run_backtest(LOSSES, **HAND)
    assert fills(result) == [
        (4, "BUY", 90, 11, "signal"), (7, "SELL", 90, 9, "signal"),
        (10, "BUY", 82, 10, "signal"), (13, "SELL", 82, 9, "signal"),
        (15, "BUY", 61, 12, "signal"),
    ]
    assert result.n_round_trips == 2
    assert result.final_equity == pytest.approx(799.0)
    assert result.max_losses == 0 and result.loss_halt_bar is None and result.loss_skipped_buys == 0
    assert losses_line(result) == []


@pytest.mark.parametrize(
    "n, trades, halt_bar, skipped, equity",
    [
        # 1: the bar 7 loss halts; the buys due on bars 10 and 15 are skipped, cash 820 to the end.
        (1, 2, 7, 2, 820.0),
        # 2: the bar 13 loss is the second in a row; the buy due on bar 15 is skipped, cash 738 to the end.
        (2, 4, 13, 1, 738.0),
        # 3: only two losses in the whole run: never halts, same as without the option.
        (3, 5, None, 0, 799.0),
    ],
)
def test_max_losses_on_the_given_case(n, trades, halt_bar, skipped, equity):
    plain = run_backtest(LOSSES, **HAND)
    result = run_backtest(LOSSES, **HAND, max_losses=n)
    assert result.trades == plain.trades[:trades]
    assert result.loss_halt_bar == halt_bar
    assert result.loss_skipped_buys == skipped
    assert result.final_equity == pytest.approx(equity)
    assert result.drawdown_skipped_buys == result.cooldown_skipped_buys == result.risk_skipped_buys == 0
    if halt_bar is None:
        assert result.daily == plain.daily


# ----------------------------------------------------------------- what counts as a loss


def test_a_win_resets_the_streak():
    # Streak 1, 0, 1, 2 (see RESET): with 2 the halt comes on bar 15, not bar 12, so the bar 14 buy still
    # fills and only the bar 17 buy is skipped. End: cash 640.
    result = run_backtest(RESET, **HAND, max_losses=2)
    assert [rt.pnl for rt in result.round_trips] == [-200, 160, -160, -160]
    assert fills(result)[-2:] == [(14, "BUY", 80, 10, "signal"), (15, "SELL", 80, 8, "signal")]
    assert result.loss_halt_bar == 15
    assert result.loss_skipped_buys == 1
    assert result.final_equity == pytest.approx(640.0)
    # Without the option the bar 17 buy fills: 64 x 11 = 704.
    assert run_backtest(RESET, **HAND).final_equity == pytest.approx(704.0)


def test_a_round_trip_at_exactly_0_is_not_a_loss_and_resets_the_streak():
    # Streak 1, 0, 1 (see ZERO): with 2 the run never halts and the bar 14 buy fills (end 704). Counting the
    # 0.00 round trip as a loss would halt on bar 9; leaving the streak unchanged would halt on bar 12.
    result = run_backtest(ZERO, **HAND, max_losses=2)
    assert [rt.pnl for rt in result.round_trips] == [-200, 0, -160]
    assert result.loss_halt_bar is None
    assert result.loss_skipped_buys == 0
    assert result.daily == run_backtest(ZERO, **HAND).daily
    assert result.final_equity == pytest.approx(704.0)


@pytest.mark.parametrize(
    "fill, sale, equity",
    [
        # Close fills: BUY 90 @ 11 on bar 4 (cash 10); stop 10 % = 9.90, bar 6 low 9.5 -> SELL 90 @ 9.90,
        # cash 901, round trip 891 - 990 = -99. The bar 9 buy (75 @ 12 without the option, end 916) is skipped.
        ("close", (6, "SELL", 90, 9.9, "stop"), 901.0),
        # Open fills: BUY 92 @ 10.80 (bar 4 open, cash 6.40); stop 9.72, bar 6 low 9.5 -> SELL 92 @ 9.72,
        # cash 900.64, round trip 894.24 - 993.60 = -99.36. The bar 9 buy (83 @ 10.80, end 1016.84) is skipped.
        ("open", (6, "SELL", 92, 9.72, "stop"), 900.64),
    ],
)
def test_a_stop_exit_counts_as_a_loss_in_both_fill_modes(fill, sale, equity):
    result = run_backtest(**candles(), **HAND, stop_pct=10, fill=fill, max_losses=1)
    assert fills(result)[-1] == pytest.approx(sale)
    assert result.n_trades == 2
    assert result.loss_halt_bar == 6
    assert result.loss_skipped_buys == 1
    assert result.final_equity == pytest.approx(equity)


def test_a_sale_the_fees_refuse_completes_no_round_trip_and_does_not_count():
    # Fee 495: bar 4 buys 45 @ 11 (495 + 495 = 990, cash 10). The bar 7 sale would give 10 + 405 - 495 < 0:
    # refused, the 45 shares are kept; the bar 13 sale likewise. The buys due on bars 10 and 15 cannot pay the
    # fee. Counting a refused sale would halt on bar 7 and count those two buys as skipped.
    result = run_backtest(LOSSES, **HAND, fee=495, max_losses=1)
    assert fills(result) == [(4, "BUY", 45, 11, "signal")]
    assert result.round_trips == []
    assert result.loss_halt_bar is None
    assert result.loss_skipped_buys == 0
    assert result.final_equity == pytest.approx(10 + 45 * 13)


# ----------------------------------------------------------------- together with the other halts


def test_a_drawdown_sale_counts_and_a_buy_both_halts_block_is_counted_under_the_drawdown_halt():
    # SMA 1/3. Bar 4: 11 > (10 + 10 + 11) / 3 -> BUY; bar 5 buys 50 @ 20, cash 0. Account value 1000 up to bar 5
    # (the peak), bar 6: 50 x 19 = 950, 5 % below -> drawdown halt. Bar 6's signal is HOLD (19 > 16.67), so
    # bar 7 has the drawdown sale: 50 @ 18.50 = 925, round trip -75, the first loss -> streak halt on bar 7.
    # Bar 10: 16 > (15 + 14 + 16) / 3 = 15 after 14 <= 15.83 -> BUY, due on bar 11: blocked by both halts,
    # counted under the drawdown halt only.
    closes = [10, 10, 10, 10, 11, 20, 19, 18.5, 15, 14, 16, 16, 17]
    result = run_backtest(closes, initial_cash=1000, short=1, long=3, max_drawdown_limit_pct=5, max_losses=1)
    assert fills(result) == [(5, "BUY", 50, 20, "signal"), (7, "SELL", 50, 18.5, "drawdown")]
    assert result.drawdown_halt_bar == 6 and result.loss_halt_bar == 7
    assert result.drawdown_skipped_buys == 1
    assert result.loss_skipped_buys == 0
    assert result.final_equity == pytest.approx(925.0)


def test_a_buy_the_cooldown_also_blocks_is_counted_under_the_losing_streak():
    # Stop 10 %, cooldown 3: the bar 6 stop sale (-99, see above) blocks bars 7 to 9 and halts the run. The
    # bar 9 buy is counted once, as a losing-streak skip (without max_losses it is a cooldown skip).
    plain = run_backtest(**candles(), **HAND, stop_pct=10, cooldown=3)
    assert (plain.cooldown_skipped_buys, plain.final_equity) == (1, pytest.approx(901.0))
    result = run_backtest(**candles(), **HAND, stop_pct=10, cooldown=3, max_losses=1)
    assert result.loss_skipped_buys == 1
    assert result.cooldown_skipped_buys == 0
    assert result.trades == plain.trades


# ----------------------------------------------------------------- settings


@pytest.mark.parametrize("bad", [-1, 1.0, 2.5, "2", True, None])
def test_max_losses_must_be_a_whole_number_of_at_least_0(bad):
    with pytest.raises(ValueError, match="max_losses must be a whole number of at least 0"):
        run_backtest(LOSSES, **HAND, max_losses=bad)


# ----------------------------------------------------------------- the text report


def test_report_line_triggered_and_not_triggered():
    assert losses_line(run_backtest(LOSSES, **HAND, max_losses=2)) == [
        "  Max losses:  halt after 2 losing round trips in a row; triggered at bar 13, no buy fills after it; "
        "1 buy skipped"
    ]
    assert losses_line(run_backtest(LOSSES, **HAND, max_losses=1)) == [
        "  Max losses:  halt after 1 losing round trip in a row; triggered at bar 7, no buy fills after it; "
        "2 buys skipped"
    ]
    assert losses_line(run_backtest(LOSSES, **HAND, max_losses=3)) == [
        "  Max losses:  halt after 3 losing round trips in a row; not triggered; 0 buys skipped"
    ]


def test_report_line_comes_after_the_drawdown_line_and_before_round_trips():
    lines = format_result(run_backtest(LOSSES, **HAND, max_drawdown_limit_pct=50, max_losses=2), 1, 2)
    names = [line.split(":")[0].strip() for line in lines]
    i = names.index("Max losses")
    assert names[i - 1] == "Drawdown" and names[i + 1] == "Round trips"


# ----------------------------------------------------------------- runs without the option are unchanged

# Fills, counters, the text report, the statistics block and the export of runs with the other settings,
# recorded from the code as it was before the losing-streak halt was added (git HEAD, run in a separate
# worktree). Each case is run both without max_losses and with max_losses=0.
CASES = {
    "plain": ("closes", {}),
    "costs": ("closes", dict(fee=1.0, fee_pct=0.1, slippage_pct=0.5, position_size=0.5)),
    "breakout": ("closes", dict(strategy="breakout", strategy_params={"window": 1}, position_size=0.5)),
    "holds_drawdown": ("closes", dict(min_hold=4, max_hold=3, max_drawdown_limit_pct=17)),
    "open": ("candles", dict(fill="open")),
    "stop_cooldown": ("candles", dict(stop_pct=10, cooldown=3)),
    "trail_target": ("candles", dict(trail_pct=10, take_profit_pct=5)),
    "atr_risk": ("candles", dict(atr_stop=True, risk_pct=1, atr_period=2, atr_mult=1)),
    "open_breakeven": ("candles", dict(fill="open", breakeven_pct=5)),
}


def run_case(name, **extra):
    data, settings = CASES[name]
    inputs = {"closes": LOSSES} if data == "closes" else candles()
    return run_backtest(**inputs, **HAND, **settings, **extra)


def record(result):
    """The parts of a result that the recorded file holds, as JSON would give them back."""
    return json.loads(json.dumps({
        "fills": [[t.bar, t.side, t.shares, t.price, t.cash_after, t.cost, t.reason] for t in result.trades],
        "equity": result.final_equity,
        "counters": [
            result.risk_skipped_buys, result.cooldown_skipped_buys, result.min_hold_skipped_sells,
            result.drawdown_halt_bar, result.drawdown_skipped_buys,
        ],
        "report": format_result(result, 1, 2) + format_stats(result),
        "export_columns": export_columns(result),
        "export_rows": export_rows(result),
    }))


@functools.lru_cache(maxsize=None)
def before():
    return json.loads((DATA / "c_before_max_losses.json").read_text())


def test_the_recorded_cases_are_all_checked():
    assert set(CASES) == set(before())


@pytest.mark.parametrize("extra", [{}, {"max_losses": 0}], ids=["left_out", "zero"])
@pytest.mark.parametrize("name", sorted(CASES))
def test_runs_without_the_option_are_unchanged(name, extra):
    assert record(run_case(name, **extra)) == before()[name]
