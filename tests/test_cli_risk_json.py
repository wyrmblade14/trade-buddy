"""--json with --risk-pct: risk_pct, atr_mult, atr_period and risk_skipped_buys.

Hand case (the candle file of test_cli_risk_sizing.py), --cash 1000 --short 1
--long 2 --risk-pct 2 --atr-mult 2 --atr-period 3: BUY signal on bar 3 with
ATR(3) = 25/18, stop 2 * 25/18 = 2.7778, risk 20 -> 7 shares, bought @ 11 on
bar 4 and sold @ 8 on bar 7: final equity 1000 - 77 + 56 = 979, 0 skipped.
With --atr-period 5 the first ATR is on bar 4, after the signal: 1 skipped.

The OLD_* JSON texts were captured from the command before --json showed
risk sizing.
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

OLD_PLAIN_JSON = (
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
    "    \"take_profit_pct\": null,\n"
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
    "        \"bar\": 7,\n"
    "        \"side\": \"SELL\",\n"
    "        \"shares\": 90,\n"
    "        \"price\": 8.0,\n"
    "        \"value\": 720.0,\n"
    "        \"cost\": 0.0,\n"
    "        \"cash_after\": 730.0,\n"
    "        \"reason\": \"signal\"\n"
    "      }\n"
    "    ],\n"
    "    \"total_costs\": 0.0,\n"
    "    \"round_trips\": 1,\n"
    "    \"winning_round_trips\": 0,\n"
    "    \"final_cash\": 730.0,\n"
    "    \"final_position\": 0,\n"
    "    \"final_price\": 8.0,\n"
    "    \"final_equity\": 730.0,\n"
    "    \"return_pct\": -27.0,\n"
    "    \"max_drawdown_pct\": -33.02752293577982,\n"
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
OLD_SIZING_COSTS_JSON = (
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
    "    \"fee\": 1.0,\n"
    "    \"fee_pct\": 0.1,\n"
    "    \"slippage_pct\": 0.5,\n"
    "    \"position_size\": 0.5,\n"
    "    \"stop_loss_pct\": null,\n"
    "    \"take_profit_pct\": null,\n"
    "    \"trades\": 2,\n"
    "    \"buys\": 1,\n"
    "    \"sells\": 1,\n"
    "    \"fills\": [\n"
    "      {\n"
    "        \"bar\": 4,\n"
    "        \"side\": \"BUY\",\n"
    "        \"shares\": 45,\n"
    "        \"price\": 11.055,\n"
    "        \"value\": 497.47499999999997,\n"
    "        \"cost\": 1.4974750000000001,\n"
    "        \"cash_after\": 501.027525,\n"
    "        \"reason\": \"signal\"\n"
    "      },\n"
    "      {\n"
    "        \"bar\": 7,\n"
    "        \"side\": \"SELL\",\n"
    "        \"shares\": 45,\n"
    "        \"price\": 7.96,\n"
    "        \"value\": 358.2,\n"
    "        \"cost\": 1.3582,\n"
    "        \"cash_after\": 857.869325,\n"
    "        \"reason\": \"signal\"\n"
    "      }\n"
    "    ],\n"
    "    \"total_costs\": 2.855675,\n"
    "    \"round_trips\": 1,\n"
    "    \"winning_round_trips\": 0,\n"
    "    \"final_cash\": 857.869325,\n"
    "    \"final_position\": 0,\n"
    "    \"final_price\": 8.0,\n"
    "    \"final_equity\": 857.869325,\n"
    "    \"return_pct\": -14.213067499999998,\n"
    "    \"max_drawdown_pct\": -17.593982445372898,\n"
    "    \"benchmark\": {\n"
    "      \"shares\": 99,\n"
    "      \"final_cash\": 3.055050000000051,\n"
    "      \"final_equity\": 795.05505,\n"
    "      \"return_pct\": -20.494494999999997,\n"
    "      \"max_drawdown_pct\": -33.24783350693991,\n"
    "      \"trades\": 1,\n"
    "      \"total_costs\": 1.99495\n"
    "    }\n"
    "  },\n"
    "  \"disclaimer\": \"Research aid only. Not financial advice.\"\n"
    "}\n"
)
OLD_EXITS_STATS_JSON = (
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
    "    \"stop_loss_pct\": 5.0,\n"
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
    "    },\n"
    "    \"stats\": {\n"
    "      \"total_return_pct\": 4.499999999999993,\n"
    "      \"cagr_pct\": 387.73784614756346,\n"
    "      \"annualized_volatility_pct\": 63.05121945469694,\n"
    "      \"sharpe_ratio\": 2.7814869927297927,\n"
    "      \"sortino_ratio\": 7.0800000000000205,\n"
    "      \"exposure_pct\": 25.0,\n"
    "      \"profit_factor\": null,\n"
    "      \"average_win\": 45.0,\n"
    "      \"average_loss\": null,\n"
    "      \"longest_drawdown_bars\": 2\n"
    "    }\n"
    "  },\n"
    "  \"disclaimer\": \"Research aid only. Not financial advice.\"\n"
    "}\n"
)
OLD_EXPORT_JSON = (
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
    "    \"take_profit_pct\": null,\n"
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
    "        \"bar\": 7,\n"
    "        \"side\": \"SELL\",\n"
    "        \"shares\": 90,\n"
    "        \"price\": 8.0,\n"
    "        \"value\": 720.0,\n"
    "        \"cost\": 0.0,\n"
    "        \"cash_after\": 730.0,\n"
    "        \"reason\": \"signal\"\n"
    "      }\n"
    "    ],\n"
    "    \"total_costs\": 0.0,\n"
    "    \"round_trips\": 1,\n"
    "    \"winning_round_trips\": 0,\n"
    "    \"final_cash\": 730.0,\n"
    "    \"final_position\": 0,\n"
    "    \"final_price\": 8.0,\n"
    "    \"final_equity\": 730.0,\n"
    "    \"return_pct\": -27.0,\n"
    "    \"max_drawdown_pct\": -33.02752293577982,\n"
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
    "      \"total_return_pct\": -27.0,\n"
    "      \"cagr_pct\": -99.99879877886636,\n"
    "      \"annualized_volatility_pct\": 163.76388748865816,\n"
    "      \"sharpe_ratio\": -5.999999999999997,\n"
    "      \"sortino_ratio\": -6.355456041144764,\n"
    "      \"exposure_pct\": 37.5,\n"
    "      \"profit_factor\": 0.0,\n"
    "      \"average_win\": null,\n"
    "      \"average_loss\": -270.0,\n"
    "      \"longest_drawdown_bars\": 2\n"
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


def test_hand_case(folder, capsys):
    bt = backtest_json(B + ["--risk-pct", "2", "--atr-mult", "2", "--atr-period", "3"], capsys)
    assert (bt["risk_pct"], bt["atr_mult"], bt["atr_period"], bt["risk_skipped_buys"]) == (2.0, 2.0, 3, 0)
    assert [(f["bar"], f["side"], f["shares"], f["price"]) for f in bt["fills"]] == [
        (4, "BUY", 7, 11.0),
        (7, "SELL", 7, 8.0),
    ]
    assert bt["final_equity"] == 979.0
    assert (bt["trades"], bt["buys"], bt["sells"]) == (2, 1, 1)


def test_period_5_skips_one_buy(folder, capsys):
    bt = backtest_json(B + ["--risk-pct", "2", "--atr-mult", "2", "--atr-period", "5"], capsys)
    assert (bt["risk_pct"], bt["atr_mult"], bt["atr_period"], bt["risk_skipped_buys"]) == (2.0, 2.0, 5, 1)
    assert bt["fills"] == [] and bt["trades"] == 0
    assert bt["final_equity"] == 1000.0


@pytest.mark.parametrize("period", ["3", "5"])
def test_json_numbers_equal_the_text_report(folder, capsys, period):
    argv = B + ["--risk-pct", "2", "--atr-mult", "2", "--atr-period", period]
    code, text, _ = run(argv, capsys)
    assert code == 0
    bt = backtest_json(argv, capsys)

    fills = re.findall(r"^    #\d+\s+bar (\d+)\s+(BUY|SELL)\s+(\d+) @\s+([\d,.]+)", text, re.M)
    assert fills == [(str(f["bar"]), f["side"], str(f["shares"]), f"{f['price']:,.2f}") for f in bt["fills"]]
    assert f"  End equity:  {bt['final_equity']:,.2f}\n" in text
    assert f"  Return:      {bt['return_pct']:+.2f}%\n" in text
    assert (
        f"  Risk sizing: {bt['risk_pct']:.2f}% of account value at risk per buy, "
        f"stop distance {bt['atr_mult']:g} x ATR({bt['atr_period']}) " in text
    )
    skipped = re.search(r"^  Skipped:     (\d+) buy", text, re.M)
    assert (int(skipped.group(1)) if skipped else 0) == bt["risk_skipped_buys"]


def test_risk_keys_sit_with_the_other_settings_and_show_the_defaults(folder, capsys):
    bt = backtest_json(B + ["--risk-pct", "2"], capsys)
    keys = list(bt)
    i = keys.index("position_size")
    assert keys[i : i + 5] == ["position_size", "risk_pct", "atr_mult", "atr_period", "stop_loss_pct"]
    j = keys.index("sells")
    assert keys[j : j + 3] == ["sells", "risk_skipped_buys", "fills"]
    assert (bt["atr_mult"], bt["atr_period"]) == (2.0, 14)  # defaults filled in
    assert bt["risk_skipped_buys"] == 1  # 8 bars: ATR(14) never exists


@pytest.mark.parametrize(
    "extra, expected",
    [
    ([], OLD_PLAIN_JSON),
    (["--position-size", "0.5", "--fee", "1", "--fee-pct", "0.1", "--slippage", "0.5"], OLD_SIZING_COSTS_JSON),
    (["--stop-loss", "5", "--take-profit", "20", "--trailing-stop", "8", "--stats"], OLD_EXITS_STATS_JSON),
    (["--stats", "--export", "E.csv"], OLD_EXPORT_JSON),
    ],
)
def test_old_json_runs_print_the_same(folder, capsys, extra, expected):
    assert run(B + ["--json"] + extra, capsys) == (0, expected, "")
