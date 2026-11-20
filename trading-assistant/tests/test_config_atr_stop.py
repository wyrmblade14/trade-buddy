"""The ATR stop from the config file: [cli] atr_stop (yes/no), with atr_mult and atr_period.

atr_stop follows the rules of the other backtest keys: used only with
--backtest (ignored otherwise, and with --scan), a candle file is needed, it
cannot go with --resample, and a wrong value is a file error (exit 1) like
stats. It is a switch like stats: "yes" turns the ATR stop on; "no" leaves it
as the command line has it, so --atr-stop wins over "atr_stop = no" (there is
no flag to turn it off). atr_mult and atr_period from the file now count when
risk sizing or the ATR stop is on, from the file or from the command line, and
are ignored quietly otherwise. For each of them a flag wins over the file.

Hand case (the candle file of test_cli_risk_sizing.py), cash 1000, short 1,
long 2: BUY signal on bar 3, ATR(3) there = 25/18; BUY 90 @ 11 on bar 4.
    atr_stop, mult 2, period 3: level 11 - 2 * 25/18 = 8.2222; bar 7 (open 8.6, low 7.5)
                                -> SELL 90 @ 8.22, reason atr, end equity 750
    mult 1:  level 9.6111; bar 7 opens at 8.6 below it      -> SELL 90 @ 8.60, end equity 784
    mult 3:  level 6.8333; never reached                    -> signal SELL 90 @ 8.00, end equity 730
    period 5 (or the default 14): no ATR on bar 3 yet       -> buy skipped (1)
    with risk_pct 2: 7 shares, sold @ 8.22                  -> end equity 980.56

The BEFORE_RUNS output was captured from the command before the atr_stop key existed.
"""

import pytest

from trading_assistant.cli import CONFIG_ENV_VAR, main
from trading_assistant.config import load_config

HAND = """\
date,open,high,low,close,volume
2026-01-01,10,10.5,9.5,10,1000
2026-01-02,9.2,9.5,8.5,9,1000
2026-01-03,8.3,8.5,7.5,8,1000
2026-01-04,8.8,9.5,8.5,9,1000
2026-01-05,10.8,11.5,10.5,11,1000
2026-01-06,12.2,13,11.2,12,1000
2026-01-07,11.5,12.5,9.8,10,1000
2026-01-08,8.6,9,7.5,8,1000
"""
CLOSES_ONLY = "date,close\n" + "".join(f"2026-01-0{i + 1},{c}\n" for i, c in enumerate([10, 9, 8, 9, 11, 12, 10, 8]))
BASE = "[cli]\nshort = 1\nlong = 2\ncash = 1000\n"
ATR_FILE = BASE + "atr_stop = yes\natr_mult = 2\natr_period = 3\n"
BASE_FLAGS = ["--short", "1", "--long", "2", "--cash", "1000"]
ATR_FLAGS = BASE_FLAGS + ["--atr-stop", "--atr-mult", "2", "--atr-period", "3"]

NEW_KEY_LIST = (
    "choose from: short, long, rsi_period, cash, fee, fee_pct, slippage, position_size, stop_loss, take_profit, "
    "trailing_stop, risk_pct, atr_mult, atr_period, atr_stop, cooldown, min_hold, max_hold, max_drawdown, breakeven, max_losses, scale_out, add_on, max_adds, fill, strategy, stats, trade_list, explain, top, min_score\n"
)

