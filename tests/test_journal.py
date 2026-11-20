"""Tests for trading_assistant.journal (add, list, summary, FIFO P&L and exit codes)."""

import subprocess
import sys
from pathlib import Path

import pytest

from trading_assistant.cli import DISCLAIMER
from trading_assistant.journal import HEADER, Ledger, main, parse_trade, read_journal, summarize

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
HEADER_LINE = ",".join(HEADER) + "\n"


def add(path, date, side, qty, price, fee=None, symbol="AAA", note=None):
    argv = [str(path), "add", "--date", date, "--symbol", symbol, "--side", side, "--qty", str(qty), "--price", str(price)]
    if fee is not None:
        argv += ["--fee", str(fee)]
    if note is not None:
        argv += ["--note", note]
    return main(argv)


def journal_file(tmp_path, body, name="j.csv"):
    path = tmp_path / name
    path.write_text(HEADER_LINE + body)
    return path


# -------------------------------------------------------------------- add


def test_add_creates_file_with_header(tmp_path, capsys):
    path = tmp_path / "new.csv"
    assert add(path, "2026-01-02", "buy", 10, 100, fee=1, note="first") == 0
    assert path.read_text() == HEADER_LINE + "2026-01-02,AAA,buy,10,100.0,1.0,first\n"
    assert "Added:" in capsys.readouterr().out


def test_add_appends_without_repeating_header_and_quotes_notes(tmp_path):
    path = tmp_path / "j.csv"
    add(path, "2026-01-02", "buy", 10, 100)
    add(path, "2026-01-03", "sell", 4, 101, note="took profit, partly")
    lines = path.read_text().splitlines()
    assert lines[0] == ",".join(HEADER) and len(lines) == 3
    assert lines[2] == '2026-01-03,AAA,sell,4,101.0,0.0,"took profit, partly"'


def test_add_after_file_without_trailing_newline(tmp_path):
    path = tmp_path / "j.csv"
    path.write_text(HEADER_LINE + "2026-01-02,AAA,buy,10,100,0,x")
    assert add(path, "2026-01-03", "sell", 1, 100) == 0
    assert len(read_journal(path)[0]) == 2


def test_symbol_is_stored_upper_case(tmp_path):
    path = tmp_path / "j.csv"
    add(path, "2026-01-02", "buy", 1, 5, symbol="abc")
    assert read_journal(path)[0][0]["symbol"] == "ABC"


def test_oversell_is_rejected_and_file_unchanged(tmp_path, capsys):
    path = tmp_path / "j.csv"
    add(path, "2026-01-02", "buy", 10, 100)
    before = path.read_bytes()
    assert add(path, "2026-01-03", "sell", 11, 100) == 1
    assert path.read_bytes() == before
    err = capsys.readouterr().err
    assert err.startswith("Error: cannot sell 11 AAA: only 10 open")


def test_oversell_on_a_new_file_does_not_create_it(tmp_path):
    path = tmp_path / "none.csv"
    assert add(path, "2026-01-02", "sell", 1, 100) == 1
    assert not path.exists()


def test_selling_a_symbol_never_bought_is_rejected(tmp_path):
    path = tmp_path / "j.csv"
    add(path, "2026-01-02", "buy", 10, 100, symbol="AAA")
    assert add(path, "2026-01-03", "sell", 1, 100, symbol="BBB") == 1


@pytest.mark.parametrize(
    "extra",
    [
        ["--qty", "0"],
        ["--qty", "2.5"],
        ["--qty", "-1"],
        ["--price", "0"],
        ["--price", "-5"],
        ["--price", "nan"],
        ["--fee", "-1"],
        ["--side", "hold"],
        ["--date", "2026-13-01"],
        ["--date", "01/02/2026"],
        ["--symbol", "two words"],
        ["--note", "a\nb"],
    ],
)
def test_add_usage_errors_exit_2(tmp_path, extra):
    argv = [str(tmp_path / "j.csv"), "add", "--date", "2026-01-02", "--symbol", "A", "--side", "buy", "--qty", "1", "--price", "1"]
    argv += extra  # a later repeat of an option wins
    with pytest.raises(SystemExit) as info:
        main(argv)
    assert info.value.code == 2
    assert not (tmp_path / "j.csv").exists()


