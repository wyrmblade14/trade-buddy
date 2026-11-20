"""--json with --atr-stop: atr_stop, atr_mult, atr_period and risk_skipped_buys.

Hand case (the candle file of test_cli_risk_sizing.py), --cash 1000 --short 1
--long 2 --atr-stop --atr-mult 2 --atr-period 3: BUY signal on bar 3 with
ATR(3) = 25/18, level 11 - 2 * 25/18 = 74/9 ~ 8.2222. BUY 90 @ 11 on bar 4; bar 7
opens at 8.6 (above the level) and its low 7.5 reaches it: SELL 90 @ 74/9 = 740,
final equity 750, reason atr, 0 skipped.
With --risk-pct 2 as well: 7 shares @ 11, sold @ 74/9 on bar 7: final equity 980.56.
With --atr-period 5 the first ATR is on bar 4, after the signal: 1 skipped (once,
also with --risk-pct).

Where the keys go (each only when its option is used, so the JSON of runs
without --atr-stop stays exactly as it was):

    ... "position_size", ["risk_pct"], "atr_mult", "atr_period", "stop_loss_pct",
        "take_profit_pct", ["trailing_stop_pct"], "atr_stop", "trades", "buys",
        "sells", "risk_skipped_buys", "fills", ...

The NEW_* text was captured from the command with this change; the BEFORE_*
texts were captured from the command before --json showed the ATR stop.
"""

import json
import re

import pytest

from trading_assistant.cli import main

