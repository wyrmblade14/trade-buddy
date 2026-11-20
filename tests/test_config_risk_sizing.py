"""Risk sizing from the config file: [cli] risk_pct, atr_mult (numbers) and atr_period (whole number).

They follow the rules of the other backtest keys: used only with --backtest
(ignored otherwise, and with --scan), a candle file is needed, they cannot go
with --resample, the same range rules as --risk-pct/--atr-mult/--atr-period,
and a flag wins over the file for each key on its own.

Hand case (the candle file of test_cli_risk_sizing.py), cash 1000, short 1,
long 2: BUY signal on bar 3, ATR(3) there = 25/18.
    risk 2, mult 2, period 3: 20 / (2 * 25/18) = 7.2   -> 7 shares @ 11
    risk 4, mult 2, period 3: 40 / 2.7778     = 14.4  -> 14 shares
    risk 2, mult 1, period 3: 20 / 1.3889     = 14.4  -> 14 shares
    risk 2, mult 3, period 3: 20 / 4.1667     = 4.8   -> 4 shares
    period 5: no ATR on bar 3 yet                     -> buy skipped (1)

The expected output of the old config files was captured from the command
before these keys existed.
"""

import pytest

from trading_assistant.cli import main
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
RISK = BASE + "risk_pct = 2\natr_mult = 2\natr_period = 3\n"
FLAGS = ["--short", "1", "--long", "2", "--cash", "1000", "--risk-pct", "2", "--atr-mult", "2", "--atr-period", "3"]


@pytest.fixture
def folder(tmp_path, monkeypatch):
    (tmp_path / "hand.csv").write_text(HAND)
    (tmp_path / "closes.csv").write_text(CLOSES_ONLY)
    (tmp_path / "scan").mkdir()
    (tmp_path / "scan" / "a.csv").write_text(CLOSES_ONLY)
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


def with_config(text, argv, capsys, folder):
    (folder / "c.ini").write_text(text)
    return run([argv[0], "--config", "c.ini", *argv[1:]], capsys)


def buy_line(out):
    return next(line for line in out.splitlines() if " BUY " in line)


# --------------------------------------------------------------------------- reading the keys


def test_keys_are_read_as_numbers_and_a_whole_number(folder):
    (folder / "c.ini").write_text("[cli]\nrisk_pct = 2\natr_mult = 1.5\natr_period = 3\n")
    cli = load_config("c.ini")["cli"]
    assert cli == {"risk_pct": 2.0, "atr_mult": 1.5, "atr_period": 3}
    assert type(cli["risk_pct"]) is float and type(cli["atr_mult"]) is float and type(cli["atr_period"]) is int


# --------------------------------------------------------------------------- file == flags


@pytest.mark.parametrize("extra", [[], ["--json"], ["--stats", "--fill", "open", "--trailing-stop", "8"]])
def test_three_keys_in_the_file_give_the_same_result_as_the_flags(folder, capsys, extra):
    from_file = with_config(RISK, ["hand.csv", "--backtest", *extra], capsys, folder)
    from_flags = run(["hand.csv", "--backtest", *FLAGS, *extra], capsys)
    assert from_file == from_flags
    assert from_file[0] == 0


def test_hand_case_from_the_file(folder, capsys):
    code, out, err = with_config(RISK, ["hand.csv", "--backtest"], capsys, folder)
    assert (code, err) == (0, "")
    assert "    #1   bar 4     BUY         7 @      11.00" in out
    assert "    #2   bar 7     SELL        7 @       8.00" in out
    assert "  Risk sizing: 2.00% of account value at risk per buy, stop distance 2 x ATR(3) " in out
    assert "  End equity:  979.00\n" in out and "Skipped:" not in out


# --------------------------------------------------------------------------- a flag wins, one key at a time