def test_missing_command_exit_2(tmp_path):
    with pytest.raises(SystemExit) as info:
        main([str(tmp_path / "j.csv")])
    assert info.value.code == 2


# ------------------------------------------------------ FIFO P&L, hand worked


def test_fifo_realized_with_partial_sells_and_fees():
    # Buy 10 @ 100 fee 10 -> lot cost 1010 (101 each).
    # Buy 10 @ 110 fee 20 -> lot cost 1120 (112 each).
    # Sell 15 @ 120 fee 6: proceeds 1800 - 6 = 1794; cost 10*101 + 5*112 = 1570; realized 224.
    # Sell 5 @ 90 fee 5: proceeds 450 - 5 = 445; cost 5*112 = 560; realized -115. Total 109.
    ledger = Ledger()
    for side, qty, price, fee in [("buy", 10, 100, 10), ("buy", 10, 110, 20), ("sell", 15, 120, 6)]:
        ledger.apply(parse_trade(["2026-01-01", "A", side, str(qty), str(price), str(fee), ""]))
    assert ledger.realized["A"] == pytest.approx(224.0)
    assert ledger.position("A") == (5, pytest.approx(560.0))
    ledger.apply(parse_trade(["2026-01-02", "A", "sell", "5", "90", "5", ""]))
    assert ledger.realized["A"] == pytest.approx(109.0)
    assert ledger.position("A") == (0, 0)


def test_summary_without_mark_hand_worked(tmp_path, capsys):
    path = tmp_path / "j.csv"
    add(path, "2026-01-02", "buy", 10, 100, fee=10)
    add(path, "2026-01-03", "buy", 10, 110, fee=20)
    add(path, "2026-01-04", "sell", 15, 120, fee=6)
    capsys.readouterr()
    assert main([str(path), "summary"]) == 0
    out = capsys.readouterr().out
    # Open: 5 shares costing 560, average 112.
    assert "AAA" in out and "112.0000" in out and "+224.00" in out
    assert "Total realized +224.00, unrealized +0.00 (excludes 1 open symbol(s) without a mark)" in out
    assert out.rstrip().endswith(DISCLAIMER)


def test_summary_with_mark_and_two_symbols(tmp_path, capsys):
    path = tmp_path / "j.csv"
    add(path, "2026-01-02", "buy", 10, 100, fee=10)
    add(path, "2026-01-03", "sell", 10, 105, symbol="AAA", fee=0)  # realized 1050 - 1010 = +40
    add(path, "2026-01-04", "buy", 4, 50, symbol="BBB")  # open 4, cost 200
    capsys.readouterr()
    assert main([str(path), "summary", "--mark", "bbb=60", "--mark", "AAA=1"]) == 0
    out = capsys.readouterr().out
    # BBB unrealized 4*60 - 200 = +40; AAA is flat so no unrealized.
    assert "+40.00" in out
    assert "Total realized +40.00, unrealized +40.00" in out
    assert "excludes" not in out


def test_summarize_function_rows():
    ledger = Ledger()
    ledger.apply(parse_trade(["2026-01-01", "A", "buy", "2", "10", "0", ""]))
    rows, totals = summarize(ledger, {"A": 12.0})
    assert rows[0]["open_qty"] == 2 and rows[0]["avg_cost"] == 10.0
    assert rows[0]["unrealized"] == pytest.approx(4.0)
    assert totals == {"realized": 0.0, "unrealized": pytest.approx(4.0), "unmarked": 0}


def test_mark_for_unknown_symbol_is_noted_on_stderr(tmp_path, capsys):
    path = tmp_path / "j.csv"
    add(path, "2026-01-02", "buy", 1, 10)
    capsys.readouterr()
    assert main([str(path), "summary", "--mark", "ZZZ=5"]) == 0
    assert "ZZZ ignored" in capsys.readouterr().err


