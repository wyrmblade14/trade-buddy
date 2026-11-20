"""Tests for the candle file reader (trading_assistant.data.load_candles).

One test per way a candle file is rejected, each checking the exact error
text, plus the accepted cases: a clean file, the messy-presentation
variations the close-only reader forgives (byte order mark, header case and
spacing, column order, extra columns, line endings, blank lines), and the
content edge cases that are deliberately allowed (flat candle, zero volume,
prices touching the low or high, fractional volume).
"""

import errno
import io
import os

import pytest

from trading_assistant.data import CANDLE_EXAMPLE, Candle, load_candles, parse_candle_text, read_candle_table

CLEAN = (
    "date,open,high,low,close,volume\n"
    "2026-01-02,100.5,103.0,99.5,101.5,12000\n"
    "2026-01-05,101.5,102.5,100.0,102.1,8000\n"
)
EXPECTED = [
    Candle(date="2026-01-02", open=100.5, high=103.0, low=99.5, close=101.5, volume=12000.0),
    Candle(date="2026-01-05", open=101.5, high=102.5, low=100.0, close=102.1, volume=8000.0),
]


def write(tmp_path, text, name="candles.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def rejects(tmp_path, text, message):
    """Assert that the file is rejected with exactly ``message`` (path prefix added)."""
    path = write(tmp_path, text)
    with pytest.raises(ValueError) as excinfo:
        load_candles(path)
    assert str(excinfo.value) == f"{path} {message}"


# --------------------------------------------------------------------------- accepted


def test_valid_file_returns_one_record_per_row(tmp_path):
    candles = load_candles(write(tmp_path, CLEAN))
    assert candles == EXPECTED
    assert all(type(c.date) is str for c in candles)
    assert all(type(v) is float for c in candles for v in (c.open, c.high, c.low, c.close, c.volume))


@pytest.mark.parametrize(
    "label, text",
    [
        ("bom", "\ufeff" + CLEAN),
        ("capitalised header", CLEAN.replace("date,open,high,low,close,volume", "Date,Open,High,Low,Close,Volume")),
        ("upper header", CLEAN.replace("date,open,high,low,close,volume", "DATE,OPEN,HIGH,LOW,CLOSE,VOLUME")),
        ("mixed case header", CLEAN.replace("date,open,high,low,close,volume", "dAtE,oPeN,hIgH,lOw,cLoSe,vOlUmE")),
        ("spaces around header names", CLEAN.replace("date,open,high,low,close,volume", " date , open , high , low , close , volume ")),
        ("tabs around header names", CLEAN.replace("date,open,high,low,close,volume", "\tdate\t,open,high,low,close,\tvolume\t")),
        ("spaces around values", CLEAN.replace("2026-01-02,100.5,103.0,99.5,101.5,12000", " 2026-01-02 , 100.5 ,  103.0,99.5 , 101.5 ,  12000 ")),
        ("crlf line endings", CLEAN.replace("\n", "\r\n")),
        ("cr only line endings", CLEAN.replace("\n", "\r")),
        ("no final newline", CLEAN.rstrip("\n")),
        ("blank lines", "date,open,high,low,close,volume\n\n2026-01-02,100.5,103.0,99.5,101.5,12000\n\n2026-01-05,101.5,102.5,100.0,102.1,8000\n\n\n"),
        (
            "columns reordered with an extra column",
            "Volume,Close,Low,High,Open,Adj Close,Date\n"
            "12000,101.5,99.5,103.0,100.5,101.0,2026-01-02\n"
            "8000,102.1,100.0,102.5,101.5,101.9,2026-01-05\n",
        ),
        (
            "all at once",
            "\ufeff Date , OPEN ,High, low , Close , Volume \r\n"
            " 2026-01-02 , 100.5 , 103.0 ,99.5, 101.5 , 12000 \r\n"
            "2026-01-05,101.5,102.5,100.0,  102.1  ,8000\r\n",
        ),
    ],
)
def test_messy_presentation_parses_identically_to_clean_input(tmp_path, label, text):
    assert parse_candle_text(text, "CSV") == EXPECTED
    assert load_candles(write(tmp_path, text)) == EXPECTED


def test_read_candle_table_reads_an_open_file_object():
    assert read_candle_table(io.StringIO(CLEAN), "CSV") == EXPECTED


def test_non_utf8_bytes_in_a_date_label_do_not_stop_the_numbers(tmp_path):
    raw = b"date,open,high,low,close,volume\ncaf\xe9,100.5,103.0,99.5,101.5,12000\n"  # Latin-1 e-acute
    path = tmp_path / "candles.csv"
    path.write_bytes(raw)
    (candle,) = load_candles(str(path))
    assert candle.date == "caf\u00e9" and candle.close == 101.5


def test_header_only_file_is_empty_not_an_error(tmp_path):
    assert load_candles(write(tmp_path, "date,open,high,low,close,volume\n")) == []


def test_flat_candle_zero_volume_and_prices_touching_the_bounds_are_accepted(tmp_path):
    text = (
        "date,open,high,low,close,volume\n"
        "2026-01-02,100,100,100,100,0\n"  # flat candle, zero volume
        "2026-01-05,103.0,103.0,99.5,99.5,12000\n"  # open == high, close == low
    )
    flat, touching = load_candles(write(tmp_path, text))
    assert flat == Candle("2026-01-02", 100.0, 100.0, 100.0, 100.0, 0.0)
    assert touching == Candle("2026-01-05", 103.0, 103.0, 99.5, 99.5, 12000.0)


def test_fractional_volume_is_accepted(tmp_path):
    # Some feeds (e.g. crypto) report fractional volume, so it is not forced to a whole number.
    (candle,) = load_candles(write(tmp_path, "date,open,high,low,close,volume\n2026-01-02,100,101,99,100,0.25\n"))
    assert candle.volume == 0.25


# --------------------------------------------------------------------------- rejected


def test_rejects_empty_file(tmp_path):
    rejects(tmp_path, "", f"has no candle header (the file is empty); expected {CANDLE_EXAMPLE}")


def test_rejects_file_with_a_missing_column(tmp_path):
    rejects(
        tmp_path,
        "date,open,high,low,close\n2026-01-02,100.5,103.0,99.5,101.5\n",
        "has no 'volume' column (found columns: 'date', 'open', 'high', 'low', 'close'); "
        f"expected {CANDLE_EXAMPLE}",
    )


def test_rejects_file_with_several_missing_columns(tmp_path):
    # A close-only file is fine for the close reader but not a candle file.
    rejects(
        tmp_path,
        "date,close\n2026-01-02,101.5\n",
        f"has no 'open', 'high', 'low', 'volume' columns (found columns: 'date', 'close'); expected {CANDLE_EXAMPLE}",
    )


def test_rejects_file_with_a_duplicated_column(tmp_path):
    rejects(
        tmp_path,
        "date,open,high,low,close,volume,Close\n2026-01-02,100.5,103.0,99.5,101.5,12000,101.6\n",
        "has more than one 'close' column ('close', 'Close'); expected exactly one",
    )


def test_rejects_non_numeric_value_with_line_number_and_column(tmp_path):
    rejects(
        tmp_path,
        "date,open,high,low,close,volume\n"
        "2026-01-02,100.5,103.0,99.5,101.5,12000\n"
        "2026-01-05,101.5,1O2.5,100.0,102.1,8000\n",
        "line 3: invalid high value '1O2.5' (expected a number like 101.5)",
    )


def test_rejects_blank_value_and_short_row(tmp_path):
    rejects(
        tmp_path,
        "date,open,high,low,close,volume\n2026-01-02,100.5,103.0,99.5,101.5\n",
        "line 2: invalid volume value '' (expected a number like 101.5)",
    )


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "1e999"], ids=["nan", "inf", "negative inf", "overflows to inf"])
def test_rejects_non_finite_value(tmp_path, bad):
    rejects(
        tmp_path,
        f"date,open,high,low,close,volume\n2026-01-02,100.5,103.0,99.5,{bad},12000\n",
        f"line 2: invalid close value {bad!r} (expected a finite number)",
    )


