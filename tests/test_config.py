"""Tests for the settings file (trading_assistant.config and cli --config)."""

import pytest

from trading_assistant.cli import CONFIG_ENV_VAR, DISCLAIMER, analyse, main
from trading_assistant.config import ConfigError, load_config

CLOSES = [float(100 + i % 7 + i // 3) for i in range(60)]


@pytest.fixture(autouse=True)
def no_env_config(monkeypatch):
    monkeypatch.delenv(CONFIG_ENV_VAR, raising=False)


@pytest.fixture
def prices(tmp_path):
    path = tmp_path / "p.csv"
    path.write_text("date,close\n" + "".join(f"2026-01-{i + 1:02d},{c}\n" for i, c in enumerate(CLOSES)))
    return str(path)


def write_config(tmp_path, text, name="settings.ini"):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def run(capsys, argv):
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out.splitlines(), captured.err


# --------------------------------------------------------------------------- loading


def test_load_config_reads_every_key(tmp_path):
    path = write_config(
        tmp_path,
        "[cli]\nshort = 3\nlong = 9\nrsi_period = 7\ncash = 5000\nfee = 1.5\nfee_pct = 0.1\n"
        "strategy = breakout\nstats = yes\n\n[strategy.breakout]\nwindow = 12\n",
    )
    assert load_config(path) == {
        "cli": {
            "short": 3, "long": 9, "rsi_period": 7, "cash": 5000.0, "fee": 1.5, "fee_pct": 0.1,
            "strategy": "breakout", "stats": True,
        },
        "strategy": {"breakout": {"window": 12}},
    }


def test_empty_file_is_fine(tmp_path):
    assert load_config(write_config(tmp_path, "")) == {"cli": {}, "strategy": {}}


# --------------------------------------------------------------------------- precedence


def test_config_sets_defaults(tmp_path, prices, capsys):
    cfg = write_config(tmp_path, "[cli]\nshort = 3\nlong = 6\ncash = 5000\n")
    code, out, _ = run(capsys, [prices, "--backtest", "--config", cfg])
    assert code == 0
    expected, _ = analyse(CLOSES, short=3, long=6, backtest=True, cash=5000.0)
    assert out == expected + [DISCLAIMER]
    assert "  Start cash:  5,000.00" in out


def test_flags_beat_config(tmp_path, prices, capsys):
    cfg = write_config(tmp_path, "[cli]\nshort = 3\nlong = 6\ncash = 5000\n")
    code, out, _ = run(capsys, [prices, "--backtest", "--config", cfg, "--short", "2", "--cash", "2000"])
    assert code == 0
    expected, _ = analyse(CLOSES, short=2, long=6, backtest=True, cash=2000.0)
    assert out == expected + [DISCLAIMER]


def test_flag_equal_to_builtin_default_still_beats_config(tmp_path, prices, capsys):
    cfg = write_config(tmp_path, "[cli]\nshort = 3\nlong = 6\nrsi_period = 5\n")
    code, out, _ = run(capsys, [prices, "--config", cfg, "--rsi-period", "14"])
    expected, _ = analyse(CLOSES, short=3, long=6, rsi_period=14)
    assert code == 0 and out == expected + [DISCLAIMER]


def test_config_beats_builtin_defaults_for_strategy_and_params(tmp_path, prices, capsys):
    cfg = write_config(tmp_path, "[cli]\nstrategy = breakout\n[strategy.breakout]\nwindow = 7\n")
    code, out, _ = run(capsys, [prices, "--backtest", "--config", cfg])
    expected, _ = analyse(CLOSES, backtest=True, strategy="breakout", strategy_params={"window": 7})
    assert code == 0 and out == expected + [DISCLAIMER]


def test_param_flag_beats_config_param(tmp_path, prices, capsys):
    cfg = write_config(tmp_path, "[cli]\nstrategy = breakout\n[strategy.breakout]\nwindow = 7\n")
    code, out, _ = run(capsys, [prices, "--backtest", "--config", cfg, "--param", "window=9"])
    expected, _ = analyse(CLOSES, backtest=True, strategy="breakout", strategy_params={"window": 9})
    assert code == 0 and out == expected + [DISCLAIMER]


def test_strategy_flag_beats_config_strategy(tmp_path, prices, capsys):
    cfg = write_config(tmp_path, "[cli]\nstrategy = breakout\n[strategy.breakout]\nwindow = 7\n")
    code, out, _ = run(capsys, [prices, "--backtest", "--config", cfg, "--strategy", "sma_cross", "--short", "3", "--long", "6"])
    expected, _ = analyse(CLOSES, short=3, long=6, backtest=True)
    assert code == 0 and out == expected + [DISCLAIMER]


def test_stats_from_config(tmp_path, prices, capsys):
    cfg = write_config(tmp_path, "[cli]\nstats = true\n")
    code, out, _ = run(capsys, [prices, "--backtest", "--config", cfg])
    assert code == 0 and any("Risk and return" in line for line in out)


def test_backtest_only_settings_are_ignored_without_backtest(tmp_path, prices, capsys):
    cfg = write_config(tmp_path, "[cli]\ncash = 5000\nfee = 1\nstats = yes\nstrategy = breakout\n")
    code, out, _ = run(capsys, [prices, "--config", cfg])
    expected, _ = analyse(CLOSES)
    assert code == 0 and out == expected + [DISCLAIMER]


# --------------------------------------------------------------------------- no config


def test_no_config_output_is_unchanged(tmp_path, prices, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_config(tmp_path, "[cli]\nshort = 2\ncash = 1\n", name="trading_assistant.ini")
    code, out, _ = run(capsys, [prices, "--backtest"])
    expected, _ = analyse(CLOSES, backtest=True)
    assert code == 0 and out == expected + [DISCLAIMER]


# --------------------------------------------------------------------------- env var


def test_env_var_names_the_file(tmp_path, prices, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_config(tmp_path, "[cli]\nshort = 3\nlong = 6\n", name="trading_assistant.ini")
    monkeypatch.setenv(CONFIG_ENV_VAR, "trading_assistant.ini")
    code, out, _ = run(capsys, [prices])
    expected, _ = analyse(CLOSES, short=3, long=6)
    assert code == 0 and out == expected + [DISCLAIMER]


def test_config_flag_beats_env_var(tmp_path, prices, capsys, monkeypatch):
    env_file = write_config(tmp_path, "[cli]\nshort = 2\nlong = 4\n", name="env.ini")
    flag_file = write_config(tmp_path, "[cli]\nshort = 3\nlong = 6\n", name="flag.ini")
    monkeypatch.setenv(CONFIG_ENV_VAR, env_file)
    code, out, _ = run(capsys, [prices, "--config", flag_file])
    expected, _ = analyse(CLOSES, short=3, long=6)
    assert code == 0 and out == expected + [DISCLAIMER]


def test_env_var_naming_a_missing_file_is_a_data_problem(tmp_path, prices, capsys, monkeypatch):
    monkeypatch.setenv(CONFIG_ENV_VAR, str(tmp_path / "nope.ini"))
    code, _, err = run(capsys, [prices])
    assert code == 1 and err.startswith("Error: cannot read config ")


def test_blank_env_var_reads_nothing(tmp_path, prices, capsys, monkeypatch):
    monkeypatch.setenv(CONFIG_ENV_VAR, "  ")
    code, out, _ = run(capsys, [prices])
    expected, _ = analyse(CLOSES)
    assert code == 0 and out == expected + [DISCLAIMER]


# --------------------------------------------------------------------------- data problems (exit 1)


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("[cli]\nspeed = 3\n", "line 2: unknown key 'speed' in [cli]"),
        ("[cli]\nshort = 3\n[extra]\nx = 1\n", "line 3: unknown section [extra]"),
        ("[cli]\nshort = ten\n", "line 2: short needs a whole number, got 'ten'"),
        ("[cli]\nshort = 2.5\n", "line 2: short needs a whole number"),
        ("[cli]\ncash = lots\n", "line 2: cash needs a number, got 'lots'"),
        ("[cli]\ncash = nan\n", "line 2: cash needs a finite number"),
        ("[cli]\nstats = maybe\n", "line 2: stats needs yes or no, got 'maybe'"),
        ("[cli]\nstrategy = magic\n", "line 2: unknown strategy 'magic'"),
        ("[strategy.magic]\nwindow = 3\n", "line 1: unknown strategy 'magic'"),
        ("[strategy.breakout]\nwindw = 3\n", "line 2: unknown parameter 'windw' for strategy 'breakout'"),
        ("[strategy.breakout]\nwindow = big\n", "line 2: window needs a number, got 'big'"),
        ("[cli]\nshort = 3\nshort = 4\n", "line 3:"),
        ("short = 3\n", "line 1:"),
        ("[cli\nshort = 3\n", "line 1:"),
        ("[DEFAULT]\nshort = 3\n", "[DEFAULT] section is not supported"),
    ],
)
def test_bad_config_is_exit_1_with_file_and_line(tmp_path, prices, capsys, text, fragment):
    cfg = write_config(tmp_path, text)
    code, out, err = run(capsys, [prices, "--backtest", "--config", cfg])
    assert code == 1
    assert out == []
    assert err.count("\n") == 1 and "Traceback" not in err
    assert err.startswith(f"Error: {cfg}")
    assert fragment in err


def test_missing_config_file_is_exit_1(tmp_path, prices, capsys):
    missing = str(tmp_path / "nope.ini")
    code, _, err = run(capsys, [prices, "--config", missing])
    assert code == 1 and err == f"Error: cannot read config {missing}: No such file or directory\n"


def test_unreadable_config_directory_is_exit_1(tmp_path, prices, capsys):
    code, _, err = run(capsys, [prices, "--config", str(tmp_path)])
    assert code == 1 and err.startswith("Error: cannot read config ")


def test_non_text_config_is_exit_1(tmp_path, prices, capsys):
    path = tmp_path / "bin.ini"
    path.write_bytes(b"\xff\xfe\x00[cli]")
    code, _, err = run(capsys, [prices, "--config", str(path)])
    assert code == 1 and "not valid UTF-8" in err


def test_load_config_raises_config_error(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write_config(tmp_path, "[nope]\n"))


# --------------------------------------------------------------------------- same validation as flags (exit 2)


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("[cli]\nshort = 30\nlong = 10\n", "--short (30) must be smaller than --long (10)"),
        ("[cli]\nshort = 0\n", "--short must be at least 1"),
        ("[cli]\nrsi_period = 0\n", "--rsi-period must be at least 1"),
        ("[cli]\ncash = 0\n", "--cash must be positive"),
        ("[cli]\nfee = -1\n", "--fee must not be negative"),
        ("[cli]\nfee_pct = 100\n", "--fee-pct must be between 0 and 100"),
        ("[cli]\nstrategy = breakout\n[strategy.breakout]\nwindow = 0\n", "window must be a whole number"),
        ("[strategy.sma_cross]\nshort = 50\nlong = 20\n", "short window must be smaller"),
    ],
)
def test_out_of_range_config_values_are_usage_errors(tmp_path, prices, capsys, text, fragment):
    cfg = write_config(tmp_path, text)
    with pytest.raises(SystemExit) as info:
        main([prices, "--backtest", "--config", cfg])
    assert info.value.code == 2
    assert fragment in capsys.readouterr().err


def test_config_short_not_below_flag_long_is_usage_error(tmp_path, prices, capsys):
    cfg = write_config(tmp_path, "[cli]\nshort = 30\n")
    with pytest.raises(SystemExit) as info:
        main([prices, "--config", cfg, "--long", "10"])
    assert info.value.code == 2
    assert "--short (30) must be smaller than --long (10)" in capsys.readouterr().err


def test_bad_flags_are_still_exit_2_even_with_a_bad_config(tmp_path, prices, capsys):
    cfg = write_config(tmp_path, "[nope]\n")
    with pytest.raises(SystemExit) as info:
        main([prices, "--config", cfg, "--resample", "daily"])
    assert info.value.code == 2
