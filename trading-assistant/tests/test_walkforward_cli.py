"""Tests for the ``python -m trading_assistant.walkforward`` command."""

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from trading_assistant.backtest import DEFAULT_CASH
from trading_assistant.cli import DISCLAIMER
from trading_assistant.samples import sideways
from trading_assistant.sweep import OVERFIT_WARNING
from trading_assistant.walkforward import format_walk_forward, main, summarize, walk_forward
from trading_assistant.walkforward import CSV_HEADER

SRC_DIR = Path(__file__).resolve().parents[1] / "src"

CLOSES = sideways()  # 150 seeded bars, two decimals, so they survive the CSV round trip exactly
SHORTS, LONGS = [2, 3, 5], [5, 10, 20]
BASE_ARGS = ["--short", "2,3,5", "--long", "5,10,20", "--train", "40", "--test", "20"]


def write_prices(tmp_path, closes=CLOSES, name="prices.csv"):
    path = tmp_path / name
    path.write_text("date,close\n" + "".join(f"2026-01-{i % 28 + 1:02d},{c}\n" for i, c in enumerate(closes)))
    return str(path)


def expected_text(closes=CLOSES, shorts=SHORTS, longs=LONGS, train=40, test=20, **kwargs):
    rows = walk_forward(closes, shorts, longs, train, test, **kwargs)
    return format_walk_forward(rows, summarize(rows)) + "\n"


def run_module(*args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "trading_assistant.walkforward", *args],
        capture_output=True,
        text=True,
        env=env,
    )


# ------------------------------------------------------------ output == format_walk_forward


def test_output_matches_format_walk_forward(tmp_path, capsys):
    assert main([write_prices(tmp_path), *BASE_ARGS]) == 0
    captured = capsys.readouterr()
    assert captured.out == expected_text()
    assert captured.err == ""


def test_output_with_step_cash_and_fees_matches_format_walk_forward(tmp_path, capsys):
    args = [*BASE_ARGS, "--step", "10", "--cash", "5000", "--fee", "1", "--fee-pct", "0.1"]
    assert main([write_prices(tmp_path), *args]) == 0
    assert capsys.readouterr().out == expected_text(step=10, cash=5000.0, fee=1.0, fee_pct=0.1)


def test_default_step_is_test(tmp_path, capsys):
    path = write_prices(tmp_path)
    assert main([path, *BASE_ARGS]) == 0
    default = capsys.readouterr().out
    assert main([path, *BASE_ARGS, "--step", "20"]) == 0
    assert capsys.readouterr().out == default


def test_default_cash_and_fees(tmp_path, capsys):
    assert main([write_prices(tmp_path), *BASE_ARGS]) == 0
    assert capsys.readouterr().out == expected_text(cash=DEFAULT_CASH, fee=0.0, fee_pct=0.0)


def test_output_ends_with_overfit_line_and_disclaimer(tmp_path, capsys):
    assert main([write_prices(tmp_path), *BASE_ARGS]) == 0
    assert capsys.readouterr().out.splitlines()[-2:] == [OVERFIT_WARNING, DISCLAIMER]


def test_exactly_one_window(tmp_path, capsys):
    # 60 bars, train 40 + test 20: one window, bars 0-39 and 40-59.
    path = write_prices(tmp_path, CLOSES[:60])
    assert main([path, *BASE_ARGS]) == 0
    out = capsys.readouterr().out
    assert out == expected_text(closes=CLOSES[:60])
    assert out.startswith("Walk-forward: 1 window;")
    assert out.splitlines()[2].split()[:3] == ["1", "0-39", "40-59"]


# ------------------------------------------------------------------- usage errors, exit 2


