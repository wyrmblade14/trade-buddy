"""--add-on PCT and --max-adds N on the command line.

up.csv is the close-only file of test_add_on.py's request case: closes 10 9 8 9 11 12 13 14 15 14 13 12, run with
--backtest --cash 1000 --short 1 --long 2 (the arithmetic is in test_add_on.py's docstring):
    --position-size 0.5: no add-on 1090.00; --add-on 10: 36 @ 14 on bar 7, 1054.00; --add-on 20: 33 @ 15 on bar 8,
    1024.00; --add-on 50: never reached, 1090.00. --add-on 10 without --position-size: 3 add-ons skipped (0 shares),
    the fills and equity of the plain run, 1180.00.

tests/data/cli_before_add_on.json was recorded from the command line before the two options existed (COLUMNS=80,
in a folder like the one ``folder`` makes): "full" holds the exit code, stdout, stderr and --export file of every
command in FULL_RUNS, and "abbreviations" one SHA-256 (exit code, stdout, stderr, any --export file) for each
shortened form of every option string (hidden aliases included), written alone and with a value after it, in a
c.csv backtest; "--scan scan --top 0" was added to the full runs later, recorded from the same unchanged command
line. Only these change on purpose: --help and its forms --h, --he, --hel (two new blocks), the "--a" ambiguity
message (it now also names --add-on) and the forms of the new options ("--ad" ... "--add-on", "--max-a" ...
"--max-adds"), which were unrecognized before.
"""

import contextlib
import hashlib
import io
import json
import re
import shutil
from pathlib import Path

import pytest

from trading_assistant.cli import build_parser, main

DATA = Path(__file__).parent / "data"
UP = [10, 9, 8, 9, 11, 12, 13, 14, 15, 14, 13, 12]
CLOSES = [10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]  # c.csv's closes, dated


def make_folder(path):
    shutil.copy(DATA / "c.csv", path / "c.csv")
    (path / "up.csv").write_text("close\n" + "".join(f"{c}\n" for c in UP))
    (path / "closes.csv").write_text("date,close\n" + "".join(f"2026-01-{i:02d},{c}\n" for i, c in enumerate(CLOSES, 1)))
    (path / "scan").mkdir()
    shutil.copy(DATA / "c.csv", path / "scan" / "c.csv")