@pytest.mark.parametrize(
    "flag, expected",
    [
        (["--risk-pct", "4"], "BUY        14 @      11.00"),
        (["--atr-mult", "1"], "BUY        14 @      11.00"),
        (["--atr-period", "5"], None),  # no ATR(5) on the signal bar: skipped
    ],
)
def test_a_flag_wins_over_the_file_for_its_own_key(folder, capsys, flag, expected):
    code, out, _ = with_config(RISK, ["hand.csv", "--backtest", *flag], capsys, folder)
    assert code == 0
    # The other two keys still come from the file.
    assert out == run(["hand.csv", "--backtest", *FLAGS, *flag], capsys)[1]
    if expected:
        assert expected in buy_line(out)
    else:
        assert "  Skipped:     1 buy " in out and " BUY " not in out


def test_file_key_is_used_next_to_flags_for_the_other_keys(folder, capsys):
    code, out, _ = with_config(BASE + "atr_mult = 3\n", ["hand.csv", "--backtest", "--risk-pct", "2", "--atr-period", "3"], capsys, folder)
    assert code == 0
    assert "BUY         4 @      11.00" in buy_line(out)
    assert "stop distance 3 x ATR(3)" in out


def test_defaults_apply_when_only_risk_pct_is_in_the_file(folder, capsys):
    code, out, _ = with_config(BASE + "risk_pct = 2\n", ["hand.csv", "--backtest"], capsys, folder)
    assert code == 0 and "stop distance 2 x ATR(14)" in out


# --------------------------------------------------------------------------- errors


@pytest.mark.parametrize(
    "keys, flags",
    [
        ("risk_pct = 0\n", ["--risk-pct", "0"]),
        ("risk_pct = -1\n", ["--risk-pct", "-1"]),
        ("risk_pct = 100.5\n", ["--risk-pct", "100.5"]),
        ("risk_pct = 2\natr_mult = 0\n", ["--risk-pct", "2", "--atr-mult", "0"]),
        ("risk_pct = 2\natr_mult = -2\n", ["--risk-pct", "2", "--atr-mult", "-2"]),
        ("risk_pct = 2\natr_period = 0\n", ["--risk-pct", "2", "--atr-period", "0"]),
    ],
)
def test_range_errors_are_the_flag_errors(folder, capsys, keys, flags):
    from_file = with_config(BASE + keys, ["hand.csv", "--backtest"], capsys, folder)
    from_flags = run(["hand.csv", "--backtest", "--short", "1", "--long", "2", "--cash", "1000", *flags], capsys)
    assert from_file == from_flags
    assert from_file[0] == 2 and from_file[1] == ""


@pytest.mark.parametrize(
    "keys, message",
    [
        ("risk_pct = abc\n", "c.ini line 5: risk_pct needs a number, got 'abc'"),
        ("risk_pct = inf\n", "c.ini line 5: risk_pct needs a finite number, got 'inf'"),
        ("risk_pct = 2\natr_mult = x\n", "c.ini line 6: atr_mult needs a number, got 'x'"),
        ("risk_pct = 2\natr_mult = nan\n", "c.ini line 6: atr_mult needs a finite number, got 'nan'"),
        ("risk_pct = 2\natr_period = 1.5\n", "c.ini line 6: atr_period needs a whole number, got '1.5'"),
        ("risk_pct = 2\nrisk_pct = 3\n", "c.ini line 6: While reading from 'c.ini' [line  6]: option 'risk_pct' in section 'cli' already exists"),
    ],
)
def test_wrong_kind_of_value_is_a_file_error(folder, capsys, keys, message):
    code, out, err = with_config(BASE + keys, ["hand.csv", "--backtest"], capsys, folder)
    assert (code, out, err) == (1, "", f"Error: {message}\n")


def test_needs_a_candle_file_like_the_flag(folder, capsys):
    from_file = with_config(BASE + "risk_pct = 2\n", ["closes.csv", "--backtest"], capsys, folder)
    assert from_file == run(["closes.csv", "--backtest", "--short", "1", "--long", "2", "--risk-pct", "2"], capsys)
    assert from_file[0] == 1 and from_file[2].startswith("Error: closes.csv has no 'open', 'high', 'low', 'volume' columns")