# (config text, arguments after the price file, stdout); all exit 0 with an empty stderr.
BEFORE_RUNS = [
    (
        "[cli]\nshort = 1\nlong = 2\ncash = 1000\natr_mult = 3\natr_period = 5\n",
        ["--backtest"],
        (
            "Bars:    8\n"
            "Last:    8.00\n"
            "Signal:  HOLD\n"
            "RSI:     n/a\n"
            "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n"
            "  Start cash:  1,000.00\n"
            "  Trades:      2 (1 buy, 1 sell)\n"
            "  Fills (bar index is 0-based):\n"
            "    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00\n"
            "    #2   bar 7     SELL       90 @       8.00  value       720.00  cost     0.00  cash       730.00\n"
            "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n"
            "  Round trips: 1 completed, 0 made money (0%)\n"
            "  Comparison              Strategy    Buy & hold\n"
            "    End equity              730.00        800.00\n"
            "    Return                 -27.00%       -20.00%\n"
            "    Max drawdown           -33.03%       -33.33%\n"
            "    Trades                       2             1\n"
            "    Costs paid                0.00          0.00\n"
            "  End cash:    730.00\n"
            "  End shares:  0 @ 8.00\n"
            "  End equity:  730.00\n"
            "  Return:      -27.00%\n"
            "Research aid only. Not financial advice.\n"
        ),
    ),
    (
        "[cli]\nshort = 1\nlong = 2\ncash = 1000\natr_mult = 0\natr_period = 0\nstop_loss = 5\n",
        ["--backtest"],
        (
            "Bars:    8\n"
            "Last:    8.00\n"
            "Signal:  HOLD\n"
            "RSI:     n/a\n"
            "Backtest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n"
            "  Start cash:  1,000.00\n"
            "  Trades:      2 (1 buy, 1 sell)\n"
            "  Fills (bar index is 0-based):\n"
            "    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00  signal\n"
            "    #2   bar 6     SELL       90 @      10.45  value       940.50  cost     0.00  cash       950.50  stop\n"
            "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n"
            "  Exits:       stop 5.00% below entry\n"
            "  Round trips: 1 completed, 0 made money (0%)\n"
            "  Comparison              Strategy    Buy & hold\n"
            "    End equity              950.50        800.00\n"
            "    Return                  -4.95%       -20.00%\n"
            "    Max drawdown           -12.80%       -33.33%\n"
            "    Trades                       2             1\n"
            "    Costs paid                0.00          0.00\n"
            "  End cash:    950.50\n"
            "  End shares:  0 @ 8.00\n"
            "  End equity:  950.50\n"
            "  Return:      -4.95%\n"
            "Research aid only. Not financial advice.\n"
        ),
    ),
    (
        "[cli]\nshort = 1\nlong = 2\ncash = 1000\nrisk_pct = 2\natr_mult = 1.5\natr_period = 3\ntrailing_stop = 8\nstats = no\n",
        ["--backtest", "--json"],
        (
            "{\n"
            "  \"bars\": 8,\n"
            "  \"last_close\": 8.0,\n"
            "  \"signal\": \"HOLD\",\n"
            "  \"rsi\": null,\n"
            "  \"rsi_label\": null,\n"
            "  \"backtest\": {\n"
            "    \"strategy\": \"sma_cross\",\n"
            "    \"params\": {\n"
            "      \"short\": 1,\n"
            "      \"long\": 2\n"
            "    },\n"
            "    \"fill\": \"close\",\n"
            "    \"start_cash\": 1000.0,\n"
            "    \"fee\": 0.0,\n"
            "    \"fee_pct\": 0.0,\n"
            "    \"slippage_pct\": 0.0,\n"
            "    \"position_size\": null,\n"
            "    \"risk_pct\": 2.0,\n"
            "    \"atr_mult\": 1.5,\n"
            "    \"atr_period\": 3,\n"
            "    \"stop_loss_pct\": null,\n"
            "    \"take_profit_pct\": null,\n"
            "    \"trailing_stop_pct\": 8.0,\n"
            "    \"trades\": 2,\n"
            "    \"buys\": 1,\n"
            "    \"sells\": 1,\n"
            "    \"risk_skipped_buys\": 0,\n"
            "    \"fills\": [\n"
            "      {\n"
            "        \"bar\": 4,\n"
            "        \"side\": \"BUY\",\n"
            "        \"shares\": 9,\n"
            "        \"price\": 11.0,\n"
            "        \"value\": 99.0,\n"
            "        \"cost\": 0.0,\n"
            "        \"cash_after\": 901.0,\n"
            "        \"reason\": \"signal\"\n"
            "      },\n"
            "      {\n"
            "        \"bar\": 6,\n"
            "        \"side\": \"SELL\",\n"
            "        \"shares\": 9,\n"
            "        \"price\": 11.5,\n"
            "        \"value\": 103.5,\n"
            "        \"cost\": 0.0,\n"
            "        \"cash_after\": 1004.5,\n"
            "        \"reason\": \"trail\"\n"
            "      }\n"
            "    ],\n"
            "    \"total_costs\": 0.0,\n"
            "    \"round_trips\": 1,\n"
            "    \"winning_round_trips\": 1,\n"
            "    \"final_cash\": 1004.5,\n"
            "    \"final_position\": 0,\n"
            "    \"final_price\": 8.0,\n"
            "    \"final_equity\": 1004.5,\n"
            "    \"return_pct\": 0.44999999999999996,\n"
            "    \"max_drawdown_pct\": -0.44598612487611494,\n"
            "    \"benchmark\": {\n"
            "      \"shares\": 100,\n"
            "      \"final_cash\": 0.0,\n"
            "      \"final_equity\": 800.0,\n"
            "      \"return_pct\": -20.0,\n"
            "      \"max_drawdown_pct\": -33.33333333333333,\n"
            "      \"trades\": 1,\n"
            "      \"total_costs\": 0.0\n"
            "    }\n"
            "  },\n"
            "  \"disclaimer\": \"Research aid only. Not financial advice.\"\n"
            "}\n"
        ),
    ),
    (
        "[cli]\nshort = 1\nlong = 2\ncash = 1000\nrisk_pct = 2\natr_period = 3\nstats = yes\nfill = open\n",
        ["--backtest", "--atr-mult", "1"],
        (
            "Bars:    8\n"
            "Last:    8.00\n"
            "Signal:  HOLD\n"
            "RSI:     n/a\n"
            "Backtest: SMA 1/2 crossover, next-bar open fills, whole shares, no shorting\n"
            "  Start cash:  1,000.00\n"
            "  Trades:      2 (1 buy, 1 sell)\n"
            "  Fills (bar index is 0-based):\n"
            "    #1   bar 4     BUY        14 @      10.80  value       151.20  cost     0.00  cash       848.80\n"
            "    #2   bar 7     SELL       14 @       8.60  value       120.40  cost     0.00  cash       969.20\n"
            "  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n"
            "  Risk sizing: 2.00% of account value at risk per buy, stop distance 1 x ATR(3) (this only sets the number of shares; no stop is placed)\n"
            "  Round trips: 1 completed, 0 made money (0%)\n"
            "  Comparison              Strategy    Buy & hold\n"
            "    End equity              969.20        800.00\n"
            "    Return                  -3.08%       -20.00%\n"
            "    Max drawdown            -4.68%       -33.33%\n"
            "    Trades                       2             1\n"
            "    Costs paid                0.00          0.00\n"
            "  End cash:    969.20\n"
            "  End shares:  0 @ 8.00\n"
            "  End equity:  969.20\n"
            "  Return:      -3.08%\n"
            "Risk and return\n"
            "  Total return:       -3.08%\n"
            "  CAGR:               -67.57%\n"
            "  Volatility (ann.):  22.64%\n"
            "  Sharpe ratio:       -4.87\n"
            "  Sortino ratio:      -5.41\n"
            "  Exposure:           37.50%\n"
            "  Profit factor:      0.00\n"
            "  Average win:        n/a\n"
            "  Average loss:       -30.80\n"
            "  Longest drawdown:   2 bars\n"
            "Research aid only. Not financial advice.\n"
        ),
    ),
]