@pytest.mark.parametrize(
    "args, message",
    [
        (["--long", "5,10", "--train", "40", "--test", "20"], "the following arguments are required: --short"),
        (["--short", "2", "--train", "40", "--test", "20"], "the following arguments are required: --long"),
        (["--short", "2", "--long", "5", "--test", "20"], "the following arguments are required: --train"),
        (["--short", "2", "--long", "5", "--train", "40"], "the following arguments are required: --test"),
        (["--short", "2,x", "--long", "5", "--train", "40", "--test", "20"], "is not a comma list of positive integers"),
        (["--short", "0", "--long", "5", "--train", "40", "--test", "20"], "is not a comma list of positive integers"),
        (["--short", "5", "--long", "5", "--train", "40", "--test", "20"], "no (short, long) pair with short < long"),
        (["--short", "2", "--long", "5", "--train", "0", "--test", "20"], "--train must be at least 1"),
        (["--short", "2", "--long", "5", "--train", "40", "--test", "0"], "--test must be at least 1"),
        (["--short", "2", "--long", "5", "--train", "40", "--test", "20", "--step", "0"], "--step must be at least 1"),
        (["--short", "2", "--long", "5", "--train", "-3", "--test", "20"], "--train must be at least 1"),
        (["--short", "2", "--long", "5", "--train", "4.5", "--test", "20"], "argument --train: invalid int value"),
        (["--short", "2", "--long", "5", "--train", "40", "--test", "x"], "argument --test: invalid int value"),
        (["--short", "2", "--long", "5", "--train", "40", "--test", "20", "--cash", "0"], "--cash must be positive"),
        (["--short", "2", "--long", "5", "--train", "40", "--test", "20", "--fee", "-1"], "--fee must not be negative"),
        (
            ["--short", "2", "--long", "5", "--train", "40", "--test", "20", "--fee-pct", "100"],
            "--fee-pct must be between 0 and 100",
        ),
    ],
)
def test_usage_errors_exit_2(tmp_path, capsys, args, message):
    with pytest.raises(SystemExit) as info:
        main([write_prices(tmp_path), *args])
    assert info.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage:" in captured.err
    assert message in captured.err


def test_no_file_argument_exit_2(capsys):
    with pytest.raises(SystemExit) as info:
        main(BASE_ARGS)
    assert info.value.code == 2
    assert "the following arguments are required: csv_path" in capsys.readouterr().err


def test_help_exit_0_mentions_disclaimer(capsys):
    with pytest.raises(SystemExit) as info:
        main(["--help"])
    assert info.value.code == 0
    out = capsys.readouterr().out
    assert "--train N" in out and "--test N" in out and "--step N" in out
    assert DISCLAIMER in out


# -------------------------------------------------------------------- data errors, exit 1


def _data_error(capsys, argv):
    assert main(argv) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("\n") == 1  # one line
    return captured.err


def test_missing_file_exit_1(tmp_path, capsys):
    err = _data_error(capsys, [str(tmp_path / "missing.csv"), *BASE_ARGS])
    assert err.startswith("Error: ")
    assert "missing.csv" in err


def test_no_close_column_exit_1(tmp_path, capsys):
    path = tmp_path / "noclose.csv"
    path.write_text("date,price\n2026-01-02,1\n")
    assert "no 'close' column" in _data_error(capsys, [str(path), *BASE_ARGS])


def test_bad_number_exit_1(tmp_path, capsys):
    path = tmp_path / "bad.csv"
    path.write_text("date,close\n2026-01-02,1\n2026-01-03,abc\n")
    assert _data_error(capsys, [str(path), *BASE_ARGS]).startswith("Error: ")


def test_no_rows_exit_1(tmp_path, capsys):
    path = tmp_path / "empty.csv"
    path.write_text("date,close\n")
    assert _data_error(capsys, [str(path), *BASE_ARGS]) == "No price rows found.\n"


def test_too_few_bars_for_one_window_exit_1(tmp_path, capsys):
    # 59 bars, train 40 + test 20 needs 60.
    err = _data_error(capsys, [write_prices(tmp_path, CLOSES[:59]), *BASE_ARGS])
    assert err == "Error: not enough prices for a walk-forward window: 59 bars, need at least train + test = 60\n"


def test_non_positive_price_reports_file_bar_number(tmp_path, capsys):
    closes = list(CLOSES)
    closes[45] = -1.0  # inside the first test block (bars 40-59)
    err = _data_error(capsys, [write_prices(tmp_path, closes), *BASE_ARGS])
    assert err == "Error: bar 45: price must be positive, got -1.0\n"


def test_non_positive_price_in_bars_no_window_uses_is_still_an_error(tmp_path, capsys):
    # 150 bars, train 40, test 20: the last window's test block ends at bar 139,
    # so bar 145 is never used, but a broken file is still rejected.
    closes = list(CLOSES)
    closes[145] = 0.0
    err = _data_error(capsys, [write_prices(tmp_path, closes), *BASE_ARGS])
    assert err == "Error: bar 145: price must be positive, got 0.0\n"


# ------------------------------------------------------ python -m: exit codes, no traceback


def test_python_m_success_matches_format_walk_forward(tmp_path):
    result = run_module(write_prices(tmp_path), *BASE_ARGS)
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected_text()
    assert result.stderr == ""