@pytest.mark.parametrize("mark", ["AAA", "AAA=", "=5", "AAA=0", "AAA=x"])
def test_bad_mark_exit_2(tmp_path, mark):
    with pytest.raises(SystemExit) as info:
        main([str(tmp_path / "j.csv"), "summary", "--mark", mark])
    assert info.value.code == 2


# ------------------------------------------------------------------ list


def test_list_and_symbol_filter(tmp_path, capsys):
    path = tmp_path / "j.csv"
    add(path, "2026-01-02", "buy", 10, 100, symbol="AAA", note="n1")
    add(path, "2026-01-03", "buy", 5, 20, symbol="BBB")
    capsys.readouterr()
    assert main([str(path), "list"]) == 0
    out = capsys.readouterr().out
    assert "AAA" in out and "BBB" in out and "2 trade(s)" in out and "n1" in out
    assert main([str(path), "list", "--symbol", "bbb"]) == 0
    out = capsys.readouterr().out
    assert "BBB" in out and "AAA" not in out and "1 trade(s)" in out


# ------------------------------------------------------------ bad journals


@pytest.mark.parametrize(
    "body, line, fragment",
    [
        ("2026-01-02,AAA,buy,10,100,0,\n2026-02-30,AAA,buy,1,1,0,\n", 3, "not a real calendar date"),
        ("2026-01-02,AAA,hold,10,100,0,\n", 2, "bad side 'hold'"),
        ("2026-01-02,AAA,buy,1.5,100,0,\n", 2, "bad qty '1.5'"),
        ("2026-01-02,AAA,buy,10,abc,0,\n", 2, "bad price 'abc'"),
        ("2026-01-02,AAA,buy,10,0,0,\n", 2, "bad price '0'"),
        ("2026-01-02,AAA,buy,10,5,-1,\n", 2, "bad fee '-1'"),
        ("2026-01-02,AAA,buy,10\n", 2, "expected 7 columns, found 4"),
        ("2026-01-02,AAA,buy,10,100,0,\n\n2026-01-03,AAA,sell,11,100,0,\n", 4, "cannot sell 11 AAA: only 10 open"),
    ],
)
def test_bad_row_reports_line_number(tmp_path, capsys, body, line, fragment):
    path = journal_file(tmp_path, body)
    for command in (["list"], ["summary"]):
        assert main([str(path)] + command) == 1
        err = capsys.readouterr().err
        assert f"line {line}: " in err and fragment in err
        assert err.startswith("Error: ") and err.count("\n") == 1


def test_add_to_a_bad_journal_is_exit_1_and_file_unchanged(tmp_path, capsys):
    path = journal_file(tmp_path, "2026-01-02,AAA,sideways,10,100,0,\n")
    before = path.read_bytes()
    assert add(path, "2026-01-03", "buy", 1, 1) == 1
    assert path.read_bytes() == before
    assert "line 2:" in capsys.readouterr().err


def test_bad_header_is_line_1(tmp_path, capsys):
    path = tmp_path / "j.csv"
    path.write_text("day,sym,side,qty,price,fee,note\n")
    assert main([str(path), "list"]) == 1
    assert "line 1: header must be" in capsys.readouterr().err


def test_missing_file_exit_1_for_list_and_summary(tmp_path, capsys):
    for command in (["list"], ["summary"]):
        assert main([str(tmp_path / "missing.csv")] + command) == 1
        assert capsys.readouterr().err.startswith("Error: cannot read")


def test_header_only_file_summarizes_to_zero(tmp_path, capsys):
    path = journal_file(tmp_path, "")
    assert main([str(path), "summary"]) == 0
    assert "Total realized +0.00, unrealized +0.00" in capsys.readouterr().out


def test_module_runs_as_subprocess(tmp_path):
    path = tmp_path / "j.csv"
    proc = subprocess.run(
        [sys.executable, "-m", "trading_assistant.journal", str(path), "add", "--date", "2026-01-02",
         "--symbol", "A", "--side", "buy", "--qty", "1", "--price", "2"],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(SRC_DIR), "PATH": ""},
    )
    assert proc.returncode == 0 and path.exists()
