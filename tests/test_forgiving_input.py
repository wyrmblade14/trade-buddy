"""Forgiving CSV input: BOM, header capitalisation, spaces around names and
values, any line endings; and helpful messages when the format is wrong.

Every case is checked on the command line path (bytes in a file) and on the
web path (text in the JSON body), which must behave identically.
"""

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from trading_assistant.cli import (
    CSV_EXAMPLE,
    decode_price_bytes,
    load_closes,
    load_price_table,
    main,
    parse_price_text,
)
from trading_assistant.web import server as web

CLEAN = "date,close\n2026-01-02,101.5\n2026-01-05,102.1\n2026-01-06,99\n"
EXPECTED = (["2026-01-02", "2026-01-05", "2026-01-06"], [101.5, 102.1, 99.0])


# --------------------------------------------------------------------------- helpers


@pytest.fixture(scope="module")
def api():
    server = web.BacktestServer(("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]

    def post(payload):
        req = Request(f"http://{host}:{port}/api/backtest", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=10) as resp:
                return resp.status, json.load(resp)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    yield post
    server.shutdown()
    server.server_close()


def write_bytes(tmp_path, data, name="prices.csv"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def cli_error(tmp_path, capsys, data):
    """Run the CLI on the bytes and return (exit code, single stderr line)."""
    path = write_bytes(tmp_path, data)
    code = main([path])
    captured = capsys.readouterr()
    lines = captured.err.splitlines()
    assert captured.out == "" and len(lines) == 1, captured
    return code, lines[0], path


# --------------------------------------------------------------------------- accepted variations


@pytest.mark.parametrize(
    "label, text",
    [
        ("clean", CLEAN),
        ("bom", "\ufeff" + CLEAN),
        ("capitalised header", "Date,Close\n2026-01-02,101.5\n2026-01-05,102.1\n2026-01-06,99\n"),
        ("upper header", "DATE,CLOSE\n2026-01-02,101.5\n2026-01-05,102.1\n2026-01-06,99\n"),
        ("mixed case header", "dAtE,cLoSe\n2026-01-02,101.5\n2026-01-05,102.1\n2026-01-06,99\n"),
        ("spaces around header names", " date , close \n2026-01-02,101.5\n2026-01-05,102.1\n2026-01-06,99\n"),
        ("tabs around header names", "\tdate\t,\tclose\t\n2026-01-02,101.5\n2026-01-05,102.1\n2026-01-06,99\n"),
        ("spaces around values", "date,close\n 2026-01-02 , 101.5 \n2026-01-05 ,  102.1\n  2026-01-06,99   \n"),
        ("crlf line endings", CLEAN.replace("\n", "\r\n")),
        ("cr only line endings", CLEAN.replace("\n", "\r")),
        ("no final newline", CLEAN.rstrip("\n")),
        ("blank lines", "date,close\n\n2026-01-02,101.5\n\n2026-01-05,102.1\n2026-01-06,99\n\n\n"),
        ("all at once", "\ufeff Date , CLOSE \r\n 2026-01-02 , 101.5 \r\n2026-01-05,  102.1\r\n 2026-01-06 ,99\r\n"),
        ("close before date, extra column", "Volume, Close ,DATE\n5,101.5, 2026-01-02\n6, 102.1 ,2026-01-05\n7,99,2026-01-06\n"),
    ],
)
def test_variations_parse_identically_to_clean_input(tmp_path, api, label, text):
    # parser
    assert parse_price_text(text, "CSV") == EXPECTED
    # command line: bytes on disk, UTF-8 with a real BOM where the text starts with one
    path = write_bytes(tmp_path, text.encode("utf-8"))
    assert load_price_table(path) == EXPECTED
    assert load_closes(path) == EXPECTED[1]
    # web: text in the request body
    status, data = api({"source": "csv", "csv": text, "short": 1, "long": 2})
    assert status == 200, data
    assert [row[1] for row in data["rows"]] == EXPECTED[0]
    assert [row[2] for row in data["rows"]] == ["101.50", "102.10", "99.00"]


def test_messy_file_gives_same_report_as_clean_file_on_cli_and_web(tmp_path, capsys, api):
    messy = "\ufeff Date , CLOSE \r\n 2026-01-02 , 101.5 \r\n2026-01-05,  102.1\r\n 2026-01-06 ,99\r\n"
    clean_path = write_bytes(tmp_path, CLEAN.encode(), "clean.csv")
    messy_path = write_bytes(tmp_path, messy.encode("utf-8"), "messy.csv")
    assert main([clean_path, "--short", "1", "--long", "2", "--backtest"]) == 0
    clean_out = capsys.readouterr().out
    assert main([messy_path, "--short", "1", "--long", "2", "--backtest"]) == 0
    assert capsys.readouterr().out == clean_out

    status, data = api({"source": "csv", "csv": messy, "short": 1, "long": 2})
    assert status == 200
    assert data["report"] + [data["disclaimer"]] == clean_out.splitlines()


def test_utf8_bom_bytes_on_disk(tmp_path):
    raw = b"\xef\xbb\xbfdate,close\n2026-01-02,101.5\n"
    assert load_price_table(write_bytes(tmp_path, raw)) == (["2026-01-02"], [101.5])
    assert decode_price_bytes(raw).startswith("date,close")


def test_non_utf8_bytes_in_a_label_do_not_stop_the_numbers(tmp_path):
    raw = b"date,close\ncaf\xe9,101.5\n2026-01-05,102.1\n"  # Latin-1 e-acute, not valid UTF-8
    dates, closes = load_price_table(write_bytes(tmp_path, raw))
    assert closes == [101.5, 102.1]
    assert dates[0] == "caf\u00e9"


def test_date_values_are_stripped_too(tmp_path):
    dates, _ = load_price_table(write_bytes(tmp_path, b"date,close\n  2026-01-02\t,1\n"))
    assert dates == ["2026-01-02"]


def test_header_matching_is_exact_after_normalising():
    # 'close' must be the whole name: 'Close Price' or 'closed' is not the close column.
    with pytest.raises(ValueError, match="found columns: 'Date', 'Close Price'"):
        parse_price_text("Date,Close Price\n2026-01-02,1\n", "CSV")
    with pytest.raises(ValueError, match="found columns: 'closed'"):
        parse_price_text("closed\n1\n", "CSV")


# --------------------------------------------------------------------------- wrong format: what was found + what is expected


WRONG = [
    (
        "no close column",
        b"Date,Price\n2026-01-02,101.5\n",
        "has no 'close' column (found columns: 'Date', 'Price'); expected " + CSV_EXAMPLE,
    ),
    (
        "semicolon separated",
        b"date;close\n2026-01-02;101.5\n",
        "has no 'close' column (found columns: 'date;close'); expected " + CSV_EXAMPLE,
    ),
    (
        "just text",
        b"hello world\n",
        "has no 'close' column (found columns: 'hello world'); expected " + CSV_EXAMPLE,
    ),
    (
        "only a bom",
        "\ufeff".encode("utf-8"),
        "has no 'close' column (the file is empty); expected " + CSV_EXAMPLE,
    ),
    (
        "non numeric value",
        b"date,close\n2026-01-02,101.5\n2026-01-05, 1O2.1 \n",
        "line 3: invalid close value '1O2.1' (expected a number like 101.5)",
    ),
    (
        "blank value",
        b"date,close\n2026-01-02,101.5\n2026-01-05,\n",
        "line 3: invalid close value '' (expected a number like 101.5)",
    ),
    (
        "short row",
        b"date,close\n2026-01-02,101.5\n2026-01-05\n",
        "line 3: invalid close value '' (expected a number like 101.5)",
    ),
    (
        "currency symbol",
        b"date,close\n2026-01-02,$101.5\n",
        "line 2: invalid close value '$101.5' (expected a number like 101.5)",
    ),
    (
        "two close columns",
        b"date,close,Close\n2026-01-02,1,2\n",
        "has more than one 'close' column ('close', 'Close'); expected exactly one",
    ),
]


@pytest.mark.parametrize("label, data, message", WRONG, ids=[w[0] for w in WRONG])
def test_wrong_format_message_on_cli(tmp_path, capsys, label, data, message):
    code, line, path = cli_error(tmp_path, capsys, data)
    assert code == 1
    assert line == f"Error: {path} {message}"
    assert "Traceback" not in line


@pytest.mark.parametrize("label, data, message", WRONG, ids=[w[0] for w in WRONG])
def test_wrong_format_message_on_web(api, label, data, message):
    status, body = api({"source": "csv", "csv": data.decode("utf-8")})
    assert status == 400
    assert body == {"ok": False, "error": f"CSV {message}"}


def test_empty_file_message_on_cli(tmp_path, capsys):
    code, line, path = cli_error(tmp_path, capsys, b"")
    assert code == 1
    assert line == f"Error: {path} has no 'close' column (the file is empty); expected {CSV_EXAMPLE}"


def test_header_only_file_is_no_rows_not_a_format_error(tmp_path, capsys):
    path = write_bytes(tmp_path, b"\xef\xbb\xbf Date , Close \r\n")
    assert load_price_table(path) == ([], [])
    assert main([path]) == 1
    assert capsys.readouterr().err.strip() == "No price rows found."


def test_message_shows_the_value_exactly_as_found_after_stripping():
    with pytest.raises(ValueError) as excinfo:
        parse_price_text("close\n  12..5  \n", "CSV")
    assert str(excinfo.value) == "CSV line 2: invalid close value '12..5' (expected a number like 101.5)"


def test_example_in_message_is_itself_valid_input():
    # The example we show users must parse.
    example = "date,close\n2026-01-02,101.5\n"
    assert "'date,close'" in CSV_EXAMPLE and "'2026-01-02,101.5'" in CSV_EXAMPLE
    assert parse_price_text(example, "CSV") == (["2026-01-02"], [101.5])