@pytest.mark.parametrize(
    "case, extra, code",
    [
        ("missing file", ["--short", "2", "--long", "5", "--train", "40", "--test", "20"], 1),
        ("too few bars", ["--short", "2", "--long", "5", "--train", "400", "--test", "20"], 1),
        ("bad price", ["--short", "2", "--long", "5", "--train", "40", "--test", "20"], 1),
        ("no pair", ["--short", "9", "--long", "5", "--train", "40", "--test", "20"], 2),
        ("zero test", ["--short", "2", "--long", "5", "--train", "40", "--test", "0"], 2),
        ("bad int", ["--short", "2", "--long", "5", "--train", "forty", "--test", "20"], 2),
        ("bad cost", ["--short", "2", "--long", "5", "--train", "40", "--test", "20", "--fee-pct", "-1"], 2),
    ],
)
def test_python_m_errors_exit_code_and_no_traceback(tmp_path, case, extra, code):
    if case == "missing file":
        path = str(tmp_path / "missing.csv")
    elif case == "bad price":
        closes = list(CLOSES)
        closes[3] = -5.0
        path = write_prices(tmp_path, closes)
    else:
        path = write_prices(tmp_path)
    result = run_module(path, *extra)
    assert result.returncode == code
    assert result.stdout == ""
    assert "Traceback" not in result.stderr
    assert result.stderr.strip()  # says what went wrong
    if code == 1:
        assert result.stderr.count("\n") == 1
    else:
        assert "usage:" in result.stderr


# ------------------------------------------------------------------------------ --json


def expected_data(closes=CLOSES, shorts=SHORTS, longs=LONGS, train=40, test=20, **kwargs):
    rows = walk_forward(closes, shorts, longs, train, test, **kwargs)
    return {"windows": rows, "summary": summarize(rows), "overfit_warning": OVERFIT_WARNING, "disclaimer": DISCLAIMER}


def test_json_matches_walk_forward_and_summarize(tmp_path, capsys):
    assert main([write_prices(tmp_path), *BASE_ARGS, "--json"]) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert list(data) == ["windows", "summary", "overfit_warning", "disclaimer"]
    assert data == expected_data()
    assert captured.err == ""