HAND = """\
date,open,high,low,close,volume
2026-01-01,10,10.5,9.5,10,1000
2026-01-02,9.2,9.5,8.5,9,1000
2026-01-03,8.3,8.5,7.5,8,1000
2026-01-04,8.8,9.5,8.5,9,1000
2026-01-05,10.8,11.5,10.5,11,1000
2026-01-06,12.2,13,11.2,12,1000
2026-01-07,11.5,12.5,9.8,10,1000
2026-01-08,8.6,9,7.5,8,1000
"""
B = ["hand.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]
ATR = ["--atr-stop", "--atr-mult", "2", "--atr-period", "3"]

NEW_HAND_JSON = (
    "{\n"
    "  \"bars\": 8,\n"
    "  \"last_close\": 8.0,\n"
    "  \"signal\": \"HOLD\",\n"
    "  \"rsi\": null,\n"
    "  \"rsi_label\": null,\n"
    "  \"backtest\": {\n"
    "    \"strategy\": \"sma_cross\",\n"
    "    \"params\": {\n"
    "      \"short\": 1,\n"
    "      \"long\": 2\n"
    "    },\n"
    "    \"fill\": \"close\",\n"
    "    \"start_cash\": 1000.0,\n"
    "    \"fee\": 0.0,\n"
    "    \"fee_pct\": 0.0,\n"
    "    \"slippage_pct\": 0.0,\n"
    "    \"position_size\": null,\n"
    "    \"atr_mult\": 2.0,\n"
    "    \"atr_period\": 3,\n"
    "    \"stop_loss_pct\": null,\n"
    "    \"take_profit_pct\": null,\n"
    "    \"atr_stop\": true,\n"
    "    \"trades\": 2,\n"
    "    \"buys\": 1,\n"
    "    \"sells\": 1,\n"
    "    \"risk_skipped_buys\": 0,\n"
    "    \"fills\": [\n"
    "      {\n"
    "        \"bar\": 4,\n"
    "        \"side\": \"BUY\",\n"
    "        \"shares\": 90,\n"
    "        \"price\": 11.0,\n"
    "        \"value\": 990.0,\n"
    "        \"cost\": 0.0,\n"
    "        \"cash_after\": 10.0,\n"
    "        \"reason\": \"signal\"\n"
    "      },\n"
    "      {\n"
    "        \"bar\": 7,\n"
    "        \"side\": \"SELL\",\n"
    "        \"shares\": 90,\n"
    "        \"price\": 8.222222222222223,\n"
    "        \"value\": 740.0000000000001,\n"
    "        \"cost\": 0.0,\n"
    "        \"cash_after\": 750.0000000000001,\n"
    "        \"reason\": \"atr\"\n"
    "      }\n"
    "    ],\n"
    "    \"total_costs\": 0.0,\n"
    "    \"round_trips\": 1,\n"
    "    \"winning_round_trips\": 0,\n"
    "    \"final_cash\": 750.0000000000001,\n"
    "    \"final_position\": 0,\n"
    "    \"final_price\": 8.0,\n"
    "    \"final_equity\": 750.0000000000001,\n"
    "    \"return_pct\": -24.99999999999999,\n"
    "    \"max_drawdown_pct\": -31.192660550458704,\n"
    "    \"benchmark\": {\n"
    "      \"shares\": 100,\n"
    "      \"final_cash\": 0.0,\n"
    "      \"final_equity\": 800.0,\n"
    "      \"return_pct\": -20.0,\n"
    "      \"max_drawdown_pct\": -33.33333333333333,\n"
    "      \"trades\": 1,\n"
    "      \"total_costs\": 0.0\n"
    "    }\n"
    "  },\n"
    "  \"disclaimer\": \"Research aid only. Not financial advice.\"\n"
    "}\n"
)
BEFORE_RISK_STATS_EXPORT_JSON = (
    "{\n"
    "  \"bars\": 8,\n"
    "  \"last_close\": 8.0,\n"
    "  \"signal\": \"HOLD\",\n"
    "  \"rsi\": null,\n"
    "  \"rsi_label\": null,\n"
    "  \"backtest\": {\n"
    "    \"strategy\": \"sma_cross\",\n"
    "    \"params\": {\n"
    "      \"short\": 1,\n"
    "      \"long\": 2\n"
    "    },\n"
    "    \"fill\": \"close\",\n"
    "    \"start_cash\": 1000.0,\n"
    "    \"fee\": 0.0,\n"
    "    \"fee_pct\": 0.0,\n"
    "    \"slippage_pct\": 0.0,\n"
    "    \"position_size\": null,\n"
    "    \"risk_pct\": 2.0,\n"
    "    \"atr_mult\": 2.0,\n"
    "    \"atr_period\": 3,\n"
    "    \"stop_loss_pct\": null,\n"
    "    \"take_profit_pct\": null,\n"
    "    \"trades\": 2,\n"
    "    \"buys\": 1,\n"
    "    \"sells\": 1,\n"
    "    \"risk_skipped_buys\": 0,\n"
    "    \"fills\": [\n"
    "      {\n"
    "        \"bar\": 4,\n"
    "        \"side\": \"BUY\",\n"
    "        \"shares\": 7,\n"
    "        \"price\": 11.0,\n"
    "        \"value\": 77.0,\n"
    "        \"cost\": 0.0,\n"
    "        \"cash_after\": 923.0,\n"
    "        \"reason\": \"signal\"\n"
    "      },\n"
    "      {\n"
    "        \"bar\": 7,\n"
    "        \"side\": \"SELL\",\n"
    "        \"shares\": 7,\n"
    "        \"price\": 8.0,\n"
    "        \"value\": 56.0,\n"
    "        \"cost\": 0.0,\n"
    "        \"cash_after\": 979.0,\n"
    "        \"reason\": \"signal\"\n"
    "      }\n"
    "    ],\n"
    "    \"total_costs\": 0.0,\n"
    "    \"round_trips\": 1,\n"
    "    \"winning_round_trips\": 0,\n"
    "    \"final_cash\": 979.0,\n"
    "    \"final_position\": 0,\n"
    "    \"final_price\": 8.0,\n"
    "    \"final_equity\": 979.0,\n"
    "    \"return_pct\": -2.1,\n"
    "    \"max_drawdown_pct\": -2.780536246276067,\n"
    "    \"benchmark\": {\n"
    "      \"shares\": 100,\n"
    "      \"final_cash\": 0.0,\n"
    "      \"final_equity\": 800.0,\n"
    "      \"return_pct\": -20.0,\n"
    "      \"max_drawdown_pct\": -33.33333333333333,\n"
    "      \"trades\": 1,\n"
    "      \"total_costs\": 0.0\n"
    "    },\n"
    "    \"export\": {\n"
    "      \"path\": \"E.csv\",\n"
    "      \"rows\": 8\n"
    "    },\n"
    "    \"stats\": {\n"
    "      \"total_return_pct\": -2.100000000000002,\n"
    "      \"cagr_pct\": -53.42242166509541,\n"
    "      \"annualized_volatility_pct\": 12.600823240338743,\n"
    "      \"sharpe_ratio\": -6.000000000000048,\n"
    "      \"sortino_ratio\": -6.363909061513708,\n"
    "      \"exposure_pct\": 37.5,\n"
    "      \"profit_factor\": 0.0,\n"
    "      \"average_win\": null,\n"
    "      \"average_loss\": -21.0,\n"
    "      \"longest_drawdown_bars\": 2\n"
    "    }\n"
    "  },\n"
    "  \"disclaimer\": \"Research aid only. Not financial advice.\"\n"
    "}\n"
)
BEFORE_RISK_EXITS_OPEN_JSON = (
    "{\n"
    "  \"bars\": 8,\n"
    "  \"last_close\": 8.0,\n"
    "  \"signal\": \"HOLD\",\n"
    "  \"rsi\": null,\n"
    "  \"rsi_label\": null,\n"
    "  \"backtest\": {\n"
    "    \"strategy\": \"sma_cross\",\n"
    "    \"params\": {\n"
    "      \"short\": 1,\n"
    "      \"long\": 2\n"
    "    },\n"
    "    \"fill\": \"open\",\n"
    "    \"start_cash\": 1000.0,\n"
    "    \"fee\": 0.0,\n"
    "    \"fee_pct\": 0.0,\n"
    "    \"slippage_pct\": 0.0,\n"
    "    \"position_size\": null,\n"
    "    \"risk_pct\": 2.0,\n"
    "    \"atr_mult\": 2.0,\n"
    "    \"atr_period\": 3,\n"
    "    \"stop_loss_pct\": 5.0,\n"
    "    \"take_profit_pct\": null,\n"
    "    \"trailing_stop_pct\": 8.0,\n"
    "    \"trades\": 2,\n"
    "    \"buys\": 1,\n"
    "    \"sells\": 1,\n"
    "    \"risk_skipped_buys\": 0,\n"
    "    \"fills\": [\n"
    "      {\n"
    "        \"bar\": 4,\n"
    "        \"side\": \"BUY\",\n"
    "        \"shares\": 7,\n"
    "        \"price\": 10.8,\n"
    "        \"value\": 75.60000000000001,\n"
    "        \"cost\": 0.0,\n"
    "        \"cash_after\": 924.4,\n"
    "        \"reason\": \"signal\"\n"
    "      },\n"
    "      {\n"
    "        \"bar\": 6,\n"
    "        \"side\": \"SELL\",\n"
    "        \"shares\": 7,\n"
    "        \"price\": 11.5,\n"
    "        \"value\": 80.5,\n"
    "        \"cost\": 0.0,\n"
    "        \"cash_after\": 1004.9,\n"
    "        \"reason\": \"trail\"\n"
    "      }\n"
    "    ],\n"
    "    \"total_costs\": 0.0,\n"
    "    \"round_trips\": 1,\n"
    "    \"winning_round_trips\": 1,\n"
    "    \"final_cash\": 1004.9,\n"
    "    \"final_position\": 0,\n"
    "    \"final_price\": 8.0,\n"
    "    \"final_equity\": 1004.9,\n"
    "    \"return_pct\": 0.4899999999999977,\n"
    "    \"max_drawdown_pct\": -0.3470844902816343,\n"
    "    \"benchmark\": {\n"
    "      \"shares\": 100,\n"
    "      \"final_cash\": 0.0,\n"
    "      \"final_equity\": 800.0,\n"
    "      \"return_pct\": -20.0,\n"
    "      \"max_drawdown_pct\": -33.33333333333333,\n"
    "      \"trades\": 1,\n"
    "      \"total_costs\": 0.0\n"
    "    }\n"
    "  },\n"
    "  \"disclaimer\": \"Research aid only. Not financial advice.\"\n"
    "}\n"
)
BEFORE_TRAIL_TARGET_JSON = (
    "{\n"
    "  \"bars\": 8,\n"
    "  \"last_close\": 8.0,\n"
    "  \"signal\": \"HOLD\",\n"
    "  \"rsi\": null,\n"
    "  \"rsi_label\": null,\n"
    "  \"backtest\": {\n"
    "    \"strategy\": \"sma_cross\",\n"
    "    \"params\": {\n"
    "      \"short\": 1,\n"
    "      \"long\": 2\n"
    "    },\n"
    "    \"fill\": \"close\",\n"
    "    \"start_cash\": 1000.0,\n"
    "    \"fee\": 0.0,\n"
    "    \"fee_pct\": 0.0,\n"
    "    \"slippage_pct\": 0.0,\n"
    "    \"position_size\": null,\n"
    "    \"stop_loss_pct\": null,\n"
    "    \"take_profit_pct\": 20.0,\n"
    "    \"trailing_stop_pct\": 8.0,\n"
    "    \"trades\": 2,\n"
    "    \"buys\": 1,\n"
    "    \"sells\": 1,\n"
    "    \"fills\": [\n"
    "      {\n"
    "        \"bar\": 4,\n"
    "        \"side\": \"BUY\",\n"
    "        \"shares\": 90,\n"
    "        \"price\": 11.0,\n"
    "        \"value\": 990.0,\n"
    "        \"cost\": 0.0,\n"
    "        \"cash_after\": 10.0,\n"
    "        \"reason\": \"signal\"\n"
    "      },\n"
    "      {\n"
    "        \"bar\": 6,\n"
    "        \"side\": \"SELL\",\n"
    "        \"shares\": 90,\n"
    "        \"price\": 11.5,\n"
    "        \"value\": 1035.0,\n"
    "        \"cost\": 0.0,\n"
    "        \"cash_after\": 1045.0,\n"
    "        \"reason\": \"trail\"\n"
    "      }\n"
    "    ],\n"
    "    \"total_costs\": 0.0,\n"
    "    \"round_trips\": 1,\n"
    "    \"winning_round_trips\": 1,\n"
    "    \"final_cash\": 1045.0,\n"
    "    \"final_position\": 0,\n"
    "    \"final_price\": 8.0,\n"
    "    \"final_equity\": 1045.0,\n"
    "    \"return_pct\": 4.5,\n"
    "    \"max_drawdown_pct\": -4.128440366972478,\n"
    "    \"benchmark\": {\n"
    "      \"shares\": 100,\n"
    "      \"final_cash\": 0.0,\n"
    "      \"final_equity\": 800.0,\n"
    "      \"return_pct\": -20.0,\n"
    "      \"max_drawdown_pct\": -33.33333333333333,\n"
    "      \"trades\": 1,\n"
    "      \"total_costs\": 0.0\n"
    "    }\n"
    "  },\n"
    "  \"disclaimer\": \"Research aid only. Not financial advice.\"\n"
    "}\n"
)
BEFORE_RISK_SKIPPED_JSON = (
    "{\n"
    "  \"bars\": 8,\n"
    "  \"last_close\": 8.0,\n"
    "  \"signal\": \"HOLD\",\n"
    "  \"rsi\": null,\n"
    "  \"rsi_label\": null,\n"
    "  \"backtest\": {\n"
    "    \"strategy\": \"sma_cross\",\n"
    "    \"params\": {\n"
    "      \"short\": 1,\n"
    "      \"long\": 2\n"
    "    },\n"
    "    \"fill\": \"close\",\n"
    "    \"start_cash\": 1000.0,\n"
    "    \"fee\": 0.0,\n"
    "    \"fee_pct\": 0.0,\n"
    "    \"slippage_pct\": 0.0,\n"
    "    \"position_size\": null,\n"
    "    \"risk_pct\": 2.0,\n"
    "    \"atr_mult\": 2.0,\n"
    "    \"atr_period\": 5,\n"
    "    \"stop_loss_pct\": null,\n"
    "    \"take_profit_pct\": null,\n"
    "    \"trades\": 0,\n"
    "    \"buys\": 0,\n"
    "    \"sells\": 0,\n"
    "    \"risk_skipped_buys\": 1,\n"
    "    \"fills\": [],\n"
    "    \"total_costs\": 0.0,\n"
    "    \"round_trips\": 0,\n"
    "    \"winning_round_trips\": 0,\n"
    "    \"final_cash\": 1000.0,\n"
    "    \"final_position\": 0,\n"
    "    \"final_price\": 8.0,\n"
    "    \"final_equity\": 1000.0,\n"
    "    \"return_pct\": 0.0,\n"
    "    \"max_drawdown_pct\": 0.0,\n"
    "    \"benchmark\": {\n"
    "      \"shares\": 100,\n"
    "      \"final_cash\": 0.0,\n"
    "      \"final_equity\": 800.0,\n"
    "      \"return_pct\": -20.0,\n"
    "      \"max_drawdown_pct\": -33.33333333333333,\n"
    "      \"trades\": 1,\n"
    "      \"total_costs\": 0.0\n"
    "    }\n"
    "  },\n"
    "  \"disclaimer\": \"Research aid only. Not financial advice.\"\n"
    "}\n"
)


@pytest.fixture
def folder(tmp_path, monkeypatch):
    (tmp_path / "hand.csv").write_text(HAND)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    return tmp_path


def run(argv, capsys):
    try:
        code = main(argv)
    except SystemExit as exc:
        code = exc.code
    out, err = capsys.readouterr()
    return code, out, err


def backtest_json(argv, capsys):
    code, out, err = run(argv + ["--json"], capsys)
    assert (code, err) == (0, "")
    return json.loads(out)["backtest"]


# --------------------------------------------------------------------------- the hand case


def test_hand_case_exact_text(folder, capsys):
    assert run(B + ATR + ["--json"], capsys) == (0, NEW_HAND_JSON, "")


def test_hand_case(folder, capsys):
    bt = backtest_json(B + ATR, capsys)
    assert (bt["atr_stop"], bt["atr_mult"], bt["atr_period"], bt["risk_skipped_buys"]) == (True, 2.0, 3, 0)
    assert "risk_pct" not in bt
    assert [(f["bar"], f["side"], f["shares"], f["reason"]) for f in bt["fills"]] == [
        (4, "BUY", 90, "signal"),
        (7, "SELL", 90, "atr"),
    ]
    assert bt["fills"][1]["price"] == pytest.approx(74 / 9)
    assert bt["final_equity"] == pytest.approx(750.0)
    assert (bt["trades"], bt["buys"], bt["sells"]) == (2, 1, 1)


def test_hand_case_with_risk_pct(folder, capsys):
    bt = backtest_json(B + ["--risk-pct", "2"] + ATR, capsys)
    assert (bt["risk_pct"], bt["atr_stop"], bt["atr_mult"], bt["atr_period"], bt["risk_skipped_buys"]) == (
        2.0, True, 2.0, 3, 0
    )
    assert [(f["bar"], f["side"], f["shares"], f["reason"]) for f in bt["fills"]] == [
        (4, "BUY", 7, "signal"),
        (7, "SELL", 7, "atr"),
    ]
    assert bt["final_equity"] == pytest.approx(923 + 7 * 74 / 9)


@pytest.mark.parametrize("extra", [[], ["--risk-pct", "2"]], ids=["atr stop", "with risk_pct"])
def test_period_5_skips_one_buy(folder, capsys, extra):
    bt = backtest_json(B + extra + ["--atr-stop", "--atr-mult", "2", "--atr-period", "5"], capsys)
    assert (bt["atr_stop"], bt["atr_period"], bt["risk_skipped_buys"]) == (True, 5, 1)
    assert bt["fills"] == [] and bt["trades"] == 0
    assert bt["final_equity"] == 1000.0


def test_atr_stop_is_json_true(folder, capsys):
    _, out, _ = run(B + ATR + ["--json"], capsys)
    assert '\n    "atr_stop": true,\n' in out


@pytest.mark.parametrize(
    "extra",
    [ATR, ["--risk-pct", "2"] + ATR, ["--atr-stop", "--atr-period", "5"], ATR + ["--fill", "open"],
     ATR + ["--stop-loss", "20", "--trailing-stop", "30", "--take-profit", "25"]],
    ids=["hand", "with risk_pct", "skipped", "open fills", "with the other exits"],
)
def test_json_numbers_equal_the_text_report(folder, capsys, extra):
    argv = B + extra
    code, text, _ = run(argv, capsys)
    assert code == 0
    bt = backtest_json(argv, capsys)

    fills = re.findall(r"^    #\d+\s+bar (\d+)\s+(BUY|SELL)\s+(\d+) @\s+([\d,.]+).*?(\w+)$", text, re.M)
    assert fills == [
        (str(f["bar"]), f["side"], str(f["shares"]), f"{f['price']:,.2f}", f["reason"]) for f in bt["fills"]
    ]
    assert f"  End equity:  {bt['final_equity']:,.2f}\n" in text
    assert f"  Return:      {bt['return_pct']:+.2f}%\n" in text
    assert f"atr {bt['atr_mult']:g} x ATR({bt['atr_period']}) below entry" in text
    skipped = re.search(r"^  Skipped:     (\d+) buy", text, re.M)
    assert (int(skipped.group(1)) if skipped else 0) == bt["risk_skipped_buys"]


# --------------------------------------------------------------------------- where the keys sit


def test_keys_with_atr_stop_alone_and_the_defaults(folder, capsys):
    bt = backtest_json(B + ["--atr-stop"], capsys)
    keys = list(bt)
    i = keys.index("position_size")
    assert keys[i : i + 4] == ["position_size", "atr_mult", "atr_period", "stop_loss_pct"]
    j = keys.index("take_profit_pct")
    assert keys[j : j + 3] == ["take_profit_pct", "atr_stop", "trades"]
    k = keys.index("sells")
    assert keys[k : k + 3] == ["sells", "risk_skipped_buys", "fills"]
    assert (bt["atr_mult"], bt["atr_period"]) == (2.0, 14)  # defaults filled in
    assert bt["risk_skipped_buys"] == 1  # 8 bars: ATR(14) never exists


def test_keys_with_risk_pct_and_a_trailing_stop(folder, capsys):
    bt = backtest_json(B + ["--risk-pct", "2", "--trailing-stop", "8"] + ATR, capsys)
    keys = list(bt)
    i = keys.index("position_size")
    assert keys[i : i + 5] == ["position_size", "risk_pct", "atr_mult", "atr_period", "stop_loss_pct"]
    j = keys.index("take_profit_pct")
    assert keys[j : j + 4] == ["take_profit_pct", "trailing_stop_pct", "atr_stop", "trades"]
    k = keys.index("sells")
    assert keys[k : k + 3] == ["sells", "risk_skipped_buys", "fills"]
    assert keys.count("atr_mult") == 1 and keys.count("risk_skipped_buys") == 1


def test_with_stats_and_export_the_keys_stay_in_place(folder, capsys):
    bt = backtest_json(B + ATR + ["--stats", "--export", "E.csv"], capsys)
    keys = list(bt)
    assert keys[-2:] == ["export", "stats"]
    assert bt["export"] == {"path": "E.csv", "rows": 8}
    assert (folder / "E.csv").read_text().splitlines()[-1].endswith(",atr")


# --------------------------------------------------------------------------- without --atr-stop: unchanged


def test_without_atr_stop_there_is_no_atr_stop_key(folder, capsys):
    for extra in ([], ["--risk-pct", "2"], ["--stop-loss", "5", "--trailing-stop", "8"]):
        assert "atr_stop" not in backtest_json(B + extra, capsys)
    bt = backtest_json(B + ["--stop-loss", "5"], capsys)
    assert "atr_mult" not in bt and "risk_skipped_buys" not in bt


@pytest.mark.parametrize(
    "extra, expected",
    [
    (["--risk-pct", "2", "--atr-mult", "2", "--atr-period", "3", "--stats", "--export", "E.csv"], BEFORE_RISK_STATS_EXPORT_JSON),
    (["--risk-pct", "2", "--atr-period", "3", "--stop-loss", "5", "--trailing-stop", "8", "--fill", "open"], BEFORE_RISK_EXITS_OPEN_JSON),
    (["--trailing-stop", "8", "--take-profit", "20"], BEFORE_TRAIL_TARGET_JSON),
    (["--risk-pct", "2", "--atr-period", "5"], BEFORE_RISK_SKIPPED_JSON),
    ],
    ids=["risk, stats, export", "risk, exits, open fills", "trail and target", "risk, skipped buy"],
)
def test_old_json_runs_print_the_same(folder, capsys, extra, expected):
    assert run(B + extra + ["--json"], capsys) == (0, expected, "")
