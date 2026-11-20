"""POST /api/scan: the command line's --scan --json for files sent in the request body."""

import json
import threading

import pytest

from trading_assistant import scan
from trading_assistant.cli import main as cli_main
from trading_assistant.web import server as web

# hand-worked series from test_combined_score.py
RISE_FLAT_JUMP = [100.0 + i for i in range(50)] + [149.0] * 9 + [155.0]  # -2
MIRROR = [300.0 - c for c in RISE_FLAT_JUMP]  # +2
RISE_LONG_FALL = [100.0 + i for i in range(43)] + [141.0 - i for i in range(17)]  # +1
FLAT_JUMP = [100.0] * 59 + [110.0]  # 0
FLAT_DROP = [100.0] * 59 + [90.0]  # 0


def csv_text(closes):
    return "date,close\n" + "".join(f"2026-{i // 28 + 1:02d}-{i % 28 + 1:02d},{c}\n" for i, c in enumerate(closes))


FILES = {
    "DOWN.csv": csv_text(RISE_FLAT_JUMP),
    "UP.csv": csv_text(MIRROR),
    "LOW.csv": csv_text(RISE_LONG_FALL),
    "zeta.csv": csv_text(FLAT_JUMP),
    "Alpha.csv": csv_text(FLAT_DROP),
    "bad.csv": "date,close\n2026-01-01,10\n2026-01-02,abc\n",
}


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
            with urlopen(req, timeout=10) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def scan(self, payload):
        status, headers, raw = self.request("POST", "/api/scan", body=payload)
        return status, json.loads(raw.decode())


@pytest.fixture(scope="module")
def client():
    server = web.BacktestServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield Client(server)
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def no_config_env(monkeypatch):
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)


def cli_json(tmp_path, files, flags, capsys):
    """The command line's --scan --json object for the same files written to a temp folder."""
    folder = tmp_path / "prices"
    folder.mkdir(exist_ok=True)
    for name, text in files.items():
        (folder / name).write_text(text)
    assert cli_main(["--scan", str(folder), "--json", *flags]) == 0
    return json.loads(capsys.readouterr().out)


# --------------------------------------------------------------------------- replies


def test_reply_is_the_scan_json_object(client, tmp_path, capsys):
    status, data = client.scan({"files": FILES})
    assert status == 200
    assert data == cli_json(tmp_path, FILES, [], capsys)
    assert list(data) == ["found", "scored", "shown", "results", "skipped"]  # no "ok" key: exactly the CLI object
    assert [r["symbol"] for r in data["results"]] == ["UP", "LOW", "Alpha", "zeta", "DOWN"]
    assert data["skipped"] == [
        {"symbol": "bad", "reason": "bad.csv line 3: invalid close value 'abc' (expected a number like 101.5)"}
    ]


@pytest.mark.parametrize(
    "settings, flags",
    [
        ({"min_score": 0}, ["--min-score", "0"]),
        ({"top": 2}, ["--top", "2"]),
        ({"min_score": 0, "top": 3}, ["--min-score", "0", "--top", "3"]),
        ({"short": 2, "long": 5, "rsi_period": 2}, ["--short", "2", "--long", "5", "--rsi-period", "2"]),
        ({"min_score": 3}, ["--min-score", "3"]),
    ],
)
def test_settings_follow_the_command_line(client, tmp_path, capsys, settings, flags):
    status, data = client.scan({"files": FILES, **settings})
    assert status == 200
    assert data == cli_json(tmp_path, FILES, flags, capsys)


def test_nothing_matched_is_an_empty_list(client):
    status, data = client.scan({"files": FILES, "min_score": 4})
    assert status == 200
    assert (data["found"], data["scored"], data["shown"], data["results"]) == (6, 5, 0, [])
    assert len(data["skipped"]) == 1


