"""The trading account used by the backtest: cash plus a whole-share position.

``Portfolio`` holds cash and a long position in a single instrument and
applies the trading rules the backtest relies on:

* whole shares only, no short selling, no leverage; cash never goes negative;
* optional costs, a fixed fee per trade plus a percentage of the traded
  value, charged on every buy and every sell;
* ``buy`` and ``sell`` raise ``ValueError`` for an impossible order (not
  enough cash, more shares than held, a share count that is not a positive
  whole number, a non-positive price) and leave the account unchanged;
* ``equity`` is the account's total value with the position marked at a price.

The backtest module re-exports ``Portfolio``, so
``from trading_assistant.backtest import Portfolio`` keeps working.

This is a research aid. It places no orders and it is not financial advice.
"""


class Portfolio:
    """Cash plus a whole-share long position in a single instrument.

    ``fee`` is a fixed amount charged on every trade; ``fee_pct`` is a
    percentage of the traded value (``1.0`` means 1 %) charged on every trade.
    """

    def __init__(self, cash, fee=0.0, fee_pct=0.0):
        if cash < 0:
            raise ValueError(f"initial cash must not be negative, got {cash}")
        if fee < 0:
            raise ValueError(f"fee must not be negative, got {fee}")
        if not 0 <= fee_pct < 100:
            raise ValueError(f"fee_pct must be between 0 and 100 (exclusive), got {fee_pct}")
        self.cash = float(cash)
        self.position = 0
        self.fee = float(fee)
        self.fee_pct = float(fee_pct)
        self.total_costs = 0.0

    def __repr__(self):
        return f"Portfolio(cash={self.cash:.2f}, position={self.position})"

    def trade_cost(self, shares, price):
        """Total cost (fixed fee + percentage) of trading ``shares`` at ``price``."""
        return self.fee + shares * price * self.fee_pct / 100.0

    def buy(self, shares, price):
        """Buy ``shares`` at ``price``. Rejects anything the cash cannot cover, costs included."""
        _check_shares(shares)
        _check_price(price)
        cost = self.trade_cost(shares, price)
        total = shares * price + cost
        if total > self.cash:
            raise ValueError(
                f"cannot buy {shares} @ {price:.2f}: cost {total:.2f} "
                f"(incl. {cost:.2f} fees) exceeds cash {self.cash:.2f}"
            )
        self.cash -= total
        self.position += shares
        self.total_costs += cost
        return cost

    def sell(self, shares, price):
        """Sell ``shares`` at ``price``. Rejects selling more than is held or
        a sale whose costs would leave the cash negative."""
        _check_shares(shares)
        _check_price(price)
        if shares > self.position:
            raise ValueError(
                f"cannot sell {shares}: only {self.position} held (no short selling)"
            )
        cost = self.trade_cost(shares, price)
        net = shares * price - cost
        if self.cash + net < 0:
            raise ValueError(
                f"cannot sell {shares} @ {price:.2f}: fees {cost:.2f} exceed proceeds "
                f"{shares * price:.2f} plus cash {self.cash:.2f}"
            )
        self.cash += net
        self.position -= shares
        self.total_costs += cost
        return cost

    def equity(self, price):
        """Cash plus the position marked at ``price``."""
        _check_price(price)
        return self.cash + self.position * price

    def max_affordable(self, price):
        """Largest whole number of shares whose cost, fees included, does not exceed the cash."""
        _check_price(price)
        budget = self.cash - self.fee
        if budget <= 0:
            return 0
        shares = int(budget / (price * (1 + self.fee_pct / 100.0)))
        # Guard against floating point rounding making the estimate one too many.
        while shares > 0 and shares * price + self.trade_cost(shares, price) > self.cash:
            shares -= 1
        return shares


def _check_shares(shares):
    if isinstance(shares, bool) or not isinstance(shares, int):
        raise ValueError(f"shares must be a whole number, got {shares!r}")
    if shares < 1:
        raise ValueError(f"shares must be at least 1, got {shares}")


def _check_price(price):
    if not price > 0:
        raise ValueError(f"price must be positive, got {price}")
