"""POST /api/walkforward: the walk-forward command's --json for prices sent in the request body."""

import json
import threading

import pytest

from trading_assistant.samples import SAMPLES, sample_table
from trading_assistant.walkforward import main as walkforward_main
from trading_assistant.walkforward import summarize, walk_forward
from trading_assistant.web import server as web

SIDEWAYS = sample_table("sideways")[1]  # 150 seeded closes, two decimals


def csv_text(closes):
    return "date,close\n" + "".join(f"2026-{i // 28 + 1:02d}-{i % 28 + 1:02d},{c}\n" for i, c in enumerate(closes))


class Client:
    def __init__(self, server):
        self.server = server
        host, port = server.server_address[:2]
        self.base = f"http://{host}:{port}"

    def request(self, method, path, body=None, headers=None):
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen

        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
        req = Request(self.base + path, data=data, method=method, headers=headers or {})
        if body is not None and "Content-Type" not in (headers or {}):
            req.add_header("Content-Type", "application/json")
        try:
            with urlopen(req, timeout=30) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def walkforward(self, payload):
        status, _, raw = self.request("POST", "/api/walkforward", body=payload)
        return status, json.loads(raw.decode())


@pytest.fixture(scope="module")
def client():
    server = web.BacktestServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield Client(server)
    server.shutdown()
    server.server_close()


def cli_run(tmp_path, capsys, text, flags):
    """Run the command on ``text`` written to a file; returns (exit code, stdout, stderr)."""
    path = tmp_path / "prices.csv"
    path.write_text(text)
    try:
        code = walkforward_main([str(path), *flags])
    except SystemExit as exc:  # usage errors
        code = exc.code
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def cli_json(tmp_path, capsys, text, flags):
    code, out, err = cli_run(tmp_path, capsys, text, [*flags, "--json"])
    assert code == 0, err
    return json.loads(out)


def cli_error(tmp_path, capsys, text, flags):
    """The one-line message the command prints for an error (usage error or data error)."""
    code, out, err = cli_run(tmp_path, capsys, text, flags)
    assert code in (1, 2) and out == ""
    last = err.strip().splitlines()[-1]
    for prefix in ("trading_assistant.walkforward: error: ", "Error: "):
        if last.startswith(prefix):
            return last[len(prefix) :]
    return last


BASE = {"short": "2,3,5", "long": "5,10,20", "train": 40, "test": 20}
BASE_FLAGS = ["--short", "2,3,5", "--long", "5,10,20", "--train", "40", "--test", "20"]


# --------------------------------------------------------------------------- replies


def test_sample_reply_is_the_command_json_and_walk_forward_plus_summarize(client, tmp_path, capsys):
    status, data = client.walkforward({"source": "sample", "sample": "sideways", **BASE})
    assert status == 200
    expected = cli_json(tmp_path, capsys, csv_text(SIDEWAYS), BASE_FLAGS)
    assert data == expected
    assert list(data) == list(expected)  # same keys in the same order; no "ok" key added
    rows = walk_forward(SIDEWAYS, [2, 3, 5], [5, 10, 20], 40, 20)
    assert data["windows"] == rows
    assert data["summary"] == summarize(rows)
    assert len(rows) > 1


def test_csv_reply_is_the_command_json(client, tmp_path, capsys):
    closes = sample_table("random_walk")[1][:300]
    text = csv_text(closes)
    payload = {"source": "csv", "csv": text, "short": "5,10", "long": "20,50", "train": 120, "test": 40}
    status, data = client.walkforward(payload)
    assert status == 200
    flags = ["--short", "5,10", "--long", "20,50", "--train", "120", "--test", "40"]
    assert data == cli_json(tmp_path, capsys, text, flags)
    rows = walk_forward(closes, [5, 10], [20, 50], 120, 40)
    assert data == {**data, "windows": rows, "summary": summarize(rows)}


def test_csv_is_the_default_source_when_csv_is_given(client, tmp_path, capsys):
    text = csv_text(SIDEWAYS)
    status, data = client.walkforward({"csv": text, **BASE})
    assert status == 200
    assert data == cli_json(tmp_path, capsys, text, BASE_FLAGS)