def run(argv):
    """(exit code, stdout, stderr) of ``main(argv)``."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


UPB = ["up.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]
CB = ["c.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]
CLB = ["closes.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]
FULL_RUNS = [
    UPB, UPB + ["--position-size", "0.5"], UPB + ["--position-size", "0.5", "--json"],
    UPB + ["--fee", "1", "--slippage", "1", "--position-size", "0.5", "--trade-list", "--stats"],
    UPB + ["--min-hold", "3", "--max-hold", "4", "--position-size", "0.5"],
    UPB + ["--max-drawdown", "5", "--max-losses", "1", "--json", "--trade-list"],
    UPB + ["--position-size", "0.5", "--export", "out.csv"], UPB + ["--chart"],
    CLB + ["--resample", "weekly"], CLB + ["--max-hold", "3", "--explain"],
    CB + ["--fill", "open", "--position-size", "0.5"], CB + ["--stop-loss", "5", "--take-profit", "8"],
    CB + ["--trailing-stop", "6", "--json"], CB + ["--risk-pct", "2", "--atr-period", "3"],
    CB + ["--atr-stop", "--atr-period", "3", "--cooldown", "2"], CB + ["--breakeven", "3", "--scale-out", "5"],
    CB + ["--strategy", "breakout", "--param", "window=3", "--trade-list"],
    ["up.csv"], ["c.csv", "--candles", "--explain", "--json"], ["--scan", "scan"], ["--scan", "scan", "--json"],
    ["--help"], ["up.csv", "--cash", "5"], ["up.csv", "--backtest", "--resample", "weekly"], ["--scan", "scan", "--top", "0"],
]
# Forms that did not exist before (the new options and their shortened forms).
NEW_FORMS = ["--ad", "--add", "--add-", "--add-o", "--add-on", "--max-a", "--max-ad", "--max-add", "--max-adds"]


def short_forms():
    """Every option string of the parser (hidden aliases included) and every shortened form of it, "--x" and longer,
    plus the forms of the new options; sorted."""
    forms = set(NEW_FORMS)
    for action in build_parser()._actions:
        for option in action.option_strings:
            if option.startswith("--"):
                forms.update(option[:n] for n in range(3, len(option) + 1))
    return sorted(forms)


def abbreviation_runs():
    """Each form written on its own and with a value after it, in a close-fill backtest of c.csv."""
    runs = []
    for form in short_forms():
        runs.append(CB + [form])
        runs.append(CB + [form, "3"])
    return runs


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def record(folder, argv):
    code, out, err = run(argv)
    rec = {"argv": argv, "code": code, "out": out, "err": err}
    exported = folder / "out.csv"
    if exported.exists():
        rec["export"] = exported.read_text()
        exported.unlink()
    for extra in ("3",):  # an --export 3 written by a shortened form
        p = folder / extra
        if p.exists():
            rec["export_3"] = p.read_text()
            p.unlink()
    return rec


def abbreviation_key(argv):
    """The words after the c.csv backtest prefix, e.g. "--max-h 3"."""
    return " ".join(argv[len(CB):])


def compact(rec):
    """A shortened-form run as one SHA-256 of its exit code, stdout, stderr and any --export file (the full runs
    are kept in full)."""
    return digest(json.dumps([rec["code"], rec["out"], rec["err"], rec.get("export_3")]))


@pytest.fixture
def folder(tmp_path, monkeypatch):
    make_folder(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    return tmp_path


BEFORE = json.loads((DATA / "cli_before_add_on.json").read_text())
BEFORE_FULL = {" ".join(rec["argv"]): rec for rec in BEFORE["full"]}
USAGE = BEFORE_FULL["up.csv --cash 5"]["err"].rsplit("trading_assistant.cli: error:", 1)[0]  # as before
SCAN_USAGE = BEFORE_FULL["--scan scan --top 0"]["err"].rsplit("trading_assistant.cli: error:", 1)[0]  # likewise
HELP_FORMS = ["--h", "--he", "--hel", "--help"]


def fill_lines(out):
    return [line.split("  value")[0].split("bar ", 1)[1].split() + [line.split()[-1]]
            for line in out.splitlines() if line.startswith("    #")]


def add_ons_line(out):
    return next(line for line in out.splitlines() if line.startswith("  Add-ons:"))


def test_up_csv_hand_cases(folder):
    ps = UPB + ["--position-size", "0.5"]
    code, out, err = run(ps + ["--add-on", "10"])
    assert (code, err) == (0, "")
    assert fill_lines(out) == [
        ["4", "BUY", "45", "@", "11.00", "signal"], ["7", "BUY", "36", "@", "14.00", "add_on"],
        ["10", "SELL", "81", "@", "13.00", "signal"],
    ]
    assert add_ons_line(out) == (
        "  Add-ons:     up to 1 per position, a buy on the next bar after a close 10.00% or more above the latest "
        "buy price, when nothing else fills on that bar; 1 add-on buy, 0 skipped (0 shares)"
    )
    # Right after the Sizing line (there is no Scale out line here) and before Round trips.
    lines = out.splitlines()
    i = lines.index(add_ons_line(out))
    assert lines[i - 1].startswith("  Sizing:") and lines[i + 1] == "  Round trips: 1 completed, 1 made money (100%)"
    assert "  End equity:  1,054.00" in lines
    # Everything else is the run without the option, apart from the fills' reasons and the numbers.
    before = BEFORE_FULL[" ".join(ps)]["out"].splitlines()
    assert lines[:4] == before[:4] and lines[-1] == before[-1]

    code, out, _ = run(ps + ["--add-on", "20"])
    assert fill_lines(out)[1] == ["8", "BUY", "33", "@", "15.00", "add_on"] and "  End equity:  1,024.00" in out
    code, out, _ = run(ps + ["--add-on", "50"])
    assert len(fill_lines(out)) == 2 and "  End equity:  1,090.00" in out and "0 add-on buys, 0 skipped" in out
    code, out, _ = run(UPB + ["--add-on", "10"])
    assert "  End equity:  1,180.00" in out and "0 add-on buys, 3 skipped (0 shares)" in out
    assert [f[:5] for f in fill_lines(out)] == [f[:5] for f in fill_lines(BEFORE_FULL[" ".join(UPB)]["out"])]

    # --export gets the reason column; --max-adds 2 shows in the line.
    code, out, _ = run(ps + ["--add-on", "10", "--max-adds", "2", "--export", "out.csv"])
    rows = (folder / "out.csv").read_text().splitlines()
    assert rows[0].endswith(",reason") and rows[8].endswith(",add_on") and "up to 2 per position" in out


def test_close_only_file_json_and_resample(folder):
    # A close-only file is enough (up.csv has no open, high or low), and --json shows the add-on keys.
    code, out, err = run(UPB + ["--position-size", "0.5", "--add-on", "10", "--json"])
    assert (code, err) == (0, "")
    data = json.loads(out)["backtest"]
    plain = json.loads(BEFORE_FULL[" ".join(UPB + ["--position-size", "0.5", "--json"])]["out"])["backtest"]
    assert [k for k in data if k not in ("add_on_pct", "max_adds", "add_on_buys", "add_on_skipped_buys")] == list(plain)
    assert [f["reason"] for f in data["fills"]] == ["signal", "add_on", "signal"]
    assert data["final_equity"] == pytest.approx(1054.0)
    # --resample: one close per week (Fridays), so the weekly bars are up.csv's closes and the run is the same.
    fridays = [f"2026-01-{d:02d}" for d in (2, 9, 16, 23, 30)] + [f"2026-02-{d:02d}" for d in (6, 13, 20, 27)]
    fridays += [f"2026-03-{d:02d}" for d in (6, 13, 20)]
    (folder / "weekly.csv").write_text("date,close\n" + "".join(f"{d},{c}\n" for d, c in zip(fridays, UP)))
    code, out, err = run(["weekly.csv"] + UPB[1:] + ["--position-size", "0.5", "--add-on", "10", "--resample", "weekly"])
    assert (code, err) == (0, "")
    assert out.splitlines()[4:] == run(UPB + ["--position-size", "0.5", "--add-on", "10"])[1].splitlines()[4:]


def test_usage_errors(folder):
    cases = [
        (["up.csv", "--add-on", "10"], "--add-on only makes sense together with --backtest"),
        (["up.csv", "--max-adds", "2"], "--max-adds only makes sense together with --backtest"),
        (UPB + ["--add-on", "0"], "--add-on must be above 0, got 0"),
        (UPB + ["--add-on", "-5"], "--add-on must be above 0, got -5"),
        (UPB + ["--add-on", "nan"], "--add-on must be above 0, got nan"),
        (UPB + ["--add-on", "inf"], "--add-on must be a finite number, got inf"),
        (UPB + ["--add-on", "ten"], "argument --add-on: invalid float value: 'ten'"),
        (UPB + ["--max-adds", "2"], "--max-adds only makes sense together with --add-on"),
        (UPB + ["--add-on", "10", "--max-adds", "0"], "--max-adds must be a whole number of at least 1, got 0"),
        (UPB + ["--add-on", "10", "--max-adds", "-1"], "--max-adds must be a whole number of at least 1, got -1"),
        (UPB + ["--add-on", "10", "--max-adds", "2.5"], "argument --max-adds: invalid int value: '2.5'"),
        (["--scan", "scan", "--add-on", "10"], "--add-on cannot be combined with --scan"),
        (["--scan", "scan", "--max-adds", "2"], "--max-adds cannot be combined with --scan"),
    ]
    for argv, message in cases:
        usage = SCAN_USAGE if argv[0] == "--scan" else USAGE
        assert run(argv) == (2, "", f"{usage}trading_assistant.cli: error: {message}\n"), argv
    # Decimals are fine, and a whole-number PCT too.
    assert run(UPB + ["--add-on", "12.5"])[0] == 0 and run(UPB + ["--add-on", "10", "--max-adds", "3"])[0] == 0


def _without_new_blocks(help_text):
    """--help with the --add-on and --max-adds blocks taken out."""
    out, skipping = [], False
    for line in help_text.splitlines(keepends=True):
        if line.startswith("  -"):
            skipping = line.startswith(("  --add-on", "  --max-adds"))
        if not skipping:
            out.append(line)
    return "".join(out)


def test_help_lists_them_and_the_usage_line_does_not(folder):
    code, out, err = run(["--help"])
    assert (code, err) == (0, "")
    assert "  --add-on PCT " in out and "  --max-adds N " in out
    assert out.index("  --scale-out PCT") < out.index("  --add-on PCT") < out.index("  --max-adds N") < out.index(
        "  --export FILE")
    assert "a close of exactly 12.10 does not set it off" in " ".join(out.split())
    assert _without_new_blocks(out) == BEFORE_FULL["--help"]["out"]
    for form in HELP_FORMS:  # the shortened forms of --help print the same
        assert run(CB + [form]) == (0, out, ""), form
    usage = out.split("\n\n", 1)[0]
    assert "add-on" not in usage and "max-adds" not in usage
    assert usage + "\n" == USAGE


def test_runs_without_the_options_print_exactly_what_they_did(folder):
    for argv in FULL_RUNS:
        if argv == ["--help"]:
            continue  # checked above
        assert record(folder, argv) == BEFORE_FULL[" ".join(argv)], argv


def test_shortened_forms_mean_what_they_meant_before(folder):
    assert sorted(BEFORE["abbreviations"]) == sorted(abbreviation_key(a) for a in abbreviation_runs())
    new = set(NEW_FORMS) | {"--a"} | set(HELP_FORMS)  # --help's forms are checked in the help test
    for argv in abbreviation_runs():
        key = abbreviation_key(argv)
        if key.split()[0] in new:
            continue  # checked below
        assert compact(record(folder, argv)) == BEFORE["abbreviations"][key], key
    # --a was ambiguous and still is; the message now names --add-on too.
    code, _, err = run(CB + ["--a", "3"])
    assert code == 2 and err.endswith(
        "error: ambiguous option: --a could match --atr-mult, --atr-period, --atr-stop, --add-on\n")
    # The new forms were unrecognized before; now each means its option.
    for form in NEW_FORMS:
        before = BEFORE["abbreviations"][f"{form} 3"]
        was = compact({"code": 2, "out": "", "err": f"{USAGE}trading_assistant.cli: error: unrecognized arguments: "
                                                    f"{form} 3\n"})
        assert before == was, form
        full = "--add-on" if "--add-on".startswith(form) else "--max-adds"
        extra = ["--add-on", "10"] if full == "--max-adds" else []
        assert run(UPB + extra + [form, "3"]) == run(UPB + extra + [full, "3"]), form


def test_max_hold_short_forms_still_mean_max_hold(folder):
    for form in ("--ma", "--max", "--max-", "--max-h", "--max-hold"):
        assert run(UPB + [form, "3"]) == run(UPB + ["--max-hold", "3"]), form
        assert "  Max hold:" in run(UPB + [form, "3"])[1]
    assert run(UPB + ["--m", "3"])[2].endswith("error: --min-score only makes sense together with --scan\n")
