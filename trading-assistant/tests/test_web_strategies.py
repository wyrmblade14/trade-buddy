"""Web page: strategy picker, strategy parameters and the statistics in the reply."""

import json
import threading

import pytest

from trading_assistant.backtest import run_backtest
from trading_assistant.samples import sample_table
from trading_assistant.strategies import STRATEGIES
from trading_assistant.web import server as web
from trading_assistant.web.assets import APP_JS, INDEX_HTML


class Client:
    def __init__(self, server):
        host, port = server.server_address[:2]
        self.base = f"http://{host}:{port}"

    def get(self, path):
        from urllib.request import urlopen

        with urlopen(self.base + path, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())

    def post(self, payload):
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen

        req = Request(
            self.base + "/api/backtest",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())


@pytest.fixture(scope="module")
def client():
    server = web.BacktestServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield Client(server)
    server.shutdown()
    server.server_close()


SAMPLE = "random_walk"


def closes():
    return list(sample_table(SAMPLE)[1])


def test_default_request_matches_explicit_sma_cross(client):
    status, plain = client.post({"sample": SAMPLE})
    status2, explicit = client.post({"sample": SAMPLE, "strategy": "sma_cross"})
    assert status == status2 == 200
    assert plain == explicit
    direct = run_backtest(closes())
    assert plain["summary"]["end_equity"]["value"] == direct.final_equity
    assert plain["summary"]["trades"] == direct.n_trades
    assert plain["strategy"] == "sma_cross"
    assert plain["strategy_params"] == {"short": 20, "long": 50}
    assert plain["params"]["short"] == 20 and plain["params"]["long"] == 50


def test_default_request_keeps_old_keys(client):
    _, data = client.post({"sample": SAMPLE})
    for key in ("ok", "source", "params", "report", "disclaimer", "summary", "trades", "columns", "rows", "csv"):
        assert key in data
    assert set(data["params"]) == {"short", "long", "rsi_period", "cash", "fee", "fee_pct"}


def test_sma_cross_windows_from_top_level_fields(client):
    _, data = client.post({"sample": SAMPLE, "short": 5, "long": 20})
    direct = run_backtest(closes(), short=5, long=20)
    assert data["summary"]["end_equity"]["value"] == direct.final_equity
    assert data["strategy_params"] == {"short": 5, "long": 20}


@pytest.mark.parametrize(
    "name,params",
    [("rsi_reversion", {}), ("rsi_reversion", {"period": 7, "oversold": 25, "overbought": 75}), ("breakout", {}), ("breakout", {"window": 10})],
)
def test_other_strategies_equal_direct_run(client, name, params):
    status, data = client.post({"sample": SAMPLE, "strategy": name, "params": params, "cash": 5000, "fee_pct": 0.1})
    assert status == 200
    direct = run_backtest(closes(), initial_cash=5000, fee_pct=0.1, strategy=name, strategy_params=params or None)
    assert data["strategy"] == name
    assert data["strategy_params"] == direct.strategy_params
    assert data["summary"]["end_equity"]["value"] == direct.final_equity
    assert data["summary"]["trades"] == direct.n_trades
    assert data["stats"] == json.loads(json.dumps(direct.stats))


def test_stats_keys_present(client):
    _, data = client.post({"sample": SAMPLE})
    assert set(data["stats"]) == set(run_backtest(closes()).stats)


@pytest.mark.parametrize(
    "payload,fragment",
    [
        ({"strategy": "nope"}, "unknown strategy"),
        ({"strategy": 5}, "unknown strategy"),
        ({"strategy": "breakout", "params": {"bogus": 1}}, "unknown parameter"),
        ({"strategy": "breakout", "params": {"window": 0}}, "window"),
        ({"strategy": "breakout", "params": {"window": "abc"}}, "must be a number"),
        ({"strategy": "breakout", "params": {"window": 10.5}}, "window"),
        ({"strategy": "breakout", "params": [1]}, "params must be an object"),
        ({"strategy": "rsi_reversion", "params": {"oversold": 80, "overbought": 20}}, "thresholds"),
        ({"strategy": "breakout", "params": {"window": 100000}}, "at most"),
        ({"strategy": "sma_cross", "short": 5, "params": {"short": 6}}, "contradicts"),
    ],
)
def test_bad_strategy_or_param_gives_standard_error(client, payload, fragment):
    status, data = client.post({"sample": SAMPLE, **payload})
    assert status == 400
    assert data["ok"] is False
    assert set(data) == {"ok", "error"}
    assert fragment in data["error"]


def test_strategy_list_is_served(client):
    status, data = client.get("/api/samples")
    assert status == 200
    names = [s["name"] for s in data["strategies"]]
    assert names == list(STRATEGIES)
    by_name = {s["name"]: s for s in data["strategies"]}
    assert by_name["breakout"]["params"] == {"window": 20}
    assert by_name["sma_cross"]["params"] == {"short": 20, "long": 50}
    assert all(s["description"] for s in data["strategies"])
    assert data["samples"] and data["limits"]


def test_page_has_picker_and_stats_table_and_no_external_resources():
    assert 'id="strategy"' in INDEX_HTML
    assert "Risk and return" in INDEX_HTML
    assert 'id="stats-table"' in INDEX_HTML
    assert "http://" not in INDEX_HTML and "https://" not in INDEX_HTML
    assert "https://" not in APP_JS and "fetch('http" not in APP_JS
    assert "innerHTML" not in APP_JS
