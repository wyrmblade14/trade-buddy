"""The portfolio engine with a strategy: run_portfolio, run_files, run_texts and strategies.first_signal_bars.

The hand-worked example: AAA and BBB over the 10 shared dates 2026-04-01 to 2026-04-10, cash 1000.

    bar      0   1   2   3   4   5   6   7   8   9
    AAA     10  11  12  13  12  11  10  11  13  14
    BBB     20  19  18  19  21  22  21  19  18  20

``tests/data/portfolio_before_strategy.json`` holds 13 runs recorded with the code as it was before
``strategy`` existed (inputs and outputs); runs without a strategy must still give exactly those.
"""

import json
import math
import random
from pathlib import Path

import pytest

from trading_assistant import cli, portfolio
from trading_assistant.backtest import max_drawdown_pct
from trading_assistant.samples import sample_csv_rows, sample_table
from trading_assistant.signals import HOLD
from trading_assistant.strategies import STRATEGIES, first_signal_bars, resolve_params

DATES = [f"2026-04-{i:02d}" for i in range(1, 11)]
AAA = [10, 11, 12, 13, 12, 11, 10, 11, 13, 14]
BBB = [20, 19, 18, 19, 21, 22, 21, 19, 18, 20]
HAND = {"AAA": AAA, "BBB": BBB}


def hand_tables(n=10):
    return {symbol: (DATES[:n], [float(c) for c in closes[:n]]) for symbol, closes in HAND.items()}


def fills(result):
    return [(t.side, t.shares, t.price, t.bar) for t in result.trades]


def test_sma_2_3_example():
    result = portfolio.run_portfolio(hand_tables(), cash=1000, short=2, long=3)
    summary = portfolio.summarize(result)
    assert result.strategy == "sma_cross" and result.strategy_params == {}
    assert (result.short, result.long) == (2, 3)
    assert summary["final_equity"] == pytest.approx(912.00)
    assert f"{summary['return_pct']:.2f}" == "-8.80"
    assert [(row["symbol"], row["trades"]) for row in summary["symbols"]] == [("AAA", 1), ("BBB", 2)]


def test_breakout_3_hand_worked_and_agrees_with_the_main_command(tmp_path, capsys):
    result = portfolio.run_portfolio(hand_tables(), cash=1000, strategy="breakout", strategy_params={"window": 3})
    assert result.strategy == "breakout" and result.strategy_params == {"window": 3}
    assert (result.short, result.long) == (None, None)
    aaa, bbb = result.results["AAA"], result.results["BBB"]

    # AAA, 500 cash. Bar 3: 13 > max(10, 11, 12) -> BUY, filled on bar 4 at 12: 41 shares (492), cash 8.
    # Bar 5: 11 < min(12, 13, 12) -> SELL, filled on bar 6 at 10: cash 8 + 410 = 418.
    # Bar 8: 13 > max(11, 10, 11) -> BUY, filled on bar 9 at 14: 29 shares (406), cash 12. End 12 + 29 * 14 = 418.
    assert fills(aaa) == [("BUY", 41, 12.0, 4), ("SELL", 41, 10.0, 6), ("BUY", 29, 14.0, 9)]
    assert aaa.equity_curve == [500, 500, 500, 500, 500, 459, 418, 418, 418, 418]
    # BBB, 500 cash. Bar 4: 21 > max(19, 18, 19) -> BUY, filled on bar 5 at 22: 22 shares (484), cash 16.
    # Bar 7: 19 < min(21, 22, 21) -> SELL, filled on bar 8 at 18: cash 16 + 396 = 412.
    assert fills(bbb) == [("BUY", 22, 22.0, 5), ("SELL", 22, 18.0, 8)]
    assert bbb.equity_curve == [500, 500, 500, 500, 500, 500, 478, 434, 412, 412]

    # Portfolio equity, date by date: AAA + BBB.
    #   bars 0-4: 500 + 500 = 1000
    #   bar 5:    459 + 500 =  959     (AAA: 8 + 41 * 11)
    #   bar 6:    418 + 478 =  896     (BBB: 16 + 22 * 21)
    #   bar 7:    418 + 434 =  852     (BBB: 16 + 22 * 19)
    #   bars 8-9: 418 + 412 =  830
    # Max drawdown: the peak is 1000 (bars 0-4) and nothing after it is higher; the lowest point after it
    # is 830, so (830 - 1000) / 1000 = -17.00%. Along the way: -4.10%, -10.40%, -14.80%, -17.00%.
    assert result.equity == [1000, 1000, 1000, 1000, 1000, 959, 896, 852, 830, 830]
    summary = portfolio.summarize(result)
    assert summary["final_equity"] == 830.0
    assert summary["return_pct"] == pytest.approx(-17.0)
    assert summary["max_drawdown_pct"] == pytest.approx((830 - 1000) / 1000 * 100) == pytest.approx(-17.0)
    # Buy and hold, same split: AAA 50 shares at 10 -> 700, BBB 25 at 20 -> 500; 1200 on 1000 is +20.00%.
    assert summary["buy_hold_return_pct"] == pytest.approx(20.0)
    assert summary["worst_symbol_drawdown"]["symbol"] == "BBB"  # -17.60% against AAA's -16.40%

    # The main command on each file alone with cash 500 gives the same fills and end equity.
    for symbol, result_alone in (("AAA", aaa), ("BBB", bbb)):
        path = tmp_path / f"{symbol}.csv"
        path.write_text("date,close\n" + "".join(f"{d},{c}\n" for d, c in zip(DATES, HAND[symbol])))
        code = cli.main([str(path), "--backtest", "--cash", "500", "--short", "2", "--long", "3",
                         "--strategy", "breakout", "--param", "window=3", "--json"])
        assert code == 0
        command = json.loads(capsys.readouterr().out)["backtest"]
        assert [(f["side"], f["shares"], f["price"], f["bar"]) for f in command["fills"]] == fills(result_alone)
        assert command["final_equity"] == result_alone.final_equity
        assert command["benchmark"]["final_equity"] == result_alone.benchmark.final_equity
    assert (aaa.final_equity, bbb.final_equity) == (418.0, 412.0)


