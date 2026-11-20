"""The three ways to run a backtest agree: command-line flags, a config file, and the web API.

For every candle file x settings combination below, the same backtest is run

    * with command-line flags (text report and --json),
    * from a config file with the same settings (text report and --json),
    * through the web API on a real server (the CSV pasted as text),
    * and directly with ``backtest.run_backtest`` as the reference,

and all of them must give the same fills, final equity, buy-and-hold final
equity and statistics. The text reports must match line for line: flags and
config give byte-identical output, and the web page's report is exactly the
command line's report (which then only adds its "Risk and return" block and
the disclaimer).

If one path changes (a new setting, a different default, a different reading
of the file) and the others are not changed with it, these tests fail.
"""

import contextlib
import io
import json
import random
import threading
from datetime import date, timedelta

import pytest

from trading_assistant.backtest import format_stats, run_backtest
from trading_assistant.cli import CONFIG_ENV_VAR, DISCLAIMER, main
from trading_assistant.data import load_candles
from trading_assistant.samples import write_sample_csv
from trading_assistant.web import server as web

# --------------------------------------------------------------------------- candle files


def _walk_text():
    buf = io.StringIO()
    write_sample_csv("random_walk", buf, candles=True)  # 750 bars, the built-in seeded sample
    return buf.getvalue()


def _gappy_text():
    """300 bars with frequent overnight gaps of 3-7 %, so stops and targets fill at the open."""
    rng = random.Random(7)
    rows = ["date,open,high,low,close,volume"]
    close = 50.0
    day = date(2024, 1, 1)
    for _ in range(300):
        if rng.random() < 0.12:
            gap = 1 + rng.choice((-1, 1)) * rng.uniform(0.03, 0.07)
        else:
            gap = 1 + rng.uniform(-0.005, 0.005)
        open_ = round(close * gap, 2)
        close = round(open_ * (1 + rng.uniform(-0.03, 0.035)), 2)
        high = round(max(open_, close) * (1 + rng.uniform(0, 0.02)), 2)
        low = round(min(open_, close) * (1 - rng.uniform(0, 0.02)), 2)
        rows.append(f"{day.isoformat()},{open_},{high},{low},{close},{rng.randrange(1000, 90000)}")
        day += timedelta(days=1)
    return "\n".join(rows) + "\n"


def _hand_text():
    """The hand-worked series of test_stop_take_profit.py (bar 7 gaps down)."""
    opens = [9, 9, 9, 9, 12, 13, 14, 9, 7, 8]
    highs = [11, 11, 11, 11, 15, 15, 17, 10, 9, 9]
    lows = [8, 8, 8, 8, 11, 12.9, 12, 7.5, 6.9, 7.5]
    closes = [10, 10, 10, 10, 14, 14, 14, 8, 8, 8]
    rows = ["date,open,high,low,close,volume"]
    for t in range(10):
        rows.append(f"2026-01-{t + 1:02d},{opens[t]},{highs[t]},{lows[t]},{closes[t]},{(t + 1) * 1000}")
    return "\n".join(rows) + "\n"


# name -> (CSV text, the SMA windows that suit its length)
FILES = {
    "walk": (_walk_text(), {"short": 5, "long": 20}),
    "gappy": (_gappy_text(), {"short": 4, "long": 12}),
    "hand": (_hand_text(), {"short": 2, "long": 3}),
}

# --------------------------------------------------------------------------- settings combinations
# Keys are the config-file / web API names. "params" are strategy parameters.
# "windows": False leaves the top-level short/long out (sma_cross windows come from params).

COMBOS = {
    "defaults": {},
    "cash and costs": {"cash": 2500, "fee": 1, "fee_pct": 0.25},
    "slippage": {"slippage": 0.5},
    "position size": {"position_size": 0.3},
    "open fills": {"fill": "open"},
    "stop loss": {"stop_loss": 3},
    "take profit": {"take_profit": 5},
    "stop and target": {"stop_loss": 3, "take_profit": 5},
    "everything": {
        "rsi_period": 9, "cash": 25000, "fee": 1, "fee_pct": 0.1, "slippage": 0.2,
        "position_size": 0.5, "fill": "open", "stop_loss": 4, "take_profit": 8,
    },
    "sma_cross windows from params": {"windows": False, "strategy": "sma_cross", "params": {"short": 3, "long": 8}, "stop_loss": 5},
    "rsi_reversion": {"strategy": "rsi_reversion", "params": {"period": 7, "oversold": 35, "overbought": 65}, "fill": "open", "stop_loss": 5},
    "breakout": {"strategy": "breakout", "params": {"window": 10}, "take_profit": 6, "slippage": 0.3},
    "ema_cross": {"strategy": "ema_cross", "params": {"short": 5, "long": 15}, "position_size": 0.5, "fee": 2},
    "momentum": {"strategy": "momentum", "params": {"window": 10, "threshold": 0.01}, "fee_pct": 0.2, "fill": "open"},
    "zscore_reversion": {"strategy": "zscore_reversion", "params": {"window": 15, "entry": -1.5, "exit": 0.5}, "stop_loss": 5},
    "hull_trend": {
        "strategy": "hull_trend", "params": {"window": 12}, "cash": 7000, "fee": 0.5, "fee_pct": 0.05,
        "slippage": 0.1, "position_size": 0.8, "fill": "open", "stop_loss": 6, "take_profit": 9,
    },
}