@pytest.fixture
def folder(tmp_path, monkeypatch):
    (tmp_path / "hand.csv").write_text(HAND)
    (tmp_path / "closes.csv").write_text(CLOSES_ONLY)
    (tmp_path / "scan").mkdir()
    (tmp_path / "scan" / "a.csv").write_text(CLOSES_ONLY)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.delenv(CONFIG_ENV_VAR, raising=False)
    return tmp_path


def run(argv, capsys):
    try:
        code = main(argv)
    except SystemExit as exc:
        code = exc.code
    out, err = capsys.readouterr()
    return code, out, err


def with_config(text, argv, capsys, folder):
    (folder / "c.ini").write_text(text)
    return run([argv[0], "--config", "c.ini", *argv[1:]], capsys)


def sell_line(out):
    return next(line for line in out.splitlines() if " SELL " in line)


# --------------------------------------------------------------------------- reading the key


@pytest.mark.parametrize(
    "raw, value",
    [("yes", True), ("no", False), ("true", True), ("false", False), ("1", True), ("0", False),
     ("on", True), ("off", False), ("YES", True), ("False", False)],
)
def test_atr_stop_is_read_as_yes_or_no(folder, raw, value):
    (folder / "c.ini").write_text(f"[cli]\natr_stop = {raw}\natr_mult = 1.5\natr_period = 3\n")
    cli = load_config("c.ini")["cli"]
    assert cli == {"atr_stop": value, "atr_mult": 1.5, "atr_period": 3}
    assert type(cli["atr_stop"]) is bool


