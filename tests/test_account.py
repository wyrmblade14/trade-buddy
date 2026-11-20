"""Tests for the trading account (trading_assistant.account.Portfolio).

Buys and sells that work, every way an order is rejected, and the account's
total value. For each rejected order the test checks that the cash, the
share count and the costs paid are exactly what they were before the order,
not only that an error was raised.
"""

import pytest

from trading_assistant.account import Portfolio


def state(p):
    """(cash, shares, costs paid) so a rejected order can be checked for no change."""
    return (p.cash, p.position, p.total_costs)


# --------------------------------------------------------------------------- buy


def test_buy_that_works_moves_cash_into_shares():
    p = Portfolio(1000)
    cost = p.buy(4, 200)
    assert cost == 0.0
    assert p.cash == 200.0
    assert p.position == 4
    assert p.total_costs == 0.0


def test_buy_that_works_with_costs_charges_fee_and_percentage():
    p = Portfolio(1000, fee=5, fee_pct=1)
    cost = p.buy(4, 200)  # value 800, costs 5 + 1 % of 800 = 13
    assert cost == 13.0
    assert p.cash == pytest.approx(1000 - 800 - 13)
    assert p.position == 4
    assert p.total_costs == 13.0


def test_buy_spending_exactly_all_cash_works():
    p = Portfolio(1000)
    p.buy(5, 200)
    assert state(p) == (0.0, 5, 0.0)


def test_buy_with_not_enough_cash_is_rejected_and_account_unchanged():
    p = Portfolio(1000)
    before = state(p)
    with pytest.raises(ValueError) as excinfo:
        p.buy(6, 200)  # costs 1200, only 1000 available
    assert str(excinfo.value) == "cannot buy 6 @ 200.00: cost 1200.00 (incl. 0.00 fees) exceeds cash 1000.00"
    assert state(p) == before == (1000.0, 0, 0.0)


def test_buy_affordable_without_costs_but_not_with_them_is_rejected_and_account_unchanged():
    p = Portfolio(1000, fee=5)
    before = state(p)
    with pytest.raises(ValueError) as excinfo:
        p.buy(5, 200)  # shares cost exactly 1000, the 5 fee tips it over
    assert str(excinfo.value) == "cannot buy 5 @ 200.00: cost 1005.00 (incl. 5.00 fees) exceeds cash 1000.00"
    assert state(p) == before == (1000.0, 0, 0.0)


def test_buy_with_not_enough_cash_after_an_earlier_buy_keeps_the_earlier_position():
    p = Portfolio(1000)
    p.buy(3, 200)
    before = state(p)
    with pytest.raises(ValueError):
        p.buy(3, 200)  # 600 needed, 400 left
    assert state(p) == before == (400.0, 3, 0.0)


# --------------------------------------------------------------------------- sell


def test_sell_that_works_moves_shares_back_into_cash():
    p = Portfolio(1000)
    p.buy(4, 200)
    cost = p.sell(4, 250)
    assert cost == 0.0
    assert p.cash == 200.0 + 4 * 250
    assert p.position == 0
    assert p.total_costs == 0.0


def test_sell_part_of_the_position_works():
    p = Portfolio(1000)
    p.buy(4, 200)
    p.sell(1, 250)
    assert state(p) == (450.0, 3, 0.0)


def test_sell_that_works_with_costs_deducts_fee_and_percentage():
    p = Portfolio(1000, fee=5, fee_pct=1)
    p.buy(4, 200)  # cash 187, costs 13
    cost = p.sell(4, 250)  # proceeds 1000, costs 5 + 1 % of 1000 = 15
    assert cost == 15.0
    assert p.cash == pytest.approx(187 + 1000 - 15)
    assert p.position == 0
    assert p.total_costs == pytest.approx(28.0)


def test_sell_with_nothing_held_is_rejected_and_account_unchanged():
    p = Portfolio(1000)
    before = state(p)
    with pytest.raises(ValueError) as excinfo:
        p.sell(1, 200)
    assert str(excinfo.value) == "cannot sell 1: only 0 held (no short selling)"
    assert state(p) == before == (1000.0, 0, 0.0)


def test_sell_more_than_held_is_rejected_and_account_unchanged():
    p = Portfolio(1000)
    p.buy(4, 200)
    before = state(p)
    with pytest.raises(ValueError) as excinfo:
        p.sell(5, 200)
    assert str(excinfo.value) == "cannot sell 5: only 4 held (no short selling)"
    assert state(p) == before == (200.0, 4, 0.0)


