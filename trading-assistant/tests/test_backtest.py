"""Tests for trading_assistant.backtest and the --backtest CLI mode.

Expected numbers are worked out by hand with short=2, long=3 so the SMAs are
easy to check. The worked examples:

LOSS sample  closes = [10, 10, 10, 10, 14, 14, 14, 8, 8, 8]
    t=3: sma2=10,    sma3=10
    t=4: sma2=12,    sma3=11.33  -> short crossed above long   -> BUY signal
    t=6: sma2=14,    sma3=14
    t=7: sma2=11,    sma3=12     -> short crossed below long   -> SELL signal
    BUY  fills next bar (bar 5) @ 14: floor(10000 / 14) = 714 shares,
         cost 714 * 14 = 9,996, cash left 4.
    SELL fills next bar (bar 8) @ 8: 714 * 8 = 5,712 proceeds, cash 5,716.
    End: 0 shares, equity 5,716, return (5716 - 10000) / 10000 = -42.84 %.

GAIN sample  closes = [10, 10, 10, 10, 14, 16, 18, 20]
    t=4: BUY signal (same SMAs as above). Fills bar 5 @ 16:
         floor(10000 / 16) = 625 shares, cost exactly 10,000, cash 0.
    No further cross. End: 625 shares @ 20 = 12,500 equity, +25.00 %.

SELL-FIRST   closes = [10, 10, 10, 10, 6, 6]
    t=4: sma2=8, sma3=8.67 -> SELL signal, but nothing is held -> skipped.

LAST-BAR     closes = [10, 10, 10, 10, 14]
    t=4: BUY signal on the final bar -> no next bar to fill on -> no trade.
"""

import pytest

from trading_assistant.backtest import (
    DEFAULT_CASH,
    BacktestResult,
    Portfolio,
    Trade,
    format_result,
    run_backtest,
    signal_at,
)
from trading_assistant.cli import main
from trading_assistant.signals import BUY, HOLD, SELL, crossover_signal

LOSS = [10.0, 10.0, 10.0, 10.0, 14.0, 14.0, 14.0, 8.0, 8.0, 8.0]
GAIN = [10.0, 10.0, 10.0, 10.0, 14.0, 16.0, 18.0, 20.0]
SELL_FIRST = [10.0, 10.0, 10.0, 10.0, 6.0, 6.0]
LAST_BAR = [10.0, 10.0, 10.0, 10.0, 14.0]


def write_csv(path, closes):
    path.write_text("date,close\n" + "\n".join(f"d{i},{c}" for i, c in enumerate(closes)) + "\n")
    return str(path)


# --------------------------------------------------------------------------- Portfolio basics


def test_portfolio_starts_with_cash_and_no_shares():
    p = Portfolio(10_000)
    assert p.cash == 10_000.0
    assert p.position == 0
    assert p.equity(123.45) == 10_000.0


def test_portfolio_negative_initial_cash_rejected():
    with pytest.raises(ValueError, match="must not be negative"):
        Portfolio(-1)


def test_portfolio_zero_cash_is_allowed_but_cannot_buy():
    p = Portfolio(0)
    assert p.max_affordable(10.0) == 0
    with pytest.raises(ValueError):
        p.buy(1, 10.0)


def test_buy_reduces_cash_and_adds_shares():
    p = Portfolio(1000)
    p.buy(3, 250.0)  # 3 * 250 = 750
    assert p.cash == 250.0
    assert p.position == 3


def test_buy_exactly_all_cash_is_allowed():
    p = Portfolio(1000)
    p.buy(4, 250.0)  # 4 * 250 = 1000, exactly the cash
    assert p.cash == 0.0
    assert p.position == 4


def test_sell_adds_cash_and_removes_shares():
    p = Portfolio(1000)
    p.buy(4, 250.0)  # cash 0, 4 shares
    p.sell(1, 300.0)  # +300
    assert p.cash == 300.0
    assert p.position == 3
    p.sell(3, 100.0)  # +300
    assert p.cash == 600.0
    assert p.position == 0