@pytest.mark.parametrize("bad, shown", [("0", "0"), ("-99.5", "-99.5")], ids=["zero", "negative"])
def test_rejects_non_positive_price(tmp_path, bad, shown):
    rejects(
        tmp_path,
        f"date,open,high,low,close,volume\n2026-01-02,100.5,103.0,{bad},101.5,12000\n",
        f"line 2: low must be positive, got {shown}",
    )


def test_rejects_negative_volume(tmp_path):
    rejects(
        tmp_path,
        "date,open,high,low,close,volume\n2026-01-02,100.5,103.0,99.5,101.5,-1\n",
        "line 2: volume must not be negative, got -1",
    )


def test_rejects_high_lower_than_low(tmp_path):
    rejects(
        tmp_path,
        "date,open,high,low,close,volume\n2026-01-02,100,99.5,100.5,100,12000\n",
        "line 2: high 99.5 is lower than the low 100.5",
    )


@pytest.mark.parametrize("open_", ["103.5", "99.0"], ids=["above high", "below low"])
def test_rejects_open_outside_the_low_high_range(tmp_path, open_):
    rejects(
        tmp_path,
        f"date,open,high,low,close,volume\n2026-01-02,{open_},103.0,99.5,101.5,12000\n",
        f"line 2: open {open_.rstrip('0').rstrip('.')} is outside the low..high range 99.5..103",
    )


def test_rejects_close_outside_the_low_high_range(tmp_path):
    rejects(
        tmp_path,
        "date,open,high,low,close,volume\n2026-01-02,100.5,103.0,99.5,103.5,12000\n",
        "line 2: close 103.5 is outside the low..high range 99.5..103",
    )


def test_rejects_blank_date(tmp_path):
    rejects(
        tmp_path,
        "date,open,high,low,close,volume\n   ,100.5,103.0,99.5,101.5,12000\n",
        "line 2: missing date (expected a value like 2026-01-02)",
    )


def test_rejects_missing_file_with_unchanged_oserror(tmp_path):
    path = str(tmp_path / "does-not-exist.csv")
    with pytest.raises(FileNotFoundError) as excinfo:
        load_candles(path)
    assert excinfo.value.errno == errno.ENOENT
    assert str(excinfo.value) == f"[Errno {errno.ENOENT}] {os.strerror(errno.ENOENT)}: {path!r}"