def test_cannot_go_with_resample(folder, capsys):
    code, out, err = with_config(BASE + "risk_pct = 2\n", ["closes.csv", "--backtest", "--resample", "weekly"], capsys, folder)
    assert (code, out) == (2, "")
    assert err.endswith("trading_assistant.cli: error: --risk-pct cannot be combined with --resample yet\n")


def test_ignored_without_backtest_and_with_scan(folder, capsys):
    plain = run(["closes.csv", "--short", "1", "--long", "2"], capsys)
    assert with_config(RISK, ["closes.csv"], capsys, folder) == plain  # not even the candle file is needed
    (folder / "c.ini").write_text(RISK)
    assert run(["--scan", "scan", "--config", "c.ini"], capsys) == run(
        ["--scan", "scan", "--short", "1", "--long", "2"], capsys
    )


# --------------------------------------------------------------------------- old config files: unchanged

OLD_RUNS = [  # (config text, price file, extra args, exit code, stdout, stderr) captured before the new keys
    ("[cli]\nshort = 1\nlong = 2\ncash = 1000\n", "hand.csv", ["--backtest"], 0, "Bars:    8\nLast:    8.00\nSignal:  HOLD\nRSI:     n/a\nBacktest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n  Start cash:  1,000.00\n  Trades:      2 (1 buy, 1 sell)\n  Fills (bar index is 0-based):\n    #1   bar 4     BUY        90 @      11.00  value       990.00  cost     0.00  cash        10.00\n    #2   bar 7     SELL       90 @       8.00  value       720.00  cost     0.00  cash       730.00\n  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n  Round trips: 1 completed, 0 made money (0%)\n  Comparison              Strategy    Buy & hold\n    End equity              730.00        800.00\n    Return                 -27.00%       -20.00%\n    Max drawdown           -33.03%       -33.33%\n    Trades                       2             1\n    Costs paid                0.00          0.00\n  End cash:    730.00\n  End shares:  0 @ 8.00\n  End equity:  730.00\n  Return:      -27.00%\nResearch aid only. Not financial advice.\n", ""),
    ("[cli]\nshort = 1\nlong = 2\nrsi_period = 3\ncash = 1000\nfee = 1\nfee_pct = 0.1\nslippage = 0.5\nposition_size = 0.5\nfill = open\nstop_loss = 5\ntake_profit = 20\ntrailing_stop = 8\nstats = yes\n", "hand.csv", ["--backtest"], 0, "Bars:    8\nLast:    8.00\nSignal:  HOLD\nRSI:     24.9 (oversold)\nBacktest: SMA 1/2 crossover, next-bar open fills, whole shares, no shorting\n  Start cash:  1,000.00\n  Trades:      2 (1 buy, 1 sell)\n  Fills (bar index is 0-based):\n    #1   bar 4     BUY        45 @      10.85  value       488.43  cost     1.49  cash       510.08  signal\n    #2   bar 6     SELL       45 @      11.44  value       514.91  cost     1.51  cash     1,023.48  trail\n  Costs:       3.00 paid (fee 1.00 per trade + 0.10% of value)\n  Slippage:    0.50% (buys fill higher, sells lower, before fees)\n  Sizing:      each buy at most 50% of account value (costs and slippage included)\n  Exits:       stop 5.00% below entry, trail 8.00% below the highest high since entry, target 20.00% above entry (the higher of stop and trail is used; it wins if a bar also touches the target)\n  Round trips: 1 completed, 1 made money (100%)\n  Comparison              Strategy    Buy & hold\n    End equity            1,023.48        795.06\n    Return                  +2.35%       -20.49%\n    Max drawdown            -2.53%       -33.25%\n    Trades                       2             1\n    Costs paid                3.00          1.99\n  End cash:    1,023.48\n  End shares:  0 @ 8.00\n  End equity:  1,023.48\n  Return:      +2.35%\nRisk and return\n  Total return:       +2.35%\n  CAGR:               130.59%\n  Volatility (ann.):  32.96%\n  Sharpe ratio:       2.68\n  Sortino ratio:      5.81\n  Exposure:           25.00%\n  Profit factor:      n/a\n  Average win:        23.48\n  Average loss:       n/a\n  Longest drawdown:   2 bars\nResearch aid only. Not financial advice.\n", ""),
    ("[cli]\nshort = 1\nlong = 2\nrsi_period = 3\ncash = 1000\nfee = 1\nfee_pct = 0.1\nslippage = 0.5\nposition_size = 0.5\nfill = open\nstop_loss = 5\ntake_profit = 20\ntrailing_stop = 8\nstats = yes\n", "hand.csv", ["--backtest", "--json"], 0, "{\n  \"bars\": 8,\n  \"last_close\": 8.0,\n  \"signal\": \"HOLD\",\n  \"rsi\": 24.875621890547265,\n  \"rsi_label\": \"oversold\",\n  \"backtest\": {\n    \"strategy\": \"sma_cross\",\n    \"params\": {\n      \"short\": 1,\n      \"long\": 2\n    },\n    \"fill\": \"open\",\n    \"start_cash\": 1000.0,\n    \"fee\": 1.0,\n    \"fee_pct\": 0.1,\n    \"slippage_pct\": 0.5,\n    \"position_size\": 0.5,\n    \"stop_loss_pct\": 5.0,\n    \"take_profit_pct\": 20.0,\n    \"trailing_stop_pct\": 8.0,\n    \"trades\": 2,\n    \"buys\": 1,\n    \"sells\": 1,\n    \"fills\": [\n      {\n        \"bar\": 4,\n        \"side\": \"BUY\",\n        \"shares\": 45,\n        \"price\": 10.854,\n        \"value\": 488.42999999999995,\n        \"cost\": 1.48843,\n        \"cash_after\": 510.08157000000006,\n        \"reason\": \"signal\"\n      },\n      {\n        \"bar\": 6,\n        \"side\": \"SELL\",\n        \"shares\": 45,\n        \"price\": 11.4425,\n        \"value\": 514.9125,\n        \"cost\": 1.5149125,\n        \"cash_after\": 1023.4791575,\n        \"reason\": \"trail\"\n      }\n    ],\n    \"total_costs\": 3.0033425,\n    \"round_trips\": 1,\n    \"winning_round_trips\": 1,\n    \"final_cash\": 1023.4791575,\n    \"final_position\": 0,\n    \"final_price\": 8.0,\n    \"final_equity\": 1023.4791575,\n    \"return_pct\": 2.3479157500000043,\n    \"max_drawdown_pct\": -2.5333662888683985,\n    \"benchmark\": {\n      \"shares\": 99,\n      \"final_cash\": 3.055050000000051,\n      \"final_equity\": 795.05505,\n      \"return_pct\": -20.494494999999997,\n      \"max_drawdown_pct\": -33.24783350693991,\n      \"trades\": 1,\n      \"total_costs\": 1.99495\n    },\n    \"stats\": {\n      \"total_return_pct\": 2.347915749999996,\n      \"cagr_pct\": 130.591931188765,\n      \"annualized_volatility_pct\": 32.95824298406118,\n      \"sharpe_ratio\": 2.67834099575222,\n      \"sortino_ratio\": 5.807385856521357,\n      \"exposure_pct\": 25.0,\n      \"profit_factor\": null,\n      \"average_win\": 23.479157500000042,\n      \"average_loss\": null,\n      \"longest_drawdown_bars\": 2\n    }\n  },\n  \"disclaimer\": \"Research aid only. Not financial advice.\"\n}\n", ""),
    ("[cli]\nshort = 1\nlong = 2\ncash = 1000\n", "hand.csv", ["--backtest", "--stop-loss", "10", "--cash", "500"], 0, "Bars:    8\nLast:    8.00\nSignal:  HOLD\nRSI:     n/a\nBacktest: SMA 1/2 crossover, next-bar fills, whole shares, no shorting\n  Start cash:  500.00\n  Trades:      2 (1 buy, 1 sell)\n  Fills (bar index is 0-based):\n    #1   bar 4     BUY        45 @      11.00  value       495.00  cost     0.00  cash         5.00  signal\n    #2   bar 6     SELL       45 @       9.90  value       445.50  cost     0.00  cash       450.50  stop\n  Costs:       0.00 paid (fee 0.00 per trade + 0.00% of value)\n  Exits:       stop 10.00% below entry\n  Round trips: 1 completed, 0 made money (0%)\n  Comparison              Strategy    Buy & hold\n    End equity              450.50        400.00\n    Return                  -9.90%       -20.00%\n    Max drawdown           -17.34%       -33.33%\n    Trades                       2             1\n    Costs paid                0.00          0.00\n  End cash:    450.50\n  End shares:  0 @ 8.00\n  End equity:  450.50\n  Return:      -9.90%\nResearch aid only. Not financial advice.\n", ""),
    ("[cli]\nspeed = 3\n", "hand.csv", ["--backtest"], 1, "", "Error: unknown.ini line 2: unknown key 'speed' in [cli]; choose from: short, long, rsi_period, cash, fee, fee_pct, slippage, position_size, stop_loss, take_profit, trailing_stop, risk_pct, atr_mult, atr_period, atr_stop, cooldown, min_hold, max_hold, max_drawdown, breakeven, max_losses, scale_out, add_on, max_adds, fill, strategy, stats, trade_list, explain, top, min_score\n"),
    ("[cli]\nrisk_pc = 2\n", "hand.csv", ["--backtest"], 1, "", "Error: typo.ini line 2: unknown key 'risk_pc' in [cli]; choose from: short, long, rsi_period, cash, fee, fee_pct, slippage, position_size, stop_loss, take_profit, trailing_stop, risk_pct, atr_mult, atr_period, atr_stop, cooldown, min_hold, max_hold, max_drawdown, breakeven, max_losses, scale_out, add_on, max_adds, fill, strategy, stats, trade_list, explain, top, min_score\n"),
    ("[cli]\nstop_loss = 0\n", "hand.csv", ["--backtest"], 2, "", "usage: trading_assistant.cli [-h] [--short SHORT] [--long LONG]\n                             [--rsi-period RSI_PERIOD] [--backtest]\n                             [--cash AMOUNT] [--fee AMOUNT] [--fee-pct PCT]\n                             [--slippage PCT] [--position-size FRACTION]\n                             [--stop-loss PCT] [--take-profit PCT]\n                             [--export FILE] [--fill {close,open}]\n                             [--resample {weekly,monthly}]\n                             [--strategy {sma_cross,rsi_reversion,breakout,ema_cross,momentum,zscore_reversion,hull_trend}]\n                             [--param KEY=VALUE] [--stats] [--config FILE]\n                             [--json] [--chart] [--candles] [--scan FOLDER]\n                             [--min-score N] [--top N] [--report FILE]\n                             csv_path\ntrading_assistant.cli: error: --stop-loss must be between 0 and 100 (both exclusive), got 0\n"),
    ("[cli]\nshort = 1.5\n", "hand.csv", ["--backtest"], 1, "", "Error: badint.ini line 2: short needs a whole number, got '1.5'\n"),
    ("[cli]\nstop_loss = 5\n", "closes.csv", ["--backtest", "--resample", "weekly"], 2, "", "usage: trading_assistant.cli [-h] [--short SHORT] [--long LONG]\n                             [--rsi-period RSI_PERIOD] [--backtest]\n                             [--cash AMOUNT] [--fee AMOUNT] [--fee-pct PCT]\n                             [--slippage PCT] [--position-size FRACTION]\n                             [--stop-loss PCT] [--take-profit PCT]\n                             [--export FILE] [--fill {close,open}]\n                             [--resample {weekly,monthly}]\n                             [--strategy {sma_cross,rsi_reversion,breakout,ema_cross,momentum,zscore_reversion,hull_trend}]\n                             [--param KEY=VALUE] [--stats] [--config FILE]\n                             [--json] [--chart] [--candles] [--scan FOLDER]\n                             [--min-score N] [--top N] [--report FILE]\n                             csv_path\ntrading_assistant.cli: error: --stop-loss cannot be combined with --resample yet\n"),
    ("[cli]\nstop_loss = 5\n", "closes.csv", ["--backtest"], 1, "", "Error: closes.csv has no 'open', 'high', 'low', 'volume' columns (found columns: 'date', 'close'); expected a header row like 'date,open,high,low,close,volume' followed by rows like '2026-01-02,100.5,103.0,99.5,101.5,12000'\n"),
]