def test_equity_marks_position_to_given_price():
    p = Portfolio(1000)
    p.buy(2, 100.0)  # cash 800, 2 shares
    assert p.equity(100.0) == 1000.0  # 800 + 2 * 100
    assert p.equity(150.0) == 1100.0  # 800 + 2 * 150
    assert p.equity(50.0) == 900.0  # 800 + 2 * 50


# --------------------------------------------------------------------------- rejections leave state unchanged


def test_buy_without_enough_cash_raises_and_leaves_state_unchanged():
    p = Portfolio(100)
    p.buy(1, 40.0)  # cash 60, 1 share
    with pytest.raises(ValueError, match="exceeds cash"):
        p.buy(2, 40.0)  # 80 > 60
    assert p.cash == 60.0
    assert p.position == 1


def test_buy_one_cent_short_is_rejected():
    p = Portfolio(99.99)
    with pytest.raises(ValueError, match="exceeds cash"):
        p.buy(1, 100.0)
    assert p.cash == 99.99
    assert p.position == 0


def test_sell_more_than_held_raises_and_leaves_state_unchanged():
    p = Portfolio(1000)
    p.buy(3, 100.0)  # cash 700, 3 shares
    with pytest.raises(ValueError, match="no short selling"):
        p.sell(4, 100.0)
    assert p.cash == 700.0
    assert p.position == 3


def test_sell_with_nothing_held_is_rejected():
    p = Portfolio(1000)
    with pytest.raises(ValueError, match="only 0 held"):
        p.sell(1, 100.0)
    assert p.cash == 1000.0
    assert p.position == 0


@pytest.mark.parametrize("bad_shares", [0, -1, 1.5, 2.0, "3", True])
def test_buy_and_sell_reject_non_whole_or_non_positive_shares(bad_shares):
    p = Portfolio(1000)
    p.buy(5, 10.0)  # cash 950, 5 shares
    with pytest.raises(ValueError, match="shares must be"):
        p.buy(bad_shares, 10.0)
    with pytest.raises(ValueError, match="shares must be"):
        p.sell(bad_shares, 10.0)
    assert p.cash == 950.0
    assert p.position == 5


@pytest.mark.parametrize("bad_price", [0, -10.0])
def test_buy_sell_equity_reject_non_positive_price(bad_price):
    p = Portfolio(1000)
    p.buy(1, 10.0)
    for action in (lambda: p.buy(1, bad_price), lambda: p.sell(1, bad_price), lambda: p.equity(bad_price)):
        with pytest.raises(ValueError, match="price must be positive"):
            action()
    assert p.cash == 990.0
    assert p.position == 1


# --------------------------------------------------------------------------- max_affordable


@pytest.mark.parametrize(
    "cash, price, expected",
    [
        (10_000, 14.0, 714),  # 714 * 14 = 9996 <= 10000 < 715 * 14 = 10010
        (10_000, 16.0, 625),  # exact
        (10_000, 10_000.0, 1),
        (10_000, 10_000.01, 0),
        (5, 14.0, 0),
        (100, 0.1, 1000),  # 1000 * 0.1 must be treated as affordable (float rounding guard)
    ],
)
def test_max_affordable_whole_shares(cash, price, expected):
    assert Portfolio(cash).max_affordable(price) == expected


def test_max_affordable_never_exceeds_cash():
    for cash in (1, 7, 99.99, 1234.56, 10_000):
        for price in (0.1, 0.3, 1.1, 3.7, 14.0, 101.35):
            p = Portfolio(cash)
            shares = p.max_affordable(price)
            assert shares * price <= cash or shares == 0
            if shares:
                p.buy(shares, price)  # must not raise
                assert p.cash >= 0.0


# --------------------------------------------------------------------------- run_backtest: hand-worked examples


def test_loss_sample_hand_worked():
    r = run_backtest(LOSS, initial_cash=10_000, short=2, long=3)

    assert r.n_trades == 2
    assert r.n_buys == 1
    assert r.n_sells == 1
    assert r.trades[0] == Trade(bar=5, side=BUY, shares=714, price=14.0, cash_after=4.0)
    assert r.trades[1] == Trade(bar=8, side=SELL, shares=714, price=8.0, cash_after=5716.0)
    assert r.trades[0].value == 9996.0
    assert r.trades[1].value == 5712.0

    assert r.initial_cash == 10_000.0
    assert r.final_cash == 5716.0
    assert r.final_position == 0
    assert r.final_price == 8.0
    assert r.final_equity == 5716.0
    assert r.return_pct == pytest.approx(-42.84)


