"""``--json``: the text report's information as one JSON object on stdout.

Both outputs come from the same ``cli.summarise`` call, so every number the
text report prints must be the JSON number formatted the way the text formats
it. Errors keep their exit codes and stderr messages, with nothing on stdout.

Hand-worked series (the LOSS sample of test_backtest.py), short=2, long=3, cash 10,000:

    closes = [10, 10, 10, 10, 14, 14, 14, 8, 8, 8]
    BUY signal at bar 4 -> fills bar 5 @ 14: 714 shares, value 9,996, cash 4
    SELL signal at bar 7 -> fills bar 8 @ 8: value 5,712, cash 5,716
    End: 0 shares, equity 5,716, return -42.84 %; one round trip, a loss.
    Buy & hold: 1,000 shares @ 10, cash 0, end 8,000, return -20 %.
    RSI (period 14) needs 15 closes -> n/a -> null.
"""

import json

import pytest

from trading_assistant import cli
from trading_assistant.cli import CONFIG_ENV_VAR, DISCLAIMER, analyse, main, report_data, report_lines, summarise
from trading_assistant.samples import sample_table

LOSS = [10.0, 10.0, 10.0, 10.0, 14.0, 14.0, 14.0, 8.0, 8.0, 8.0]


@pytest.fixture(autouse=True)
def no_env_config(monkeypatch):
    monkeypatch.delenv(CONFIG_ENV_VAR, raising=False)


@pytest.fixture
def files(tmp_path):
    """Input files; returns a dict name -> path."""
    paths = {}

    def put(name, text):
        path = tmp_path / name
        path.write_text(text)
        paths[name] = str(path)

    put("loss.csv", "date,close\n" + "".join(f"2026-01-{i + 1:02d},{c}\n" for i, c in enumerate(LOSS)))
    dates, closes = sample_table("random_walk")
    put("walk.csv", "date,close\n" + "".join(f"{d},{c:.2f}\n" for d, c in zip(dates, closes)))
    rows, prev = ["date,open,high,low,close,volume"], closes[0]
    for d, c in zip(dates, closes):
        o = round(prev, 2)
        rows.append(f"{d},{o},{round(max(o, c) * 1.01, 2)},{round(min(o, c) * 0.99, 2)},{c:.2f},1000")
        prev = c
    put("candles.csv", "\n".join(rows) + "\n")
    put("tiny.csv", "close\n10\n11\n12\n")
    put("empty.csv", "close\n")
    put("bad.csv", "close\n10\nabc\n")
    put("nodate.csv", "close\n" + "".join(f"{c}\n" for c in LOSS))
    put("negative.csv", "close\n" + "".join(f"{10 - i}\n" for i in range(12)))
    put("stats.ini", "[cli]\nstats = yes\n")
    put("badcfg.ini", "[cli]\nspeed = 3\n")
    paths["dir"] = str(tmp_path)
    return paths


def run(argv):
    """(exit code, stdout, stderr) for ``main(argv)``, usage errors included."""
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def run_json(argv):
    code, out, err = run(argv + ["--json"])
    assert code == 0 and err == ""
    return json.loads(out)  # fails unless stdout is exactly one JSON value


STATS_FORMAT = [  # (text label, key, format spec, suffix) as in backtest.format_stats
    ("Total return:", "total_return_pct", "+.2f", "%"),
    ("CAGR:", "cagr_pct", ".2f", "%"),
    ("Volatility (ann.):", "annualized_volatility_pct", ".2f", "%"),
    ("Sharpe ratio:", "sharpe_ratio", ".2f", ""),
    ("Sortino ratio:", "sortino_ratio", ".2f", ""),
    ("Exposure:", "exposure_pct", ".2f", "%"),
    ("Profit factor:", "profit_factor", ".2f", ""),
    ("Average win:", "average_win", ",.2f", ""),
    ("Average loss:", "average_loss", ",.2f", ""),
    ("Longest drawdown:", "longest_drawdown_bars", "d", " bars"),
]


