"""Command line: --strategy, --param and --stats."""

import pytest

from trading_assistant.backtest import format_result, format_stats, run_backtest
from trading_assistant.cli import DISCLAIMER, load_closes, main

# 60 daily closes: a dip, then a steady rise.
OK_CSV_TEXT = """\
date,close
2026-01-02,99.50
2026-01-05,99.25
2026-01-06,99.00
2026-01-07,98.50
2026-01-08,98.25
2026-01-09,98.00
2026-01-12,97.50
2026-01-13,97.25
2026-01-14,97.00
2026-01-15,96.50
2026-01-16,96.25
2026-01-19,96.00
2026-01-20,95.50
2026-01-21,95.25
2026-01-22,95.00
2026-01-23,94.50
2026-01-26,94.25
2026-01-27,94.00
2026-01-28,93.50
2026-01-29,93.25
2026-01-30,93.00
2026-02-02,92.50
2026-02-03,92.25
2026-02-04,92.00
2026-02-05,91.50
2026-02-06,91.25
2026-02-09,91.00
2026-02-10,90.50
2026-02-11,90.25
2026-02-12,90.00
2026-02-13,89.50
2026-02-16,89.25
2026-02-17,89.00
2026-02-18,88.50
2026-02-19,88.25
2026-02-20,88.00
2026-02-23,87.50
2026-02-24,87.25
2026-02-25,87.00
2026-02-26,86.50
2026-02-27,86.25
2026-03-02,86.00
2026-03-03,85.50
2026-03-04,85.25
2026-03-05,85.00
2026-03-06,86.30
2026-03-09,87.15
2026-03-10,88.45
2026-03-11,89.30
2026-03-12,90.60
2026-03-13,91.45
2026-03-16,92.75
2026-03-17,93.60
2026-03-18,94.90
2026-03-19,95.75
2026-03-20,97.05
2026-03-23,97.90
2026-03-24,99.20
2026-03-25,100.05
2026-03-26,101.35
"""
OK_CSV = None


@pytest.fixture(autouse=True, scope="module")
def _ok_csv(tmp_path_factory):
    global OK_CSV
    path = tmp_path_factory.mktemp("data") / "ok.csv"
    path.write_text(OK_CSV_TEXT)
    OK_CSV = str(path)


