"""Config keys for the later backtest options: slippage, position_size, fill, stop_loss, take_profit.

They behave like the older backtest-only keys (cash, fee, ...): used only with
--backtest, a flag written on the command line wins over the file, the file
wins over the built-in default, range rules are the flags' rules (exit 2),
and a value of the wrong kind is a config error (exit 1) naming file and line.
A config ``fill = open``, ``stop_loss`` or ``take_profit`` reads the file as a
candle file exactly as the flags do.

Hand-worked run, everything from the file (short=2, long=3, cash 10,000):

    [cli]
    fill = open
    slippage = 1
    position_size = 0.5
    stop_loss = 10
    (take_profit = 20 in the second case)

Candles (the series of test_stop_take_profit.py):

    bar   open  high   low  close
     4     12    15    11     14      BUY signal
     5     13    15  12.9     14      BUY fills at this open
     6     14    17    12     14
     7      9    10   7.5      8      opens below the stop (gap), SELL signal
     8      7     9   6.9      8

BUY bar 5 at the open 13, slipped 1 % -> 13.13. Budget 0.5 * 10,000 = 5,000:
    floor(5,000 / 13.13) = 380 shares (381 would cost 5,002.53), value 4,989.40, cash 5,010.60.
    Entry 13.13 -> stop level 13.13 * 0.9 = 11.817, target level 13.13 * 1.2 = 15.756.

Stop only: bar 6 opens 14, low 12 -> above 11.817, nothing. Bar 7 opens at 9 <= 11.817 (gap):
    the stop fills at the open 9, slipped 1 % -> 8.91; 380 * 8.91 = 3,385.80, cash 8,396.40.
    The SELL signal due at bar 8 finds no position. End equity 8,396.40, return -16.04 %.
Stop and target: bar 6 opens 14 (between the levels), high 17 >= 15.756, low 12 > 11.817:
    target at the level 15.756, slipped 1 % -> 15.59844; 380 * 15.59844 = 5,927.4072,
    cash 5,010.60 + 5,927.4072 = 10,938.0072 (report: 15.60, 5,927.41, 10,938.01).
Buy & hold (open fill + 1 % slippage, all-in): 9 * 1.01 = 9.09 -> 1,100 shares, cash 1,
    end 1 + 1,100 * 8 = 8,801.00.
"""

import pytest

from trading_assistant.cli import CONFIG_ENV_VAR, DISCLAIMER, analyse, main
from trading_assistant.config import ConfigError, load_config

OPENS = [9.0, 9.0, 9.0, 9.0, 12.0, 13.0, 14.0, 9.0, 7.0, 8.0]
HIGHS = [11.0, 11.0, 11.0, 11.0, 15.0, 15.0, 17.0, 10.0, 9.0, 9.0]
LOWS = [8.0, 8.0, 8.0, 8.0, 11.0, 12.9, 12.0, 7.5, 6.9, 7.5]
CLOSES = [10.0, 10.0, 10.0, 10.0, 14.0, 14.0, 14.0, 8.0, 8.0, 8.0]
SMA = ["--short", "2", "--long", "3"]

# key -> (config value, a different flag value); both valid
NEW_KEYS = {
    "slippage": ("2", "1"),
    "position_size": ("0.25", "0.5"),
    "fill": ("open", "close"),
    "stop_loss": ("50", "10"),
    "take_profit": ("50", "20"),
}


@pytest.fixture(autouse=True)
def no_env_config(monkeypatch):
    monkeypatch.delenv(CONFIG_ENV_VAR, raising=False)


@pytest.fixture
def candles(tmp_path):
    rows = ["date,open,high,low,close,volume"]
    for t in range(len(CLOSES)):
        rows.append(f"2026-01-{t + 1:02d},{OPENS[t]},{HIGHS[t]},{LOWS[t]},{CLOSES[t]},{(t + 1) * 1000}")
    path = tmp_path / "candles.csv"
    path.write_text("\n".join(rows) + "\n")
    return str(path)


