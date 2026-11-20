"""Tests for trading_assistant.alerts (tokenizer, parser, evaluation and ``python -m`` command)."""

import subprocess
import sys
from pathlib import Path

import pytest

from trading_assistant.alerts import evaluate, main, parse_rule, parse_rules, tokenize
from trading_assistant.cli import DISCLAIMER

SRC_DIR = Path(__file__).resolve().parents[1] / "src"


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def run_one(rule_text, closes):
    return evaluate(parse_rules(rule_text), closes)[0]


# ------------------------------------------------------- tokenizer and parser


def test_tokenize_splits_numbers_words_and_symbols():
    assert tokenize("rsi(14) < 30") == ["rsi", "(", "14", ")", "<", "30"]
    assert tokenize("close>=-2.5") == ["close", ">=", "-2.5"]
    assert tokenize("close crosses_above sma(50)  # note") == ["close", "crosses_above", "sma", "(", "50", ")"]


def test_tokenize_blank_and_comment_lines_are_empty():
    assert tokenize("") == []
    assert tokenize("   # only a comment") == []


def test_tokenize_rejects_stray_character():
    with pytest.raises(ValueError, match=r"line 4: unexpected character '\$'"):
        tokenize("close > $5", 4)


def test_parse_good_rules_with_comments_and_blank_lines():
    text = "# watch list\n\nrsi(14) < 30\nclose crosses_above sma(50)   # trend\nclose > 105.5\n"
    rules = parse_rules(text)
    assert [r["line"] for r in rules] == [3, 4, 5]
    assert [r["text"] for r in rules] == ["rsi(14) < 30", "close crosses_above sma(50)", "close > 105.5"]
    assert rules[0]["left"] == ("ind", "rsi", 14) and rules[0]["right"] == ("num", 30.0)
    assert rules[1]["left"] == ("close",) and rules[1]["right"] == ("ind", "sma", 50)


def test_parse_rule_blank_is_none():
    assert parse_rule("  # nothing") is None


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("foo > 3", "line 1: unexpected token 'foo'"),
        ("close", "line 1: expected an operator after 'close'"),
        ("close ~ 3", "line 1: unexpected character '~'"),
        ("close == 3", "line 1: unexpected character '='"),
        ("close above 3", "line 1: unknown operator 'above'"),
        ("close >", "line 1: expected a value at the end of the rule"),
        ("close > 3 4", "line 1: unexpected token '4' after the rule"),
        ("sma 5 > 3", "line 1: expected '(' after 'sma'"),
        ("sma(0) > 3", "line 1: window must be a positive whole number, got '0'"),
        ("sma(2.5) > 3", "line 1: window must be a positive whole number"),
        ("sma(5 > 3", "line 1: expected ')' but found '>'"),
        ("sma(5", "line 1: expected ')' but found the end of the rule"),
        ("> 3", "line 1: unexpected token '>'"),
    ],
)
def test_parse_errors_name_line_and_token(text, fragment):
    with pytest.raises(ValueError) as info:
        parse_rules(text)
    assert fragment in str(info.value)


def test_parse_error_reports_the_right_line_number():
    with pytest.raises(ValueError, match="line 3: unexpected token 'bogus'"):
        parse_rules("close > 1\n# c\nbogus < 2\n")


def test_rule_text_is_never_evaluated():
    with pytest.raises(ValueError):
        parse_rules("__import__('os').getcwd() > 1")


# ---------------------------------------------------------------- evaluation

CLOSES = [10.0, 11.0, 12.0, 13.0, 14.0]  # last close 14, previous 13


@pytest.mark.parametrize(
    "rule, fired",
    [
        ("close < 15", True),
        ("close < 14", False),
        ("close <= 14", True),
        ("close <= 13.5", False),
        ("close > 13.5", True),
        ("close > 14", False),
        ("close >= 14", True),
        ("close >= 14.5", False),
    ],
)
def test_comparison_operators_use_last_bar(rule, fired):
    result = run_one(rule, CLOSES)
    assert result["fired"] is fired
    assert result["left"] == 14.0
    assert result["reason"] is None


def test_indicator_values_are_reported():
    # sma(3) of 12, 13, 14 = 13.
    result = run_one("close > sma(3)", CLOSES)
    assert result["fired"] is True
    assert (result["left"], result["right"]) == (14.0, 13.0)


def test_crosses_above_needs_below_or_equal_before_and_above_now():
    # sma(2): 12.5 -> 11.5 -> ... build: closes 10, 10, 8, 12.
    # sma(2) before last = (10+8)/2 = 9, close before = 8 (<= 9); last sma = 10, close = 12 (> 10).
    closes = [10.0, 10.0, 8.0, 12.0]
    result = run_one("close crosses_above sma(2)", closes)
    assert result["fired"] is True
    assert (result["prev_left"], result["prev_right"]) == (8.0, 9.0)
    assert (result["left"], result["right"]) == (12.0, 10.0)


def test_crosses_above_does_not_fire_if_already_above():
    result = run_one("close crosses_above 11", [10.0, 12.0, 13.0])
    assert result["fired"] is False


def test_crosses_above_fires_from_equal():
    assert run_one("close crosses_above 10", [10.0, 11.0])["fired"] is True


