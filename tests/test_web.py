"""Tests for the local web page (trading_assistant.web) and the sample series.

A real server is started on an ephemeral loopback port for each test module
and driven with urllib / raw sockets, so routing, headers, limits and error
handling are exercised exactly as a browser would see them.
"""

import errno
import io
import json
import logging
import re
import socket
import threading
import time

import pytest

from trading_assistant.cli import main as cli_main
from trading_assistant.samples import SAMPLES, describe_samples, sample_table
from trading_assistant.samples import main as samples_main
from trading_assistant.web import server as web
from trading_assistant.web.assets import APP_JS, INDEX_HTML, STYLE_CSS

# --------------------------------------------------------------------------- fixtures / helpers


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

    def get(self, path, headers=None):
        return self.request("GET", path, headers=headers)

    def post_json(self, path, payload, headers=None):
        status, hdrs, raw = self.request("POST", path, body=payload, headers=headers)
        return status, hdrs, json.loads(raw.decode())

    def raw(self, text):
        """Send raw bytes over a socket and return the decoded response."""
        host, port = self.server.server_address[:2]
        with socket.create_connection((host, port), timeout=10) as sock:
            sock.sendall(text.encode() if isinstance(text, str) else text)
            sock.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        return b"".join(chunks).decode(errors="replace")