FLAG = {
    "short": "--short", "long": "--long", "rsi_period": "--rsi-period", "cash": "--cash", "fee": "--fee",
    "fee_pct": "--fee-pct", "slippage": "--slippage", "position_size": "--position-size", "fill": "--fill",
    "stop_loss": "--stop-loss", "take_profit": "--take-profit", "strategy": "--strategy",
}

CASES = [(f, c) for f in FILES for c in COMBOS]


def settings_for(file_name, combo_name):
    combo = dict(COMBOS[combo_name])
    windows = combo.pop("windows", True)
    return {**(FILES[file_name][1] if windows else {}), **combo}


# --------------------------------------------------------------------------- the paths


@pytest.fixture(autouse=True)
def no_env_config(monkeypatch):
    monkeypatch.delenv(CONFIG_ENV_VAR, raising=False)


@pytest.fixture(scope="module")
def server():
    srv = web.BacktestServer(("127.0.0.1", 0))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


@pytest.fixture(scope="module")
def csv_paths(tmp_path_factory):
    folder = tmp_path_factory.mktemp("candles")
    paths = {}
    for name, (text, _) in FILES.items():
        path = folder / f"{name}.csv"
        path.write_text(text)
        paths[name] = str(path)
    return paths


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    assert code == 0 and err.getvalue() == "", err.getvalue()
    return out.getvalue()


def flag_argv(settings):
    argv = ["--backtest"]
    for key, value in settings.items():
        if key == "params":
            for name, v in value.items():
                argv += ["--param", f"{name}={v}"]
        else:
            argv += [FLAG[key], str(value)]
    return argv


def config_text(settings):
    lines = ["[cli]"] + [f"{k} = {v}" for k, v in settings.items() if k != "params"] + ["stats = yes"]
    if "params" in settings:
        lines += ["", f"[strategy.{settings.get('strategy', 'sma_cross')}]"] + [f"{k} = {v}" for k, v in settings["params"].items()]
    return "\n".join(lines) + "\n"


def run_web(server, csv_text, settings):
    from urllib.request import Request, urlopen

    host, port = server.server_address[:2]
    payload = {"source": "csv", "csv": csv_text, **settings}
    req = Request(f"http://{host}:{port}/api/backtest", data=json.dumps(payload).encode(), method="POST",
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=30) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
    assert data["ok"] is True
    return data


def run_engine(path, settings):
    candles = load_candles(path)
    return run_backtest(
        [c.close for c in candles],
        initial_cash=settings.get("cash", 10_000.0),
        short=settings.get("short", 20),
        long=settings.get("long", 50),
        fee=settings.get("fee", 0.0),
        fee_pct=settings.get("fee_pct", 0.0),
        strategy=settings.get("strategy", "sma_cross"),
        strategy_params=settings.get("params"),
        fill=settings.get("fill", "close"),
        opens=[c.open for c in candles],
        slippage_pct=settings.get("slippage", 0.0),
        position_size=settings.get("position_size"),
        stop_pct=settings.get("stop_loss"),
        take_profit_pct=settings.get("take_profit"),
        highs=[c.high for c in candles],
        lows=[c.low for c in candles],
    )


def engine_fills(result):
    return [(t.bar, t.side, t.shares, t.price, t.value, t.cost, t.cash_after, t.reason) for t in result.trades]


def json_fills(backtest):
    return [(f["bar"], f["side"], f["shares"], f["price"], f["value"], f["cost"], f["cash_after"], f["reason"]) for f in backtest["fills"]]


def web_fills(data):
    return [
        (t["bar"], t["side"], t["shares"], t["price"]["value"], t["value"]["value"], t["cost"]["value"],
         t["cash_after"]["value"], t.get("reason", "signal"))  # the web adds "reason" only when exits are in use
        for t in data["trades"]
    ]