def test_crosses_below_needs_above_or_equal_before_and_below_now():
    assert run_one("close crosses_below 10", [11.0, 9.0])["fired"] is True
    assert run_one("close crosses_below 10", [10.0, 9.0])["fired"] is True
    assert run_one("close crosses_below 10", [9.0, 8.0])["fired"] is False
    assert run_one("close crosses_below 10", [11.0, 10.0])["fired"] is False


def test_cross_with_one_bar_is_not_enough_data():
    result = run_one("close crosses_above 10", [11.0])
    assert result["fired"] is False
    assert result["reason"] == "not enough data"


def test_warmup_means_not_fired_with_reason():
    result = run_one("sma(10) > 0", CLOSES)
    assert result["fired"] is False
    assert result["reason"] == "not enough data"
    assert result["left"] is None


def test_cross_with_previous_bar_still_in_warmup():
    # sma(4) first exists on bar index 3, so the previous bar of a 4-bar series has none.
    result = run_one("close crosses_above sma(4)", [1.0, 2.0, 3.0, 9.0])
    assert result["fired"] is False and result["reason"] == "not enough data"


def test_rsi_all_gains_is_100():
    result = run_one("rsi(3) >= 100", [1.0, 2.0, 3.0, 4.0, 5.0])
    assert result["fired"] is True and result["left"] == 100.0


def test_ema_rule_hand_worked():
    # ema(2) seed (1+2)/2 = 1.5; alpha 2/3; next = 2/3*3 + 1/3*1.5 = 2.5.
    result = run_one("ema(2) < 2.6", [1.0, 2.0, 3.0])
    assert result["left"] == pytest.approx(2.5)
    assert result["fired"] is True


def test_empty_prices_are_not_enough_data():
    assert run_one("close > 1", [])["reason"] == "not enough data"


def test_results_follow_rule_order_and_keep_line_numbers():
    results = evaluate(parse_rules("\nclose > 1\nclose < 1\n"), [5.0])
    assert [(r["line"], r["fired"]) for r in results] == [(2, True), (3, False)]


# ----------------------------------------------------------------------- CLI


def prices(tmp_path, closes=CLOSES):
    return write(tmp_path, "prices.csv", "date,close\n" + "".join(f"2026-01-{i + 1:02d},{c}\n" for i, c in enumerate(closes)))


def test_cli_prints_only_fired_rules_exit_0(tmp_path, capsys):
    rules = write(tmp_path, "rules.txt", "close > 13\nclose < 5\n")
    assert main([rules, prices(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "1 of 2 rules fired" in out
    assert "FIRED  close > 13" in out
    assert "close < 5" not in out
    assert out.rstrip().endswith(DISCLAIMER)


def test_cli_exit_0_when_nothing_fires(tmp_path, capsys):
    rules = write(tmp_path, "rules.txt", "close < 5\n")
    assert main([rules, prices(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "No rules fired." in out and DISCLAIMER in out


def test_cli_all_prints_every_rule_with_status(tmp_path, capsys):
    rules = write(tmp_path, "rules.txt", "close > 13\nclose < 5\nsma(50) > 1\n")
    assert main([rules, prices(tmp_path), "--all"]) == 0
    out = capsys.readouterr().out
    assert "FIRED  close > 13" in out
    assert "no     close < 5" in out
    assert "sma(50) > 1  (not enough data)" in out


def test_cli_bad_rules_file_exit_1_with_line_number(tmp_path, capsys):
    rules = write(tmp_path, "rules.txt", "close > 1\nnonsense\n")
    assert main([rules, prices(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error: ") and "line 2: unexpected token 'nonsense'" in err
    assert err.count("\n") == 1 and "Traceback" not in err


def test_cli_no_rules_exit_1(tmp_path, capsys):
    rules = write(tmp_path, "rules.txt", "# nothing\n\n")
    assert main([rules, prices(tmp_path)]) == 1
    assert "no rules found" in capsys.readouterr().err


def test_cli_missing_files_exit_1(tmp_path, capsys):
    rules = write(tmp_path, "rules.txt", "close > 1\n")
    assert main([str(tmp_path / "nope.txt"), prices(tmp_path)]) == 1
    assert capsys.readouterr().err.startswith("Error: ")
    assert main([rules, str(tmp_path / "nope.csv")]) == 1
    assert capsys.readouterr().err.startswith("Error: ")


def test_cli_bad_price_file_exit_1(tmp_path, capsys):
    rules = write(tmp_path, "rules.txt", "close > 1\n")
    bad = write(tmp_path, "bad.csv", "date,open\n2026-01-01,5\n")
    assert main([rules, bad]) == 1
    assert capsys.readouterr().err.startswith("Error: ")


def test_cli_usage_error_exit_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as info:
        main([str(tmp_path / "rules.txt")])
    assert info.value.code == 2


def test_module_runs_as_subprocess(tmp_path):
    rules = write(tmp_path, "rules.txt", "close > 13\n")
    proc = subprocess.run(
        [sys.executable, "-m", "trading_assistant.alerts", rules, prices(tmp_path)],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(SRC_DIR), "PATH": ""},
    )
    assert proc.returncode == 0
    assert "FIRED  close > 13" in proc.stdout
