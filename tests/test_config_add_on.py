"""Config keys add_on (a number, like scale_out) and max_adds (a whole number, like max_hold) for --add-on and
--max-adds.

Rules: each flag wins over its key. add_on 0 or negative is the flag's error (exit 2); a value that is not a number,
nan or inf is a config error (exit 1). max_adds 2.5 or abc is a config error (exit 1); 0 is the flag's error (exit 2).
max_adds is used only when add_on or --add-on is there; otherwise it is ignored quietly, like a cooldown without a
stop, and, also like cooldown, its range is still checked (0 is exit 2). Without --backtest or with --scan both keys
are ignored (only a value of the wrong kind is still an error, when the file is read).

up.csv with short 1, long 2, cash 1000, position_size 0.5 in the file: add_on 10 gives 1054.00, add_on 20 gives
1024.00, the flag runs' numbers (arithmetic in test_add_on.py). s.csv (closes 10 8 9 10 11.5 12 13 14 15 17 16 16.5,
position_size 0.25, add_on 10) is test_add_on.py's max_adds case: 3 add-ons give 1292.00, 1 gives 1257.00.

"Without the keys the config behaves as before": every backtest command of tests/data/cli_before_add_on.json (flags
recorded before the options existed) is turned into a config file holding those settings, and must print what the
flags printed then.
"""

import json

from test_cli_add_on import BEFORE_FULL, FULL_RUNS, UPB, folder, run  # noqa: F401  (folder is a fixture)

BASE = "[cli]\nshort = 1\nlong = 2\ncash = 1000\nposition_size = 0.5\n"
S = [10, 8, 9, 10, 11.5, 12, 13, 14, 15, 17, 16, 16.5]
FLAG_ARGS = UPB + ["--position-size", "0.5"]


def cfg(folder, text, name="t.ini"):
    (folder / name).write_text(text)
    return name


def add_ons_line(out):
    return next(line for line in out.splitlines() if line.startswith("  Add-ons:"))


def test_file_runs_print_exactly_what_the_flags_print(folder):
    for pct in ("10", "20"):
        name = cfg(folder, BASE + f"add_on = {pct}\n")
        for extra in ([], ["--json"]):
            assert run(["up.csv", "--backtest", "--config", name] + extra) == run(FLAG_ARGS + ["--add-on", pct] + extra)
    out = run(["up.csv", "--backtest", "--config", cfg(folder, BASE + "add_on = 10\n")])[1]
    assert "  End equity:  1,054.00" in out and "up to 1 per position" in add_ons_line(out)
    b = json.loads(run(["up.csv", "--backtest", "--config", cfg(folder, BASE + "add_on = 20\n"), "--json"])[1])["backtest"]
    assert (b["add_on_pct"], b["max_adds"], b["add_on_buys"], b["add_on_skipped_buys"], b["final_equity"]) == (
        20.0, 1, 1, 0, 1024.0)


def test_each_flag_wins_over_its_key(folder):
    name = cfg(folder, BASE + "add_on = 10\n")
    assert run(["up.csv", "--backtest", "--config", name, "--add-on", "20"]) == run(FLAG_ARGS + ["--add-on", "20"])
    (folder / "s.csv").write_text("close\n" + "".join(f"{c}\n" for c in S))
    s = ["s.csv", "--backtest", "--short", "1", "--long", "2", "--cash", "1000", "--position-size", "0.25"]
    name = cfg(folder, "[cli]\nadd_on = 10\nmax_adds = 3\n")
    three, one = run(s + ["--config", name]), run(s + ["--config", name, "--max-adds", "1"])
    assert three == run(s + ["--add-on", "10", "--max-adds", "3"]) and "  End equity:  1,292.00" in three[1]
    assert one == run(s + ["--add-on", "10", "--max-adds", "1"]) and "  End equity:  1,257.00" in one[1]
    assert "up to 3 per position" in add_ons_line(three[1]) and "up to 1 per position" in add_ons_line(one[1])
    # The file's max_adds goes with the flag's --add-on (add_on from the flag counts), and vice versa.
    name = cfg(folder, "[cli]\nmax_adds = 3\n")
    assert run(s + ["--config", name, "--add-on", "10"]) == three
    name = cfg(folder, "[cli]\nadd_on = 10\n")
    assert run(s + ["--config", name, "--max-adds", "3"]) == three