# --------------------------------------------------------------------------- file == flags


@pytest.mark.parametrize("extra", [[], ["--json"], ["--stats", "--fill", "open", "--trailing-stop", "8"], ["--risk-pct", "2"]])
def test_the_keys_in_the_file_give_the_same_result_as_the_flags(folder, capsys, extra):
    from_file = with_config(ATR_FILE, ["hand.csv", "--backtest", *extra], capsys, folder)
    from_flags = run(["hand.csv", "--backtest", *ATR_FLAGS, *extra], capsys)
    assert from_file == from_flags
    assert from_file[0] == 0


def test_hand_case_from_the_file(folder, capsys):
    code, out, err = with_config(ATR_FILE, ["hand.csv", "--backtest"], capsys, folder)
    assert (code, err) == (0, "")
    assert "    #1   bar 4     BUY        90 @      11.00" in out
    assert sell_line(out).startswith("    #2   bar 7     SELL       90 @       8.22") and sell_line(out).endswith("  atr")
    assert "  Exits:       atr 2 x ATR(3) below entry\n" in out
    assert "  End equity:  750.00\n" in out and "Skipped:" not in out


def test_hand_case_with_risk_pct_from_the_file(folder, capsys):
    code, out, _ = with_config(ATR_FILE + "risk_pct = 2\n", ["hand.csv", "--backtest"], capsys, folder)
    assert code == 0
    assert sell_line(out).startswith("    #2   bar 7     SELL        7 @       8.22")
    assert "(the ATR stop sells at this distance, as of the buy that opened the position, below the average entry price; a gap, slippage, fees or a later buy can lose more)" in out
    assert "  End equity:  980.56\n" in out


def test_json_from_the_file(folder, capsys):
    code, out, _ = with_config(ATR_FILE, ["hand.csv", "--backtest", "--json"], capsys, folder)
    assert code == 0
    assert '    "atr_mult": 2.0,\n    "atr_period": 3,\n' in out and '    "atr_stop": true,\n' in out


def test_the_environment_variable_file_works_like_config(folder, capsys, monkeypatch):
    (folder / "env.ini").write_text(ATR_FILE)
    monkeypatch.setenv(CONFIG_ENV_VAR, "env.ini")
    from_env = run(["hand.csv", "--backtest"], capsys)
    monkeypatch.delenv(CONFIG_ENV_VAR)
    assert from_env == run(["hand.csv", "--backtest", *ATR_FLAGS], capsys)


# --------------------------------------------------------------------------- file and command line together


def test_defaults_apply_when_only_atr_stop_is_in_the_file(folder, capsys):
    code, out, _ = with_config(BASE + "atr_stop = yes\n", ["hand.csv", "--backtest"], capsys, folder)
    assert code == 0
    assert "  Exits:       atr 2 x ATR(14) below entry\n" in out
    assert "  Skipped:     1 buy (ATR stop: no usable ATR on the signal bar)\n" in out


def test_the_flag_wins_over_atr_stop_no(folder, capsys):
    text = BASE + "atr_stop = no\natr_mult = 2\natr_period = 3\n"
    from_file = with_config(text, ["hand.csv", "--backtest", "--atr-stop"], capsys, folder)
    assert from_file == run(["hand.csv", "--backtest", *ATR_FLAGS], capsys)
    assert "  atr" in sell_line(from_file[1])


