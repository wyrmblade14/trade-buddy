"""POST /api/walkforward with ``warmup`` (the command's ``--warmup``).

tests/data/wf_api_before_warmup.json holds the request (tests/data/wf.csv, short 1, long 3, train 12,
test 6, cash 1000) and the raw reply the server sent for it before ``warmup`` existed. A request without
the field, or with false, null or "", must still get exactly those bytes. The warmed-up numbers are worked
out by hand in test_walkforward_warmup.py.
"""

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from trading_assistant.walkforward import main as walkforward_main
from trading_assistant.web import server as web

DATA = Path(__file__).resolve().parent / "data"
WF = str(DATA / "wf.csv")
BEFORE = json.loads((DATA / "wf_api_before_warmup.json").read_text())
MISSING = object()


@pytest.fixture(scope="module")
def post():
    server = web.BacktestServer(("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]

    def post(payload):
        body = json.dumps(payload).encode()
        req = Request(f"http://{host}:{port}/api/walkforward", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urlopen(req, timeout=30) as resp:
                return resp.status, resp.read().decode()
        except HTTPError as exc:
            return exc.code, exc.read().decode()

    yield post
    server.shutdown()
    server.server_close()


def with_warmup(value):
    payload = dict(BEFORE["request"])
    if value is not MISSING:
        payload["warmup"] = value
    return payload


@pytest.mark.parametrize("value", [MISSING, False, None, ""], ids=["no key", "false", "null", "empty string"])
def test_off_gives_exactly_the_old_reply(post, value):
    assert post(with_warmup(value)) == (BEFORE["status"], BEFORE["body"])


def test_on_matches_the_command_json(post, capsys):
    status, body = post(with_warmup(True))
    assert status == 200
    assert body.startswith('{"warmup": true, "windows": [')
    assert walkforward_main([WF, "--short", "1", "--long", "3", "--train", "12", "--test", "6", "--cash", "1000",
                             "--warmup", "--json"]) == 0
    command = json.loads(capsys.readouterr().out)
    reply = json.loads(body)
    assert reply == command and list(reply) == list(command)  # same numbers, same key order
    assert reply["warmup"] is True and reply["windows"][0]["test_return_pct"] == pytest.approx(7.6)


def test_anything_but_true_false_null_or_empty_is_a_400(post):
    for value, shown in [("true", " got 'true'"), ("yes", " got 'yes'"), (1, " got 1"), (0, " got 0"),
                         (1.5, " got 1.5"), ([], ""), ({}, "")]:
        message = "warmup must be true or false" + ("," + shown if shown else "")
        assert post(with_warmup(value)) == (400, json.dumps({"ok": False, "error": message})), value
    # Read before the settings are checked against each other: a bad warmup comes before "no pair".
    status, body = post({**with_warmup("yes"), "short": "5"})
    assert (status, json.loads(body)["error"]) == (400, "warmup must be true or false, got 'yes'")