def test_names_are_treated_like_a_folder_listing(client):
    files = {
        "UP.csv": FILES["UP.csv"],
        "LOUD.CSV": FILES["DOWN.csv"],  # capital extension counts, symbol LOUD
        "notes.txt": "not prices",  # other names are ignored
        "old.csv.bak": "date,close\nx,abc\n",
        ".csv": "date,close\n1\n",  # no name before the extension: not a .csv file, as in a folder
    }
    status, data = client.scan({"files": files})
    assert status == 200
    assert data["found"] == 2
    assert [r["symbol"] for r in data["results"]] == ["UP", "LOUD"]


def test_a_bad_file_does_not_stop_the_others(client):
    files = {
        "good.csv": FILES["UP.csv"],
        "noclose.csv": "date,price\nx,1\n",
        "empty.csv": "",
        "header.csv": "date,close\n",
    }
    status, data = client.scan({"files": files})
    assert status == 200
    assert [r["symbol"] for r in data["results"]] == ["good"]
    assert [s["symbol"] for s in data["skipped"]] == ["empty", "header", "noclose"]
    assert data["skipped"][1]["reason"] == "header.csv: no price rows found"


def test_string_numbers_null_and_empty_mean_what_they_do_for_backtests(client):
    assert client.scan({"files": FILES, "top": "2", "min_score": "0"})[1]["shown"] == 2
    assert client.scan({"files": FILES, "top": None, "min_score": "", "short": None})[1]["shown"] == 5


def test_hostile_names_come_back_escaped(client):
    name = "<script>alert(1)<script>.csv"
    status, headers, raw = client.request("POST", "/api/scan", body={"files": {name: FILES["UP.csv"]}})
    assert status == 200 and b"<script>" not in raw
    assert json.loads(raw)["results"][0]["symbol"] == "<script>alert(1)<script>"
    assert "default-src 'none'" in headers["Content-Security-Policy"]


