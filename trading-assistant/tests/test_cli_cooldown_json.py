"""--json with --cooldown N: cooldown_bars and cooldown_skipped_buys, only when --cooldown is used.

The hand file is the 11-bar candle file of test_cli_cooldown.py (--cash 1000
--short 1 --long 2 --stop-loss 10): --cooldown 3 skips the bar 9 buy (end 901),
--cooldown 2 does not (end 916).

BEFORE_ALL_KEYS_JSON was captured from the command before --cooldown existed
(the unchanged code at git HEAD) with every optional backtest key present.
"""

import json

import pytest

from trading_assistant.cli import main

HAND = """\
date,open,high,low,close,volume
2026-01-01,10,10.5,9.5,10,1000
2026-01-02,9.2,9.5,8.5,9,1000
2026-01-05,8.3,8.5,7.5,8,1000
2026-01-06,8.8,9.5,8.5,9,1000
2026-01-07,10.8,11.5,10.5,11,1000
2026-01-08,11,12,10.8,12,1000
2026-01-09,11.5,12,9.5,10,1000
2026-01-12,9.8,10.2,9.6,10,1000
2026-01-13,10,11.5,9.9,11,1000
2026-01-14,10.8,12.5,10.5,12,1000
2026-01-15,12,12.4,11.8,12.2,1000
"""
B = ["--backtest", "--cash", "1000", "--short", "1", "--long", "2", "--stop-loss", "10"]
ALL_KEYS = [
    "--trailing-stop", "8", "--take-profit", "20", "--atr-stop", "--atr-mult", "1", "--atr-period", "1",
    "--risk-pct", "0.16", "--stats", "--export", "E.csv",
]

BEFORE_ALL_KEYS_JSON = (
    '{\n'
    '  "bars": 11,\n'
    '  "last_close": 12.2,\n'
    '  "signal": "HOLD",\n'
    '  "rsi": null,\n'
    '  "rsi_label": null,\n'
    '  "backtest": {\n'
    '    "strategy": "sma_cross",\n'
    '    "params": {\n'
    '      "short": 1,\n'
    '      "long": 2\n'
    '    },\n'
    '    "fill": "close",\n'
    '    "start_cash": 1000.0,\n'
    '    "fee": 0.0,\n'
    '    "fee_pct": 0.0,\n'
    '    "slippage_pct": 0.0,\n'
    '    "position_size": null,\n'
    '    "risk_pct": 0.16,\n'
    '    "atr_mult": 1.0,\n'
    '    "atr_period": 1,\n'
    '    "stop_loss_pct": 10.0,\n'
    '    "take_profit_pct": 20.0,\n'
    '    "trailing_stop_pct": 8.0,\n'
    '    "atr_stop": true,\n'
    '    "trades": 3,\n'
    '    "buys": 2,\n'
    '    "sells": 1,\n'
    '    "risk_skipped_buys": 0,\n'
    '    "fills": [\n'
    '      {\n'
    '        "bar": 4,\n'
    '        "side": "BUY",\n'
    '        "shares": 1,\n'
    '        "price": 11.0,\n'
    '        "value": 11.0,\n'
    '        "cost": 0.0,\n'
    '        "cash_after": 989.0,\n'
    '        "reason": "signal"\n'
    '      },\n'
    '      {\n'
    '        "bar": 6,\n'
    '        "side": "SELL",\n'
    '        "shares": 1,\n'
    '        "price": 11.040000000000001,\n'
    '        "value": 11.040000000000001,\n'
    '        "cost": 0.0,\n'
    '        "cash_after": 1000.04,\n'
    '        "reason": "trail"\n'
    '      },\n'
    '      {\n'
    '        "bar": 9,\n'
    '        "side": "BUY",\n'
    '        "shares": 1,\n'
    '        "price": 12.0,\n'
    '        "value": 12.0,\n'
    '        "cost": 0.0,\n'
    '        "cash_after": 988.04,\n'
    '        "reason": "signal"\n'
    '      }\n'
    '    ],\n'
    '    "total_costs": 0.0,\n'
    '    "round_trips": 1,\n'
    '    "winning_round_trips": 1,\n'
    '    "final_cash": 988.04,\n'
    '    "final_position": 1,\n'
    '    "final_price": 12.2,\n'
    '    "final_equity": 1000.24,\n'
    '    "return_pct": 0.02400000000000091,\n'
    '    "max_drawdown_pct": -0.09590409590409954,\n'
    '    "benchmark": {\n'
    '      "shares": 100,\n'
    '      "final_cash": 0.0,\n'
    '      "final_equity": 1220.0,\n'
    '      "return_pct": 22.0,\n'
    '      "max_drawdown_pct": -20.0,\n'
    '      "trades": 1,\n'
    '      "total_costs": 0.0\n'
    '    },\n'
    '    "export": {\n'
    '      "path": "E.csv",\n'
    '      "rows": 11\n'
    '    },\n'
    '    "stats": {\n'
    '      "total_return_pct": 0.024000000000001798,\n'
    '      "cagr_pct": 0.6065596033120402,\n'
    '      "annualized_volatility_pct": 0.7396662584210426,\n'
    '      "sharpe_ratio": 0.820906208860871,\n'
    '      "sortino_ratio": 1.2612231168398016,\n'
    '      "exposure_pct": 36.36363636363637,\n'
    '      "profit_factor": null,\n'
    '      "average_win": 0.040000000000000924,\n'
    '      "average_loss": null,\n'
    '      "longest_drawdown_bars": 5\n'
    '    }\n'
    '  },\n'
    '  "disclaimer": "Research aid only. Not financial advice."\n'
    '}\n'
)


