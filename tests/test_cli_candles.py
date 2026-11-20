"""Tests for --candles on the command line and the candle reader's order and
number-format checks.

With --candles the file is read by ``data.load_candles`` and its closes are
analysed exactly like a close-only file's: a candle file whose open, high,
low and close are all equal must give byte-identical output to the close-only
file with the same dates and closes. A problem in the candle file is one
``Error:`` line on stderr with exit code 1; --candles with --resample is a
usage error (exit code 2).
"""

import pytest

from trading_assistant.cli import build_parser, main, validate_args
from trading_assistant.data import CANDLE_EXAMPLE, load_candles

DATES = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
CLOSES = [101.5, 102.1, 99.0, 100.0, 103.0, 104.5]
HEADER = "date,open,high,low,close,volume\n"


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def close_only_file(tmp_path, name="closes.csv"):
    return write(tmp_path, name, "date,close\n" + "".join(f"{d},{c}\n" for d, c in zip(DATES, CLOSES)))


def flat_candle_file(tmp_path, name="flat.csv"):
    """Candle file with open == high == low == close for every bar."""
    return write(tmp_path, name, HEADER + "".join(f"{d},{c},{c},{c},{c},1000\n" for d, c in zip(DATES, CLOSES)))


def real_candle_file(tmp_path, name="candles.csv"):
    """Candle file whose opens, highs and lows differ from the closes."""
    rows = "".join(f"{d},{c - 0.5},{c + 1.0},{c - 1.0},{c},{(i + 1) * 1000}\n" for i, (d, c) in enumerate(zip(DATES, CLOSES)))
    return write(tmp_path, name, HEADER + rows)


def run(argv, capsys):
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --------------------------------------------------------------------------- accepted


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["--chart"],
        ["--backtest"],
        ["--backtest", "--stats", "--chart", "--fee", "1", "--fee-pct", "0.5"],
        ["--backtest", "--strategy", "breakout", "--param", "window=2"],
    ],
    ids=["report", "chart", "backtest", "backtest with stats chart and costs", "other strategy"],
)
def test_flat_candle_file_gives_identical_output_to_close_only_file(tmp_path, capsys, extra):
    argv = ["--short", "2", "--long", "3"] + extra
    assert run([close_only_file(tmp_path)] + argv, capsys) == run([flat_candle_file(tmp_path), "--candles"] + argv, capsys)


def test_flat_candle_file_exports_identical_rows(tmp_path, capsys):
    argv = ["--short", "2", "--long", "3", "--backtest", "--export"]
    code_a, out_a, _ = run([close_only_file(tmp_path), *argv, str(tmp_path / "a.csv")], capsys)
    code_b, out_b, _ = run([flat_candle_file(tmp_path), "--candles", *argv, str(tmp_path / "b.csv")], capsys)
    assert code_a == code_b == 0
    assert (tmp_path / "a.csv").read_text() == (tmp_path / "b.csv").read_text()
    assert out_a.replace("a.csv", "b.csv") == out_b  # only the export file name differs


def test_candle_file_is_analysed_on_its_closes(tmp_path, capsys):
    # The opens, highs and lows differ, but only the closes matter, so the report matches the close-only file.
    argv = ["--short", "2", "--long", "3", "--backtest"]
    assert run([real_candle_file(tmp_path), "--candles"] + argv, capsys) == run([close_only_file(tmp_path)] + argv, capsys)
    code, out, err = run([real_candle_file(tmp_path), "--candles"] + argv, capsys)
    assert code == 0 and err == ""
    assert "Bars:    6" in out and "Last:    104.50" in out


def test_candles_flag_works_with_messy_presentation(tmp_path, capsys):
    messy = "\ufeff Volume , CLOSE ,low,High, Open , Date \r\n" + "".join(
        f" 1000 , {c} ,{c},{c}, {c} , {d} \r\n" for d, c in zip(DATES, CLOSES)
    )
    path = write(tmp_path, "messy.csv", messy)
    argv = ["--short", "2", "--long", "3", "--backtest"]
    assert run([path, "--candles"] + argv, capsys) == run([close_only_file(tmp_path)] + argv, capsys)