def test_gain_sample_hand_worked():
    r = run_backtest(GAIN, initial_cash=10_000, short=2, long=3)

    assert r.n_trades == 1
    assert r.trades == [Trade(bar=5, side=BUY, shares=625, price=16.0, cash_after=0.0)]
    assert r.final_cash == 0.0
    assert r.final_position == 625
    assert r.final_price == 20.0
    assert r.final_equity == 12_500.0
    assert r.return_pct == pytest.approx(25.0)


def test_gain_sample_with_different_cash():
    # 1,000 cash: floor(1000 / 16) = 62 shares, cost 992, cash 8.
    # End: 8 + 62 * 20 = 1,248 -> +24.80 %
    r = run_backtest(GAIN, initial_cash=1_000, short=2, long=3)
    assert r.trades == [Trade(bar=5, side=BUY, shares=62, price=16.0, cash_after=8.0)]
    assert r.final_equity == 1248.0
    assert r.return_pct == pytest.approx(24.8)


def test_sell_signal_with_nothing_held_is_skipped():
    assert signal_at(SELL_FIRST, 4, short=2, long=3) == SELL
    r = run_backtest(SELL_FIRST, initial_cash=10_000, short=2, long=3)
    assert r.trades == []
    assert r.final_cash == 10_000.0
    assert r.final_position == 0
    assert r.final_equity == 10_000.0
    assert r.return_pct == 0.0


def test_signal_on_last_bar_is_never_filled():
    assert signal_at(LAST_BAR, 4, short=2, long=3) == BUY
    r = run_backtest(LAST_BAR, initial_cash=10_000, short=2, long=3)
    assert r.trades == []
    assert r.final_equity == 10_000.0


def test_buy_skipped_when_cash_cannot_cover_one_share():
    # BUY fills @ 14 but only 13.99 cash -> 0 shares -> skipped, no error.
    r = run_backtest(LOSS, initial_cash=13.99, short=2, long=3)
    assert r.trades == []
    assert r.final_cash == 13.99


def test_buy_with_cash_for_exactly_one_share():
    # 14 cash -> 1 share @ 14 at bar 5, sold @ 8 at bar 8 -> 8 cash, -42.857 %
    r = run_backtest(LOSS, initial_cash=14, short=2, long=3)
    assert [(t.bar, t.side, t.shares) for t in r.trades] == [(5, BUY, 1), (8, SELL, 1)]
    assert r.final_cash == 8.0
    assert r.return_pct == pytest.approx(-42.857, abs=0.001)


def test_too_short_history_means_no_trades():
    r = run_backtest([10.0, 11.0, 12.0], initial_cash=10_000, short=2, long=3)
    assert r.trades == []
    assert r.final_equity == 10_000.0


def test_default_cash_is_10000():
    assert DEFAULT_CASH == 10_000.0
    r = run_backtest(GAIN, short=2, long=3)
    assert r.initial_cash == 10_000.0
    assert r.trades[0].shares == 625