def test_atr_stop_no_alone_changes_nothing(folder, capsys):
    plain = run(["hand.csv", "--backtest", *BASE_FLAGS], capsys)
    for text in (BASE + "atr_stop = no\n", BASE + "atr_stop = no\natr_mult = 3\natr_period = 5\n"):
        assert with_config(text, ["hand.csv", "--backtest"], capsys, folder) == plain
    assert plain[0] == 0 and "Exits" not in plain[1]


@pytest.mark.parametrize(
    "flag, level_line",
    [
        (["--atr-mult", "1"], "    #2   bar 7     SELL       90 @       8.60"),  # gap below 9.61
        (["--atr-mult", "3"], "    #2   bar 7     SELL       90 @       8.00"),  # level 6.83 never reached
        (["--atr-period", "5"], None),  # no ATR(5) on the signal bar: skipped
    ],
)
def test_a_flag_wins_over_the_file_for_its_own_key(folder, capsys, flag, level_line):
    code, out, _ = with_config(ATR_FILE, ["hand.csv", "--backtest", *flag], capsys, folder)
    assert code == 0
    # The other keys still come from the file.
    assert out == run(["hand.csv", "--backtest", *ATR_FLAGS, *flag], capsys)[1]
    if level_line:
        assert sell_line(out).startswith(level_line)
    else:
        assert "  Skipped:     1 buy " in out and " BUY " not in out


def test_file_atr_keys_count_with_the_atr_stop_flag(folder, capsys):
    # The file has no atr_stop and no risk_pct: --atr-stop on the command line makes atr_mult/atr_period count.
    text = BASE + "atr_mult = 1\natr_period = 3\n"
    code, out, _ = with_config(text, ["hand.csv", "--backtest", "--atr-stop"], capsys, folder)
    assert code == 0
    assert "  Exits:       atr 1 x ATR(3) below entry\n" in out
    assert out == run(["hand.csv", "--backtest", *BASE_FLAGS, "--atr-stop", "--atr-mult", "1", "--atr-period", "3"], capsys)[1]


def test_file_atr_stop_lets_atr_flags_be_used_without_risk_pct(folder, capsys):
    code, out, err = with_config(BASE + "atr_stop = yes\n", ["hand.csv", "--backtest", "--atr-mult", "2", "--atr-period", "3"], capsys, folder)
    assert (code, err) == (0, "")
    assert out == run(["hand.csv", "--backtest", *ATR_FLAGS], capsys)[1]


# --------------------------------------------------------------------------- ignored quietly


def test_file_atr_keys_without_risk_pct_or_atr_stop_are_ignored_quietly(folder, capsys):
    plain = with_config(BASE, ["hand.csv", "--backtest"], capsys, folder)
    for keys in ("atr_mult = 3\natr_period = 5\n", "atr_mult = 0\natr_period = 0\n", "atr_stop = no\natr_mult = 0\n"):
        assert with_config(BASE + keys, ["hand.csv", "--backtest"], capsys, folder) == plain
    assert plain[0] == 0 and plain[2] == ""


def test_ignored_without_backtest_and_with_scan(folder, capsys):
    plain = run(["closes.csv", "--short", "1", "--long", "2"], capsys)
    assert with_config(ATR_FILE, ["closes.csv"], capsys, folder) == plain  # not even the candle file is needed
    (folder / "c.ini").write_text(ATR_FILE)
    assert run(["--scan", "scan", "--config", "c.ini"], capsys) == run(
        ["--scan", "scan", "--short", "1", "--long", "2"], capsys
    )


# --------------------------------------------------------------------------- errors


@pytest.mark.parametrize(
    "keys, flags",
    [
        ("atr_stop = yes\natr_mult = 0\n", ["--atr-stop", "--atr-mult", "0"]),
        ("atr_stop = yes\natr_mult = -2\n", ["--atr-stop", "--atr-mult", "-2"]),
        ("atr_stop = yes\natr_period = 0\n", ["--atr-stop", "--atr-period", "0"]),
    ],
)
def test_range_errors_are_the_flag_errors(folder, capsys, keys, flags):
    from_file = with_config(BASE + keys, ["hand.csv", "--backtest"], capsys, folder)
    from_flags = run(["hand.csv", "--backtest", *BASE_FLAGS, *flags], capsys)
    assert from_file == from_flags
    assert from_file[0] == 2 and from_file[1] == ""