def test_help_mentions_candles(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    assert "--candles" in capsys.readouterr().out


def test_without_candles_flag_a_candle_file_is_still_read_as_a_close_file(tmp_path, capsys):
    # A candle file has a 'close' column, so the close-only reader accepts it unchanged.
    code, out, err = run([real_candle_file(tmp_path), "--short", "2", "--long", "3"], capsys)
    assert code == 0 and err == ""
    assert "Last:    104.50" in out


# --------------------------------------------------------------------------- candle file problems: exit 1, one line


PROBLEMS = [
    ("empty file", "", f"has no candle header (the file is empty); expected {CANDLE_EXAMPLE}"),
    (
        "close-only file",
        "date,close\n2026-01-02,101.5\n",
        f"has no 'open', 'high', 'low', 'volume' columns (found columns: 'date', 'close'); expected {CANDLE_EXAMPLE}",
    ),
    (
        "high below low",
        HEADER + "2026-01-02,100,99.5,100.5,100,1000\n",
        "line 2: high 99.5 is lower than the low 100.5",
    ),
    (
        "bad number",
        HEADER + "2026-01-02,100,101,99,100,1000\n2026-01-05,100,101,99,abc,1000\n",
        "line 3: invalid close value 'abc' (expected a number like 101.5)",
    ),
    (
        "dates out of order",
        HEADER + "2026-01-05,100,101,99,100,1000\n2026-01-02,100,101,99,100,1000\n",
        "line 3: date '2026-01-02' is before the previous date '2026-01-05' on line 2 (dates must be in ascending order)",
    ),
    (
        "underscore separator",
        HEADER + "2026-01-02,100,101,99,100,1_000\n",
        "line 2: invalid volume value '1_000' (expected a number like 101.5, without '_' separators)",
    ),
]


@pytest.mark.parametrize("label, text, message", PROBLEMS, ids=[p[0] for p in PROBLEMS])
def test_candle_file_problem_is_one_error_line_and_exit_1(tmp_path, capsys, label, text, message):
    path = write(tmp_path, "bad.csv", text)
    code, out, err = run([path, "--candles", "--short", "2", "--long", "3", "--backtest"], capsys)
    assert code == 1
    assert out == ""
    assert err == f"Error: {path} {message}\n"
    assert "Traceback" not in err


def test_missing_candle_file_is_one_error_line_and_exit_1(tmp_path, capsys):
    path = str(tmp_path / "does-not-exist.csv")
    code, out, err = run([path, "--candles"], capsys)
    assert code == 1 and out == ""
    assert err.splitlines() == [f"Error: [Errno 2] No such file or directory: {path!r}"]


def test_header_only_candle_file_is_no_rows(tmp_path, capsys):
    code, out, err = run([write(tmp_path, "empty.csv", HEADER), "--candles"], capsys)
    assert code == 1 and out == ""
    assert err == "No price rows found.\n"


# --------------------------------------------------------------------------- --candles with --resample: usage error, exit 2


@pytest.mark.parametrize("period", ["weekly", "monthly"])
def test_candles_with_resample_is_a_usage_error(tmp_path, capsys, period):
    path = flat_candle_file(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        main([path, "--candles", "--resample", period])
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines()[-1] == "trading_assistant.cli: error: --candles cannot be combined with --resample yet"
    assert "Traceback" not in captured.err


def test_candles_with_resample_is_rejected_before_the_file_is_read(tmp_path, capsys):
    # Usage errors come first: the (missing) file is never opened.
    with pytest.raises(SystemExit) as excinfo:
        main([str(tmp_path / "nope.csv"), "--candles", "--resample", "weekly"])
    assert excinfo.value.code == 2
    assert "--candles cannot be combined with --resample yet" in capsys.readouterr().err


def test_validate_args_rejects_candles_with_resample(capsys):
    parser = build_parser()
    args = parser.parse_args(["p.csv", "--candles", "--resample", "monthly"])
    with pytest.raises(SystemExit) as excinfo:
        validate_args(parser, args)
    assert excinfo.value.code == 2
    assert "--candles cannot be combined with --resample yet" in capsys.readouterr().err


def test_resample_without_candles_still_works(tmp_path, capsys):
    code, out, err = run([close_only_file(tmp_path), "--resample", "weekly", "--short", "1", "--long", "2"], capsys)
    assert code == 0 and err == ""
    assert "Bars:    2" in out  # 2026-01-02 (week 1) and 2026-01-05..09 (week 2)


# --------------------------------------------------------------------------- reader: date order and number format


def rejects(tmp_path, text, message):
    path = write(tmp_path, "candles.csv", text)
    with pytest.raises(ValueError) as excinfo:
        load_candles(path)
    assert str(excinfo.value) == f"{path} {message}"


def test_reader_rejects_date_before_the_previous_one(tmp_path):
    rejects(
        tmp_path,
        HEADER + "2026-01-02,100,101,99,100,1000\n2026-01-05,100,101,99,100,1000\n2026-01-04,100,101,99,100,1000\n",
        "line 4: date '2026-01-04' is before the previous date '2026-01-05' on line 3 (dates must be in ascending order)",
    )


def test_reader_rejects_repeated_date(tmp_path):
    rejects(
        tmp_path,
        HEADER + "2026-01-02,100,101,99,100,1000\n2026-01-02,100,101,99,100,1000\n",
        "line 3: date '2026-01-02' repeats the date on line 2",
    )


def test_reader_rejects_repeated_date_even_with_different_spacing(tmp_path):
    rejects(
        tmp_path,
        HEADER + "2026-01-02,100,101,99,100,1000\n 2026-01-02 ,100,101,99,100,1000\n",
        "line 3: date '2026-01-02' repeats the date on line 2",
    )


def test_reader_rejects_repeat_of_a_date_further_back_as_out_of_order(tmp_path):
    # Only the previous row is compared; an older date reappearing is "before the previous date".
    rejects(
        tmp_path,
        HEADER + "2026-01-02,100,101,99,100,1000\n2026-01-05,100,101,99,100,1000\n2026-01-02,100,101,99,100,1000\n",
        "line 4: date '2026-01-02' is before the previous date '2026-01-05' on line 3 (dates must be in ascending order)",
    )


@pytest.mark.parametrize(
    "column, row",
    [
        ("open", "2026-01-02,1_00,101,99,100,1000"),
        ("high", "2026-01-02,100,1_01,99,100,1000"),
        ("low", "2026-01-02,100,101,9_9,100,1000"),
        ("close", "2026-01-02,100,101,99,1_00,1000"),
        ("volume", "2026-01-02,100,101,99,100,1_000"),
    ],
)
def test_reader_rejects_underscore_separators_in_every_number_column(tmp_path, column, row):
    value = row.split(",")[["date", "open", "high", "low", "close", "volume"].index(column)]
    rejects(tmp_path, HEADER + row + "\n", f"line 2: invalid {column} value {value!r} (expected a number like 101.5, without '_' separators)")


def test_reader_rejects_underscore_separator_with_the_right_line_number(tmp_path):
    rejects(
        tmp_path,
        HEADER + "2026-01-02,100,101,99,100,1000\n2026-01-05,100,101,99,100,1_000\n",
        "line 3: invalid volume value '1_000' (expected a number like 101.5, without '_' separators)",
    )


def test_reader_rejects_underscore_value_that_is_not_a_number_as_plain_invalid(tmp_path):
    # 'a_b' never was a number, so it gets the ordinary message, not the separator hint.
    rejects(
        tmp_path,
        HEADER + "2026-01-02,100,101,99,100,a_b\n",
        "line 2: invalid volume value 'a_b' (expected a number like 101.5)",
    )


def test_reader_still_accepts_ascending_dates_and_plain_numbers(tmp_path):
    path = write(tmp_path, "ok.csv", HEADER + "2026-01-02,100,101,99,100,1000\n2026-01-05,100,101,99,100,1e3\n2026-01-06,100,101,99,100,2000.5\n")
    candles = load_candles(path)
    assert [c.date for c in candles] == ["2026-01-02", "2026-01-05", "2026-01-06"]
    assert [c.volume for c in candles] == [1000.0, 1000.0, 2000.5]