@pytest.fixture
def closes_only(tmp_path):
    path = tmp_path / "closes.csv"
    path.write_text("date,close\n" + "".join(f"2026-01-{t + 1:02d},{c}\n" for t, c in enumerate(CLOSES)))
    return str(path)


def write_config(tmp_path, text):
    path = tmp_path / "settings.ini"
    path.write_text(text)
    return str(path)


def flag(key):
    return "--" + key.replace("_", "-")


def run(capsys, argv):
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out.splitlines(), captured.err


def fill_lines(out):
    return [line.split() for line in out if line.startswith("    #")]


# --------------------------------------------------------------------------- loading


def test_load_config_reads_the_new_keys_with_their_types(tmp_path):
    path = write_config(
        tmp_path, "[cli]\nslippage = 0.5\nposition_size = 1\nfill = open\nstop_loss = 8\ntake_profit = 12.5\n"
    )
    cli = load_config(path)["cli"]
    assert cli == {"slippage": 0.5, "position_size": 1.0, "fill": "open", "stop_loss": 8.0, "take_profit": 12.5}
    assert all(isinstance(cli[k], float) for k in ("slippage", "position_size", "stop_loss", "take_profit"))


def test_unknown_key_message_lists_the_new_keys(tmp_path):
    with pytest.raises(ConfigError) as excinfo:
        load_config(write_config(tmp_path, "[cli]\nspeed = 3\n"))
    assert str(excinfo.value).endswith(
        "unknown key 'speed' in [cli]; choose from: short, long, rsi_period, cash, fee, fee_pct, "
        "slippage, position_size, stop_loss, take_profit, trailing_stop, risk_pct, atr_mult, atr_period, atr_stop, cooldown, min_hold, max_hold, max_drawdown, breakeven, max_losses, scale_out, add_on, max_adds, fill, "
        "strategy, stats, trade_list, explain, top, min_score"
    )


# --------------------------------------------------------------------------- file beats default, flag beats file


@pytest.mark.parametrize("key", list(NEW_KEYS))
def test_config_value_acts_exactly_like_the_flag(tmp_path, candles, capsys, key):
    value = NEW_KEYS[key][0]
    cfg = write_config(tmp_path, f"[cli]\n{key} = {value}\n")
    from_file = run(capsys, [candles, "--backtest", *SMA, "--config", cfg])
    from_flag = run(capsys, [candles, "--backtest", *SMA, flag(key), value])
    default = run(capsys, [candles, "--backtest", *SMA])
    assert from_file[0] == 0 and from_file == from_flag
    assert from_file[1] != default[1]  # the file really beat the built-in default


@pytest.mark.parametrize("key", list(NEW_KEYS))
def test_flag_on_the_command_line_beats_the_config_value(tmp_path, candles, capsys, key):
    file_value, flag_value = NEW_KEYS[key]
    cfg = write_config(tmp_path, f"[cli]\n{key} = {file_value}\n")
    both = run(capsys, [candles, "--backtest", *SMA, "--config", cfg, flag(key), flag_value])
    flag_only = run(capsys, [candles, "--backtest", *SMA, flag(key), flag_value])
    file_only = run(capsys, [candles, "--backtest", *SMA, "--config", cfg])
    assert both[0] == 0 and both == flag_only
    assert both[1] != file_only[1]  # the two values really give different reports


def test_fill_close_flag_beats_config_fill_open_and_the_file_is_read_as_closes(tmp_path, closes_only, capsys):
    # --fill close equals the built-in default, but written on the command line it still wins, so a
    # close-only file is fine (fill = open from the file would have needed a candle file)
    cfg = write_config(tmp_path, "[cli]\nfill = open\n")
    code, out, err = run(capsys, [closes_only, "--backtest", *SMA, "--config", cfg, "--fill", "close"])
    expected, _ = analyse(CLOSES, short=2, long=3, backtest=True)
    assert code == 0 and err == "" and out == expected + [DISCLAIMER]