@pytest.mark.parametrize("text, price, extra, code, out, err", OLD_RUNS)
def test_old_config_files_behave_the_same(folder, capsys, text, price, extra, code, out, err):
    # Error messages name the file they were captured with (<kind>.ini); write it under that name.
    file_name = next((f"{c}.ini" for c in ("unknown", "typo", "range", "badint", "stopres", "base", "all") if f"{c}.ini" in err), "old.ini")
    (folder / file_name).write_text(text)
    assert run([price, "--config", file_name, *extra], capsys) == (code, out, err)


# --------------------------------------------------------------------------- atr keys in the file without risk_pct

NEW_KEY_LIST = (
    "choose from: short, long, rsi_period, cash, fee, fee_pct, slippage, position_size, stop_loss, take_profit, "
    "trailing_stop, risk_pct, atr_mult, atr_period, atr_stop, cooldown, min_hold, max_hold, max_drawdown, breakeven, max_losses, scale_out, add_on, max_adds, fill, strategy, stats, trade_list, explain, top, min_score\n"
)


def test_file_atr_keys_without_risk_pct_are_ignored_quietly(folder, capsys):
    for extra in ([], ["--json"]):
        without = with_config(BASE, ["hand.csv", "--backtest", *extra], capsys, folder)
        with_atr = with_config(BASE + "atr_mult = 3\natr_period = 5\n", ["hand.csv", "--backtest", *extra], capsys, folder)
        assert with_atr == without
        assert with_atr[0] == 0 and with_atr[2] == ""
    assert "Risk sizing" not in with_config(BASE + "atr_mult = 3\n", ["hand.csv", "--backtest"], capsys, folder)[1]


def test_ignored_atr_keys_are_not_range_checked(folder, capsys):
    # Ignored means not used at all, so 0 (out of range for the flags) is no error here.
    code, out, err = with_config(BASE + "atr_mult = 0\natr_period = 0\n", ["hand.csv", "--backtest"], capsys, folder)
    assert (code, err) == (0, "") and "Risk sizing" not in out


def test_atr_flag_without_risk_pct_is_still_an_error(folder, capsys):
    code, out, err = with_config(BASE + "atr_period = 3\n", ["hand.csv", "--backtest", "--atr-mult", "3"], capsys, folder)
    assert (code, out) == (2, "")
    assert err.endswith("trading_assistant.cli: error: --atr-mult only makes sense together with --risk-pct or --atr-stop\n")


def test_misspelled_risk_key_shows_the_new_list(folder, capsys):
    code, out, err = with_config("[cli]\nrisk_pc = 2\n", ["hand.csv", "--backtest"], capsys, folder)
    assert (code, out) == (1, "")
    assert err == "Error: c.ini line 2: unknown key 'risk_pc' in [cli]; " + NEW_KEY_LIST