@pytest.fixture(scope="module")
def runs(server, csv_paths, tmp_path_factory):
    """Every case through every path, once; keyed by (file, combo)."""
    cfg_dir = tmp_path_factory.mktemp("configs")
    out = {}
    for i, (file_name, combo_name) in enumerate(CASES):
        settings = settings_for(file_name, combo_name)
        path = csv_paths[file_name]
        cfg = cfg_dir / f"case{i}.ini"
        cfg.write_text(config_text(settings))
        flags = flag_argv(settings)
        out[(file_name, combo_name)] = {
            "settings": settings,
            "cli_text": run_cli([path] + flags + ["--stats"]),
            "cli_json": json.loads(run_cli([path] + flags + ["--stats", "--json"])),
            "cfg_text": run_cli([path, "--backtest", "--config", str(cfg)]),
            "cfg_json": json.loads(run_cli([path, "--backtest", "--config", str(cfg), "--json"])),
            "web": run_web(server, FILES[file_name][0], settings),
            "engine": run_engine(path, settings),
        }
    return out


ids = [f"{f}-{c}" for f, c in CASES]


# --------------------------------------------------------------------------- agreement


@pytest.mark.parametrize("case", CASES, ids=ids)
def test_flags_and_config_file_give_identical_output(runs, case):
    r = runs[case]
    assert r["cfg_text"] == r["cli_text"]
    assert r["cfg_json"] == r["cli_json"]


@pytest.mark.parametrize("case", CASES, ids=ids)
def test_same_fills_on_every_path(runs, case):
    r = runs[case]
    expected = engine_fills(r["engine"])
    assert json_fills(r["cli_json"]["backtest"]) == expected
    assert json_fills(r["cfg_json"]["backtest"]) == expected
    assert web_fills(r["web"]) == expected


@pytest.mark.parametrize("case", CASES, ids=ids)
def test_same_final_equity_and_buy_and_hold_on_every_path(runs, case):
    r = runs[case]
    engine = r["engine"]
    for bt in (r["cli_json"]["backtest"], r["cfg_json"]["backtest"]):
        assert bt["final_equity"] == engine.final_equity
        assert bt["benchmark"]["final_equity"] == engine.benchmark.final_equity
    assert r["web"]["summary"]["end_equity"]["value"] == engine.final_equity
    assert r["web"]["summary"]["buy_hold"]["end_equity"]["value"] == engine.benchmark.final_equity


@pytest.mark.parametrize("case", CASES, ids=ids)
def test_same_stats_on_every_path(runs, case):
    r = runs[case]
    expected = json.loads(json.dumps(r["engine"].stats))
    assert r["cli_json"]["backtest"]["stats"] == expected
    assert r["cfg_json"]["backtest"]["stats"] == expected
    assert r["web"]["stats"] == expected


@pytest.mark.parametrize("case", CASES, ids=ids)
def test_same_strategy_and_parameters_on_every_path(runs, case):
    r = runs[case]
    bt = r["cli_json"]["backtest"]
    assert (bt["strategy"], bt["params"]) == (r["engine"].strategy, r["engine"].strategy_params)
    assert (r["web"]["strategy"], r["web"]["strategy_params"]) == (bt["strategy"], bt["params"])


@pytest.mark.parametrize("case", CASES, ids=ids)
def test_web_report_is_the_command_line_report_line_for_line(runs, case):
    r = runs[case]
    cli_lines = r["cli_text"].splitlines()
    web_lines = r["web"]["report"]
    n = len(web_lines)
    assert cli_lines[:n] == web_lines
    # after the shared report the command line only adds its stats block (--stats) and the disclaimer
    assert cli_lines[n:] == format_stats(r["engine"]) + [DISCLAIMER]
    assert r["web"]["disclaimer"] == DISCLAIMER


# --------------------------------------------------------------------------- the cases really exercise the features


def test_the_cases_cover_every_setting_and_strategy():
    used = set()
    strategies = set()
    for combo in COMBOS.values():
        used |= set(combo) - {"windows"}
        strategies.add(combo.get("strategy", "sma_cross"))
    assert used >= {"rsi_period", "cash", "fee", "fee_pct", "slippage", "position_size", "fill", "stop_loss", "take_profit", "strategy", "params"}
    from trading_assistant.strategies import strategy_names

    assert strategies == set(strategy_names())


def test_the_cases_produce_real_trades_stops_targets_and_gap_fills(runs, csv_paths):
    reasons = set()
    gap_fills = 0
    opens = {name: [c.open for c in load_candles(path)] for name, path in csv_paths.items()}
    for (file_name, _), r in runs.items():
        for t in r["engine"].trades:
            reasons.add(t.reason)
            slip = r["settings"].get("slippage", 0.0)
            if t.reason in ("stop", "target") and t.price == opens[file_name][t.bar] * (1 - slip / 100.0 if slip else 1):
                gap_fills += 1
    assert reasons == {"signal", "stop", "target"}
    assert gap_fills > 0  # at least one exit filled at a gapped open, not at its level
    assert sum(len(r["engine"].trades) for r in runs.values()) > 500
    assert all(r["engine"].trades for (f, _), r in runs.items() if f == "walk")  # every walk case trades
