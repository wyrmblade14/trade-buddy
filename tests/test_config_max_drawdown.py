"""Config key max_drawdown: the same as --max-drawdown, the flag wins, ignored without --backtest and with --scan."""

import pytest

from trading_assistant.cli import main


def close_file(closes):
    return "date,close\n" + "".join(f"2026-01-{d:02d},{c}\n" for d, c in enumerate(closes, start=5))


CLOSES = [10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]  # closes.csv of docs/cli.md
RALLY = [10, 10, 10, 10, 11, 20, 32, 28, 30, 25, 35, 36]  # worked out in test_max_drawdown.py
B = ["closes.csv", "--backtest", "--cash", "1000", "--short", "1", "--long", "2"]


@pytest.fixture
def folder(tmp_path, monkeypatch):
    (tmp_path / "closes.csv").write_text(close_file(CLOSES))
    (tmp_path / "rally.csv").write_text(close_file(RALLY))
    (tmp_path / "scan").mkdir()
    (tmp_path / "scan" / "a.csv").write_text(close_file(CLOSES))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)
    return tmp_path


def run(argv, capsys):
    try:
        code = main(argv)
    except SystemExit as exc:
        code = exc.code
    out, err = capsys.readouterr()
    return code, out, err


def with_config(folder, capsys, text, argv):
    (folder / "c.ini").write_text(text)
    return run([*argv, "--config", "c.ini"], capsys)


@pytest.mark.parametrize("price, long, pct", [("closes.csv", "2", "16"), ("closes.csv", "2", "17"), ("rally.csv", "3", "12.5")])
@pytest.mark.parametrize("json", [[], ["--json"]])
def test_the_key_gives_exactly_what_the_flag_gives(folder, capsys, price, long, pct, json):
    argv = [price, "--backtest", "--cash", "1000", "--short", "1", "--long", long, *json]
    from_file = with_config(folder, capsys, f"[cli]\nmax_drawdown = {pct}\n", argv)
    from_flag = run([*argv, "--max-drawdown", pct], capsys)
    assert from_file == from_flag and from_file[0] == 0
    assert ("Drawdown:" in from_file[1]) != bool(json) and ("drawdown_halt_bar" in from_file[1]) == bool(json)


@pytest.mark.parametrize(
    "value, code, err",
    [
        ("0", 2, "error: --max-drawdown must be above 0 and below 100, got 0\n"),
        ("100", 2, "error: --max-drawdown must be above 0 and below 100, got 100\n"),
        ("ten", 1, "Error: c.ini line 2: max_drawdown needs a number, got 'ten'\n"),
    ],
)
def test_bad_values_give_the_flag_rule_worded_for_the_file(folder, capsys, value, code, err):
    got = with_config(folder, capsys, f"[cli]\nmax_drawdown = {value}\n", B)
    assert got[:2] == (code, "") and got[2].endswith(err)


def test_the_flag_wins_and_the_key_is_ignored_without_backtest_or_with_scan(folder, capsys):
    # Two valid values: the run uses the flag's 17 (no halt, 925.00), not the file's 16 (halt on bar 6, 910.00).
    code, out, _ = with_config(folder, capsys, "[cli]\nmax_drawdown = 16\n", [*B, "--max-drawdown", "17"])
    assert code == 0 and "halt at 17.00% below the peak account value at a close; not triggered" in out
    assert "\n  End equity:  925.00\n" in out
    # The flag wins, and then the file's value is not used at all: 0 in the file is no error.
    assert with_config(folder, capsys, "[cli]\nmax_drawdown = 0\n", [*B, "--max-drawdown", "16"]) == run(
        [*B, "--max-drawdown", "16"], capsys
    )
    # Without --backtest and with --scan the key is ignored, even 0 ...
    for argv in (["closes.csv"], ["--scan", "scan"]):
        assert with_config(folder, capsys, "[cli]\nmax_drawdown = 0\n", argv) == run(argv, capsys)
        # ... but a value that is not a number is still the config error, as for every key.
        code, out, err = with_config(folder, capsys, "[cli]\nmax_drawdown = ten\n", argv)
        assert (code, out, err) == (1, "", "Error: c.ini line 2: max_drawdown needs a number, got 'ten'\n")
