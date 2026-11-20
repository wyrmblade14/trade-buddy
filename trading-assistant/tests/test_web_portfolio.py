"""POST /api/portfolio: the portfolio command's --json for files sent in the request body.

The 8-bar example's figures are worked out by hand in test_portfolio_summary.py.
"""

import json
import socket
import threading

import pytest

from trading_assistant import portfolio
from trading_assistant.cli import DISCLAIMER
from trading_assistant.web import server as web

DATES = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07",
         "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13"]


def csv_text(closes, dates=DATES):
    return "date,close\n" + "".join(f"{d},{c}\n" for d, c in zip(dates, closes))


A = csv_text([10, 9, 8, 9, 11, 12, 10, 8])
B = csv_text([20, 20, 19, 21, 22, 20, 18, 17])
BAD = "date,close\n2026-01-02,30\n2026-01-05,abc\n"
BAD_REASON = "BAD.csv line 3: invalid close value 'abc' (expected a number like 101.5)"
SETTINGS = {"short": 1, "long": 2, "cash": 1000}

# short 1, long 2, cash 1000 -> 500 each, no fees:
#   portfolio 1000 1000 1000 1000 1000 1001 867 777; A 500 .. 545 455 365; B 500 .. 456 412 412
#   buy & hold A 50 @ 10 -> 400, B 25 @ 20 -> 425
EXPECTED_SUMMARY = {
    "short": 1, "long": 2, "fee": 0.0, "fee_pct": 0.0,
    "start_date": "2026-01-02", "end_date": "2026-01-13", "shared_dates": 8,
    "initial_cash": 1000.0, "final_equity": 777.0,
    "return_pct": pytest.approx(-22.3),
    "max_drawdown_pct": pytest.approx(-224 / 1001 * 100),
    "buy_hold_return_pct": pytest.approx(-17.5),
    "worst_symbol_drawdown": {"symbol": "A", "max_drawdown_pct": pytest.approx(-180 / 545 * 100)},
    "symbols": [
        {"symbol": "A", "bars_used": 8, "bars_lost": 0, "return_pct": pytest.approx(-27.0),
         "trades": 2, "buy_hold_return_pct": pytest.approx(-20.0)},
        {"symbol": "B", "bars_used": 8, "bars_lost": 0, "return_pct": pytest.approx(-17.6),
         "trades": 2, "buy_hold_return_pct": pytest.approx(-15.0)},
    ],
}


class Client:
    def __init__(self, server):
        self.server = server
        self.host, self.port = server.server_address[:2]

    def request(self, method, path, body=None, headers=None):
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen

        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
        req = Request(f"http://{self.host}:{self.port}{path}", data=data, method=method, headers=headers or {})
        if body is not None and "Content-Type" not in (headers or {}):
            req.add_header("Content-Type", "application/json")
        try:
            with urlopen(req, timeout=10) as resp:
                return resp.status, resp.read()
        except HTTPError as exc:
            return exc.code, exc.read()

    def post(self, payload):
        status, raw = self.request("POST", "/api/portfolio", body=payload)
        return status, json.loads(raw)


