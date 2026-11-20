"""--scan FOLDER: combined scores for every .csv file directly inside a folder.

The price series are the hand-worked 60-bar series from test_combined_score.py,
so the expected parts and scores are known from that file's working.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from trading_assistant import scan
from trading_assistant.cli import DISCLAIMER, _scan_requested, build_parser, main

SRC_DIR = Path(__file__).resolve().parents[1] / "src"

RISE_FLAT_JUMP = [100.0 + i for i in range(50)] + [149.0] * 9 + [155.0]  # score -2: +1 -1 -1 -1
MIRROR = [300.0 - c for c in RISE_FLAT_JUMP]  # score +2: -1 +1 +1 +1
RISE_LONG_FALL = [100.0 + i for i in range(43)] + [141.0 - i for i in range(17)]  # +1: +1 +1 -1 0
FLAT_JUMP = [100.0] * 59 + [110.0]  # 0: +1 -1 +1 -1
FLAT_DROP = [100.0] * 59 + [90.0]  # 0: -1 +1 -1 +1
RISE_DROP = [100.0 + i for i in range(59)] + [140.0]  # 0: +1 0 -1 0


@pytest.fixture(autouse=True)
def no_config_env(monkeypatch):
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)


def write_prices(path, closes):
    path.write_text("date,close\n" + "".join(f"2026-{i // 28 + 1:02d}-{i % 28 + 1:02d},{c}\n" for i, c in enumerate(closes)))


def run(argv, capsys):
    code = main(argv)
    out, err = capsys.readouterr()
    return code, out.splitlines(), err


def usage_error(argv, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    out, err = capsys.readouterr()
    assert excinfo.value.code == 2
    assert out == ""
    assert "Traceback" not in err
    return err.strip().splitlines()[-1]


# --------------------------------------------------------------------------- table and ordering


def test_table_highest_score_first_and_ties_in_name_order(tmp_path, capsys):
    write_prices(tmp_path / "DOWN.csv", RISE_FLAT_JUMP)
    write_prices(tmp_path / "UP.csv", MIRROR)
    write_prices(tmp_path / "LOW.csv", RISE_LONG_FALL)
    # three files scoring 0, written out of name order
    write_prices(tmp_path / "zeta.csv", FLAT_JUMP)
    write_prices(tmp_path / "Alpha.csv", FLAT_DROP)
    write_prices(tmp_path / "mid.csv", RISE_DROP)
    code, out, err = run(["--scan", str(tmp_path)], capsys)
    assert code == 0 and err == ""
    assert out == [
        f"Scan:    {tmp_path}, 6 scored, 0 skipped",
        "Symbol  Bars  Score  Crossover  RSI  MACD  Bollinger",
        "UP        60     +2         -1   +1    +1         +1",
        "LOW       60     +1         +1   +1    -1          0",
        "Alpha     60      0         -1   +1    -1         +1",
        "mid       60      0         +1    0    -1          0",
        "zeta      60      0         +1   -1    +1         -1",
        "DOWN      60     -2         +1   -1    -1         -1",
        DISCLAIMER,
    ]


def test_only_csv_files_directly_inside_the_folder(tmp_path, capsys):
    write_prices(tmp_path / "AAA.csv", FLAT_JUMP)
    write_prices(tmp_path / "BBB.CSV", FLAT_DROP)  # capital extension still counts, symbol BBB
    (tmp_path / "sub").mkdir()
    write_prices(tmp_path / "sub" / "INNER.csv", MIRROR)  # in a subfolder: ignored
    (tmp_path / "folder.csv").mkdir()  # a folder named like a CSV file: ignored
    (tmp_path / "notes.txt").write_text("not prices")
    (tmp_path / "prices.json").write_text("{}")
    (tmp_path / "old.csv.bak").write_text("date,close\nx,abc\n")
    (tmp_path / "README").write_text("hello")
    code, out, _ = run(["--scan", str(tmp_path)], capsys)
    assert code == 0
    assert out[0] == f"Scan:    {tmp_path}, 2 scored, 0 skipped"
    assert [line.split()[0] for line in out[2:4]] == ["AAA", "BBB"]
    assert len(out) == 5 and out[-1] == DISCLAIMER
    assert not any("INNER" in line or "folder" in line or "notes" in line for line in out)


# --------------------------------------------------------------------------- skipped files


def test_bad_files_are_skipped_and_listed_after_the_table(tmp_path, capsys):
    write_prices(tmp_path / "good.csv", MIRROR)
    (tmp_path / "badnum.csv").write_text("date,close\n2026-01-01,10\n2026-01-02,abc\n")
    (tmp_path / "noclose.csv").write_text("date,price\n2026-01-01,10\n")
    (tmp_path / "empty.csv").write_text("")
    (tmp_path / "header.csv").write_text("date,close\n")
    code, out, err = run(["--scan", str(tmp_path)], capsys)
    assert code == 0 and err == ""
    assert out[0] == f"Scan:    {tmp_path}, 1 scored, 4 skipped"
    assert out[2] == "good      60     +2         -1   +1    +1         +1"
    assert out[3] == "Skipped: 4"
    skipped = out[4:8]
    assert skipped == [
        "  badnum.csv line 3: invalid close value 'abc' (expected a number like 101.5)",
        "  empty.csv has no 'close' column (the file is empty); expected a header row like "
        "'date,close' followed by rows like '2026-01-02,101.5'",
        "  header.csv: no price rows found",
        "  noclose.csv has no 'close' column (found columns: 'date', 'price'); expected a header row like "
        "'date,close' followed by rows like '2026-01-02,101.5'",
    ]
    assert out[8] == DISCLAIMER and len(out) == 9


def test_a_file_that_cannot_be_opened_is_skipped(tmp_path, capsys, monkeypatch):
    write_prices(tmp_path / "good.csv", FLAT_JUMP)
    write_prices(tmp_path / "locked.csv", FLAT_JUMP)
    real_open = open

    def fake_open(path, *args, **kwargs):
        if os.path.basename(path) == "locked.csv":
            raise PermissionError(13, "Permission denied", path)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(scan, "open", fake_open, raising=False)
    code, out, _ = run(["--scan", str(tmp_path)], capsys)
    assert code == 0
    assert out[0] == f"Scan:    {tmp_path}, 1 scored, 1 skipped"
    assert "  locked.csv: cannot read the file (Permission denied)" in out


def test_skip_reasons_are_one_line(tmp_path, capsys):
    write_prices(tmp_path / "good.csv", FLAT_JUMP)
    # a quoted header holding a line break still gives a one-line reason
    (tmp_path / "odd.csv").write_text('"da\nte",price\nx,1\n')
    code, out, _ = run(["--scan", str(tmp_path)], capsys)
    assert code == 0
    reason = out[out.index("Skipped: 1") + 1]
    assert reason.startswith("  odd.csv has no 'close' column")
    assert out[-1] == DISCLAIMER


def test_too_short_history_is_scored_zero_not_skipped(tmp_path, capsys):
    # like combined_score: a part with no value yet counts as 0
    write_prices(tmp_path / "tiny.csv", [1.0, 2.0, 3.0])
    code, out, _ = run(["--scan", str(tmp_path)], capsys)
    assert code == 0
    assert out[2] == "tiny       3      0          0    0     0          0"


# --------------------------------------------------------------------------- windows follow the flags


def test_short_long_and_rsi_period_are_followed(tmp_path, capsys):
    # RISE_DROP: closes 100..158 then 140.
    # Defaults: SMA20 148.55 > SMA50 134.12 -> +1, RSI14 41.935 -> 0, MACD -1, Bollinger 0 = 0.
    # --short 2 --long 5: SMA2 (158 + 140)/2 = 149 < SMA5 (155+156+157+158+140)/5 = 153.2 -> -1.
    # --rsi-period 2: gain 1, loss 0 up to the drop, then gain 1/2, loss 18/2 = 9,
    #   RSI = 100 * 0.5 / 9.5 = 5.263, under 30 -> +1. MACD and Bollinger keep their defaults.
    write_prices(tmp_path / "X.csv", RISE_DROP)
    _, out, _ = run(["--scan", str(tmp_path)], capsys)
    assert out[2] == "X         60      0         +1    0    -1          0"
    _, out, _ = run(["--scan", str(tmp_path), "--short", "2", "--long", "5", "--rsi-period", "2"], capsys)
    assert out[2] == "X         60     -1         -1   +1    -1          0"


def test_config_file_windows_apply_and_flags_win(tmp_path, capsys):
    folder = tmp_path / "prices"
    folder.mkdir()
    write_prices(folder / "X.csv", RISE_DROP)
    config = tmp_path / "settings.ini"
    config.write_text("[cli]\nshort = 2\nlong = 5\nrsi_period = 2\ncash = 500\n")  # cash is ignored
    _, out, _ = run(["--scan", str(folder), "--config", str(config)], capsys)
    assert out[2] == "X         60     -1         -1   +1    -1          0"
    # flags written on the command line win over the file: back to 20/50/14
    argv = ["--scan", str(folder), "--config", str(config), "--short", "20", "--long", "50", "--rsi-period", "14"]
    _, out, _ = run(argv, capsys)
    assert out[2] == "X         60      0         +1    0    -1          0"


def test_bad_config_file_is_a_data_error(tmp_path, capsys):
    write_prices(tmp_path / "X.csv", RISE_DROP)
    config = tmp_path / "bad.ini"
    config.write_text("[cli]\nnope = 1\n")
    code, out, err = run(["--scan", str(tmp_path), "--config", str(config)], capsys)
    assert code == 1 and out == []
    assert err.startswith("Error:") and len(err.strip().splitlines()) == 1


# --------------------------------------------------------------------------- folder problems: exit 1


def one_error_line(argv, capsys):
    code, out, err = run(argv, capsys)
    assert code == 1
    assert out == []
    lines = err.strip().splitlines()
    assert len(lines) == 1 and "Traceback" not in err
    return lines[0]


def test_missing_folder(tmp_path, capsys):
    missing = tmp_path / "nope"
    assert one_error_line(["--scan", str(missing)], capsys) == f"Error: scan folder {missing} does not exist"


def test_a_file_instead_of_a_folder(tmp_path, capsys):
    path = tmp_path / "p.csv"
    write_prices(path, FLAT_JUMP)
    assert one_error_line(["--scan", str(path)], capsys) == f"Error: scan folder {path} is not a folder"


def test_folder_without_csv_files(tmp_path, capsys):
    (tmp_path / "notes.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    write_prices(tmp_path / "sub" / "deep.csv", FLAT_JUMP)
    assert one_error_line(["--scan", str(tmp_path)], capsys) == f"Error: no .csv files directly inside {tmp_path}"


def test_empty_folder(tmp_path, capsys):
    assert one_error_line(["--scan", str(tmp_path)], capsys) == f"Error: no .csv files directly inside {tmp_path}"


def test_no_file_could_be_scored(tmp_path, capsys):
    (tmp_path / "a.csv").write_text("date,close\nx,abc\n")
    (tmp_path / "b.csv").write_text("date,price\nx,1\n")
    assert one_error_line(["--scan", str(tmp_path)], capsys) == (
        f"Error: none of the 2 .csv files in {tmp_path} could be scored (2 skipped)"
    )


def test_unreadable_folder(tmp_path, capsys, monkeypatch):
    def refuse(path):
        raise PermissionError(13, "Permission denied", path)

    monkeypatch.setattr(scan.os, "listdir", refuse)
    assert one_error_line(["--scan", str(tmp_path)], capsys) == (
        f"Error: cannot read scan folder {tmp_path}: Permission denied"
    )


# --------------------------------------------------------------------------- usage mistakes: exit 2


def test_scan_with_a_price_file_is_a_usage_error(tmp_path, capsys):
    path = tmp_path / "p.csv"
    write_prices(path, FLAT_JUMP)
    message = usage_error([str(path), "--scan", str(tmp_path)], capsys)
    assert message.endswith(f"--scan cannot be combined with a price file (got {path})")


@pytest.mark.parametrize(
    "extra, flag",
    [
        (["--backtest"], "--backtest"),
        (["--cash", "500"], "--cash"),
        (["--fee", "1"], "--fee"),
        (["--fee-pct", "0.1"], "--fee-pct"),
        (["--slippage", "0.1"], "--slippage"),
        (["--position-size", "0.5"], "--position-size"),
        (["--stop-loss", "5"], "--stop-loss"),
        (["--take-profit", "5"], "--take-profit"),
        (["--export", "out.csv"], "--export"),
        (["--fill", "open"], "--fill"),
        (["--strategy", "breakout"], "--strategy"),
        (["--param", "window=5"], "--param"),
        (["--stats"], "--stats"),
        (["--chart"], "--chart"),
        (["--candles"], "--candles"),
        (["--resample", "weekly"], "--resample"),
    ],
)
def test_scan_with_backtest_or_report_options_is_a_usage_error(tmp_path, capsys, extra, flag):
    write_prices(tmp_path / "X.csv", FLAT_JUMP)
    message = usage_error(["--scan", str(tmp_path)] + extra, capsys)
    assert message.endswith(f"{flag} cannot be combined with --scan")


@pytest.mark.parametrize(
    "extra, text",
    [
        (["--short", "50", "--long", "20"], "--short (50) must be smaller than --long (20)"),
        (["--rsi-period", "0"], "--rsi-period must be at least 1"),
        (["--short", "abc"], "invalid int value"),
    ],
)
def test_bad_windows_with_scan_are_usage_errors(tmp_path, capsys, extra, text):
    message = usage_error(["--scan", str(tmp_path)] + extra, capsys)
    assert text in message


def test_scan_needs_a_folder(capsys):
    assert usage_error(["--scan"], capsys).endswith("argument --scan: expected one argument")
    assert usage_error(["--scan", " "], capsys).endswith("--scan needs a folder name")


# --------------------------------------------------------------------------- single-file use is unchanged


def test_scan_is_only_picked_up_as_an_option():
    assert not _scan_requested(["p.csv", "--short", "5", "--long", "9"])
    assert not _scan_requested(["p.csv", "--s"])  # ambiguous abbreviation, left to the normal parser
    assert not _scan_requested(["--", "--scan"])  # after -- it is a file name
    assert _scan_requested(["--scan", "d"]) and _scan_requested(["--scan=d"]) and _scan_requested(["--sca", "d"])


def test_normal_parser_still_needs_a_price_file():
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args([])
    assert excinfo.value.code == 2
    assert build_parser().parse_args(["p.csv"]).scan is None


def test_single_file_report_is_not_affected(tmp_path, capsys):
    path = tmp_path / "p.csv"
    write_prices(path, FLAT_JUMP)
    code, out, err = run([str(path)], capsys)
    assert code == 0 and err == ""
    assert out[0] == "Bars:    60" and out[-1] == DISCLAIMER
    assert not any("Scan" in line for line in out)


# --------------------------------------------------------------------------- as a real command


def run_module(*argv):
    env = dict(os.environ)
    env.pop("TRADING_ASSISTANT_CONFIG", None)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-m", "trading_assistant", *argv], capture_output=True, text=True, env=env)


def test_command_line_exit_codes_without_tracebacks(tmp_path):
    write_prices(tmp_path / "UP.csv", MIRROR)
    (tmp_path / "bad.csv").write_text("date,close\nx,abc\n")
    ok = run_module("--scan", str(tmp_path))
    assert ok.returncode == 0 and ok.stderr == ""
    assert ok.stdout.splitlines()[-1] == DISCLAIMER
    missing = run_module("--scan", str(tmp_path / "missing"))
    assert missing.returncode == 1 and missing.stdout == ""
    assert missing.stderr.startswith("Error:") and len(missing.stderr.splitlines()) == 1
    usage = run_module("--scan", str(tmp_path), "--backtest")
    assert usage.returncode == 2 and "Traceback" not in usage.stderr


# --------------------------------------------------------------------------- --min-score and --top

HEADER_ROW = "Symbol  Bars  Score  Crossover  RSI  MACD  Bollinger"
ROW = {
    "UP": "UP        60     +2         -1   +1    +1         +1",
    "LOW": "LOW       60     +1         +1   +1    -1          0",
    "Alpha": "Alpha     60      0         -1   +1    -1         +1",
    "mid": "mid       60      0         +1    0    -1          0",
    "zeta": "zeta      60      0         +1   -1    +1         -1",
    "DOWN": "DOWN      60     -2         +1   -1    -1         -1",
}


@pytest.fixture
def six(tmp_path):
    """The six hand-worked files: UP +2, LOW +1, Alpha / mid / zeta 0, DOWN -2."""
    folder = tmp_path / "six"
    folder.mkdir()
    write_prices(folder / "DOWN.csv", RISE_FLAT_JUMP)
    write_prices(folder / "UP.csv", MIRROR)
    write_prices(folder / "LOW.csv", RISE_LONG_FALL)
    write_prices(folder / "zeta.csv", FLAT_JUMP)
    write_prices(folder / "Alpha.csv", FLAT_DROP)
    write_prices(folder / "mid.csv", RISE_DROP)
    return folder


def test_without_trim_options_the_output_is_unchanged(six, capsys):
    _, out, _ = run(["--scan", str(six)], capsys)
    assert out == [f"Scan:    {six}, 6 scored, 0 skipped", HEADER_ROW] + list(ROW.values()) + [DISCLAIMER]


def test_min_score_keeps_scores_at_or_above(six, capsys):
    code, out, err = run(["--scan", str(six), "--min-score", "0"], capsys)
    assert code == 0 and err == ""
    assert out == [
        f"Scan:    {six}, 6 found, 6 scored, 0 skipped, 5 with score >= 0, 5 shown",
        HEADER_ROW,
        ROW["UP"], ROW["LOW"], ROW["Alpha"], ROW["mid"], ROW["zeta"],
        DISCLAIMER,
    ]


def test_min_score_boundary_is_inclusive(six, capsys):
    _, out, _ = run(["--scan", str(six), "--min-score", "1"], capsys)
    assert out[0].endswith(", 2 with score >= 1, 2 shown")
    assert out[2:4] == [ROW["UP"], ROW["LOW"]]
    _, out, _ = run(["--scan", str(six), "--min-score", "2"], capsys)
    assert out[2:-1] == [ROW["UP"]]


def test_negative_min_score_keeps_everything(six, capsys):
    _, out, _ = run(["--scan", str(six), "--min-score", "-4"], capsys)
    assert out[0] == f"Scan:    {six}, 6 found, 6 scored, 0 skipped, 6 with score >= -4, 6 shown"
    assert out[2:-1] == list(ROW.values())


def test_top_keeps_the_first_rows_in_table_order(six, capsys):
    code, out, _ = run(["--scan", str(six), "--top", "2"], capsys)
    assert code == 0
    assert out == [
        f"Scan:    {six}, 6 found, 6 scored, 0 skipped, 2 shown (top 2)",
        HEADER_ROW,
        ROW["UP"], ROW["LOW"],
        DISCLAIMER,
    ]


def test_top_cuts_through_a_tie_in_name_order(six, capsys):
    # the three 0 scores are Alpha, mid, zeta in name order; top 4 keeps Alpha and mid
    _, out, _ = run(["--scan", str(six), "--top", "4"], capsys)
    assert out[2:-1] == [ROW["UP"], ROW["LOW"], ROW["Alpha"], ROW["mid"]]


def test_top_larger_than_the_rows_shows_them_all(six, capsys):
    _, out, _ = run(["--scan", str(six), "--top", "50"], capsys)
    assert out[0] == f"Scan:    {six}, 6 found, 6 scored, 0 skipped, 6 shown (top 50)"
    assert out[2:-1] == list(ROW.values())


def test_min_score_then_top(six, capsys):
    # min score 0 leaves UP, LOW, Alpha, mid, zeta; top 3 then keeps the first three
    _, out, _ = run(["--scan", str(six), "--top", "3", "--min-score", "0"], capsys)
    assert out == [
        f"Scan:    {six}, 6 found, 6 scored, 0 skipped, 5 with score >= 0, 3 shown (top 3)",
        HEADER_ROW,
        ROW["UP"], ROW["LOW"], ROW["Alpha"],
        DISCLAIMER,
    ]


def test_skipped_list_is_always_shown_in_full(six, capsys):
    (six / "bad.csv").write_text("date,close\n2026-01-01,10\n2026-01-02,abc\n")
    (six / "header.csv").write_text("date,close\n")
    _, out, _ = run(["--scan", str(six), "--min-score", "1", "--top", "1"], capsys)
    assert out == [
        f"Scan:    {six}, 8 found, 6 scored, 2 skipped, 2 with score >= 1, 1 shown (top 1)",
        HEADER_ROW,
        ROW["UP"],
        "Skipped: 2",
        "  bad.csv line 3: invalid close value 'abc' (expected a number like 101.5)",
        "  header.csv: no price rows found",
        DISCLAIMER,
    ]


def test_nothing_matched_is_not_an_error(six, capsys):
    (six / "bad.csv").write_text("date,close\nx,abc\n")
    code, out, err = run(["--scan", str(six), "--min-score", "3", "--top", "2"], capsys)
    assert code == 0 and err == ""
    assert out == [
        f"Scan:    {six}, 7 found, 6 scored, 1 skipped, 0 with score >= 3, 0 shown (top 2)",
        HEADER_ROW,
        "  (no file matched: no score at or above 3)",
        "Skipped: 1",
        "  bad.csv line 2: invalid close value 'abc' (expected a number like 101.5)",
        DISCLAIMER,
    ]


def test_trim_options_do_not_hide_folder_errors(tmp_path, capsys):
    missing = tmp_path / "missing"
    assert one_error_line(["--scan", str(missing), "--top", "1"], capsys) == (
        f"Error: scan folder {missing} does not exist"
    )
    (tmp_path / "a.csv").write_text("date,close\nx,abc\n")
    assert one_error_line(["--scan", str(tmp_path), "--min-score", "-4"], capsys).startswith(
        "Error: none of the 1 .csv file in"
    )


@pytest.mark.parametrize(
    "argv, text",
    [
        (["--min-score", "1"], "--min-score only makes sense together with --scan"),
        (["--top", "2"], "--top only makes sense together with --scan"),
        (["--top", "2", "--min-score", "0"], "only makes sense together with --scan"),
    ],
)
def test_trim_options_without_scan_are_usage_errors(tmp_path, capsys, argv, text):
    path = tmp_path / "p.csv"
    write_prices(path, FLAT_JUMP)
    assert usage_error([str(path)] + argv, capsys).endswith(text)


@pytest.mark.parametrize(
    "extra, text",
    [
        (["--top", "0"], "--top must be at least 1, got 0"),
        (["--top", "-3"], "--top must be at least 1, got -3"),
        (["--top", "x"], "argument --top: invalid int value: 'x'"),
        (["--min-score", "1.5"], "argument --min-score: invalid int value: '1.5'"),
        (["--min-score"], "argument --min-score: expected one argument"),
    ],
)
def test_bad_trim_values_are_usage_errors(six, capsys, extra, text):
    assert usage_error(["--scan", str(six)] + extra, capsys).endswith(text)


def test_t_still_means_take_profit():
    # before --top existed, argparse read "--t" as an abbreviation of --take-profit
    parser = build_parser()
    assert parser.parse_args(["p.csv", "--backtest", "--t", "5"]).take_profit == 5.0
    assert parser.parse_args(["p.csv", "--backtest", "--t=7"]).take_profit == 7.0
    args = parser.parse_args(["p.csv", "--top", "3"])
    assert (args.top, args.take_profit) == (3, None)


def test_t_errors_still_name_take_profit(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["p.csv", "--backtest", "--t"])
    assert capsys.readouterr().err.strip().endswith("argument --take-profit: expected one argument")


def test_command_line_nothing_matched_exits_0(six):
    done = run_module("--scan", str(six), "--min-score", "4")
    assert done.returncode == 0 and done.stderr == ""
    assert "(no file matched: no score at or above 4)" in done.stdout


# --------------------------------------------------------------------------- --scan --json


def parts_of(up, rsi_, macd_, boll):
    return {"crossover": up, "rsi": rsi_, "macd": macd_, "bollinger": boll}


JSON_ROWS = {
    "UP": {"symbol": "UP", "bars": 60, "score": 2, "parts": parts_of(-1, 1, 1, 1)},
    "LOW": {"symbol": "LOW", "bars": 60, "score": 1, "parts": parts_of(1, 1, -1, 0)},
    "Alpha": {"symbol": "Alpha", "bars": 60, "score": 0, "parts": parts_of(-1, 1, -1, 1)},
    "mid": {"symbol": "mid", "bars": 60, "score": 0, "parts": parts_of(1, 0, -1, 0)},
    "zeta": {"symbol": "zeta", "bars": 60, "score": 0, "parts": parts_of(1, -1, 1, -1)},
    "DOWN": {"symbol": "DOWN", "bars": 60, "score": -2, "parts": parts_of(1, -1, -1, -1)},
}
BAD_REASON = "bad.csv line 3: invalid close value 'abc' (expected a number like 101.5)"
ZED_REASON = (
    "Zed.CSV has no 'close' column (found columns: 'date', 'price'); "
    "expected a header row like 'date,close' followed by rows like '2026-01-02,101.5'"
)


# the skipped list keeps the scan's file order: names sorted as written, so "Zed.CSV" before "bad.csv"
SKIPPED = [{"symbol": "Zed", "reason": ZED_REASON}, {"symbol": "bad", "reason": BAD_REASON}]


@pytest.fixture
def six_and_bad(six):
    (six / "bad.csv").write_text("date,close\n2026-01-01,10\n2026-01-02,abc\n")
    (six / "Zed.CSV").write_text("date,price\n2026-01-01,10\n")
    return six


def run_json(argv, capsys):
    code = main(argv)
    out, err = capsys.readouterr()
    assert code == 0 and err == ""
    assert DISCLAIMER not in out and "Symbol" not in out.splitlines()[0]
    return json.loads(out)  # fails unless stdout is exactly one JSON value


def test_json_object_without_trimming(six_and_bad, capsys):
    data = run_json(["--scan", str(six_and_bad), "--json"], capsys)
    assert data == {
        "found": 8,
        "scored": 6,
        "shown": 6,
        "results": list(JSON_ROWS.values()),
        "skipped": SKIPPED,
    }
    assert list(data) == ["found", "scored", "shown", "results", "skipped"]
    assert list(data["results"][0]) == ["symbol", "bars", "score", "parts"]
    assert list(data["results"][0]["parts"]) == ["crossover", "rsi", "macd", "bollinger"]


def test_json_follows_min_score_and_top_and_keeps_all_skipped(six_and_bad, capsys):
    data = run_json(["--scan", str(six_and_bad), "--json", "--min-score", "0", "--top", "3"], capsys)
    assert (data["found"], data["scored"], data["shown"]) == (8, 6, 3)
    assert data["results"] == [JSON_ROWS["UP"], JSON_ROWS["LOW"], JSON_ROWS["Alpha"]]
    assert data["skipped"] == SKIPPED
    data = run_json(["--scan", str(six_and_bad), "--json", "--top", "4"], capsys)
    assert [r["symbol"] for r in data["results"]] == ["UP", "LOW", "Alpha", "mid"]
    data = run_json(["--scan", str(six_and_bad), "--json", "--min-score", "1"], capsys)
    assert (data["shown"], [r["symbol"] for r in data["results"]]) == (2, ["UP", "LOW"])


def test_json_nothing_matched_is_an_empty_list_and_exit_0(six_and_bad, capsys):
    data = run_json(["--scan", str(six_and_bad), "--json", "--min-score", "3"], capsys)
    assert data == {
        "found": 8,
        "scored": 6,
        "shown": 0,
        "results": [],
        "skipped": SKIPPED,
    }


def test_json_follows_the_windows(tmp_path, capsys):
    # same hand-worked case as test_short_long_and_rsi_period_are_followed
    write_prices(tmp_path / "X.csv", RISE_DROP)
    data = run_json(["--scan", str(tmp_path), "--json", "--short", "2", "--long", "5", "--rsi-period", "2"], capsys)
    assert data["results"] == [{"symbol": "X", "bars": 60, "score": -1, "parts": parts_of(-1, 1, -1, 0)}]
    assert data["skipped"] == []


def parse_table(lines):
    """Read a --scan text table back into the same shape as the JSON object."""
    # top line: "Scan:    FOLDER, 8 found, 6 scored, 2 skipped, 5 with score >= 0, 3 shown (top 3)"
    counts = {}
    for piece in lines[0].split(", ")[1:]:
        words = piece.split()
        if words[1] in ("found", "scored", "skipped", "shown"):
            counts[words[1]] = int(words[0])
    assert lines[1] == HEADER_ROW
    results, i = [], 2
    while i < len(lines) and lines[i] != DISCLAIMER and not lines[i].startswith(("Skipped:", "  (no file matched")):
        symbol, bars, score, *parts = lines[i].split()
        results.append({
            "symbol": symbol,
            "bars": int(bars),
            "score": int(score),
            "parts": dict(zip(("crossover", "rsi", "macd", "bollinger"), map(int, parts))),
        })
        i += 1
    reasons = [line[2:] for line in lines if line.startswith("  ") and not line.startswith("  (no file")]
    counts.setdefault("found", counts["scored"] + counts["skipped"])  # top line without trimming
    counts.setdefault("shown", len(results))
    assert counts["skipped"] == len(reasons)
    return counts, results, reasons


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["--min-score", "0"],
        ["--min-score", "-2"],
        ["--top", "2"],
        ["--min-score", "0", "--top", "3"],
        ["--min-score", "3"],
        ["--short", "2", "--long", "5", "--rsi-period", "2", "--top", "5"],
    ],
)
def test_json_read_back_matches_the_table(six_and_bad, capsys, extra):
    argv = ["--scan", str(six_and_bad)] + extra
    table_code, table_lines, table_err = run(argv, capsys)
    data = run_json(argv + ["--json"], capsys)
    assert table_code == 0 and table_err == "" and table_lines[-1] == DISCLAIMER
    counts, results, reasons = parse_table(table_lines)
    assert (data["found"], data["scored"], data["shown"]) == (counts["found"], counts["scored"], counts["shown"])
    assert data["results"] == results
    assert [item["reason"] for item in data["skipped"]] == reasons
    assert [item["symbol"] for item in data["skipped"]] == [r.split(".")[0] for r in reasons]


def json_error(argv, capsys, code):
    if code == 2:
        with pytest.raises(SystemExit) as excinfo:
            main(argv)
        got = excinfo.value.code
    else:
        got = main(argv)
    out, err = capsys.readouterr()
    assert got == code
    assert out == ""
    assert "Traceback" not in err
    return err.strip().splitlines()[-1]


def test_json_errors_are_unchanged(tmp_path, capsys):
    missing = tmp_path / "missing"
    argv = ["--scan", str(missing)]
    plain = json_error(argv, capsys, 1)
    assert json_error(argv + ["--json"], capsys, 1) == plain == f"Error: scan folder {missing} does not exist"
    (tmp_path / "a.csv").write_text("date,close\nx,abc\n")
    argv = ["--scan", str(tmp_path), "--min-score", "0"]
    assert json_error(argv + ["--json"], capsys, 1) == json_error(argv, capsys, 1)


@pytest.mark.parametrize(
    "extra, text",
    [
        (["--chart"], "--chart cannot be combined with --scan"),
        (["--backtest"], "--backtest cannot be combined with --scan"),
        (["--cash", "500"], "--cash cannot be combined with --scan"),
        (["--candles"], "--candles cannot be combined with --scan"),
        (["--resample", "weekly"], "--resample cannot be combined with --scan"),
        (["--top", "0"], "--top must be at least 1, got 0"),
        (["--short", "9", "--long", "3"], "--short (9) must be smaller than --long (3)"),
    ],
)
def test_json_with_other_options_is_still_a_usage_error(six, capsys, extra, text):
    assert json_error(["--scan", str(six), "--json"] + extra, capsys, 2).endswith(text)


def test_json_with_a_price_file_and_scan_is_a_usage_error(six, capsys):
    path = six / "UP.csv"
    assert json_error([str(path), "--scan", str(six), "--json"], capsys, 2).endswith(
        f"--scan cannot be combined with a price file (got {path})"
    )


def test_command_line_json_is_the_only_output(six_and_bad):
    done = run_module("--scan", str(six_and_bad), "--json", "--top", "1")
    assert done.returncode == 0 and done.stderr == ""
    data = json.loads(done.stdout)
    assert data["results"] == [JSON_ROWS["UP"]] and len(data["skipped"]) == 2
    assert DISCLAIMER not in done.stdout


# --------------------------------------------------------------------------- --scan --report FILE

import datetime  # noqa: E402  (kept next to the report tests that use it)
import re  # noqa: E402

FIXED_DAY = datetime.date(2026, 3, 2)

SENTENCE = {
    "UP": "UP scored +2: the 20-bar average is below the 50-bar average (crossover -1), "
    "the 14-bar RSI is under 30 (RSI +1), the MACD histogram is above 0 (MACD +1) and "
    "the last close is below the lower Bollinger band (Bollinger +1).",
    "LOW": "LOW scored +1: the 20-bar average is above the 50-bar average (crossover +1), "
    "the 14-bar RSI is under 30 (RSI +1), the MACD histogram is below 0 (MACD -1) and "
    "the last close is inside or on the Bollinger bands or there is not enough history (Bollinger 0).",
    "Alpha": "Alpha scored 0: the 20-bar average is below the 50-bar average (crossover -1), "
    "the 14-bar RSI is under 30 (RSI +1), the MACD histogram is below 0 (MACD -1) and "
    "the last close is below the lower Bollinger band (Bollinger +1).",
}


def md(text):
    """Markdown-escaped text as the report writes it (a backslash before \\ ` * _ [ ] < > | #)."""
    return "".join("\\" + ch if ch in "\\`*_[]<>|#" else ch for ch in str(text))


@pytest.fixture
def fixed_day(monkeypatch):
    monkeypatch.setattr(scan, "report_date", lambda: FIXED_DAY)


def test_report_exact_text(six_and_bad, tmp_path, capsys, fixed_day):
    report = tmp_path / "out" / "scan.md"
    report.parent.mkdir()
    code, out, err = run(["--scan", str(six_and_bad), "--min-score", "0", "--top", "3", "--report", str(report)], capsys)
    assert code == 0 and err == ""
    assert report.read_text(encoding="utf-8") == "\n".join([
        f"# Scan report: {md(six_and_bad)}",
        "",
        "Date: 2026-03-02",
        "",
        "## Settings",
        "",
        f"- Folder: {md(six_and_bad)}",
        "- Crossover: 20-bar against 50-bar simple moving average (above scores +1, below scores -1)",
        "- RSI: 14 bars (under 30 scores +1, over 70 scores -1)",
        "- MACD: 12 / 26 / 9 (histogram above 0 scores +1, below 0 scores -1)",
        "- Bollinger: 20 bars, 2 deviations (close below the lower band scores +1, above the upper band scores -1)",
        "- Min score: 0",
        "- Top: 3",
        "- Files: 8 found, 6 scored, 2 skipped, 3 shown",
        "",
        "## Results",
        "",
        "| Symbol | Bars | Score | Crossover | RSI | MACD | Bollinger |",
        "|---|---:|---:|---:|---:|---:|---:|",
        "| UP | 60 | +2 | -1 | +1 | +1 | +1 |",
        "| LOW | 60 | +1 | +1 | +1 | -1 | 0 |",
        "| Alpha | 60 | 0 | -1 | +1 | -1 | +1 |",
        "",
        "- " + SENTENCE["UP"],
        "- " + SENTENCE["LOW"],
        "- " + SENTENCE["Alpha"],
        "",
        "## Skipped",
        "",
        "- " + md(ZED_REASON),
        "- " + md(BAD_REASON),
        "",
        DISCLAIMER,
        "",
    ])


@pytest.mark.parametrize(
    "extra",
    [[], ["--min-score", "0"], ["--top", "2"], ["--min-score", "3"], ["--json"], ["--json", "--min-score", "1", "--top", "1"]],
)
def test_screen_output_is_the_same_with_a_report(six_and_bad, tmp_path, capsys, extra):
    argv = ["--scan", str(six_and_bad)] + extra
    code_plain, out_plain, err_plain = run(argv, capsys)
    report = tmp_path / "r.md"
    code, out, err = run(argv + ["--report", str(report)], capsys)
    assert (code, out, err) == (code_plain, out_plain, err_plain) == (0, out_plain, "")
    assert report.exists()
    if "--json" in extra:
        json.loads("\n".join(out))  # still only the JSON object


def report_rows(text):
    """The table rows and the explanation sentences of a report."""
    lines = text.splitlines()
    start = lines.index("| Symbol | Bars | Score | Crossover | RSI | MACD | Bollinger |") + 2
    rows = []
    for line in lines[start:]:
        if not line.startswith("| "):
            break
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    sentences = [line[2:] for line in lines if line.startswith("- ") and " scored " in line]
    return rows, sentences


@pytest.mark.parametrize("extra", [[], ["--min-score", "0"], ["--top", "4"], ["--short", "2", "--long", "5", "--rsi-period", "2"]])
def test_report_rows_and_sentences_match_the_screen(six_and_bad, tmp_path, capsys, extra):
    write_prices(six_and_bad / "flat.csv", [100.0] * 60)  # crossover 0 and MACD 0
    write_prices(six_and_bad / "tiny.csv", [1.0, 2.0, 3.0])  # every part 0
    report = tmp_path / "r.md"
    _, out, _ = run(["--scan", str(six_and_bad), "--report", str(report)] + extra, capsys)
    _, screen_rows, _ = parse_table(out)
    rows, sentences = report_rows(report.read_text(encoding="utf-8"))
    assert [r[0] for r in rows] == [r["symbol"] for r in screen_rows]
    assert len(sentences) == len(rows)
    for row, screen, sentence in zip(rows, screen_rows, sentences):
        signed = [f"{v:+d}" if v else "0" for v in [screen["score"], *screen["parts"].values()]]
        assert row == [screen["symbol"], str(screen["bars"])] + signed
        # the sentence names the same score and the same four parts
        assert sentence.startswith(f"{screen['symbol']} scored {signed[0]}: ")
        assert re.findall(r"\((crossover|RSI|MACD|Bollinger) ([+-]?\d)\)", sentence) == list(
            zip(["crossover", "RSI", "MACD", "Bollinger"], signed[1:])
        )


def test_report_sentences_for_every_part_value(six_and_bad, tmp_path, capsys):
    write_prices(six_and_bad / "flat.csv", [100.0] * 60)
    write_prices(six_and_bad / "tiny.csv", [1.0, 2.0, 3.0])
    report = tmp_path / "r.md"
    run(["--scan", str(six_and_bad), "--report", str(report)], capsys)
    text = report.read_text(encoding="utf-8")
    for phrase in [
        "the 20-bar average is above the 50-bar average (crossover +1)",
        "the 20-bar average is below the 50-bar average (crossover -1)",
        "the 20-bar and 50-bar averages are level or there is not enough history (crossover 0)",
        "the 14-bar RSI is under 30 (RSI +1)",
        "the 14-bar RSI is over 70 (RSI -1)",
        "the 14-bar RSI is from 30 to 70 or there is not enough history (RSI 0)",
        "the MACD histogram is above 0 (MACD +1)",
        "the MACD histogram is below 0 (MACD -1)",
        "the MACD histogram is at 0 or there is not enough history (MACD 0)",
        "the last close is below the lower Bollinger band (Bollinger +1)",
        "the last close is above the upper Bollinger band (Bollinger -1)",
        "the last close is inside or on the Bollinger bands or there is not enough history (Bollinger 0)",
    ]:
        assert phrase in text, phrase
    assert (
        "- flat scored -1: the 20-bar and 50-bar averages are level or there is not enough history (crossover 0), "
        "the 14-bar RSI is over 70 (RSI -1), the MACD histogram is at 0 or there is not enough history (MACD 0) and "
        "the last close is inside or on the Bollinger bands or there is not enough history (Bollinger 0)."
    ) in text.splitlines()


def test_report_uses_the_windows_given(tmp_path, capsys, fixed_day):
    folder = tmp_path / "prices"
    folder.mkdir()
    write_prices(folder / "X.csv", RISE_DROP)  # hand-worked: -1 / +1 / -1 / 0 with 2 / 5 / 2
    report = tmp_path / "r.md"
    run(["--scan", str(folder), "--short", "2", "--long", "5", "--rsi-period", "2", "--report", str(report)], capsys)
    lines = report.read_text(encoding="utf-8").splitlines()
    assert "- Crossover: 2-bar against 5-bar simple moving average (above scores +1, below scores -1)" in lines
    assert "- RSI: 2 bars (under 30 scores +1, over 70 scores -1)" in lines
    assert "- Min score: none" in lines and "- Top: none" in lines
    assert "- Files: 1 found, 1 scored, 0 skipped, 1 shown" in lines
    assert "| X | 60 | -1 | -1 | +1 | -1 | 0 |" in lines
    assert (
        "- X scored -1: the 2-bar average is below the 5-bar average (crossover -1), "
        "the 2-bar RSI is under 30 (RSI +1), the MACD histogram is below 0 (MACD -1) and "
        "the last close is inside or on the Bollinger bands or there is not enough history (Bollinger 0)."
    ) in lines
    assert lines[lines.index("## Skipped") + 2] == "None."
    assert lines[-1] == DISCLAIMER


def test_report_when_nothing_matched(six_and_bad, tmp_path, capsys, fixed_day):
    report = tmp_path / "r.md"
    code, out, _ = run(["--scan", str(six_and_bad), "--min-score", "3", "--report", str(report)], capsys)
    assert code == 0 and "  (no file matched: no score at or above 3)" in out
    lines = report.read_text(encoding="utf-8").splitlines()
    header = lines.index("| Symbol | Bars | Score | Crossover | RSI | MACD | Bollinger |")
    assert lines[header + 1 : header + 4] == ["|---|---:|---:|---:|---:|---:|---:|", "", "No file matched: no score at or above 3."]
    assert "- Files: 8 found, 6 scored, 2 skipped, 0 shown" in lines
    assert [line for line in lines if line.startswith("- ") and ".csv" in line.lower()] == [
        "- " + md(ZED_REASON),
        "- " + md(BAD_REASON),
    ]


def test_report_escapes_markdown_in_names(tmp_path, capsys):
    folder = tmp_path / "prices"
    folder.mkdir()
    write_prices(folder / "my_co|b.csv", MIRROR)
    (folder / "bad_one.csv").write_text("date,close\nx,abc\n")
    report = tmp_path / "r.md"
    _, out, _ = run(["--scan", str(folder), "--report", str(report)], capsys)
    assert out[2].startswith("my_co|b ")  # the screen shows the plain name
    text = report.read_text(encoding="utf-8")
    assert "| my\\_co\\|b | 60 | +2 |" in text
    assert "- my\\_co\\|b scored +2: " in text
    assert "- bad\\_one.csv line 2: invalid close value 'abc'" in text


def test_an_existing_report_file_is_replaced(six, tmp_path, capsys):
    report = tmp_path / "r.md"
    report.write_text("old report\n")
    assert run(["--scan", str(six), "--report", str(report)], capsys)[0] == 0
    assert report.read_text(encoding="utf-8").startswith(f"# Scan report: {md(six)}\n")


# --------------------------------------------------------------------------- --report mistakes


def test_report_without_scan_is_a_usage_error(tmp_path, capsys):
    path = tmp_path / "p.csv"
    write_prices(path, FLAT_JUMP)
    report = tmp_path / "r.md"
    assert usage_error([str(path), "--report", str(report)], capsys).endswith(
        "--report only makes sense together with --scan"
    )
    assert not report.exists()


@pytest.mark.parametrize(
    "extra, text",
    [
        (["--report", ""], "--report needs a file name"),
        (["--report", "  "], "--report needs a file name"),
        (["--report"], "argument --report: expected one argument"),
        (["--backtest"], "--backtest cannot be combined with --scan"),
        (["--chart"], "--chart cannot be combined with --scan"),
        (["--top", "0"], "--top must be at least 1, got 0"),
        (["--short", "9", "--long", "3"], "--short (9) must be smaller than --long (3)"),
    ],
)
def test_usage_errors_with_a_report_write_nothing(six, tmp_path, capsys, extra, text):
    report = tmp_path / "r.md"
    argv = ["--scan", str(six)] + (extra if extra[0] == "--report" else ["--report", str(report)] + extra)
    assert usage_error(argv, capsys).endswith(text)
    assert not report.exists()


@pytest.mark.parametrize("as_json", [False, True])
def test_report_path_problems_stop_before_any_output(six, tmp_path, capsys, as_json):
    extra = ["--json"] if as_json else []
    folder_target = tmp_path / "a_folder"
    folder_target.mkdir()
    assert one_error_line(["--scan", str(six), "--report", str(folder_target)] + extra, capsys) == (
        f"Error: cannot write report {folder_target}: it is a folder"
    )
    missing_parent = tmp_path / "missing"
    assert one_error_line(["--scan", str(six), "--report", str(missing_parent / "r.md")] + extra, capsys) == (
        f"Error: cannot write report {missing_parent / 'r.md'}: folder {missing_parent} does not exist"
    )
    assert not missing_parent.exists()
    price = six / "UP.csv"
    before = price.read_bytes()
    assert one_error_line(["--scan", str(six), "--report", str(price)] + extra, capsys) == (
        f"Error: --report refuses to overwrite the price file {price}"
    )
    assert price.read_bytes() == before


def test_a_skipped_price_file_is_not_overwritten_either(six_and_bad, capsys):
    bad = six_and_bad / "bad.csv"
    before = bad.read_bytes()
    assert one_error_line(["--scan", str(six_and_bad), "--report", str(bad)], capsys) == (
        f"Error: --report refuses to overwrite the price file {bad}"
    )
    assert bad.read_bytes() == before


def test_folder_errors_with_a_report_are_unchanged_and_write_nothing(tmp_path, capsys):
    report = tmp_path / "r.md"
    missing = tmp_path / "missing"
    assert one_error_line(["--scan", str(missing), "--report", str(report)], capsys) == (
        f"Error: scan folder {missing} does not exist"
    )
    folder = tmp_path / "prices"
    folder.mkdir()
    (folder / "a.csv").write_text("date,close\nx,abc\n")
    assert one_error_line(["--scan", str(folder), "--report", str(report), "--json"], capsys).startswith(
        "Error: none of the 1 .csv file in"
    )
    assert not report.exists()


@pytest.mark.parametrize("as_json", [False, True])
def test_a_write_failure_after_the_output_is_exit_1(six, tmp_path, capsys, monkeypatch, as_json):
    extra = ["--json"] if as_json else []
    code_plain, out_plain, _ = run(["--scan", str(six)] + extra, capsys)
    report = tmp_path / "r.md"
    real_open = open

    def fake_open(path, *args, **kwargs):
        if str(path) == str(report):
            raise PermissionError(13, "Permission denied", str(path))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(scan, "open", fake_open, raising=False)
    code, out, err = run(["--scan", str(six), "--report", str(report)] + extra, capsys)
    assert code_plain == 0 and code == 1
    assert out == out_plain  # the normal output was already printed, unchanged
    assert err.strip().splitlines() == [f"Error: cannot write report {report}: Permission denied"]
    assert not report.exists()


def test_re_still_means_resample():
    # before --report existed, argparse read "--re" as an abbreviation of --resample
    parser = build_parser()
    assert parser.parse_args(["p.csv", "--re", "weekly"]).resample == "weekly"
    assert parser.parse_args(["p.csv", "--re=monthly"]).resample == "monthly"
    args = build_parser(scan=True).parse_args(["--scan", "d", "--rep", "r.md"])
    assert (args.report, args.resample) == ("r.md", None)


def test_re_errors_still_name_resample(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["p.csv", "--re", "daily"])
    assert "argument --resample: invalid choice: 'daily'" in capsys.readouterr().err


def test_command_line_report_with_a_relative_name(six, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    env = dict(os.environ)
    env.pop("TRADING_ASSISTANT_CONFIG", None)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    done = subprocess.run(
        [sys.executable, "-m", "trading_assistant", "--scan", str(six), "--json", "--report", "report.md"],
        capture_output=True, text=True, env=env, cwd=work,
    )
    assert done.returncode == 0 and done.stderr == ""
    assert json.loads(done.stdout)["shown"] == 6
    assert sorted(os.listdir(work)) == ["report.md"]  # written where asked and nowhere else
    lines = (work / "report.md").read_text(encoding="utf-8").splitlines()
    assert re.fullmatch(r"Date: \d{4}-\d{2}-\d{2}", lines[2])
    assert lines[-1] == DISCLAIMER


# --------------------------------------------------------------------------- config file: top and min_score

from trading_assistant.config import ConfigError, load_config  # noqa: E402


def write_ini(tmp_path, text, name="settings.ini"):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_load_config_reads_top_and_min_score_as_whole_numbers(tmp_path):
    cli = load_config(write_ini(tmp_path, "[cli]\ntop = 3\nmin_score = -1\n"))["cli"]
    assert cli == {"top": 3, "min_score": -1}
    assert all(type(cli[k]) is int for k in cli)


def test_config_top_and_min_score_apply_to_a_scan(six, tmp_path, capsys):
    cfg = write_ini(tmp_path, "[cli]\ntop = 3\nmin_score = 0\n")
    from_file = run(["--scan", str(six), "--config", str(cfg)], capsys)
    from_flags = run(["--scan", str(six), "--top", "3", "--min-score", "0"], capsys)
    assert from_file == from_flags
    assert from_file[1][0].endswith(", 5 with score >= 0, 3 shown (top 3)")
    data = run_json(["--scan", str(six), "--config", str(cfg), "--json"], capsys)
    assert [r["symbol"] for r in data["results"]] == ["UP", "LOW", "Alpha"]


def test_flags_win_over_the_config_file(six, tmp_path, capsys):
    cfg = write_ini(tmp_path, "[cli]\ntop = 1\nmin_score = 2\n")
    _, out, _ = run(["--scan", str(six), "--config", str(cfg), "--top", "4", "--min-score", "-2"], capsys)
    assert out[0].endswith(", 6 with score >= -2, 4 shown (top 4)")
    _, out, _ = run(["--scan", str(six), "--config", str(cfg), "--top", "4"], capsys)  # min_score still from the file
    assert out[0].endswith(", 1 with score >= 2, 1 shown (top 4)")


def test_config_from_the_environment_variable_applies_too(six, tmp_path, capsys, monkeypatch):
    cfg = write_ini(tmp_path, "[cli]\ntop = 2\n")
    monkeypatch.setenv("TRADING_ASSISTANT_CONFIG", str(cfg))
    _, out, _ = run(["--scan", str(six)], capsys)
    assert out[0].endswith(", 2 shown (top 2)")


@pytest.mark.parametrize(
    "text, message",
    [
        ("[cli]\ntop = 1.5\n", "line 2: top needs a whole number, got '1.5'"),
        ("[cli]\nshort = 5\nmin_score = high\n", "line 3: min_score needs a whole number, got 'high'"),
        ("[cli]\ntop =\n", "line 2: top needs a whole number, got ''"),
        ("[cli]\nscan = prices\n", "line 2: unknown key 'scan' in [cli]"),
        ("[cli]\nreport = r.md\n", "line 2: unknown key 'report' in [cli]"),
        ("[cli]\nfolder = prices\n", "line 2: unknown key 'folder' in [cli]"),
    ],
)
def test_bad_config_values_are_config_errors_naming_the_file(six, tmp_path, capsys, text, message):
    cfg = write_ini(tmp_path, text)
    line = one_error_line(["--scan", str(six), "--config", str(cfg)], capsys)
    assert line.startswith(f"Error: {cfg} ") and message in line


def test_unknown_key_message_ends_with_the_scan_keys(tmp_path):
    with pytest.raises(ConfigError) as excinfo:
        load_config(write_ini(tmp_path, "[cli]\nspeed = 3\n"))
    assert str(excinfo.value).endswith("fill, strategy, stats, trade_list, explain, top, min_score")


@pytest.mark.parametrize("top", ["0", "-2"])
def test_config_top_out_of_range_is_a_usage_error_in_a_scan(six, tmp_path, capsys, top):
    cfg = write_ini(tmp_path, f"[cli]\ntop = {top}\n")
    assert usage_error(["--scan", str(six), "--config", str(cfg)], capsys).endswith(
        f"--top must be at least 1, got {top}"
    )


def test_config_scan_keys_are_ignored_without_scan(tmp_path, capsys):
    path = tmp_path / "p.csv"
    write_prices(path, FLAT_JUMP)
    plain = run([str(path)], capsys)
    cfg = write_ini(tmp_path, "[cli]\ntop = 0\nmin_score = 9\n")  # out of range, but not a scan
    assert run([str(path), "--config", str(cfg)], capsys) == plain
    assert plain[0] == 0


def test_config_scan_keys_show_in_the_report_settings(six, tmp_path, capsys):
    cfg = write_ini(tmp_path, "[cli]\ntop = 2\nmin_score = 1\n")
    report = tmp_path / "r.md"
    run(["--scan", str(six), "--config", str(cfg), "--report", str(report)], capsys)
    lines = report.read_text(encoding="utf-8").splitlines()
    assert "- Min score: 1" in lines and "- Top: 2" in lines