def assert_json_matches_text(argv):
    """Run ``argv`` as text and as JSON; every number in the text must be the JSON number, formatted."""
    code, text, err = run(argv)
    assert code == 0 and err == ""
    data = run_json(argv)
    lines = text.splitlines()
    assert lines[-1] == DISCLAIMER == data["disclaimer"]
    assert lines[0] == f"Bars:    {data['bars']}"
    assert lines[1] == f"Last:    {data['last_close']:.2f}"
    assert lines[2] == f"Signal:  {data['signal']}"
    rsi = "n/a" if data["rsi"] is None else f"{data['rsi']:.1f} ({data['rsi_label']})"
    assert lines[3] == f"RSI:     {rsi}"
    assert (data["rsi"] is None) == (data["rsi_label"] is None)

    if "--backtest" not in argv:
        assert "backtest" not in data and len(lines) == 5
        return data, lines
    bt, bench = data["backtest"], data["backtest"]["benchmark"]
    exits = bt["stop_loss_pct"] is not None or bt["take_profit_pct"] is not None
    if bt["strategy"] == "sma_cross":
        title = f"SMA {bt['params']['short']}/{bt['params']['long']} crossover"
    else:
        title = f"{bt['strategy']} ({', '.join(f'{k}={v}' for k, v in bt['params'].items())})"
    fills_word = "next-bar open fills" if bt["fill"] == "open" else "next-bar fills"
    assert lines[4] == f"Backtest: {title}, {fills_word}, whole shares, no shorting"
    assert f"  Start cash:  {bt['start_cash']:,.2f}" in lines
    assert f"  Trades:      {bt['trades']} ({bt['buys']} buy, {bt['sells']} sell)" in lines
    fill_lines = [line.split() for line in lines if line.startswith("    #")]
    assert len(fill_lines) == len(bt["fills"]) == bt["trades"]
    for i, (tokens, f) in enumerate(zip(fill_lines, bt["fills"]), start=1):
        expected = [
            f"#{i}", "bar", str(f["bar"]), f["side"], str(f["shares"]), "@", f"{f['price']:,.2f}",
            "value", f"{f['value']:,.2f}", "cost", f"{f['cost']:,.2f}", "cash", f"{f['cash_after']:,.2f}",
        ] + ([f["reason"]] if exits else [])
        assert tokens == expected
        assert f["value"] == pytest.approx(f["shares"] * f["price"])
    assert any(
        line.startswith(f"  Costs:       {bt['total_costs']:,.2f} paid (fee {bt['fee']:,.2f} per trade + {bt['fee_pct']:.2f}% of value)")
        for line in lines
    )
    n_rt, wins = bt["round_trips"], bt["winning_round_trips"]
    rt_line = f"  Round trips: {n_rt} completed, {wins} made money ({wins / n_rt * 100:.0f}%)" if n_rt else "  Round trips: 0 completed"
    assert rt_line in lines
    for label, a, b in [
        ("End equity", f"{bt['final_equity']:,.2f}", f"{bench['final_equity']:,.2f}"),
        ("Return", f"{bt['return_pct']:+.2f}%", f"{bench['return_pct']:+.2f}%"),
        ("Max drawdown", f"{bt['max_drawdown_pct']:.2f}%", f"{bench['max_drawdown_pct']:.2f}%"),
        ("Trades", str(bt["trades"]), str(bench["trades"])),
        ("Costs paid", f"{bt['total_costs']:,.2f}", f"{bench['total_costs']:,.2f}"),
    ]:
        assert f"    {label:<16s}{a:>14s}{b:>14s}" in lines
    assert f"  End cash:    {bt['final_cash']:,.2f}" in lines
    assert f"  End shares:  {bt['final_position']} @ {bt['final_price']:,.2f}" in lines
    assert f"  End equity:  {bt['final_equity']:,.2f}" in lines
    assert f"  Return:      {bt['return_pct']:+.2f}%" in lines
    assert bt["final_equity"] == pytest.approx(bt["final_cash"] + bt["final_position"] * bt["final_price"])

    if "stats" in bt:
        assert "Risk and return" in lines
        assert list(bt["stats"]) == [key for _, key, _, _ in STATS_FORMAT]
        for label, key, spec, suffix in STATS_FORMAT:
            value = bt["stats"][key]
            shown = "n/a" if value is None else format(value, spec) + suffix
            assert f"  {label:<20s}{shown}" in lines
    else:
        assert "Risk and return" not in lines
    return data, lines