def run(capsys, *args):
    code = main([OK_CSV, *args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def exit_code_of(*args):
    with pytest.raises(SystemExit) as info:
        main([OK_CSV, *args])
    return info.value.code


def test_strategy_without_backtest_is_usage_error(capsys):
    assert exit_code_of("--strategy", "breakout") == 2
    assert "--strategy only makes sense together with --backtest" in capsys.readouterr().err


def test_param_without_backtest_is_usage_error(capsys):
    assert exit_code_of("--param", "window=5") == 2
    assert "--param only makes sense" in capsys.readouterr().err


def test_stats_without_backtest_is_usage_error():
    assert exit_code_of("--stats") == 2


def test_unknown_strategy_is_usage_error(capsys):
    assert exit_code_of("--backtest", "--strategy", "nope") == 2
    assert "invalid choice" in capsys.readouterr().err


@pytest.mark.parametrize(
    "param,fragment",
    [
        ("window", "KEY=VALUE"),
        ("=5", "KEY=VALUE"),
        ("window=", "KEY=VALUE"),
        ("window=abc", "needs a number"),
        ("window=nan", "finite"),
        ("bogus=1", "unknown parameter"),
        ("window=0", "window"),
        ("window=2.5", "window"),
    ],
)
def test_bad_param_is_usage_error(capsys, param, fragment):
    assert exit_code_of("--backtest", "--strategy", "breakout", "--param", param) == 2
    assert fragment in capsys.readouterr().err


def test_duplicate_param_is_usage_error(capsys):
    assert exit_code_of("--backtest", "--strategy", "breakout", "--param", "window=5", "--param", "window=6") == 2


def test_param_for_other_strategy_is_unknown(capsys):
    assert exit_code_of("--backtest", "--strategy", "breakout", "--param", "short=3") == 2
    assert "unknown parameter" in capsys.readouterr().err


def test_bad_threshold_pair_is_usage_error(capsys):
    assert exit_code_of("--backtest", "--strategy", "rsi_reversion", "--param", "oversold=80", "--param", "overbought=20") == 2
    assert "thresholds" in capsys.readouterr().err


def test_sma_param_conflicting_with_explicit_short_is_usage_error(capsys):
    assert exit_code_of("--backtest", "--short", "5", "--param", "short=6") == 2
    assert "contradicts" in capsys.readouterr().err


def test_sma_param_equal_to_explicit_short_is_fine(capsys):
    code, out, _ = run(capsys, "--backtest", "--short", "5", "--long", "10", "--param", "short=5")
    assert code == 0
    assert "SMA 5/10" in out


def test_sma_param_alone_sets_windows(capsys):
    code, out, _ = run(capsys, "--backtest", "--param", "short=3", "--param", "long=8")
    direct = run_backtest(load_closes(OK_CSV), short=3, long=8)
    assert code == 0
    assert "\n".join(format_result(direct, 3, 8)) in out


@pytest.mark.parametrize(
    "name,args,params",
    [
        ("rsi_reversion", [], {}),
        ("rsi_reversion", ["--param", "period=5", "--param", "oversold=35"], {"period": 5, "oversold": 35}),
        ("breakout", [], {}),
        ("breakout", ["--param", "window=10"], {"window": 10}),
    ],
)
def test_strategy_backtest_matches_run_backtest(capsys, name, args, params):
    code, out, _ = run(capsys, "--backtest", "--strategy", name, *args)
    direct = run_backtest(load_closes(OK_CSV), strategy=name, strategy_params=params or None)
    assert code == 0
    assert f"Backtest: {name} (" in out
    assert "\n".join(format_result(direct, 20, 50)) in out
    assert f"  End equity:  {direct.final_equity:,.2f}" in out


def test_signal_line_unchanged_by_strategy(capsys):
    _, plain, _ = run(capsys, "--backtest")
    _, other, _ = run(capsys, "--backtest", "--strategy", "breakout")
    assert [l for l in plain.splitlines() if l.startswith("Signal:")] == [
        l for l in other.splitlines() if l.startswith("Signal:")
    ]


def test_stats_block_appears_before_disclaimer(capsys):
    code, out, _ = run(capsys, "--backtest", "--strategy", "breakout", "--param", "window=10", "--stats")
    direct = run_backtest(load_closes(OK_CSV), strategy="breakout", strategy_params={"window": 10})
    assert code == 0
    assert "\n".join(format_stats(direct)) + "\n" + DISCLAIMER + "\n" == out[out.index("Risk and return"):]


def test_stats_block_absent_by_default(capsys):
    _, out, _ = run(capsys, "--backtest")
    assert "Risk and return" not in out


def test_default_output_unchanged_with_explicit_default_strategy(capsys):
    _, plain, _ = run(capsys, "--backtest", "--short", "5", "--long", "10")
    _, explicit, _ = run(capsys, "--backtest", "--short", "5", "--long", "10", "--strategy", "sma_cross")
    assert plain == explicit


def test_analysis_only_output_unchanged(capsys):
    code, out, err = run(capsys)
    assert code == 0 and err == ""
    assert "Backtest" not in out and "Risk and return" not in out


def test_strategy_with_stats_and_export(capsys, tmp_path):
    target = tmp_path / "out.csv"
    code, out, _ = run(capsys, "--backtest", "--strategy", "breakout", "--stats", "--export", str(target))
    assert code == 0
    assert target.exists()
    assert out.index("Exported:") < out.index("Risk and return") < out.index(DISCLAIMER)