def test_file_atr_keys_are_range_checked_with_the_atr_stop_flag(folder, capsys):
    code, out, err = with_config(BASE + "atr_mult = 0\n", ["hand.csv", "--backtest", "--atr-stop"], capsys, folder)
    assert (code, out) == (2, "")
    assert err.endswith("trading_assistant.cli: error: --atr-mult must be above 0, got 0\n")


@pytest.mark.parametrize(
    "keys, message",
    [
        ("atr_stop = maybe\n", "c.ini line 5: atr_stop needs yes or no, got 'maybe'"),
        ("atr_stop = 2\n", "c.ini line 5: atr_stop needs yes or no, got '2'"),
        ("atr_stop =\n", "c.ini line 5: atr_stop needs yes or no, got ''"),
        ("atr_stop = yes\natr_stop = no\n", "c.ini line 6: While reading from 'c.ini' [line  6]: option 'atr_stop' in section 'cli' already exists"),
    ],
)
def test_wrong_kind_of_value_is_a_file_error_like_stats(folder, capsys, keys, message):
    code, out, err = with_config(BASE + keys, ["hand.csv", "--backtest"], capsys, folder)
    assert (code, out, err) == (1, "", f"Error: {message}\n")
    # the same kind of error as stats
    stats = with_config(BASE + keys.replace("atr_stop", "stats"), ["hand.csv", "--backtest"], capsys, folder)
    assert stats == (1, "", f"Error: {message}\n".replace("atr_stop", "stats"))


def test_a_wrong_value_is_an_error_even_without_backtest(folder, capsys):
    # Like every key, the file is type-checked when it is read, before it is known what is used.
    code, _, err = with_config(BASE + "atr_stop = maybe\n", ["closes.csv"], capsys, folder)
    assert (code, err) == (1, "Error: c.ini line 5: atr_stop needs yes or no, got 'maybe'\n")


def test_needs_a_candle_file_like_the_flag(folder, capsys):
    from_file = with_config(BASE + "atr_stop = yes\n", ["closes.csv", "--backtest"], capsys, folder)
    assert from_file == run(["closes.csv", "--backtest", *BASE_FLAGS, "--atr-stop"], capsys)
    assert from_file[0] == 1 and from_file[2].startswith("Error: closes.csv has no 'open', 'high', 'low', 'volume' columns")


def test_cannot_go_with_resample(folder, capsys):
    code, out, err = with_config(BASE + "atr_stop = yes\n", ["closes.csv", "--backtest", "--resample", "weekly"], capsys, folder)
    assert (code, out) == (2, "")
    assert err.endswith("trading_assistant.cli: error: --atr-stop cannot be combined with --resample yet\n")


def test_atr_stop_no_goes_with_resample(folder, capsys):
    plain = run(["closes.csv", "--backtest", *BASE_FLAGS, "--resample", "weekly"], capsys)
    assert with_config(BASE + "atr_stop = no\n", ["closes.csv", "--backtest", "--resample", "weekly"], capsys, folder) == plain
    assert plain[0] == 0


def test_unknown_key_message_lists_atr_stop_after_atr_period(folder, capsys):
    code, out, err = with_config("[cli]\natr_stp = yes\n", ["hand.csv", "--backtest"], capsys, folder)
    assert (code, out) == (1, "")
    assert err == "Error: c.ini line 2: unknown key 'atr_stp' in [cli]; " + NEW_KEY_LIST


# --------------------------------------------------------------------------- old config files: unchanged


@pytest.mark.parametrize("text, argv, out", BEFORE_RUNS, ids=["atr keys ignored", "atr keys 0 ignored", "risk json", "risk, flag wins"])
def test_old_config_files_behave_the_same(folder, capsys, text, argv, out):
    assert with_config(text, ["hand.csv", *argv], capsys, folder) == (0, out, "")