@pytest.mark.parametrize(
    "settings, flags",
    [
        ({"step": 10}, ["--step", "10"]),
        ({"step": 25}, ["--step", "25"]),
        ({"cash": 5000}, ["--cash", "5000"]),
        ({"fee": 1, "fee_pct": 0.1}, ["--fee", "1", "--fee-pct", "0.1"]),
        (
            {"step": "10", "cash": "2500.5", "fee": "0.5", "fee_pct": "0.25"},
            ["--step", "10", "--cash", "2500.5", "--fee", "0.5", "--fee-pct", "0.25"],
        ),
        ({"short": [2, 3, 5], "long": [5, 10, 20]}, []),
        ({"short": " 3,2 ", "long": "20,5,20"}, ["--short", "3,2", "--long", "20,5,20"]),
    ],
)
def test_settings_follow_the_command_line(client, tmp_path, capsys, settings, flags):
    status, data = client.walkforward({"sample": "sideways", **BASE, **settings})
    assert status == 200
    assert data == cli_json(tmp_path, capsys, csv_text(SIDEWAYS), [*BASE_FLAGS, *flags])


def test_every_sample_matches_the_command(client, tmp_path, capsys):
    for name in SAMPLES:
        closes = sample_table(name)[1]
        payload = {"sample": name, "short": "5,10", "long": "20,40", "train": 100, "test": 50}
        status, data = client.walkforward(payload)
        assert status == 200, (name, data)
        flags = ["--short", "5,10", "--long", "20,40", "--train", "100", "--test", "50"]
        assert data == cli_json(tmp_path, capsys, csv_text(closes), flags), name


# ----------------------------------------------------- errors: same message as the command


@pytest.mark.parametrize(
    "settings, flags",
    [
        ({"short": "9", "long": "5"}, ["--short", "9", "--long", "5", "--train", "40", "--test", "20"]),
        ({"train": 0}, ["--short", "2,3,5", "--long", "5,10,20", "--train", "0", "--test", "20"]),
        ({"test": 0}, ["--short", "2,3,5", "--long", "5,10,20", "--train", "40", "--test", "0"]),
        ({"step": 0}, [*BASE_FLAGS, "--step", "0"]),
        ({"train": -5}, ["--short", "2,3,5", "--long", "5,10,20", "--train", "-5", "--test", "20"]),
        ({"short": "2,x"}, ["--short", "2,x", "--long", "5,10,20", "--train", "40", "--test", "20"]),
        ({"short": "0"}, ["--short", "0", "--long", "5,10,20", "--train", "40", "--test", "20"]),
        ({"long": [0]}, ["--short", "2,3,5", "--long", "0", "--train", "40", "--test", "20"]),
        ({"cash": 0}, [*BASE_FLAGS, "--cash", "0"]),
        ({"fee": -1}, [*BASE_FLAGS, "--fee", "-1"]),
        ({"fee_pct": 100}, [*BASE_FLAGS, "--fee-pct", "100"]),
        ({"train": 140}, ["--short", "2,3,5", "--long", "5,10,20", "--train", "140", "--test", "20"]),
    ],
)
def test_setting_errors_match_the_command(client, tmp_path, capsys, settings, flags):
    status, data = client.walkforward({"sample": "sideways", **BASE, **settings})
    assert status == 400
    assert data == {"ok": False, "error": cli_error(tmp_path, capsys, csv_text(SIDEWAYS), flags)}


@pytest.mark.parametrize(
    "text",
    [
        "date,close\n2026-01-01,10\n2026-01-02,-1\n2026-01-03,11\n",  # non-positive price
        csv_text(SIDEWAYS[:100]) + "2026-09-01,0\n" + "".join(f"2026-09-02,{c}\n" for c in SIDEWAYS[:30]),
        "date,close\n",  # no rows
        "date,price\n2026-01-01,10\n",  # no close column
        "date,close\n2026-01-01,10\n2026-01-02,abc\n",  # bad number
    ],
)
def test_data_errors_match_the_command(client, tmp_path, capsys, text):
    payload = {"csv": text, "short": "1", "long": "2", "train": 1, "test": 1}
    status, data = client.walkforward(payload)
    assert status == 400
    flags = ["--short", "1", "--long", "2", "--train", "1", "--test", "1"]
    expected = cli_error(tmp_path, capsys, text, flags)
    assert data == {"ok": False, "error": expected.replace(str(tmp_path / "prices.csv"), "CSV")}


def test_bad_price_is_reported_with_its_bar_in_the_whole_series(client):
    closes = list(SIDEWAYS)
    closes[145] = -1.0  # after the last test block (bars 40-139 are used), still an error
    status, data = client.walkforward({"csv": csv_text(closes), **BASE})
    assert (status, data) == (400, {"ok": False, "error": "bar 145: price must be positive, got -1.0"})