# --------------------------------------------------------------------------- backtest-only


def test_new_keys_are_ignored_without_backtest(tmp_path, closes_only, capsys):
    cfg = write_config(
        tmp_path, "[cli]\nslippage = 1\nposition_size = 0.5\nfill = open\nstop_loss = 10\ntake_profit = 20\n"
    )
    code, out, err = run(capsys, [closes_only, *SMA, "--config", cfg])
    expected, _ = analyse(CLOSES, short=2, long=3)
    # no usage error, and a close-only file is fine: the candle-reading keys do nothing without --backtest
    assert code == 0 and err == "" and out == expected + [DISCLAIMER]


def test_a_config_without_the_new_keys_gives_the_same_report_as_before(tmp_path, candles, capsys):
    cfg = write_config(tmp_path, "[cli]\ncash = 5000\nfee = 1\n")
    with_cfg = run(capsys, [candles, "--backtest", *SMA, "--config", cfg])
    flags = run(capsys, [candles, "--backtest", *SMA, "--cash", "5000", "--fee", "1"])
    assert with_cfg[0] == 0 and with_cfg == flags
    assert not any("Slippage" in l or "Sizing" in l or "Exits" in l or "open fills" in l for l in with_cfg[1])


# --------------------------------------------------------------------------- candle file, exactly like the flags


@pytest.mark.parametrize("key, value", [("fill", "open"), ("stop_loss", "10"), ("take_profit", "20")])
def test_candle_keys_read_the_file_as_candles_like_the_flags(tmp_path, closes_only, capsys, key, value):
    cfg = write_config(tmp_path, f"[cli]\n{key} = {value}\n")
    from_file = run(capsys, [closes_only, "--backtest", *SMA, "--config", cfg])
    from_flag = run(capsys, [closes_only, "--backtest", *SMA, flag(key), value])
    assert from_file == from_flag
    code, out, err = from_file
    assert code == 1 and out == []
    assert err.startswith(f"Error: {closes_only} has no 'open', 'high', 'low', 'volume' columns")


@pytest.mark.parametrize(
    "key, value, message",
    [
        ("fill", "open", "--fill open cannot be combined with --resample yet"),
        ("stop_loss", "10", "--stop-loss cannot be combined with --resample yet"),
        ("take_profit", "20", "--take-profit cannot be combined with --resample yet"),
    ],
)
def test_candle_keys_with_resample_are_usage_errors(tmp_path, closes_only, capsys, key, value, message):
    cfg = write_config(tmp_path, f"[cli]\n{key} = {value}\n")
    with pytest.raises(SystemExit) as info:
        main([closes_only, "--backtest", *SMA, "--config", cfg, "--resample", "weekly"])
    assert info.value.code == 2
    assert capsys.readouterr().err.splitlines()[-1] == f"trading_assistant.cli: error: {message}"


# --------------------------------------------------------------------------- out of range: usage error (exit 2)


@pytest.mark.parametrize(
    "key, value, message",
    [
        ("slippage", "100", "--slippage must be between 0 and 100 (exclusive), got 100"),
        ("slippage", "-1", "--slippage must be between 0 and 100 (exclusive), got -1"),
        ("position_size", "0", "--position-size must be above 0 and at most 1, got 0"),
        ("position_size", "1.5", "--position-size must be above 0 and at most 1, got 1.5"),
        ("stop_loss", "0", "--stop-loss must be between 0 and 100 (both exclusive), got 0"),
        ("stop_loss", "100", "--stop-loss must be between 0 and 100 (both exclusive), got 100"),
        ("take_profit", "0", "--take-profit must be positive, got 0"),
        ("take_profit", "-5", "--take-profit must be positive, got -5"),
    ],
)
def test_out_of_range_values_are_usage_errors_like_the_flags(tmp_path, candles, capsys, key, value, message):
    cfg = write_config(tmp_path, f"[cli]\n{key} = {value}\n")
    with pytest.raises(SystemExit) as info:
        main([candles, "--backtest", *SMA, "--config", cfg])
    assert info.value.code == 2
    file_err = capsys.readouterr().err
    assert file_err.splitlines()[-1] == f"trading_assistant.cli: error: {message}"
    with pytest.raises(SystemExit) as info:
        main([candles, "--backtest", *SMA, flag(key), value])
    assert info.value.code == 2 and capsys.readouterr().err == file_err  # identical to the flag


