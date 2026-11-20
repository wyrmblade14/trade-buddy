"""Tests for trading_assistant.portfolio.run_portfolio.

Every expected value below is worked out by hand, not computed.
"""

import pytest

from trading_assistant.portfolio import run_portfolio
from trading_assistant.signals import BUY, SELL

DATES = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07",
         "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13"]


def test_two_symbols_hand_worked():
    # cash 1000 -> 500 each; short 1, long 2, no fees. short SMA(1) is the
    # close, so the short SMA is above SMA(2) exactly when the close rose.
    # The first signal is on bar 2 (needs long + 1 = 3 bars); a signal on
    # bar t fills at the close of bar t + 1.
    #
    # bar            0    1    2    3    4    5    6    7
    # A close       10    9    8    9   11   12   10    8
    # A signal                HOLD BUY HOLD HOLD SELL
    #   bar 4: buy floor(500 / 11) = 45 @ 11 = 495, cash 5
    #   bar 7: sell 45 @ 8 = 360, cash 365
    # A equity     500  500  500  500  500  545  455  365
    #
    # B close       20   20   19   21   22   20   18   17
    # B signal                SELL BUY HOLD SELL HOLD
    #   bar 2's SELL (20 = 20 -> 19 < 19.5) is skipped: nothing held
    #   bar 4: buy floor(500 / 22) = 22 @ 22 = 484, cash 16
    #   bar 6: sell 22 @ 18 = 396, cash 412
    # B equity     500  500  500  500  500  456  412  412
    #
    # Portfolio   1000 1000 1000 1000 1000 1001  867  777
    tables = {
        "A": (DATES, [10.0, 9.0, 8.0, 9.0, 11.0, 12.0, 10.0, 8.0]),
        "B": (DATES, [20.0, 20.0, 19.0, 21.0, 22.0, 20.0, 18.0, 17.0]),
    }

    out = run_portfolio(tables, cash=1000, short=1, long=2, fee=0.0, fee_pct=0.0)

    assert out.dates == DATES
    assert out.equity == [1000, 1000, 1000, 1000, 1000, 1001, 867, 777]

    a, b = out.results["A"], out.results["B"]
    assert a.initial_cash == 500 and b.initial_cash == 500
    assert a.equity_curve == [500, 500, 500, 500, 500, 545, 455, 365]
    assert b.equity_curve == [500, 500, 500, 500, 500, 456, 412, 412]
    assert [(t.bar, t.side, t.shares, t.price) for t in a.trades] == [(4, BUY, 45, 11.0), (7, SELL, 45, 8.0)]
    assert [(t.bar, t.side, t.shares, t.price) for t in b.trades] == [(4, BUY, 22, 22.0), (6, SELL, 22, 18.0)]


def test_three_symbols_starting_cash_adds_up_to_total():
    # 1000 / 3 each. C has an extra date (2026-01-01) that the others lack, so
    # it is dropped and all three run on the same 4 shared dates
    # (exactly long + 2 = 4, the fewest allowed).
    four = DATES[:4]
    tables = {
        "A": (four, [10.0, 11.0, 12.0, 13.0]),
        "B": (four, [20.0, 21.0, 22.0, 23.0]),
        "C": (["2026-01-01"] + four, [29.0, 30.0, 31.0, 32.0, 33.0]),
    }

    out = run_portfolio(tables, cash=1000, short=1, long=2)

    assert out.dates == four
    starting = [r.initial_cash for r in out.results.values()]
    assert starting[0] == starting[1] == starting[2]
    assert sum(starting) == 1000
    assert out.equity[0] == 1000


def test_too_few_shared_dates_raises_one_line():
    # long 2 needs 4 shared dates; these symbols share only 3.
    three = DATES[:3]
    tables = {
        "A": (three, [10.0, 11.0, 12.0]),
        "B": (three + ["2026-01-07"], [20.0, 21.0, 22.0, 23.0]),
    }
    with pytest.raises(ValueError) as exc:
        run_portfolio(tables, cash=1000, short=1, long=2)
    message = str(exc.value)
    assert message == "only 3 dates shared by all 2 symbols; need at least 4 (long window 2 + 2)"
    assert "\n" not in message


def test_no_shared_dates_raises_one_line():
    tables = {
        "A": (DATES[:4], [10.0, 11.0, 12.0, 13.0]),
        "B": (DATES[4:], [20.0, 21.0, 22.0, 23.0]),
    }
    with pytest.raises(ValueError) as exc:
        run_portfolio(tables, cash=1000, short=1, long=2)
    message = str(exc.value)
    assert message == "only 0 dates shared by all 2 symbols; need at least 4 (long window 2 + 2)"
    assert "\n" not in message


@pytest.mark.parametrize(
    "tables, count",
    [
        ({}, 0),
        ({"A": (DATES, [10.0, 9.0, 8.0, 9.0, 11.0, 12.0, 10.0, 8.0])}, 1),
    ],
)
def test_fewer_than_two_symbols_raises_one_line(tables, count):
    with pytest.raises(ValueError) as exc:
        run_portfolio(tables, cash=1000, short=1, long=2)
    message = str(exc.value)
    assert message == f"a portfolio needs at least 2 symbols, got {count}"
    assert "\n" not in message