def test_cash_never_negative_and_position_never_short_over_whole_run():
    # Alternating regime changes produce several BUY/SELL crosses.
    closes = [10.0] * 4 + [14.0] * 3 + [8.0] * 3 + [13.0] * 3 + [7.0] * 3 + [12.0] * 3
    r = run_backtest(closes, initial_cash=10_000, short=2, long=3)
    assert r.n_trades >= 4
    for trade in r.trades:
        assert trade.cash_after >= 0.0
        assert trade.shares >= 1
    assert r.final_position >= 0
    # Sides must alternate starting with BUY: you can only sell what you bought.
    assert [t.side for t in r.trades] == [BUY, SELL] * (r.n_trades // 2) + ([BUY] if r.n_trades % 2 else [])


# --------------------------------------------------------------------------- no look-ahead


def test_signal_at_equals_signal_on_full_prefix():
    closes = [10.0, 11.0, 9.0, 12.0, 13.0, 11.0, 10.0, 14.0, 15.0, 9.0, 8.0, 12.0, 13.0, 14.0]
    for short, long in [(2, 3), (2, 5), (3, 4)]:
        for t in range(len(closes)):
            assert signal_at(closes, t, short, long) == crossover_signal(closes[: t + 1], short, long)


def test_future_prices_do_not_change_earlier_trades():
    base = list(GAIN)  # BUY fills at bar 5 @ 16
    altered = base[:6] + [1.0, 1.0]  # crash after the fill
    r_base = run_backtest(base, initial_cash=10_000, short=2, long=3)
    r_alt = run_backtest(altered, initial_cash=10_000, short=2, long=3)

    # The fill at bar 5 only depends on bars 0..5, so it is identical.
    assert r_base.trades[0] == r_alt.trades[0] == Trade(5, BUY, 625, 16.0, 0.0)
    assert r_base.final_equity == 12_500.0

    # In the altered series the crash creates a SELL cross at t=6:
    #   sma2 = (16 + 1) / 2 = 8.5 < sma3 = (14 + 16 + 1) / 3 = 10.33
    #   (previous bar: sma2 = 15 >= sma3 = 13.33)
    # which fills at bar 7 @ 1.0: 625 * 1 = 625 cash.
    assert r_alt.trades == [Trade(5, BUY, 625, 16.0, 0.0), Trade(7, SELL, 625, 1.0, 625.0)]
    assert r_alt.final_position == 0
    assert r_alt.final_equity == 625.0
    assert r_alt.return_pct == pytest.approx(-93.75)


def test_fill_uses_next_bar_price_not_signal_bar_price():
    # Signal at t=4 (close 14). Fill must be at closes[5] = 16, not 14.
    r = run_backtest(GAIN, initial_cash=10_000, short=2, long=3)
    assert r.trades[0].bar == 5
    assert r.trades[0].price == 16.0
    assert r.trades[0].shares == 625  # 10000 / 16, not 10000 / 14 = 714


# --------------------------------------------------------------------------- run_backtest input validation


def test_run_backtest_rejects_empty_prices():
    with pytest.raises(ValueError, match="no prices"):
        run_backtest([], short=2, long=3)


@pytest.mark.parametrize("cash", [0, -100])
def test_run_backtest_rejects_non_positive_cash(cash):
    with pytest.raises(ValueError, match="initial cash must be positive"):
        run_backtest(GAIN, initial_cash=cash, short=2, long=3)


def test_run_backtest_rejects_non_positive_price_with_bar_index():
    with pytest.raises(ValueError, match="bar 2: price must be positive"):
        run_backtest([10.0, 11.0, 0.0, 12.0], short=2, long=3)


def test_run_backtest_rejects_short_not_smaller_than_long():
    with pytest.raises(ValueError, match="short window must be smaller"):
        run_backtest(GAIN, short=3, long=3)


# --------------------------------------------------------------------------- format_result


def test_format_result_loss_sample():
    r = run_backtest(LOSS, initial_cash=10_000, short=2, long=3)
    lines = format_result(r, 2, 3)
    assert lines[0].startswith("Backtest: SMA 2/3 crossover")
    assert lines[1] == "  Start cash:  10,000.00"
    assert lines[2] == "  Trades:      2 (1 buy, 1 sell)"
    assert "bar 5" in lines[4] and "BUY" in lines[4] and "714" in lines[4] and "14.00" in lines[4]
    assert "bar 8" in lines[5] and "SELL" in lines[5] and "5,712.00" in lines[5] and "5,716.00" in lines[5]
    assert lines[-4] == "  End cash:    5,716.00"
    assert lines[-3] == "  End shares:  0 @ 8.00"
    assert lines[-2] == "  End equity:  5,716.00"
    assert lines[-1] == "  Return:      -42.84%"


def test_format_result_no_trades_has_no_fill_block():
    r = run_backtest(LAST_BAR, initial_cash=10_000, short=2, long=3)
    lines = format_result(r, 2, 3)
    assert lines[2] == "  Trades:      0 (0 buy, 0 sell)"
    assert not any("Fills" in line for line in lines)
    assert lines[-1] == "  Return:      +0.00%"


def test_backtest_result_properties():
    r = BacktestResult(initial_cash=100.0, final_cash=40.0, final_position=3, final_price=30.0)
    assert r.final_equity == 130.0
    assert r.return_pct == pytest.approx(30.0)
    assert (r.n_trades, r.n_buys, r.n_sells) == (0, 0, 0)


# --------------------------------------------------------------------------- CLI: --backtest


def test_cli_backtest_loss_sample(tmp_path, capsys):
    path = write_csv(tmp_path / "loss.csv", LOSS)
    assert main([path, "--short", "2", "--long", "3", "--backtest"]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    # Standard report is still first and unchanged.
    assert lines[:4] == ["Bars:    10", "Last:    8.00", "Signal:  HOLD", "RSI:     n/a"]
    assert "  Trades:      2 (1 buy, 1 sell)" in lines
    assert "  End equity:  5,716.00" in lines
    assert "  Return:      -42.84%" in lines
    assert lines[-1] == "Research aid only. Not financial advice."


def test_cli_backtest_gain_sample_with_cash(tmp_path, capsys):
    path = write_csv(tmp_path / "gain.csv", GAIN)
    assert main([path, "--short", "2", "--long", "3", "--backtest", "--cash", "1000"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "  Start cash:  1,000.00" in lines
    assert "  Trades:      1 (1 buy, 0 sell)" in lines
    assert "  End shares:  62 @ 20.00" in lines
    assert "  End equity:  1,248.00" in lines
    assert "  Return:      +24.80%" in lines


def test_cli_backtest_default_cash_is_10000(tmp_path, capsys):
    path = write_csv(tmp_path / "gain.csv", GAIN)
    assert main([path, "--short", "2", "--long", "3", "--backtest"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "  Start cash:  10,000.00" in lines
    assert "  End equity:  12,500.00" in lines
    assert "  Return:      +25.00%" in lines


def test_cli_without_backtest_flag_output_is_unchanged(tmp_path, capsys):
    path = write_csv(tmp_path / "loss.csv", LOSS)
    assert main([path, "--short", "2", "--long", "3"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "Bars:    10",
        "Last:    8.00",
        "Signal:  HOLD",
        "RSI:     n/a",
        "Research aid only. Not financial advice.",
    ]


def test_cli_cash_without_backtest_is_usage_error(tmp_path, capsys):
    path = write_csv(tmp_path / "gain.csv", GAIN)
    with pytest.raises(SystemExit) as excinfo:
        main([path, "--cash", "5000"])
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "--cash only makes sense together with --backtest" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("cash", ["0", "-1", "-0.5"])
def test_cli_non_positive_cash_is_usage_error(tmp_path, capsys, cash):
    path = write_csv(tmp_path / "gain.csv", GAIN)
    with pytest.raises(SystemExit) as excinfo:
        main([path, "--backtest", "--cash", cash])
    assert excinfo.value.code == 2
    assert "--cash must be positive" in capsys.readouterr().err


def test_cli_non_numeric_cash_is_usage_error(tmp_path, capsys):
    path = write_csv(tmp_path / "gain.csv", GAIN)
    with pytest.raises(SystemExit) as excinfo:
        main([path, "--backtest", "--cash", "lots"])
    assert excinfo.value.code == 2
    assert "invalid float value" in capsys.readouterr().err


def test_cli_backtest_non_positive_price_is_one_line_error(tmp_path, capsys):
    path = write_csv(tmp_path / "neg.csv", [10.0, -5.0, 10.0])
    assert main([path, "--backtest"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""  # nothing printed before the error
    assert captured.err.splitlines() == ["Error: bar 1: price must be positive, got -5.0"]


def test_cli_backtest_keeps_existing_data_errors(tmp_path, capsys):
    assert main([str(tmp_path / "missing.csv"), "--backtest"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("Error:")
    assert len(captured.err.splitlines()) == 1


def test_cli_help_mentions_backtest_and_cash(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "--backtest" in out
    assert "--cash" in out
    assert "10,000" in out
