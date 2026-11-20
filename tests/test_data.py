"""Tests for the price CSV reader (trading_assistant.data).

One test per way ``load_price_table`` rejects a file, each checking the exact
error text, plus one valid file. The rejection paths are the four ValueError
raise sites in ``parse_price_text`` and the OSError that ``load_price_table``
lets through unchanged when the file cannot be opened.
"""

import errno
import os

import pytest

from trading_assistant.data import CSV_EXAMPLE, load_price_table


def write(tmp_path, text, name="prices.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------- valid file


def test_valid_file_returns_dates_and_closes(tmp_path):
    path = write(tmp_path, "date,close\n2026-01-02,101.5\n2026-01-05,102.1\n2026-01-06,99\n")
    dates, closes = load_price_table(path)
    assert dates == ["2026-01-02", "2026-01-05", "2026-01-06"]
    assert closes == [101.5, 102.1, 99.0]
    assert all(type(c) is float for c in closes)


# --------------------------------------------------------------------------- rejected files


def test_rejects_empty_file(tmp_path):
    path = write(tmp_path, "")
    with pytest.raises(ValueError) as excinfo:
        load_price_table(path)
    assert str(excinfo.value) == f"{path} has no 'close' column (the file is empty); expected {CSV_EXAMPLE}"


def test_rejects_file_without_close_column(tmp_path):
    path = write(tmp_path, "date,price\n2026-01-02,101.5\n")
    with pytest.raises(ValueError) as excinfo:
        load_price_table(path)
    assert (
        str(excinfo.value)
        == f"{path} has no 'close' column (found columns: 'date', 'price'); expected {CSV_EXAMPLE}"
    )


def test_rejects_file_with_more_than_one_close_column(tmp_path):
    path = write(tmp_path, "date,close,Close\n2026-01-02,101.5,101.6\n")
    with pytest.raises(ValueError) as excinfo:
        load_price_table(path)
    assert str(excinfo.value) == f"{path} has more than one 'close' column ('close', 'Close'); expected exactly one"


def test_rejects_file_with_non_numeric_close_value(tmp_path):
    path = write(tmp_path, "date,close\n2026-01-02,101.5\n2026-01-05,abc\n")
    with pytest.raises(ValueError) as excinfo:
        load_price_table(path)
    # Line numbers are 1-based and count the header line, so the bad row is line 3.
    assert str(excinfo.value) == f"{path} line 3: invalid close value 'abc' (expected a number like 101.5)"


def test_rejects_missing_file_with_unchanged_oserror(tmp_path):
    path = str(tmp_path / "does-not-exist.csv")
    with pytest.raises(FileNotFoundError) as excinfo:
        load_price_table(path)
    assert excinfo.value.errno == errno.ENOENT
    assert excinfo.value.filename == path
    assert str(excinfo.value) == f"[Errno {errno.ENOENT}] {os.strerror(errno.ENOENT)}: {path!r}"