def test_weights_with_a_strategy_hand_worked():
    weights = portfolio.parse_weights(["AAA=60", "BBB=40"])
    result = portfolio.run_portfolio(hand_tables(), cash=1000, weights=weights, strategy="breakout",
                                     strategy_params={"window": 3})
    # AAA, 600: BUY 50 at 12 (cash 0), SELL 50 at 10 (500), BUY 35 at 14 (490, cash 10): end 500.
    # BBB, 400: BUY 18 at 22 (396, cash 4), SELL 18 at 18 (324, cash 328): end 328.
    assert fills(result.results["AAA"]) == [("BUY", 50, 12.0, 4), ("SELL", 50, 10.0, 6), ("BUY", 35, 14.0, 9)]
    assert fills(result.results["BBB"]) == [("BUY", 18, 22.0, 5), ("SELL", 18, 18.0, 8)]
    summary = portfolio.summarize(result)
    assert summary["weights"] == {"AAA": 60.0, "BBB": 40.0}
    assert summary["initial_cash"] == 1000.0 and summary["final_equity"] == 828.0
    assert summary["return_pct"] == pytest.approx(-17.2)
    # Buy and hold, same weights: AAA 60 shares -> 840, BBB 20 shares -> 400; 1240 on 1000 is +24.00%.
    assert summary["buy_hold_return_pct"] == pytest.approx(24.0)
    # run_texts (the web page's path) gives the same numbers.
    texts = {f"{s}.csv": "date,close\n" + "".join(f"{d},{c}\n" for d, c in zip(DATES, cs)) for s, cs in HAND.items()}
    data = portfolio.run_texts(texts, cash=1000, weights=weights, strategy="breakout", strategy_params={"window": 3})
    assert data["summary"]["final_equity"] == 828.0 and data["skipped"] == []


# Parameters for which the first signal needs 9 bars, so exactly 10 shared dates are needed.
TEN_DATES = [
    ("sma_cross", {"short": 2, "long": 8}, "need at least 10 (long window 8 + 2)"),
    ("ema_cross", {"short": 2, "long": 8}, "need at least 10 for ema_cross (short=2, long=8): 9 for its first signal + 1 to fill it"),
    ("breakout", {"window": 8}, "need at least 10 for breakout (window=8): 9 for its first signal + 1 to fill it"),
    ("zscore_reversion", {"window": 8},
     "need at least 10 for zscore_reversion (window=8, entry=-2.0, exit=0.0): 9 for its first signal + 1 to fill it"),
    ("rsi_reversion", {"period": 7},
     "need at least 10 for rsi_reversion (period=7, oversold=30, overbought=70): 9 for its first signal + 1 to fill it"),
    ("momentum", {"window": 7},
     "need at least 10 for momentum (window=7, threshold=0.0): 9 for its first signal + 1 to fill it"),
    ("hull_trend", {"window": 6}, "need at least 10 for hull_trend (window=6): 9 for its first signal + 1 to fill it"),
]


@pytest.mark.parametrize("strategy, params, message", TEN_DATES, ids=[case[0] for case in TEN_DATES])
def test_too_few_shared_dates(strategy, params, message):
    portfolio.run_portfolio(hand_tables(10), strategy=strategy, strategy_params=params)  # 10 is enough
    with pytest.raises(portfolio.PortfolioError) as caught:
        portfolio.run_files(hand_tables(9), [], "pf", strategy=strategy, strategy_params=params)
    assert str(caught.value) == "only 9 dates shared by all 2 symbols; " + message


def test_refused_strategy_settings():
    tables = hand_tables()
    for strategy, params, message in (
        ("breakout", {"window": 0}, "window must be a whole number of at least 1, got 0"),
        ("breakout", {"period": 3}, "unknown parameter 'period' for strategy 'breakout'; choose from: window"),
        ("sma_cross", {"window": 3}, "unknown parameter 'window' for strategy 'sma_cross'; choose from: short, long"),
        ("sma_cross", {"short": 3, "long": 3}, "short window must be smaller than long window"),
        ("nope", None, "unknown strategy 'nope'; choose from: " + ", ".join(STRATEGIES)),
    ):
        with pytest.raises(portfolio.PortfolioError) as caught:
            portfolio.run_files(tables, [], "pf", strategy=strategy, strategy_params=params)
        assert str(caught.value) == message