def test_sell_more_than_held_after_a_partial_sell_is_rejected_and_account_unchanged():
    p = Portfolio(1000)
    p.buy(4, 200)
    p.sell(3, 200)
    before = state(p)
    with pytest.raises(ValueError) as excinfo:
        p.sell(2, 200)
    assert str(excinfo.value) == "cannot sell 2: only 1 held (no short selling)"
    assert state(p) == before == (800.0, 1, 0.0)


def test_sell_whose_costs_would_make_cash_negative_is_rejected_and_account_unchanged():
    p = Portfolio(24, fee=10)
    p.buy(1, 10)  # cash 4, 1 share, costs 10
    before = state(p)
    with pytest.raises(ValueError) as excinfo:
        p.sell(1, 5)  # proceeds 5 - fee 10 = -5; cash 4 - 5 < 0
    assert str(excinfo.value) == "cannot sell 1 @ 5.00: fees 10.00 exceed proceeds 5.00 plus cash 4.00"
    assert state(p) == before == (4.0, 1, 10.0)


# --------------------------------------------------------------------------- bad share counts


@pytest.mark.parametrize(
    "shares, message",
    [
        (0, "shares must be at least 1, got 0"),
        (-1, "shares must be at least 1, got -1"),
        (-100, "shares must be at least 1, got -100"),
        (1.5, "shares must be a whole number, got 1.5"),
        (0.5, "shares must be a whole number, got 0.5"),
        (2.0, "shares must be a whole number, got 2.0"),
    ],
    ids=["zero", "negative", "very negative", "fractional", "fraction below one", "float with .0"],
)
def test_buy_with_zero_negative_or_fractional_shares_is_rejected_and_account_unchanged(shares, message):
    p = Portfolio(1000)
    before = state(p)
    with pytest.raises(ValueError) as excinfo:
        p.buy(shares, 10)
    assert str(excinfo.value) == message
    assert state(p) == before == (1000.0, 0, 0.0)


@pytest.mark.parametrize(
    "shares, message",
    [
        (0, "shares must be at least 1, got 0"),
        (-1, "shares must be at least 1, got -1"),
        (-100, "shares must be at least 1, got -100"),
        (1.5, "shares must be a whole number, got 1.5"),
        (0.5, "shares must be a whole number, got 0.5"),
        (2.0, "shares must be a whole number, got 2.0"),
    ],
    ids=["zero", "negative", "very negative", "fractional", "fraction below one", "float with .0"],
)
def test_sell_with_zero_negative_or_fractional_shares_is_rejected_and_account_unchanged(shares, message):
    p = Portfolio(1000)
    p.buy(4, 200)
    before = state(p)
    with pytest.raises(ValueError) as excinfo:
        p.sell(shares, 200)
    assert str(excinfo.value) == message
    assert state(p) == before == (200.0, 4, 0.0)


# --------------------------------------------------------------------------- account total value


def test_total_value_of_a_new_account_is_its_cash_at_any_price():
    p = Portfolio(1000)
    assert p.equity(1) == 1000.0
    assert p.equity(123.45) == 1000.0


def test_total_value_is_cash_plus_shares_marked_at_the_given_price():
    p = Portfolio(1000)
    p.buy(4, 200)  # cash 200, 4 shares
    assert p.equity(200) == 1000.0  # unchanged at the buy price
    assert p.equity(250) == 200 + 4 * 250  # 1200: marked up
    assert p.equity(150) == 200 + 4 * 150  # 800: marked down


def test_total_value_does_not_change_the_account():
    p = Portfolio(1000)
    p.buy(4, 200)
    before = state(p)
    p.equity(999)
    assert state(p) == before


def test_total_value_after_a_buy_without_costs_equals_the_starting_cash():
    p = Portfolio(1000)
    p.buy(3, 300)
    assert p.equity(300) == 1000.0


def test_total_value_after_a_buy_with_costs_is_the_starting_cash_less_the_costs():
    p = Portfolio(1000, fee=5, fee_pct=1)
    cost = p.buy(4, 200)
    assert p.equity(200) == pytest.approx(1000 - cost)


def test_total_value_after_a_round_trip_is_the_new_cash():
    p = Portfolio(1000)
    p.buy(4, 200)
    p.sell(4, 250)
    assert p.position == 0
    assert p.equity(1) == p.cash == 1200.0


@pytest.mark.parametrize("bad_price", [0, -1, -0.01])
def test_total_value_rejects_non_positive_price(bad_price):
    p = Portfolio(1000)
    with pytest.raises(ValueError) as excinfo:
        p.equity(bad_price)
    assert str(excinfo.value) == f"price must be positive, got {bad_price}"