# --------------------------------------------------------------------------- shape


def test_without_backtest_the_object_has_the_four_fields_and_the_disclaimer(files):
    data = run_json([files["walk.csv"]])
    assert list(data) == ["bars", "last_close", "signal", "rsi", "rsi_label", "disclaimer"]
    assert isinstance(data["bars"], int) and isinstance(data["last_close"], float)
    assert isinstance(data["rsi"], float) and data["signal"] in ("BUY", "SELL", "HOLD")


def test_stdout_is_one_json_object_and_nothing_else(files):
    code, out, err = run([files["walk.csv"], "--backtest", "--stats", "--json"])
    assert code == 0 and err == ""
    assert out.startswith("{") and out.endswith("}\n")
    data = json.loads(out)  # the whole of stdout is one object
    assert isinstance(data, dict)
    assert DISCLAIMER not in out.replace(json.dumps(DISCLAIMER), "")  # only inside the object


def test_numbers_are_json_numbers_not_strings(files):
    bt = run_json([files["walk.csv"], "--backtest", "--stats"])["backtest"]

    def walk(value, path="backtest"):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, f"{path}.{k}")
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, f"{path}[{i}]")
        elif isinstance(value, str):
            assert path.rsplit(".", 1)[-1] in ("strategy", "fill", "side", "reason"), path

    walk(bt)


def test_hand_worked_backtest(files):
    data = run_json([files["loss.csv"], "--backtest", "--short", "2", "--long", "3"])
    assert data["bars"] == 10 and data["last_close"] == 8.0 and data["rsi"] is None and data["rsi_label"] is None
    bt = data["backtest"]
    assert (bt["strategy"], bt["params"], bt["fill"], bt["start_cash"]) == ("sma_cross", {"short": 2, "long": 3}, "close", 10000.0)
    assert bt["fills"] == [
        {"bar": 5, "side": "BUY", "shares": 714, "price": 14.0, "value": 9996.0, "cost": 0.0, "cash_after": 4.0, "reason": "signal"},
        {"bar": 8, "side": "SELL", "shares": 714, "price": 8.0, "value": 5712.0, "cost": 0.0, "cash_after": 5716.0, "reason": "signal"},
    ]
    assert (bt["final_cash"], bt["final_position"], bt["final_equity"]) == (5716.0, 0, 5716.0)
    assert bt["return_pct"] == pytest.approx(-42.84)
    assert (bt["trades"], bt["buys"], bt["sells"], bt["round_trips"], bt["winning_round_trips"]) == (2, 1, 1, 1, 0)
    assert bt["benchmark"] == {
        "shares": 1000, "final_cash": 0.0, "final_equity": 8000.0, "return_pct": -20.0,
        "max_drawdown_pct": pytest.approx(-42.857142857), "trades": 1, "total_costs": 0.0,
    }
    assert "stats" not in bt and "export" not in bt
    assert (bt["position_size"], bt["stop_loss_pct"], bt["take_profit_pct"]) == (None, None, None)


def test_rsi_value_and_label_when_defined(files):
    data = run_json([files["loss.csv"], "--rsi-period", "3", "--short", "2", "--long", "3"])
    assert isinstance(data["rsi"], float) and data["rsi_label"] in ("overbought", "oversold", "neutral")