BRUTE = [
    ("sma_cross", {}), ("sma_cross", {"short": 1, "long": 3}),
    ("ema_cross", {}), ("ema_cross", {"short": 2, "long": 4}),
    ("breakout", {}), ("breakout", {"window": 2}),
    ("zscore_reversion", {}), ("zscore_reversion", {"window": 3}),
    ("rsi_reversion", {}), ("rsi_reversion", {"period": 2}),
    ("momentum", {}), ("momentum", {"window": 1}),
    ("hull_trend", {}), ("hull_trend", {"window": 4}),
]


def _series(rng, n):
    """Positive closes: a random walk, or a V or an inverted V that turns at a random bar."""
    style = rng.randrange(3)
    turn = rng.randrange(n)
    price, closes = 100.0, []
    for i in range(n):
        drift = 0.0 if style == 0 else (-1.0 if (i < turn) == (style == 1) else 1.0)
        price = max(1.0, price + drift * rng.uniform(0, 3) + rng.gauss(0, 2))
        closes.append(round(price, 2))
    return closes


@pytest.mark.parametrize("strategy, overrides", BRUTE, ids=[f"{s}-{p or 'defaults'}" for s, p in BRUTE])
def test_first_signal_bars_by_brute_force(strategy, overrides):
    # With first_signal_bars(...) closes the last bar can signal (some series does), and no bar before it
    # ever does (on any series tried).
    params = resolve_params(strategy, overrides)
    function = STRATEGIES[strategy][0]
    first = first_signal_bars(strategy, params)
    rng = random.Random(f"{strategy}{overrides}")
    found = 0
    for trial in range(5000):
        closes = _series(rng, first)
        signals = [function(closes, t, **params) for t in range(first)]
        assert signals[:-1] == [HOLD] * (first - 1), (closes, signals)
        found += signals[-1] != HOLD
        if found and trial >= 300:
            break
    assert found, f"no series of {first} closes gave a signal on its last bar"


def test_first_signal_bars_rules():
    assert first_signal_bars("sma_cross", {"short": 20, "long": 50}) == 51  # the old long + 2 dates, less the fill
    assert first_signal_bars("hull_trend", {"window": 20}) == 20 + math.isqrt(20) + 1
    with pytest.raises(ValueError, match="unknown strategy"):
        first_signal_bars("nope", {})


# -- runs without a strategy: exactly as recorded before it existed ----------------------------------------

BEFORE = json.loads((Path(__file__).parent / "data" / "portfolio_before_strategy.json").read_text())
SAMPLE_SYMBOLS = ("downtrend", "sideways", "uptrend")


def _tables(name):
    if name == "hand":
        return hand_tables()
    if name == "hand_one":
        return {"AAA": hand_tables()["AAA"]}
    return {symbol: sample_table(symbol) for symbol in SAMPLE_SYMBOLS}


def _texts(name):
    if name == "hand":
        return {f"{s}.csv": "date,close\n" + "".join(f"{d},{c}\n" for d, c in zip(DATES, cs)) for s, cs in HAND.items()}
    return {f"{s}.csv": "".join(",".join(row) + "\n" for row in sample_csv_rows(s)) for s in SAMPLE_SYMBOLS}


def _replay(case, **extra):
    kw = {**case["kw"], **extra}
    if "weights" in kw:
        kw["weights"] = portfolio.parse_weights([f"{s}={p}" for s, p in kw["weights"].items()])
    try:
        if case["via"] == "run_texts":
            return {"json": portfolio.run_texts(_texts(case["tables"]), **kw)}
        if case["via"] == "run_files":
            result = portfolio.run_files(_tables(case["tables"]), [], "pf", **kw)
        else:
            result = portfolio.run_portfolio(_tables(case["tables"]), **kw)
    except ValueError as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    summary = portfolio.summarize(result)
    return {"summary": summary, "text": portfolio.format_portfolio(summary), "csv": portfolio.csv_rows(result)}


def test_runs_without_a_strategy_are_unchanged():
    assert len(BEFORE) == 13
    for case in BEFORE:
        windows = {"short": case["kw"].get("short", 20), "long": case["kw"].get("long", 50)}
        as_params = {key: value for key, value in case["kw"].items() if key not in ("short", "long")}
        # Round-trip through JSON so tuples and lists, ints and floats compare as they were stored.
        assert json.loads(json.dumps(_replay(case))) == case["output"], case["kw"]
        assert json.loads(json.dumps(_replay(case, strategy="sma_cross"))) == case["output"], case["kw"]
        spelled = {**case, "kw": as_params}
        assert json.loads(json.dumps(_replay(spelled, strategy="sma_cross", strategy_params=windows))) \
            == case["output"], case["kw"]