def test_bad_values(folder):
    usage_error = lambda message: message  # noqa: E731  (the end of stderr, after "error: ")
    cases = [
        ("add_on = 0\n", 2, usage_error("--add-on must be above 0, got 0")),
        ("add_on = -5\n", 2, usage_error("--add-on must be above 0, got -5")),
        ("add_on = abc\n", 1, "Error: t.ini line 6: add_on needs a number, got 'abc'"),
        ("add_on = nan\n", 1, "Error: t.ini line 6: add_on needs a finite number, got 'nan'"),
        ("add_on = inf\n", 1, "Error: t.ini line 6: add_on needs a finite number, got 'inf'"),
        ("add_on = 10\nmax_adds = 2.5\n", 1, "Error: t.ini line 7: max_adds needs a whole number, got '2.5'"),
        ("add_on = 10\nmax_adds = abc\n", 1, "Error: t.ini line 7: max_adds needs a whole number, got 'abc'"),
        ("add_on = 10\nmax_adds = 0\n", 2, usage_error("--max-adds must be a whole number of at least 1, got 0")),
        ("max_adds = 0\n", 2, usage_error("--max-adds must be a whole number of at least 1, got 0")),
    ]
    for text, code, message in cases:
        got = run(["up.csv", "--backtest", "--config", cfg(folder, BASE + text)])
        assert got[0] == code and got[1] == "", text
        if code == 2:
            assert got[2].endswith(f"trading_assistant.cli: error: {message}\n") and got[2].startswith("usage: "), text
        else:
            assert got[2] == message + "\n", text
    # A typo lists both keys, after scale_out.
    got = run(["up.csv", "--backtest", "--config", cfg(folder, "[cli]\nadd_ons = 10\n")])
    assert got[0] == 1 and ", scale_out, add_on, max_adds, fill, " in got[2]


def test_ignored_without_backtest_with_scan_and_max_adds_without_add_on(folder):
    plain = run(FLAG_ARGS)
    # max_adds without add_on (file or flag): ignored quietly, the run is the one without it.
    assert run(["up.csv", "--backtest", "--config", cfg(folder, BASE + "max_adds = 2\n")]) == plain
    # Without --backtest both keys are ignored, even values the range check would refuse.
    name = cfg(folder, BASE + "add_on = 0\nmax_adds = 0\n")
    assert run(["up.csv", "--config", name]) == run(["up.csv", "--short", "1", "--long", "2"])
    # ...but a value of the wrong kind is still an error when the file is read.
    assert run(["up.csv", "--config", cfg(folder, BASE + "add_on = abc\n")])[0] == 1
    # With --scan they are ignored too.
    name = cfg(folder, "[cli]\nadd_on = 10\nmax_adds = 0\n")
    assert run(["--scan", "scan", "--config", name]) == run(["--scan", "scan"])
    # A --max-adds flag still needs --add-on or add_on: the file's max_adds does not make it valid.
    got = run(["up.csv", "--backtest", "--config", cfg(folder, BASE + "max_adds = 2\n"), "--max-adds", "2"])
    assert got[0] == 2 and got[2].endswith("error: --max-adds only makes sense together with --add-on\n")


KEY_OF = {"--cash": "cash", "--short": "short", "--long": "long", "--fee": "fee", "--slippage": "slippage",
          "--position-size": "position_size", "--min-hold": "min_hold", "--max-hold": "max_hold",
          "--max-drawdown": "max_drawdown", "--max-losses": "max_losses", "--fill": "fill", "--stop-loss": "stop_loss",
          "--take-profit": "take_profit", "--trailing-stop": "trailing_stop", "--risk-pct": "risk_pct",
          "--atr-period": "atr_period", "--cooldown": "cooldown", "--breakeven": "breakeven",
          "--scale-out": "scale_out", "--strategy": "strategy"}
SWITCH_KEYS = {"--atr-stop": "atr_stop", "--trade-list": "trade_list", "--stats": "stats"}


def as_config(argv):
    """(arguments left on the command line, config text) for a recorded command: every setting that has a key."""
    left, keys, params = [], [], []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in KEY_OF:
            keys.append(f"{KEY_OF[arg]} = {argv[i + 1]}")
            i += 2
        elif arg in SWITCH_KEYS:
            keys.append(f"{SWITCH_KEYS[arg]} = yes")
            i += 1
        elif arg == "--param":
            params.append(argv[i + 1].replace("=", " = "))
            i += 2
        else:
            left.append(arg)
            i += 1
    text = "[cli]\n" + "".join(k + "\n" for k in keys)
    if params:
        strategy = argv[argv.index("--strategy") + 1]
        text += f"[strategy.{strategy}]\n" + "".join(p + "\n" for p in params)
    return left, text


def test_without_the_keys_config_files_give_what_the_flags_gave_before(folder):
    checked = 0
    for argv in FULL_RUNS:
        if "--backtest" not in argv or "--resample" in argv and argv[0] == "up.csv":
            continue
        left, text = as_config(argv)
        assert "add_on" not in text and len(left) < len(argv)
        name = cfg(folder, text, "old.ini")
        code, out, err = run(left + ["--config", name])
        before = BEFORE_FULL[" ".join(argv)]
        assert (code, out, err) == (before["code"], before["out"], before["err"]), argv
        if "export" in before:
            assert (folder / "out.csv").read_text() == before["export"]
            (folder / "out.csv").unlink()
        checked += 1
    assert checked == 17