def _start(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


@pytest.fixture(scope="module")
def client():
    server = web.BacktestServer(("127.0.0.1", 0))
    _start(server)
    yield Client(server)
    server.shutdown()
    server.server_close()


def sample_csv_text(name):
    dates, closes = sample_table(name)
    return "date,close\n" + "".join(f"{d},{c:.2f}\n" for d, c in zip(dates, closes))


def cli_run(tmp_path, name, short, long, cash, fee, fee_pct, rsi=14):
    """Run the command line on a sample and return (report lines, exported csv text)."""
    path = tmp_path / f"{name}.csv"
    path.write_text(sample_csv_text(name))
    export = tmp_path / f"{name}_export.csv"
    argv = [
        str(path), "--short", str(short), "--long", str(long), "--rsi-period", str(rsi), "--backtest",
        "--cash", str(cash), "--fee", str(fee), "--fee-pct", str(fee_pct), "--export", str(export),
    ]
    return argv, export


# --------------------------------------------------------------------------- samples


def test_samples_are_deterministic_and_sane():
    for name in SAMPLES:
        dates, closes = sample_table(name)
        dates2, closes2 = sample_table(name)
        assert closes == closes2 and dates == dates2
        assert len(dates) == len(closes) >= 100
        assert all(c > 0 for c in closes)
        assert all(round(c, 2) == c for c in closes)
        assert dates == sorted(dates) and len(set(dates)) == len(dates)


def test_samples_snapshot_values():
    # Frozen first values: the series must come out the same on every run and machine.
    assert sample_table("uptrend")[1][:3] == [100.44, 100.5, 100.36]
    assert sample_table("downtrend")[1][:3] == [100.82, 100.5, 101.32]
    assert sample_table("sideways")[1][:3] == [98.09, 98.09, 98.12]
    assert sample_table("random_walk")[1][:3] == [100.91, 100.75, 100.55]
    assert sample_table("uptrend")[0][:2] == ["2023-01-02", "2023-01-03"]
    assert [len(sample_table(n)[1]) for n in SAMPLES] == [200, 200, 150, 750]


def test_sample_shapes_match_their_names():
    up, down = sample_table("uptrend")[1], sample_table("downtrend")[1]
    assert up[-1] > up[0] * 1.3
    assert down[-1] < down[0] * 0.8
    side = sample_table("sideways")[1]
    assert 90 < min(side) and max(side) < 110 and abs(side[-1] - side[0]) < 10
    walk = sample_table("random_walk")[1]
    assert len(walk) == 750 and max(walk) / min(walk) > 1.3


def test_unknown_sample_raises():
    with pytest.raises(ValueError, match="unknown sample 'x'"):
        sample_table("x")


def test_describe_samples_lists_all():
    info = describe_samples()
    assert [s["name"] for s in info] == list(SAMPLES)
    assert all(s["bars"] > 0 and s["label"] and s["description"] for s in info)


def test_samples_cli_writes_csv_the_cli_can_read(tmp_path, capsys):
    out = tmp_path / "s.csv"
    assert samples_main(["sideways", str(out)]) == 0
    text = out.read_text()
    assert text.startswith("date,close\n2023-01-02,98.09\n")
    assert cli_main([str(out), "--short", "5", "--long", "20"]) == 0
    assert "Bars:    150" in capsys.readouterr().out


def test_samples_cli_stdout_list_and_errors(capsys):
    assert samples_main(["uptrend"]) == 0
    assert capsys.readouterr().out.startswith("date,close\n")
    assert samples_main(["--list"]) == 0
    assert "random_walk" in capsys.readouterr().out
    assert samples_main(["nope"]) == 1
    assert "unknown sample" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        samples_main([])


# --------------------------------------------------------------------------- static page + headers


def test_index_page_and_assets(client):
    status, headers, body = client.get("/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    html = body.decode()
    assert 'id="run"' in html and 'id="source"' in html and 'id="download"' in html
    assert 'src="/app.js"' in html and 'href="/style.css"' in html
    for path, ctype in [("/style.css", "text/css"), ("/app.js", "text/javascript")]:
        status, headers, body = client.get(path)
        assert status == 200 and headers["Content-Type"].startswith(ctype)
        assert body.decode().strip()


@pytest.mark.parametrize("path", ["/", "/app.js", "/api/samples", "/nope"])
def test_security_headers_on_every_response(client, path):
    status, headers, _ = client.get(path)
    csp = headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp and "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp and "http" not in csp
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Cache-Control"] == "no-store"
    assert headers["Server"] == "TradingAssistant"  # no Python version leak


def test_page_has_no_inline_script_style_or_remote_resources():
    assert not re.search(r"<script(?![^>]*\ssrc=)", INDEX_HTML)
    assert "<style" not in INDEX_HTML and ' style="' not in INDEX_HTML
    assert not re.search(r"\son\w+=", INDEX_HTML)
    assert not re.search(r"https?://", INDEX_HTML + STYLE_CSS)
    assert not re.search(r"https?://(?!www\.w3\.org/2000/svg)", APP_JS)
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert forbidden not in APP_JS


def test_api_samples_and_health(client):
    status, _, data = client.get("/api/samples")[0], None, json.loads(client.get("/api/samples")[2])
    assert status == 200 and data["ok"]
    assert [s["name"] for s in data["samples"]] == list(SAMPLES)
    assert data["limits"]["max_bars"] == web.MAX_BARS
    assert json.loads(client.get("/api/health")[2]) == {"ok": True}


@pytest.mark.parametrize(
    "path",
    ["/nope", "/index.html", "/../pyproject.toml", "/src/trading_assistant/cli.py", "/etc/passwd", "/api", "/api/backtest/x"],
)
def test_unknown_paths_are_404_json(client, path):
    status, headers, body = client.get(path)
    assert status == 404
    assert headers["Content-Type"].startswith("application/json")
    assert json.loads(body) == {"ok": False, "error": "not found"}


def test_path_traversal_over_raw_socket_is_404(client):
    for target in ("/../../etc/passwd", "/..%2F..%2Fetc/passwd", "//etc/passwd"):
        reply = client.raw(f"GET {target} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        assert " 404 " in reply.splitlines()[0]
        assert "root:" not in reply and "Traceback" not in reply


def test_favicon_is_empty_204(client):
    status, _, body = client.get("/favicon.ico")
    assert status == 204 and body == b""


@pytest.mark.parametrize("method, path, status", [("PUT", "/", 405), ("DELETE", "/api/backtest", 405), ("PATCH", "/", 405), ("OPTIONS", "/api/backtest", 405), ("GET", "/api/backtest", 405), ("POST", "/", 404), ("POST", "/api/samples", 404)])
def test_unsupported_methods(client, method, path, status):
    code, headers, body = client.request(method, path, body=b"{}" if method != "GET" else None)
    assert code == status
    assert json.loads(body)["ok"] is False


def test_head_request_has_headers_and_no_body(client):
    code, headers, body = client.request("HEAD", "/")
    assert code == 200 and body == b"" and int(headers["Content-Length"]) > 1000


def test_bad_host_header_is_rejected(client, caplog):
    with caplog.at_level(logging.WARNING, logger="trading_assistant.web"):
        status, _, body = client.get("/", headers={"Host": "evil.example"})
    assert status == 400
    assert json.loads(body)["error"] == "unexpected Host header"
    assert "evil.example" in caplog.text
    for good in ("localhost", "127.0.0.1", f"localhost:{client.server.server_address[1]}"):
        assert client.get("/api/health", headers={"Host": good})[0] == 200


def test_malformed_request_line_gets_json_error_not_html(client):
    # No HTTP version: http.server treats it as HTTP/0.9 and sends a body only.
    reply = client.raw("GARBAGE\r\n\r\n")
    assert reply.startswith('{"ok": false, "error": "Bad request syntax')
    assert "<html" not in reply.lower() and "Traceback" not in reply
    # Unsupported version: same treatment, still JSON and never HTML.
    reply = client.raw("GET / HTTP/9.9\r\nHost: 127.0.0.1\r\n\r\n")
    assert reply.startswith('{"ok": false, "error": "Invalid HTTP version')
    assert "<html" not in reply.lower() and "Traceback" not in reply


# --------------------------------------------------------------------------- agreement with the command line


@pytest.mark.parametrize("name", list(SAMPLES))
@pytest.mark.parametrize("short, long, cash, fee, fee_pct", [(20, 50, 10000, 0, 0), (5, 20, 2500, 1, 0.1)])
def test_page_and_cli_give_identical_report_and_csv(client, tmp_path, capsys, name, short, long, cash, fee, fee_pct):
    argv, export = cli_run(tmp_path, name, short, long, cash, fee, fee_pct)
    assert cli_main(argv) == 0
    cli_lines = capsys.readouterr().out.splitlines()
    cli_lines = [line for line in cli_lines if not line.startswith("  Exported:")]
    assert cli_lines[-1] == "Research aid only. Not financial advice."

    status, _, data = client.post_json(
        "/api/backtest",
        {"source": "sample", "sample": name, "short": short, "long": long, "cash": cash, "fee": fee, "fee_pct": fee_pct},
    )
    assert status == 200 and data["ok"], data
    assert data["report"] + [data["disclaimer"]] == cli_lines
    assert data["csv"] == export.read_bytes().decode()  # byte-for-byte, \r\n included
    assert len(data["rows"]) == len(sample_table(name)[1])
    assert data["columns"][0] == "bar"


def test_pasted_csv_matches_sample_and_cli(client, tmp_path, capsys):
    text = sample_csv_text("random_walk")
    argv, export = cli_run(tmp_path, "random_walk", 10, 30, 10000, 2, 0.25)
    assert cli_main(argv) == 0
    cli_report = [l for l in capsys.readouterr().out.splitlines() if not l.startswith("  Exported:")][:-1]

    status, _, pasted = client.post_json("/api/backtest", {"source": "csv", "csv": text, "short": 10, "long": 30, "fee": 2, "fee_pct": 0.25})
    status2, _, sampled = client.post_json("/api/backtest", {"sample": "random_walk", "short": 10, "long": 30, "fee": 2, "fee_pct": 0.25})
    assert status == status2 == 200
    assert pasted["report"] == sampled["report"] == cli_report
    assert pasted["csv"] == sampled["csv"] == export.read_bytes().decode()
    assert pasted["source"]["label"] == "Pasted / uploaded CSV"


def test_summary_and_trades_match_the_report_text(client):
    status, _, data = client.post_json("/api/backtest", {"sample": "sideways", "short": 5, "long": 20, "fee": 1, "fee_pct": 0.1})
    assert status == 200
    report = "\n".join(data["report"])
    s = data["summary"]
    assert f"  End equity:  {s['end_equity']['text']}" in report
    assert f"  Return:      {s['return_pct']['text']}" in report
    assert f"  Costs:       {s['costs_paid']['text']} paid" in report
    assert f"  Trades:      {s['trades']} ({s['buys']} buy, {s['sells']} sell)" in report
    assert s["win_rate_text"].startswith(f"{s['winning_round_trips']}/{s['round_trips']}")
    assert s["max_drawdown_pct"]["text"] in report and s["buy_hold"]["max_drawdown_pct"]["text"] in report
    for t in data["trades"]:
        assert f"bar {t['bar']:<5d} {t['side']:<4s} {t['shares']:>8d} @ {t['price']['text']:>10s}" in report
    # every trade appears as an action in the per-bar rows
    actions = [(int(r[0]), r[4]) for r in data["rows"] if r[4]]
    assert actions == [(t["bar"], t["side"]) for t in data["trades"]]


def test_string_numbers_and_defaults_are_accepted(client):
    status, _, a = client.post_json("/api/backtest", {"sample": "uptrend", "short": "5", "long": "20", "cash": "10,000", "fee": "", "fee_pct": None})
    status2, _, b = client.post_json("/api/backtest", {"sample": "uptrend", "short": 5, "long": 20})
    assert status == status2 == 200
    assert a["report"] == b["report"]
    assert a["params"] == {"short": 5, "long": 20, "rsi_period": 14, "cash": 10000.0, "fee": 0.0, "fee_pct": 0.0}


# --------------------------------------------------------------------------- bad input


@pytest.mark.parametrize(
    "payload, status, message",
    [
        ({"sample": "sideways", "short": 50, "long": 20}, 400, "--short (50) must be smaller than --long (20)"),
        ({"sample": "sideways", "short": 20, "long": 20}, 400, "--short (20) must be smaller than --long (20)"),
        ({"sample": "sideways", "short": 0}, 400, "--short must be at least 1"),
        ({"sample": "sideways", "long": -3}, 400, "--long must be at least 1"),
        ({"sample": "sideways", "rsi_period": 0}, 400, "--rsi-period must be at least 1"),
        ({"sample": "sideways", "short": "abc"}, 400, "short must be a whole number, got 'abc'"),
        ({"sample": "sideways", "short": 2.5}, 400, "short must be a whole number, got 2.5"),
        ({"sample": "sideways", "short": True}, 400, "short must be a whole number"),
        ({"sample": "sideways", "short": [1]}, 400, "short must be a whole number"),
        ({"sample": "sideways", "cash": 0}, 400, "--cash must be positive, got 0"),
        ({"sample": "sideways", "cash": -5}, 400, "--cash must be positive"),
        ({"sample": "sideways", "cash": "lots"}, 400, "cash must be a number, got 'lots'"),
        ({"sample": "sideways", "cash": "1e999"}, 400, "cash must be a finite number"),
        ({"sample": "sideways", "cash": 1e13}, 400, "--cash must be at most"),
        ({"sample": "sideways", "fee": -1}, 400, "--fee must not be negative, got -1"),
        ({"sample": "sideways", "fee_pct": 100}, 400, "--fee-pct must be between 0 and 100 (exclusive), got 100"),
        ({"sample": "sideways", "fee_pct": -0.1}, 400, "--fee-pct must be between 0 and 100"),
        ({"sample": "sideways", "short": 600, "long": 700}, 400, "--short must be at most 500, got 600"),
        ({"sample": "sideways", "long": 501}, 400, "--long must be at most 500, got 501"),
        ({"sample": "nope"}, 400, "unknown sample 'nope'; choose one of: uptrend, downtrend, sideways, random_walk"),
        ({"sample": 5}, 400, "unknown sample"),
        ({}, 400, "unknown sample ''"),
        ({"source": "magic"}, 400, "source must be 'sample' or 'csv'"),
        ({"source": "csv"}, 400, "paste or upload a CSV"),
        ({"source": "csv", "csv": "   "}, 400, "paste or upload a CSV"),
        ({"source": "csv", "csv": 42}, 400, "paste or upload a CSV"),
        ({"source": "csv", "csv": "date,price\n1,2\n"}, 400, "CSV has no 'close' column"),
        ({"source": "csv", "csv": "date,close\nd1,10\nd2,abc\n"}, 400, "CSV line 3: invalid close value 'abc'"),
        ({"source": "csv", "csv": "date,close\nd1,10\nd2,\n"}, 400, "CSV line 3: invalid close value ''"),
        ({"source": "csv", "csv": "date,close\nd1,10\nd2,-5\n"}, 400, "bar 1: price must be positive, got -5.0"),
        ({"source": "csv", "csv": "date,close\nd1,0\n"}, 400, "bar 0: price must be positive, got 0.0"),
        ({"source": "csv", "csv": "date,close\n"}, 400, "No price rows found."),
        ({"source": "csv", "csv": "garbage"}, 400, "CSV has no 'close' column"),
    ],
)
def test_bad_input_gives_clear_json_error(client, payload, status, message):
    code, headers, data = client.post_json("/api/backtest", payload)
    assert code == status
    assert headers["Content-Type"].startswith("application/json")
    assert data["ok"] is False
    assert message in data["error"]
    assert "Traceback" not in data["error"]


def test_error_messages_match_the_command_line(tmp_path, capsys, client):
    # The page must report exactly what the command line would for the same mistake.
    path = tmp_path / "p.csv"
    path.write_text("date,close\nd1,10\nd2,abc\n")
    assert cli_main([str(path), "--backtest"]) == 1
    cli_err = capsys.readouterr().err.strip()
    _, _, data = client.post_json("/api/backtest", {"source": "csv", "csv": path.read_text()})
    assert cli_err == "Error: " + data["error"].replace("CSV line", f"{path} line")

    with pytest.raises(SystemExit):
        cli_main([str(path), "--backtest", "--short", "50", "--long", "20"])
    cli_usage = capsys.readouterr().err.strip().splitlines()[-1]
    _, _, data = client.post_json("/api/backtest", {"sample": "uptrend", "short": 50, "long": 20})
    assert cli_usage.endswith(data["error"])


@pytest.mark.parametrize("body, ctype, status, message", [
    (b"not json", "application/json", 400, "not valid JSON"),
    (b"[1, 2]", "application/json", 400, "must be a JSON object"),
    (b'"text"', "application/json", 400, "must be a JSON object"),
    (b"\xff\xfe", "application/json", 400, "must be UTF-8"),
    (b"{}", "text/plain", 415, "Content-Type must be application/json"),
    (b"{}", "application/x-www-form-urlencoded", 415, "Content-Type must be application/json"),
])
def test_bad_bodies(client, body, ctype, status, message):
    code, _, raw = client.request("POST", "/api/backtest", body=body, headers={"Content-Type": ctype})
    assert code == status
    assert message in json.loads(raw)["error"]


def test_json_with_charset_parameter_is_accepted(client):
    code, _, raw = client.request("POST", "/api/backtest", body=b'{"sample": "uptrend"}', headers={"Content-Type": "application/json; charset=utf-8"})
    assert code == 200 and json.loads(raw)["ok"]


def test_missing_content_length_and_chunked_are_rejected(client):
    reply = client.raw("POST /api/backtest HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n")
    assert " 411 " in reply.splitlines()[0] and "Content-Length header is required" in reply
    reply = client.raw(
        "POST /api/backtest HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
        "Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n2\r\n{}\r\n0\r\n\r\n"
    )
    assert " 411 " in reply.splitlines()[0] and "chunked" in reply
    reply = client.raw("POST /api/backtest HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: abc\r\nConnection: close\r\n\r\n")
    assert " 400 " in reply.splitlines()[0] and "invalid Content-Length" in reply


# --------------------------------------------------------------------------- size and time limits


def test_body_over_limit_is_refused_before_reading(client):
    reply = client.raw(
        "POST /api/backtest HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
        f"Content-Length: {web.MAX_BODY_BYTES + 1}\r\n\r\n" + "{"
    )
    assert " 413 " in reply.splitlines()[0]
    assert f"the limit is {web.MAX_BODY_BYTES:,}" in reply


def test_body_exactly_at_limit_is_read(client):
    filler = "x" * (web.MAX_BODY_BYTES - len('{"sample":"uptrend","pad":""}'))
    body = json.dumps({"sample": "uptrend", "pad": filler}, separators=(",", ":")).encode()
    assert len(body) == web.MAX_BODY_BYTES
    code, _, raw = client.request("POST", "/api/backtest", body=body)
    assert code == 200 and json.loads(raw)["ok"]


def test_too_many_rows_is_413(client, monkeypatch):
    monkeypatch.setattr(web, "MAX_BARS", 50)
    text = "close\n" + "10\n" * 51
    code, _, data = client.post_json("/api/backtest", {"source": "csv", "csv": text, "short": 2, "long": 3})
    assert code == 413
    assert data["error"] == "too many price rows (51); the limit is 50"
    code, _, data = client.post_json("/api/backtest", {"source": "csv", "csv": "close\n" + "10\n" * 50, "short": 2, "long": 3})
    assert code == 200


def test_csv_over_character_limit_is_413(monkeypatch):
    # Over HTTP the body-size check fires first; the CSV check guards direct callers.
    monkeypatch.setattr(web, "MAX_BODY_BYTES", 200)
    with pytest.raises(web.WebError) as excinfo:
        web.parse_request({"source": "csv", "csv": "close\n" + "10\n" * 100})
    assert excinfo.value.status == 413 and "CSV is too large" in excinfo.value.message


def test_pasted_csv_of_max_rows_runs_within_the_time_limit(client):
    # The biggest allowed input with the biggest allowed windows must finish comfortably.
    closes = [100 + ((i * 7919) % 1000) / 100 for i in range(web.MAX_BARS)]
    text = "close\n" + "".join(f"{c:.2f}\n" for c in closes)
    started = time.monotonic()
    code, _, data = client.post_json("/api/backtest", {"source": "csv", "csv": text, "short": web.MAX_WINDOW - 1, "long": web.MAX_WINDOW})
    elapsed = time.monotonic() - started
    assert code == 200 and data["ok"]
    assert len(data["rows"]) == web.MAX_BARS
    assert elapsed < web.MAX_RUN_SECONDS


def test_run_that_exceeds_time_limit_is_abandoned_with_message(monkeypatch, caplog):
    server = web.BacktestServer(("127.0.0.1", 0), max_run_seconds=0.2)
    _start(server)
    try:
        real = web.build_response

        def slow(params):
            time.sleep(0.6)
            return real(params)

        monkeypatch.setattr(web, "build_response", slow)
        code, _, data = Client(server).post_json("/api/backtest", {"sample": "uptrend"})
        assert code == 503
        assert data["error"].startswith("the run took longer than 0.2 seconds and was abandoned")
    finally:
        server.shutdown()
        server.server_close()


def test_too_many_concurrent_runs_is_429(client):
    slots = client.server.run_slots
    held = 0
    try:
        while slots.acquire(blocking=False):
            held += 1
        code, _, data = client.post_json("/api/backtest", {"sample": "uptrend"})
        assert code == 429 and "busy" in data["error"]
    finally:
        for _ in range(held):
            slots.release()
    assert client.post_json("/api/backtest", {"sample": "uptrend"})[0] == 200


# --------------------------------------------------------------------------- never a stack trace


def test_unexpected_exception_is_logged_and_answered_generically(client, monkeypatch, caplog):
    def boom(params):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(web, "build_response", boom)
    with caplog.at_level(logging.ERROR, logger="trading_assistant.web"):
        code, headers, data = client.post_json("/api/backtest", {"sample": "uptrend"})
    assert code == 500
    assert data == {"ok": False, "error": "internal error; see the server log"}
    assert "secret internal detail" not in json.dumps(data)
    assert "Traceback" in caplog.text and "secret internal detail" in caplog.text  # but it IS in the log


def test_requests_are_logged_with_status_and_timing(client, caplog):
    with caplog.at_level(logging.INFO, logger="trading_assistant.web"):
        client.get("/api/health")
        client.get("/nope")
    assert re.search(r"GET /api/health 200 \d+ms", caplog.text)
    assert re.search(r"GET /nope 404 \d+ms", caplog.text)


def test_hostile_csv_content_comes_back_escaped_in_json_only(client):
    evil = '<script>alert(1)</script>'
    text = f"date,close\n{evil},10\nd2,11\nd3,12\nd4,13\n"
    code, headers, raw = client.request("POST", "/api/backtest", body={"source": "csv", "csv": text, "short": 2, "long": 3})
    assert code == 200
    assert headers["Content-Type"].startswith("application/json") and headers["X-Content-Type-Options"] == "nosniff"
    assert b"<script>" not in raw  # JSON-escaped as \u003c... never raw markup
    data = json.loads(raw)
    assert data["rows"][0][1] == evil  # the value itself is preserved for the page to insert as text
    assert evil in data["csv"]


# --------------------------------------------------------------------------- parse_request unit tests


def test_parse_request_defaults():
    params = web.parse_request({"sample": "sideways"})
    assert (params["short"], params["long"], params["rsi_period"]) == (20, 50, 14)
    assert (params["cash"], params["fee"], params["fee_pct"]) == (10000.0, 0.0, 0.0)
    assert params["closes"] == sample_table("sideways")[1]
    assert params["dates"] == sample_table("sideways")[0]


def test_parse_request_csv_without_date_column():
    params = web.parse_request({"csv": "close\n1\n2\n3\n", "short": 1, "long": 2})
    assert params["dates"] is None and params["closes"] == [1.0, 2.0, 3.0]


def test_parse_request_rejects_non_object():
    with pytest.raises(web.WebError) as excinfo:
        web.parse_request(["x"])
    assert excinfo.value.status == 400


# --------------------------------------------------------------------------- ports and start-up


def _occupy_port():
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    return sock, sock.getsockname()[1]


def test_create_server_moves_to_next_free_port_when_default_is_busy(caplog):
    sock, port = _occupy_port()
    try:
        with caplog.at_level(logging.WARNING, logger="trading_assistant.web"):
            server = web.create_server("127.0.0.1", port, explicit_port=False)
        try:
            assert server.server_address[1] != port
            assert port < server.server_address[1] <= port + web.PORT_SEARCH_SPAN
            assert f"port {port} was busy; using port {server.server_address[1]} instead" in caplog.text
        finally:
            server.server_close()
    finally:
        sock.close()


def test_create_server_explicit_busy_port_raises():
    sock, port = _occupy_port()
    try:
        with pytest.raises(OSError) as excinfo:
            web.create_server("127.0.0.1", port, explicit_port=True)
        assert excinfo.value.errno == errno.EADDRINUSE
    finally:
        sock.close()


def test_main_reports_busy_port_clearly(capsys):
    sock, port = _occupy_port()
    try:
        assert web.main(["--port", str(port)]) == 1
        err = capsys.readouterr().err
        assert err.strip() == f"Error: port {port} is already in use; pick another with --port"
    finally:
        sock.close()


def test_main_rejects_bad_port(capsys):
    assert web.main(["--port", "70000"]) == 2
    assert "--port must be between 0 and 65535" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        web.main(["--port", "abc"])


def test_main_serves_and_stops_cleanly_on_keyboard_interrupt(monkeypatch, capsys):
    def fake_serve(server):
        server.server_close()

    monkeypatch.setattr(web, "serve", fake_serve)
    assert web.main(["--port", "0"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Trading assistant page: http://localhost:")
    assert "Not financial advice" in out


def test_serve_stops_on_keyboard_interrupt_and_closes_socket(caplog):
    server = web.BacktestServer(("127.0.0.1", 0))
    port = server.server_address[1]

    def interrupt_soon():
        time.sleep(0.2)
        server.shutdown()  # what Ctrl+C does from the outside: serve_forever returns

    threading.Thread(target=interrupt_soon, daemon=True).start()
    with caplog.at_level(logging.INFO, logger="trading_assistant.web"):
        web.serve(server)
    assert "stopped" in caplog.text
    # the port is free again straight away
    probe = socket.socket()
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    probe.bind(("127.0.0.1", port))
    probe.close()


def test_server_binds_loopback_by_default_and_checks_host():
    server = web.BacktestServer(("127.0.0.1", 0))
    try:
        assert server.allowed_hosts == {"localhost", "127.0.0.1", "::1"}
        assert server.url.startswith("http://localhost:")
    finally:
        server.server_close()
    assert web._is_loopback("127.0.0.1") and web._is_loopback("localhost") and web._is_loopback("127.1.2.3")
    assert not web._is_loopback("0.0.0.0") and not web._is_loopback("192.168.1.5")
