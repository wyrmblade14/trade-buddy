"""Tests for trading_assistant.portfolio.summarize.

The 8-bar two-symbol example from test_portfolio_run.py; every expected value
below is worked out by hand, not computed.
"""

import pytest

from trading_assistant.portfolio import run_portfolio, summarize

DATES = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07",
         "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13"]
A_CLOSES = [10.0, 9.0, 8.0, 9.0, 11.0, 12.0, 10.0, 8.0]
B_CLOSES = [20.0, 20.0, 19.0, 21.0, 22.0, 20.0, 18.0, 17.0]

# cash 1000 -> 500 each; short 1, long 2, no fees (see test_portfolio_run.py):
#   A equity     500  500  500  500  500  545  455  365   (buy 45 @ 11, sell 45 @ 8)
#   B equity     500  500  500  500  500  456  412  412   (buy 22 @ 22, sell 22 @ 18)
#   Portfolio   1000 1000 1000 1000 1000 1001  867  777
#
# Portfolio return:  (777 - 1000) / 1000        = -22.3 %
# Portfolio drawdown from the SUMMED curve: peak 1001 -> 777
#                    (777 - 1001) / 1001        = -22.3776... %
#   (averaging the symbols' drawdowns would give (-33.03 + -17.6) / 2 = -25.31 %)
# Buy and hold, on bar 0 with each symbol's 500:
#   A: 50 shares @ 10 -> 50 * 8  = 400   (-20 %)
#   B: 25 shares @ 20 -> 25 * 17 = 425   (-15 %)
#   together 825 against 1000             = -17.5 %
# Symbol drawdowns:
#   A: peak 545 -> 365  (365 - 545) / 545 = -33.0275... %   <- worst
#   B: peak 500 -> 412  (412 - 500) / 500 = -17.6 %
# Symbol returns: A (365 - 500) / 500 = -27 %,  B (412 - 500) / 500 = -17.6 %


def _expected(b_lost):
    return {
        "short": 1,
        "long": 2,
        "fee": 0.0,
        "fee_pct": 0.0,
        "start_date": "2026-01-02",
        "end_date": "2026-01-13",
        "shared_dates": 8,
        "initial_cash": 1000.0,
        "final_equity": 777.0,
        "return_pct": pytest.approx(-22.3),
        "max_drawdown_pct": pytest.approx(-224 / 1001 * 100),
        "buy_hold_return_pct": pytest.approx(-17.5),
        "worst_symbol_drawdown": {"symbol": "A", "max_drawdown_pct": pytest.approx(-180 / 545 * 100)},
        "symbols": [
            {"symbol": "A", "bars_used": 8, "bars_lost": 0, "return_pct": pytest.approx(-27.0),
             "trades": 2, "buy_hold_return_pct": pytest.approx(-20.0)},
            {"symbol": "B", "bars_used": 8, "bars_lost": b_lost, "return_pct": pytest.approx(-17.6),
             "trades": 2, "buy_hold_return_pct": pytest.approx(-15.0)},
        ],
    }


def test_summary_of_the_8_bar_example():
    tables = {"A": (DATES, A_CLOSES), "B": (DATES, B_CLOSES)}
    summary = summarize(run_portfolio(tables, cash=1000, short=1, long=2))
    assert summary == _expected(b_lost=0)


def test_drawdown_comes_from_the_summed_curve_not_the_symbol_average():
    tables = {"A": (DATES, A_CLOSES), "B": (DATES, B_CLOSES)}
    summary = summarize(run_portfolio(tables, cash=1000, short=1, long=2))
    assert summary["max_drawdown_pct"] == pytest.approx(-22.3776, abs=1e-4)
    assert summary["max_drawdown_pct"] != pytest.approx(-25.3138, abs=1e-4)  # the average


def test_lost_bars_are_counted_per_symbol():
    # B gets two extra dates that A lacks; both are dropped, so the shared
    # series, and every number, is the same as above except B lost 2 bars.
    tables = {
        "A": (DATES, A_CLOSES),
        "B": (["2025-12-31"] + DATES + ["2026-01-14"], [99.0] + B_CLOSES + [99.0]),
    }
    summary = summarize(run_portfolio(tables, cash=1000, short=1, long=2))
    assert summary == _expected(b_lost=2)