def test_the_disk_is_never_touched(client, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the web scan must not touch the disk")

    for target in ("open",):
        monkeypatch.setattr(scan, target, refuse, raising=False)
    monkeypatch.setattr(scan.os, "listdir", refuse)
    monkeypatch.setattr(scan.os.path, "isfile", refuse)
    monkeypatch.setattr(scan.os.path, "isdir", refuse)
    # even a name that exists on the server is only a label
    status, data = client.scan({"files": {"pyproject.csv": FILES["UP.csv"], "README.csv": "date,close\n"}})
    assert status == 200
    assert [r["symbol"] for r in data["results"]] == ["pyproject"]


# --------------------------------------------------------------------------- errors


@pytest.mark.parametrize(
    "payload, status, message",
    [
        ([1, 2], 400, "request body must be a JSON object"),
        ({}, 400, "no files: send at least one .csv file in files"),
        ({"files": {}}, 400, "no files: send at least one .csv file in files"),
        ({"files": None}, 400, "no files: send at least one .csv file in files"),
        ({"files": ["a.csv"]}, 400, "files must be an object of file name to CSV text"),
        ({"files": "a.csv"}, 400, "files must be an object of file name to CSV text"),
        ({"files": {"a.csv": 5}}, 400, "files['a.csv'] must be CSV text"),
        ({"files": {"a.csv": None}}, 400, "files['a.csv'] must be CSV text"),
        ({"files": {"../a.csv": "x"}}, 400, "file name '../a.csv' must not contain a folder part"),
        ({"files": {"sub/a.csv": "x"}}, 400, "file name 'sub/a.csv' must not contain a folder part"),
        ({"files": {"c:\\a.csv": "x"}}, 400, "file name 'c:\\\\a.csv' must not contain a folder part"),
        ({"files": {"notes.txt": "x"}}, 400, "no .csv files in the request"),
        ({"files": {"a.csv": "date,close\nx,abc\n", "b.csv": ""}}, 400,
         "none of the 2 .csv files in the request could be scored (2 skipped)"),
        ({"files": FILES, "top": 0}, 400, "--top must be at least 1, got 0"),
        ({"files": FILES, "top": -1}, 400, "--top must be at least 1, got -1"),
        ({"files": FILES, "top": "x"}, 400, "top must be a whole number, got 'x'"),
        ({"files": FILES, "min_score": 1.5}, 400, "min_score must be a whole number, got 1.5"),
        ({"files": FILES, "min_score": True}, 400, "min_score must be a whole number"),
        ({"files": FILES, "short": 50, "long": 20}, 400, "--short (50) must be smaller than --long (20)"),
        ({"files": FILES, "rsi_period": 0}, 400, "--rsi-period must be at least 1"),
        ({"files": FILES, "long": 501}, 400, "--long must be at most 500, got 501"),
    ],
)
def test_bad_requests_get_one_line_errors(client, payload, status, message):
    code, data = client.scan(payload)
    assert code == status
    assert data == {"ok": False, "error": message}


def test_window_and_trim_messages_match_the_command_line(tmp_path, capsys, client):
    (tmp_path / "a.csv").write_text(FILES["UP.csv"])
    for flags, payload in [
        (["--top", "0"], {"top": 0}),
        (["--short", "9", "--long", "3"], {"short": 9, "long": 3}),
    ]:
        with pytest.raises(SystemExit):
            cli_main(["--scan", str(tmp_path), *flags])
        cli_line = capsys.readouterr().err.strip().splitlines()[-1]
        _, data = client.scan({"files": FILES, **payload})
        assert cli_line.endswith(data["error"])


def test_too_many_rows_in_one_file_is_413(client, monkeypatch):
    monkeypatch.setattr(web, "MAX_BARS", 59)
    code, data = client.scan({"files": {"a.csv": FILES["UP.csv"], "b.csv": "date,close\n1\n"}})
    assert code == 413
    assert data == {"ok": False, "error": "a.csv has too many price rows (60); the limit is 59"}


def test_body_over_the_limit_is_refused(client, monkeypatch):
    monkeypatch.setattr(web, "MAX_BODY_BYTES", 500)
    code, _, raw = client.request("POST", "/api/scan", body={"files": FILES})
    assert code == 413 and "request body is too large" in json.loads(raw)["error"]


def test_busy_server_is_429(client):
    slots = []
    server_slots = client.server.run_slots
    while server_slots.acquire(blocking=False):  # take every run slot, as long runs would
        slots.append(1)
    try:
        code, data = client.scan({"files": FILES})
    finally:
        for _ in slots:
            server_slots.release()
    assert code == 429 and data["ok"] is False


def test_a_slow_scan_is_abandoned(monkeypatch):
    server = web.BacktestServer(("127.0.0.1", 0), max_run_seconds=0.2)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    release = threading.Event()
    real = web.scan_texts

    def slow(*args, **kwargs):
        release.wait(5)
        return real(*args, **kwargs)

    monkeypatch.setattr(web, "scan_texts", slow)
    try:
        code, data = Client(server).scan({"files": FILES})
    finally:
        release.set()
        server.shutdown()
        server.server_close()
    assert code == 503 and "was abandoned" in data["error"]


@pytest.mark.parametrize("method, status", [("GET", 405), ("PUT", 405), ("DELETE", 405)])
def test_other_methods(client, method, status):
    code, _, raw = client.request(method, "/api/scan", body=b"{}" if method != "GET" else None)
    assert code == status and json.loads(raw)["ok"] is False


def test_content_type_must_be_json(client):
    code, _, raw = client.request("POST", "/api/scan", body=b"{}", headers={"Content-Type": "text/plain"})
    assert code == 415 and json.loads(raw)["error"] == "Content-Type must be application/json"


def test_backtest_route_is_unchanged(client):
    code, _, raw = client.request("POST", "/api/backtest", body={"sample": "uptrend"})
    data = json.loads(raw)
    assert code == 200 and data["ok"] is True and "report" in data
