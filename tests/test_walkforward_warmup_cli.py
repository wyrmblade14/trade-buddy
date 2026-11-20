"""Tests for ``python -m trading_assistant.walkforward ... --warmup`` (the command line only).

tests/data/wf_cli_before_warmup.json holds what the command printed (and wrote with --csv) for four
runs on tests/data/wf.csv before --warmup existed: text, --json, --csv with a fee, and a --step that
overlaps the test blocks. Without --warmup the output must still be exactly that. The numbers with
--warmup are worked out by hand in test_walkforward_warmup.py.
"""

import json
from pathlib import Path

import pytest

from trading_assistant.cli import load_price_table
from trading_assistant.walkforward import CSV_HEADER, format_walk_forward, main, summarize, walk_forward

DATA = Path(__file__).resolve().parent / "data"
WF = str(DATA / "wf.csv")
BEFORE = json.loads((DATA / "wf_cli_before_warmup.json").read_text())

HEADER_WARMUP = (
    "each SMA crossover pair was chosen on its train bars only, then traded and scored on the test bars after"
    " them, with its moving averages warmed up on up to long bars just before each test block"
)


def test_without_warmup_every_output_is_unchanged(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # the --csv run writes out.csv here and prints "Wrote 2 rows to out.csv"
    for name, before in BEFORE.items():
        out = tmp_path / "out.csv"
        if out.exists():
            out.unlink()
        assert main([WF, *before["args"]]) == before["exit"], name
        captured = capsys.readouterr()
        assert (captured.out, captured.err) == (before["stdout"], before["stderr"]), name
        assert (out.read_text() if out.exists() else None) == before["csv"], name


def test_warmup_text(capsys):
    assert main([WF, "--short", "1", "--long", "3", "--train", "12", "--test", "6", "--cash", "1000", "--warmup"]) == 0
    assert capsys.readouterr().out == (
        f"Walk-forward: 1 window; {HEADER_WARMUP}\n"
        "Window  Train bars   Test bars    Pair     Train      Test  Buy&Hold Trades\n"
        "     1        0-11       12-17     1/3    +0.00%    +7.60%   +40.00%      1\n"
        "Test return, compounded over the windows: +7.60%\n"
        "Buy & hold, compounded over the windows:  +40.00%\n"
        "Mean test return per window: +7.60%\n"
        "Windows beating buy & hold: 0 of 1\n"
        "Windows without test trades: 0 of 1\n"
        "Best in-sample parameters overfit; check them on data they were not chosen on.\n"
        "Research aid only. Not financial advice.\n"
    )

    # Window 2 (test bars 11-14) makes no trade even warmed up: its only BUY crossing is on bar 14, its last bar.
    assert main([WF, "--short", "2", "--long", "3", "--train", "7", "--test", "4", "--cash", "1000", "--warmup"]) == 0
    lines = capsys.readouterr().out.splitlines()
    rows = walk_forward(load_price_table(WF)[1], [2], [3], 7, 4, cash=1000, warmup=True)
    assert [r["test_trades"] for r in rows] == [1, 0] and summarize(rows)["windows_without_trades"] == 1
    assert lines[0] == f"Walk-forward: 2 windows; {HEADER_WARMUP}"
    assert lines[-3] == (
        "Note: 1 of 2 windows made no trades in the test block (no BUY crossover on a test bar before its last, or,"
        " near the start of the data, fewer than long bars before the block to warm up); their 0.00% says nothing"
        " about the pair."
    )


def test_json_and_csv_with_warmup(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    args = [WF, "--short", "1", "--long", "3", "--train", "12", "--test", "6", "--cash", "1000", "--warmup"]
    assert main([*args, "--json", "--csv", "out.csv"]) == 0
    out = capsys.readouterr().out
    assert main(args) == 0
    text = capsys.readouterr().out

    # "warmup": true comes first, then the four keys as without --warmup; stdout is only the JSON object.
    assert out.startswith('{\n  "warmup": true,\n  "windows": [\n')
    data = json.loads(out)
    assert list(data) == ["warmup", "windows", "summary", "overfit_warning", "disclaimer"]
    assert data["warmup"] is True
    assert data["windows"] == walk_forward(load_price_table(WF)[1], [1], [3], 12, 6, cash=1000, warmup=True)
    assert data["windows"][0]["test_return_pct"] == pytest.approx(7.6) and data["windows"][0]["test_trades"] == 1
    # The JSON numbers are the ones the text of the same run shows.
    assert format_walk_forward(data["windows"], data["summary"], warmup=True) + "\n" == text

    # The CSV keeps its columns: the header is the one written before --warmup existed; the row is the JSON's.
    lines = (tmp_path / "out.csv").read_text().splitlines()
    assert lines[0] == ",".join(CSV_HEADER) == BEFORE["two_windows_fee_csv"]["csv"].splitlines()[0]
    (row,) = data["windows"]
    assert lines[1:] == [",".join(f"{row[k]:.4f}" if k.endswith("_pct") else str(row[k]) for k in CSV_HEADER)]
    assert lines[1] == "1,0,12,12,18,1,3,0.0000,7.6000,-6.5972,1,40.0000"


@pytest.mark.parametrize(
    "extra, message",
    [(["--warmup", "5"], "unrecognized arguments: 5"), (["--warmup=5"], "argument --warmup: ignored explicit argument '5'")],
)
def test_warmup_takes_no_value(capsys, extra, message):
    with pytest.raises(SystemExit) as exc:
        main([WF, "--short", "1", "--long", "3", "--train", "12", "--test", "6", *extra])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == "" and message in captured.err