@pytest.fixture(scope="module")
def client():
    server = web.BacktestServer(("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield Client(server)
    server.shutdown()
    server.server_close()


def command(tmp_path, files, args, capsys):
    """``(exit code, stdout, stderr)`` of the portfolio command on ``files`` written to a fresh folder."""
    folder = tmp_path / f"run{len(list(tmp_path.iterdir()))}"
    folder.mkdir()
    for name, text in files.items():
        (folder / name).write_text(text)
    try:
        code = portfolio.main([str(folder), *map(str, args)])
    except SystemExit as exc:  # argparse usage errors
        code = exc.code
    out, err = capsys.readouterr()
    return code, out, err


# ---------------------------------------------------------------- replies


def test_8_bar_example(client):
    status, data = client.post({"files": {"A.csv": A, "B.csv": B}, **SETTINGS})
    assert status == 200
    assert data == {"summary": EXPECTED_SUMMARY, "skipped": [], "disclaimer": DISCLAIMER}


def test_bad_file_is_skipped(client):
    status, data = client.post({"files": {"A.csv": A, "B.csv": B, "BAD.csv": BAD}, **SETTINGS})
    assert status == 200
    assert data == {"summary": EXPECTED_SUMMARY, "skipped": [{"file": "BAD.csv", "reason": BAD_REASON}],
                    "disclaimer": DISCLAIMER}


def test_files_in_reverse_order_give_the_same_reply(client):
    files = {"A.csv": A, "B.csv": B, "BAD.csv": BAD, "C.csv": "close\n1\n"}
    forward = client.request("POST", "/api/portfolio", body={"files": files, **SETTINGS})
    backward = client.request("POST", "/api/portfolio", body={"files": dict(reversed(files.items())), **SETTINGS})
    assert forward[0] == backward[0] == 200
    assert forward[1] == backward[1]  # byte for byte


def test_reply_equals_the_command_json(client, tmp_path, capsys):
    files = {"A.csv": A, "B.csv": B, "BAD.csv": BAD, "C.csv": csv_text([30, 29, 31, 33, 32, 30, 31, 35])}
    settings = {"short": 1, "long": 2, "cash": 1000, "fee": 0.5, "fee_pct": 0.1}
    code, out, err = command(
        tmp_path, files, ["--short", 1, "--long", 2, "--cash", 1000, "--fee", 0.5, "--fee-pct", 0.1, "--json"], capsys
    )
    assert (code, err) == (0, "")
    status, data = client.post({"files": files, **settings})
    assert status == 200
    assert data == json.loads(out)


# ---------------------------------------------------------------- the command's errors are 400s


def test_command_exit_1_cases_are_400_with_its_messages(client, tmp_path, capsys):
    # The command's own message, word for word, where no folder name is involved.
    same_as_command = {
        "too few shared dates": ({"A.csv": A, "B.csv": B}, {"short": 1, "long": 7}, ["--short", 1, "--long", 7]),
        "duplicate date": ({"A.csv": A, "B.csv": csv_text([20, 20, 19, 21], DATES[:2] + DATES[1:3])},
                           SETTINGS, ["--short", 1, "--long", 2]),
    }
    for case, (files, settings, args) in same_as_command.items():
        code, out, err = command(tmp_path, files, args, capsys)
        assert code == 1 and out == "", case
        status, data = client.post({"files": files, **settings})
        assert status == 400, case
        assert err == f"Error: {data['error']}\n", case
    # Where the command names the folder, the request is called "the request".
    status, data = client.post({"files": {"A.csv": A, "NODATE.csv": "close\n1\n"}, **SETTINGS})
    assert (status, data) == (400, {"ok": False, "error": "only 1 of the 2 .csv files in the request could be used"
                                                          " (1 skipped); a portfolio needs at least 2"})
    status, data = client.post({"files": {"notes.txt": "hello"}, **SETTINGS})
    assert (status, data) == (400, {"ok": False, "error": "no .csv files in the request"})


def test_command_exit_2_cases_are_400_with_its_messages(client, tmp_path, capsys):
    cases = [
        ({"short": 0, "long": 2}, ["--short", 0, "--long", 2]),
        ({"short": 1, "long": 0}, ["--short", 1, "--long", 0]),
        ({"short": 2, "long": 2}, ["--short", 2, "--long", 2]),
        ({"short": 3, "long": 2}, ["--short", 3, "--long", 2]),
        ({"cash": 0}, ["--cash", 0]),
        ({"cash": -5}, ["--cash", -5]),
        ({"fee": -1}, ["--fee", -1]),
        ({"fee_pct": -1}, ["--fee-pct", -1]),
        ({"fee_pct": 100}, ["--fee-pct", 100]),
        ({"cash": float("inf")}, ["--cash", "inf"]),
        ({"fee": float("nan")}, ["--fee", "nan"]),
    ]
    for settings, args in cases:
        code, out, err = command(tmp_path, {"A.csv": A, "B.csv": B}, args, capsys)
        assert code == 2 and out == "", args
        status, data = client.post({"files": {"A.csv": A, "B.csv": B}, **settings})
        assert status == 400, args
        assert err.endswith(f"trading_assistant.portfolio: error: {data['error']}\n"), args


def test_folder_part_in_a_file_name_is_400(client):
    status, data = client.post({"files": {"../A.csv": A, "B.csv": B}, **SETTINGS})
    assert (status, data) == (400, {"ok": False, "error": "file name '../A.csv' must not contain a folder part"})


# ---------------------------------------------------------------- the usual POST rules


def test_get_is_405(client):
    status, raw = client.request("GET", "/api/portfolio")
    assert (status, json.loads(raw)) == (405, {"ok": False, "error": "use POST for /api/portfolio"})


def test_content_type_must_be_json_415(client):
    status, raw = client.request("POST", "/api/portfolio", body=b"{}", headers={"Content-Type": "text/plain"})
    assert (status, json.loads(raw)) == (415, {"ok": False, "error": "Content-Type must be application/json"})


def test_content_length_is_required_411(client):
    request = (f"POST /api/portfolio HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
               f"Connection: close\r\n\r\n")
    with socket.create_connection((client.host, client.port), timeout=10) as sock:
        sock.sendall(request.encode())
        sock.shutdown(socket.SHUT_WR)
        reply = b"".join(iter(lambda: sock.recv(65536), b"")).decode()
    assert reply.startswith("HTTP/1.1 411 ")
    assert json.loads(reply.split("\r\n\r\n", 1)[1]) == {"ok": False, "error": "Content-Length header is required"}


def test_body_and_row_limits_are_413(client, monkeypatch):
    monkeypatch.setattr(web, "MAX_BARS", 7)  # each file has 8 rows
    status, data = client.post({"files": {"A.csv": A, "B.csv": B}, **SETTINGS})
    assert (status, data) == (413, {"ok": False, "error": "A.csv has too many price rows (8); the limit is 7"})
    monkeypatch.setattr(web, "MAX_BODY_BYTES", 100)
    status, data = client.post({"files": {"A.csv": A, "B.csv": B}, **SETTINGS})
    assert status == 413 and data["error"].startswith("request body is too large")


def test_busy_server_is_429(client):
    taken = 0
    while client.server.run_slots.acquire(blocking=False):  # take every run slot, as long runs would
        taken += 1
    try:
        status, data = client.post({"files": {"A.csv": A, "B.csv": B}, **SETTINGS})
    finally:
        for _ in range(taken):
            client.server.run_slots.release()
    assert (status, data) == (429, {"ok": False, "error": "the server is busy with other runs; try again in a moment"})


def test_slow_run_is_abandoned_503(monkeypatch):
    server = web.BacktestServer(("127.0.0.1", 0), max_run_seconds=0.2)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    release = threading.Event()
    real = portfolio.run_texts

    def slow(*args, **kwargs):
        release.wait(5)
        return real(*args, **kwargs)

    monkeypatch.setattr(portfolio, "run_texts", slow)
    try:
        status, data = Client(server).post({"files": {"A.csv": A, "B.csv": B}, **SETTINGS})
    finally:
        release.set()
        server.shutdown()
        server.server_close()
    assert status == 503 and "was abandoned" in data["error"]