# --------------------------------------------------------------------------- JSON == text, for the same input


@pytest.mark.parametrize(
    "args",
    [
        ["walk.csv"],
        ["walk.csv", "--short", "5", "--long", "20", "--rsi-period", "7"],
        ["tiny.csv", "--short", "1", "--long", "2"],
        ["loss.csv", "--backtest", "--short", "2", "--long", "3"],
        ["walk.csv", "--backtest"],
        ["walk.csv", "--backtest", "--stats"],
        ["walk.csv", "--backtest", "--short", "5", "--long", "20", "--fee", "1", "--fee-pct", "0.1", "--stats"],
        ["walk.csv", "--backtest", "--strategy", "breakout", "--param", "window=10", "--stats"],
        ["walk.csv", "--backtest", "--strategy", "rsi_reversion", "--cash", "2500"],
        ["walk.csv", "--backtest", "--param", "short=4", "--param", "long=15"],  # windows traded come from --param
        ["walk.csv", "--backtest", "--resample", "weekly", "--short", "2", "--long", "5", "--stats"],
        ["candles.csv", "--candles", "--backtest", "--short", "5", "--long", "20"],
        ["candles.csv", "--backtest", "--fill", "open", "--slippage", "0.5", "--position-size", "0.5", "--short", "5", "--long", "20"],
        ["candles.csv", "--backtest", "--stop-loss", "3", "--take-profit", "6", "--short", "5", "--long", "20", "--stats"],
        ["tiny.csv", "--backtest", "--short", "1", "--long", "2", "--stats"],
        ["loss.csv", "--backtest", "--short", "2", "--long", "3", "--stats"],
    ],
    ids=lambda a: " ".join(a),
)
def test_json_matches_the_text_report(files, args):
    assert_json_matches_text([files[args[0]]] + args[1:])


def test_stats_null_exactly_where_the_text_says_n_a(files):
    data, lines = assert_json_matches_text([files["tiny.csv"], "--backtest", "--short", "1", "--long", "2", "--stats"])
    stats = data["backtest"]["stats"]
    nulls = [key for key, value in stats.items() if value is None]
    assert nulls  # this short run has undefined statistics
    assert sum(line.endswith("n/a") for line in lines[lines.index("Risk and return"):]) == len(nulls)


def test_exit_reasons_appear_in_fills(files):
    data, _ = assert_json_matches_text(
        [files["candles.csv"], "--backtest", "--stop-loss", "3", "--take-profit", "6", "--short", "5", "--long", "20"]
    )
    reasons = {f["reason"] for f in data["backtest"]["fills"]}
    assert reasons <= {"signal", "stop", "target"} and reasons & {"stop", "target"}


def test_stats_from_config_file_are_included(files):
    data, _ = assert_json_matches_text([files["walk.csv"], "--backtest", "--config", files["stats.ini"]])
    assert "stats" in data["backtest"]


def test_export_writes_the_same_file_and_reports_it(files, tmp_path):
    text_out, json_out = str(tmp_path / "text.csv"), str(tmp_path / "json.csv")
    code, text, _ = run([files["walk.csv"], "--backtest", "--export", text_out])
    data = run_json([files["walk.csv"], "--backtest", "--export", json_out])
    assert code == 0
    assert open(text_out).read() == open(json_out).read()
    rows = data["backtest"]["export"]["rows"]
    assert data["backtest"]["export"] == {"path": json_out, "rows": rows}
    assert f"  Exported:    {rows} rows to {text_out}" in text.splitlines()


# --------------------------------------------------------------------------- one analysis, two renderings