@pytest.mark.parametrize("key", ["short", "long", "train", "test"])
@pytest.mark.parametrize("missing", [None, "", "drop"])
def test_required_settings(client, key, missing):
    payload = {"sample": "sideways", **BASE}
    if missing == "drop":
        del payload[key]
    else:
        payload[key] = missing
    status, data = client.walkforward(payload)
    assert (status, data) == (400, {"ok": False, "error": f"the following arguments are required: --{key}"})


@pytest.mark.parametrize(
    "settings, message",
    [
        ({"short": {"a": 1}}, "short must be a comma list of positive integers like 5,10,20"),
        ({"long": [5, "10"]}, "long must be a comma list of positive integers like 5,10,20"),
        ({"long": [True]}, "long must be a comma list of positive integers like 5,10,20"),
        ({"train": "forty"}, "train must be a whole number, got 'forty'"),
        ({"test": 2.5}, "test must be a whole number, got 2.5"),
        ({"step": True}, "step must be a whole number"),
        ({"cash": "lots"}, "cash must be a number, got 'lots'"),
        ({"short": "2", "long": "501"}, f"--long must be at most {web.MAX_WINDOW}, got 501"),
        ({"cash": 2e12}, f"--cash must be at most {web.MAX_CASH:,.0f}"),
        ({"sample": "nope"}, f"unknown sample 'nope'; choose one of: {', '.join(SAMPLES)}"),
        ({"source": "disk"}, "source must be 'sample' or 'csv'"),
        ({"source": "csv"}, "paste or upload a CSV with a 'close' column, or pick a sample"),
    ],
)
def test_bad_requests_are_one_line_400s(client, settings, message):
    status, data = client.walkforward({"sample": "sideways", **BASE, **settings})
    assert (status, data) == (400, {"ok": False, "error": message})


def test_body_must_be_an_object(client):
    status, data = client.walkforward([1, 2])
    assert (status, data) == (400, {"ok": False, "error": "request body must be a JSON object"})


def test_content_type_must_be_json(client):
    status, _, raw = client.request(
        "POST", "/api/walkforward", body=json.dumps(BASE).encode(), headers={"Content-Type": "text/plain"}
    )
    assert status == 415
    assert json.loads(raw) == {"ok": False, "error": "Content-Type must be application/json"}


def test_get_is_405(client):
    status, _, raw = client.request("GET", "/api/walkforward")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "use POST for /api/walkforward"}


def test_errors_never_leak_a_traceback(client):
    for payload in ({"short": {"x": []}}, {"train": [1]}, {"csv": 5, "source": "csv"}, {"sample": ["x"]}):
        status, _, raw = client.request("POST", "/api/walkforward", body={"sample": "sideways", **BASE, **payload})
        assert status == 400
        assert b"Traceback" not in raw


# --------------------------------------------------------------------------- limits


def test_too_many_rows_is_413(client, monkeypatch):
    monkeypatch.setattr(web, "MAX_BARS", 100)
    status, data = client.walkforward({"sample": "sideways", **BASE})
    assert (status, data) == (413, {"ok": False, "error": "too many price rows (150); the limit is 100"})


def test_work_limit_boundary(client, monkeypatch):
    # sideways: 150 bars, train 40, test 20 -> 5 windows; [2,3,5] x [5,10,20] has
    # 8 pairs with short < long. Work = 5 * (8 * 40 + 20) = 1,700 bar-steps.
    monkeypatch.setattr(web, "MAX_WALKFORWARD_BAR_STEPS", 1700)
    status, _ = client.walkforward({"sample": "sideways", **BASE})
    assert status == 200
    monkeypatch.setattr(web, "MAX_WALKFORWARD_BAR_STEPS", 1699)
    status, data = client.walkforward({"sample": "sideways", **BASE})
    assert status == 413
    assert data["ok"] is False
    assert data["error"].startswith(
        "this walk-forward is too big for the web page (5 windows x 8 pairs, 1,700 bar-steps;"
    )


def test_default_work_limit_allows_the_documented_example(client):
    # The command's docstring example: --short 5,10,20 --long 20,50,100 --train 250 --test 60,
    # on the 750-bar random walk: 8 windows x 8 pairs.
    payload = {"sample": "random_walk", "short": "5,10,20", "long": "20,50,100", "train": 250, "test": 60}
    status, data = client.walkforward(payload)
    assert status == 200
    assert data["summary"]["windows"] == 8


def test_busy_server_is_429(client):
    slots = client.server.run_slots
    taken = 0
    while slots.acquire(blocking=False):
        taken += 1
    try:
        status, data = client.walkforward({"sample": "sideways", **BASE})
    finally:
        for _ in range(taken):
            slots.release()
    assert (status, data) == (429, {"ok": False, "error": "the server is busy with other runs; try again in a moment"})