@pytest.fixture
def folder(tmp_path, monkeypatch):
    (tmp_path / "hand.csv").write_text(HAND)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    return tmp_path


def run(argv, capsys):
    code = main(argv)
    out, err = capsys.readouterr()
    assert (code, err) == (0, "")
    return out


@pytest.mark.parametrize(
    "n, skipped, fills, final_cash, final_equity, return_pct",
    [
        (3, 1, [(4, "BUY", 90, 11.0, "signal"), (6, "SELL", 90, 9.9, "stop")], 901.0, 901.0, -9.9),
        (2, 0, [(4, "BUY", 90, 11.0, "signal"), (6, "SELL", 90, 9.9, "stop"), (9, "BUY", 75, 12.0, "signal")], 1.0, 916.0, -8.4),
    ],
)
def test_hand_case_json_matches_the_text_report(folder, capsys, n, skipped, fills, final_cash, final_equity, return_pct):
    data = json.loads(run(["hand.csv", *B, "--cooldown", str(n), "--json"], capsys))["backtest"]
    assert (data["cooldown_bars"], data["cooldown_skipped_buys"]) == (n, skipped)
    assert [(f["bar"], f["side"], f["shares"], f["price"], f["reason"]) for f in data["fills"]] == fills
    assert (data["final_cash"], data["final_equity"]) == (pytest.approx(final_cash), pytest.approx(final_equity))
    assert data["return_pct"] == pytest.approx(return_pct)
    # The same run as text says the same.
    text = run(["hand.csv", *B, "--cooldown", str(n)], capsys).splitlines()
    bars = "bar" if n == 1 else "bars"
    buys = "buy" if skipped == 1 else "buys"
    assert f"  Cooldown:    {n} {bars} after a stop, trail or atr exit; {skipped} {buys} skipped" in text
    assert f"  End equity:  {final_equity:,.2f}" in text and f"  Return:      {return_pct:+.2f}%" in text
    assert len([line for line in text if line.startswith("    #")]) == len(fills) == data["trades"]


def test_key_places(folder, capsys):
    # Stop only: cooldown_bars right after take_profit_pct, cooldown_skipped_buys right after sells.
    keys = list(json.loads(run(["hand.csv", *B, "--cooldown", "3", "--json"], capsys))["backtest"])
    assert keys[keys.index("take_profit_pct") :][:6] == [
        "take_profit_pct", "cooldown_bars", "trades", "buys", "sells", "cooldown_skipped_buys",
    ]
    # Every optional key: the keys as before, plus cooldown_bars after atr_stop and
    # cooldown_skipped_buys after risk_skipped_buys.
    keys = list(json.loads(run(["hand.csv", *B, *ALL_KEYS, "--cooldown", "3", "--json"], capsys))["backtest"])
    before = list(json.loads(BEFORE_ALL_KEYS_JSON)["backtest"])
    i, j = before.index("atr_stop") + 1, before.index("risk_skipped_buys") + 1
    assert keys == before[:i] + ["cooldown_bars"] + before[i:j] + ["cooldown_skipped_buys"] + before[j:]


def test_without_cooldown_the_json_is_exactly_as_before(folder, capsys):
    assert run(["hand.csv", *B, *ALL_KEYS, "--json"], capsys) == BEFORE_ALL_KEYS_JSON


def test_export_is_the_same_with_or_without_json(folder, capsys):
    run(["hand.csv", *B, "--cooldown", "3", "--export", "E.csv", "--json"], capsys)
    with_json = (folder / "E.csv").read_text()
    run(["hand.csv", *B, "--cooldown", "3", "--export", "E.csv"], capsys)
    assert (folder / "E.csv").read_text() == with_json
    assert "cooldown" not in with_json