def test_text_and_json_come_from_the_same_summarise_call(files, monkeypatch):
    calls = []
    real = cli.summarise

    def spy(*args, **kwargs):
        summary = real(*args, **kwargs)
        summary["signal"] = "FROM-SUMMARISE"
        calls.append(1)
        return summary

    monkeypatch.setattr(cli, "summarise", spy)
    _, text, _ = run([files["loss.csv"], "--backtest", "--short", "2", "--long", "3"])
    code, out, _ = run([files["loss.csv"], "--backtest", "--short", "2", "--long", "3", "--json"])
    assert len(calls) == 2 and code == 0
    assert "Signal:  FROM-SUMMARISE" in text.splitlines()
    assert json.loads(out)["signal"] == "FROM-SUMMARISE"


def test_analyse_is_report_lines_of_summarise():
    kwargs = dict(short=2, long=3, backtest=True, fee=1, fee_pct=0.5)
    summary = summarise(LOSS, **kwargs)
    lines, result = analyse(LOSS, **kwargs)
    assert lines == report_lines(summary) and result == summary["result"]
    assert analyse(LOSS, 2, 3)[0] == analyse(LOSS, short=2, long=3)[0]  # positional arguments still work
    data = report_data(summary)
    assert data["backtest"]["final_equity"] == result.final_equity


# --------------------------------------------------------------------------- errors: same as without --json


ERROR_CASES = [
    # exit 1: data problems
    (["dir/missing.csv"], 1),
    (["empty.csv"], 1),
    (["bad.csv"], 1),
    (["negative.csv", "--backtest", "--short", "2", "--long", "3"], 1),
    (["walk.csv", "--config", "badcfg.ini"], 1),
    (["walk.csv", "--backtest", "--export", "walk.csv"], 1),
    (["walk.csv", "--backtest", "--export", "dir"], 1),
    (["walk.csv", "--backtest", "--fill", "open"], 1),
    (["nodate.csv", "--resample", "weekly", "--short", "2", "--long", "3"], 1),
    # exit 2: usage problems
    (["walk.csv", "--short", "50", "--long", "20"], 2),
    (["walk.csv", "--cash", "5"], 2),
    (["walk.csv", "--stats"], 2),
    (["walk.csv", "--backtest", "--param", "nope"], 2),
    (["walk.csv", "--backtest", "--fill", "open", "--resample", "weekly"], 2),
    (["walk.csv", "--backtest", "--slippage", "100"], 2),
    (["walk.csv", "--resample", "daily"], 2),
]


def _argv(files, args):
    out = []
    for a in args:
        if a.startswith("dir/"):
            out.append(files["dir"] + "/" + a[4:])
        else:
            out.append(files.get(a, a))
    return out


@pytest.mark.parametrize("args, expected_code", ERROR_CASES, ids=lambda x: " ".join(x) if isinstance(x, list) else str(x))
def test_errors_are_the_same_with_and_without_json(files, args, expected_code):
    argv = _argv(files, args)
    text = run(argv)
    as_json = run(argv + ["--json"])
    assert text[0] == as_json[0] == expected_code
    assert text[1] == as_json[1] == ""  # nothing on stdout
    assert as_json[2] == text[2] and as_json[2].strip()  # the same message on stderr


def test_json_with_chart_is_a_usage_error(files):
    code, out, err = run([files["walk.csv"], "--chart", "--json"])
    assert code == 2 and out == ""
    assert err.splitlines()[-1] == (
        "trading_assistant.cli: error: --chart cannot be combined with --json (the JSON output is one object and nothing else)"
    )
    assert run([files["walk.csv"], "--chart"])[0] == 0  # --chart alone is unchanged


# --------------------------------------------------------------------------- default text output unchanged


def test_text_output_without_json_is_the_analyse_report(files):
    code, text, err = run([files["loss.csv"], "--backtest", "--short", "2", "--long", "3"])
    expected, _ = analyse(LOSS, short=2, long=3, backtest=True)
    assert code == 0 and err == "" and text.splitlines() == expected + [DISCLAIMER]


def test_help_mentions_json(capsys):
    with pytest.raises(SystemExit) as info:
        main(["--help"])
    assert info.value.code == 0 and "--json" in capsys.readouterr().out