def test_json_with_step_cash_and_fees_matches(tmp_path, capsys):
    args = [*BASE_ARGS, "--step", "10", "--cash", "5000", "--fee", "1", "--fee-pct", "0.1", "--json"]
    assert main([write_prices(tmp_path), *args]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data == expected_data(step=10, cash=5000.0, fee=1.0, fee_pct=0.1)
    assert data["summary"]["test_blocks_contiguous"] is False


def test_json_is_the_only_output(tmp_path, capsys):
    assert main([write_prices(tmp_path), *BASE_ARGS, "--json"]) == 0
    out = capsys.readouterr().out
    json.loads(out)  # the whole of stdout is one JSON object
    assert json.loads(out)["disclaimer"] == DISCLAIMER
    assert json.loads(out)["overfit_warning"] == OVERFIT_WARNING
    assert "Walk-forward:" not in out


def test_json_one_window(tmp_path, capsys):
    assert main([write_prices(tmp_path, CLOSES[:60]), *BASE_ARGS, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data == expected_data(closes=CLOSES[:60])
    assert [w["window"] for w in data["windows"]] == [1]
    assert data["summary"]["windows"] == 1


def test_json_data_errors_are_reported_as_without_json(tmp_path, capsys):
    path = write_prices(tmp_path, CLOSES[:59])
    assert main([path, *BASE_ARGS]) == 1
    plain = capsys.readouterr()
    assert main([path, *BASE_ARGS, "--json"]) == 1
    with_json = capsys.readouterr()
    assert with_json.out == plain.out == ""
    assert with_json.err == plain.err != ""


def test_json_usage_errors_exit_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as info:
        main([write_prices(tmp_path), "--short", "2", "--long", "5", "--train", "40", "--test", "0", "--json"])
    assert info.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--test must be at least 1" in captured.err


# ------------------------------------------------------------------------------- --csv


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.reader(f))


def expected_csv(rows):
    out = [list(CSV_HEADER)]
    for r in rows:
        out.append(
            [
                str(r["window"]),
                str(r["train_start"]),
                str(r["train_end"]),
                str(r["test_start"]),
                str(r["test_end"]),
                str(r["short"]),
                str(r["long"]),
                f"{r['train_return_pct']:.4f}",
                f"{r['test_return_pct']:.4f}",
                f"{r['test_max_drawdown_pct']:.4f}",
                str(r["test_trades"]),
                f"{r['buy_hold_return_pct']:.4f}",
            ]
        )
    return out


def test_csv_header():
    assert CSV_HEADER == (
        "window",
        "train_start",
        "train_end",
        "test_start",
        "test_end",
        "short",
        "long",
        "train_return_pct",
        "test_return_pct",
        "test_max_drawdown_pct",
        "test_trades",
        "buy_hold_return_pct",
    )


def test_csv_rows_match_walk_forward(tmp_path, capsys):
    out_csv = tmp_path / "windows.csv"
    args = [*BASE_ARGS, "--fee", "1", "--fee-pct", "0.1", "--csv", str(out_csv)]
    assert main([write_prices(tmp_path), *args]) == 0
    capsys.readouterr()
    rows = walk_forward(CLOSES, SHORTS, LONGS, 40, 20, fee=1.0, fee_pct=0.1)
    assert len(rows) > 1
    assert read_csv(out_csv) == expected_csv(rows)


def test_csv_still_prints_the_text_with_a_wrote_line(tmp_path, capsys):
    out_csv = tmp_path / "windows.csv"
    assert main([write_prices(tmp_path), *BASE_ARGS, "--csv", str(out_csv)]) == 0
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    rows = walk_forward(CLOSES, SHORTS, LONGS, 40, 20)
    wrote = f"Wrote {len(rows)} rows to {out_csv}"
    # Same text as without --csv, plus the "Wrote" line just before the overfit line.
    assert lines[-3:] == [wrote, OVERFIT_WARNING, DISCLAIMER]
    assert [line for line in lines if line != wrote] == expected_text().splitlines()
    assert captured.err == ""


def test_csv_with_json_writes_the_file_and_prints_only_json(tmp_path, capsys):
    out_csv = tmp_path / "windows.csv"
    assert main([write_prices(tmp_path), *BASE_ARGS, "--json", "--csv", str(out_csv)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data == expected_data()
    assert read_csv(out_csv) == expected_csv(data["windows"])


def test_csv_refuses_to_overwrite_input(tmp_path, capsys):
    path = write_prices(tmp_path)
    before = Path(path).read_text()
    assert main([path, *BASE_ARGS, "--csv", path]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"Error: --csv refuses to overwrite the input file {path}\n"
    assert Path(path).read_text() == before


def test_csv_refuses_input_under_another_name(tmp_path, capsys):
    path = write_prices(tmp_path)
    before = Path(path).read_text()
    link = tmp_path / "link.csv"
    link.symlink_to(path)
    for other in (str(tmp_path / "." / "prices.csv"), str(link)):
        assert main([path, *BASE_ARGS, "--csv", other]) == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "refuses to overwrite the input file" in captured.err
    assert Path(path).read_text() == before


def test_csv_refuses_to_overwrite_input_with_json(tmp_path, capsys):
    path = write_prices(tmp_path)
    assert main([path, *BASE_ARGS, "--json", "--csv", path]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "refuses to overwrite the input file" in captured.err


def test_csv_unwritable_exit_1(tmp_path, capsys):
    target = tmp_path / "no_dir" / "out.csv"
    assert main([write_prices(tmp_path), *BASE_ARGS, "--csv", str(target)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(f"Error: cannot write {target}: ")
    assert captured.err.count("\n") == 1
    assert not target.exists()


def test_csv_to_a_folder_exit_1(tmp_path, capsys):
    folder = tmp_path / "folder"
    folder.mkdir()
    assert main([write_prices(tmp_path), *BASE_ARGS, "--json", "--csv", str(folder)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(f"Error: cannot write {folder}: ")


def test_csv_not_written_when_the_data_is_bad(tmp_path, capsys):
    out_csv = tmp_path / "windows.csv"
    assert main([write_prices(tmp_path, CLOSES[:59]), *BASE_ARGS, "--csv", str(out_csv)]) == 1
    assert capsys.readouterr().out == ""
    assert not out_csv.exists()


@pytest.mark.parametrize("name", ["", "   "])
def test_csv_empty_name_exit_2(tmp_path, capsys, name):
    with pytest.raises(SystemExit) as info:
        main([write_prices(tmp_path), *BASE_ARGS, "--csv", name])
    assert info.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--csv needs a file name" in captured.err


def test_python_m_json_and_csv(tmp_path):
    out_csv = tmp_path / "windows.csv"
    result = run_module(write_prices(tmp_path), *BASE_ARGS, "--json", "--csv", str(out_csv))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == expected_data()
    assert read_csv(out_csv) == expected_csv(expected_data()["windows"])


@pytest.mark.parametrize("case", ["same file", "no folder", "empty name", "json bad data"])
def test_python_m_csv_and_json_errors_no_traceback(tmp_path, case):
    path = write_prices(tmp_path)
    extra, code = {
        "same file": (["--csv", path], 1),
        "no folder": (["--csv", str(tmp_path / "no_dir" / "out.csv")], 1),
        "empty name": (["--csv", ""], 2),
        "json bad data": (["--json", "--train", "400"], 1),
    }[case]
    result = run_module(path, *BASE_ARGS, *extra)
    assert result.returncode == code
    assert result.stdout == ""
    assert "Traceback" not in result.stderr
    assert result.stderr.strip()