# --------------------------------------------------------------------------- wrong kind: config error (exit 1)


@pytest.mark.parametrize(
    "key, value, fragment",
    [
        ("slippage", "lots", "slippage needs a number, got 'lots'"),
        ("slippage", "nan", "slippage needs a finite number, got 'nan'"),
        ("position_size", "half", "position_size needs a number, got 'half'"),
        ("position_size", "inf", "position_size needs a finite number, got 'inf'"),
        ("stop_loss", "10%", "stop_loss needs a number, got '10%'"),
        ("take_profit", "-inf", "take_profit needs a finite number, got '-inf'"),
        ("fill", "midday", "unknown fill 'midday'; choose from: close, open"),
        ("fill", "Open", "unknown fill 'Open'; choose from: close, open"),
        ("fill", "", "unknown fill ''; choose from: close, open"),
    ],
)
def test_wrong_kind_of_value_is_a_config_error_with_file_and_line(tmp_path, candles, capsys, key, value, fragment):
    cfg = write_config(tmp_path, f"[cli]\ncash = 5000\n{key} = {value}\n")
    code, out, err = run(capsys, [candles, "--backtest", *SMA, "--config", cfg])
    assert code == 1 and out == []
    assert err == f"Error: {cfg} line 3: {fragment}\n"


# --------------------------------------------------------------------------- hand-worked run, all from the file


def test_hand_worked_run_with_every_new_key_from_the_file(tmp_path, candles, capsys):
    cfg = write_config(tmp_path, "[cli]\nfill = open\nslippage = 1\nposition_size = 0.5\nstop_loss = 10\n")
    code, out, err = run(capsys, [candles, "--backtest", *SMA, "--config", cfg])
    assert code == 0 and err == ""
    assert fill_lines(out) == [
        ["#1", "bar", "5", "BUY", "380", "@", "13.13", "value", "4,989.40", "cost", "0.00", "cash", "5,010.60", "signal"],
        ["#2", "bar", "7", "SELL", "380", "@", "8.91", "value", "3,385.80", "cost", "0.00", "cash", "8,396.40", "stop"],
    ]
    assert "Backtest: SMA 2/3 crossover, next-bar open fills, whole shares, no shorting" in out
    assert f"    {'End equity':<16s}{'8,396.40':>14s}{'8,801.00':>14s}" in out
    assert f"    {'Return':<16s}{'-16.04%':>14s}{'-11.99%':>14s}" in out
    assert "  End cash:    8,396.40" in out
    flags = run(capsys, [candles, "--backtest", *SMA, "--fill", "open", "--slippage", "1", "--position-size", "0.5", "--stop-loss", "10"])
    assert flags == (code, out, err)


def test_hand_worked_run_with_target_from_the_file(tmp_path, candles, capsys):
    cfg = write_config(
        tmp_path, "[cli]\nfill = open\nslippage = 1\nposition_size = 0.5\nstop_loss = 10\ntake_profit = 20\n"
    )
    code, out, err = run(capsys, [candles, "--backtest", *SMA, "--config", cfg])
    assert code == 0 and err == ""
    assert fill_lines(out)[1] == [
        "#2", "bar", "6", "SELL", "380", "@", "15.60", "value", "5,927.41", "cost", "0.00", "cash", "10,938.01", "target",
    ]
    assert "  End cash:    10,938.01" in out
