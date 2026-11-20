"""--max-drawdown PCT on the command line: the hand cases of test_max_drawdown.py through the CLI, closes only."""

import pytest

from trading_assistant.cli import build_parser, main


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


def fill_tails(out):
    """(bar, side, price, reason) of each fill line."""
    rows = [line.split() for line in out.splitlines() if line.startswith("    #")]
    return [(int(r[2]), r[3], r[6], r[-1]) for r in rows]


@pytest.mark.parametrize(
    "argv, fills, state, equity",
    [
        ([*B, "--max-drawdown", "16"], [(4, "BUY", "11.00", "signal"), (7, "SELL", "10.00", "signal")],
         "16.00% below the peak account value at a close; triggered at bar 6, no buy fills after it; 1 buy skipped",
         "910.00"),
        ([*B, "--max-drawdown", "17"],
         [(4, "BUY", "11.00", "signal"), (7, "SELL", "10.00", "signal"), (9, "BUY", "12.00", "signal")],
         "17.00% below the peak account value at a close; not triggered; 0 buys skipped", "925.00"),
        (["rally.csv", *B[1:6], "--long", "3", "--max-drawdown", "12.5"],
         [(5, "BUY", "20.00", "signal"), (8, "SELL", "30.00", "drawdown")],
         "12.50% below the peak account value at a close; triggered at bar 7, no buy fills after it; 1 buy skipped",
         "1,500.00"),
    ],
)
def test_hand_cases_on_a_close_only_file(folder, capsys, argv, fills, state, equity):
    code, out, err = run(argv, capsys)
    assert (code, err) == (0, "")
    assert fill_tails(out) == fills
    assert f"\n  Drawdown:    halt at {state}\n  Round trips:" in out
    assert f"\n  End equity:  {equity}\n" in out


def test_resample_is_allowed(folder, capsys):
    code, out, err = run([*B, "--max-drawdown", "5", "--resample", "weekly"], capsys)
    assert (code, err) == (0, "") and "\n  Drawdown:    halt at 5.00% below the peak" in out


@pytest.mark.parametrize(
    "argv, message",
    [
        ([*B, "--max-drawdown", "0"], "--max-drawdown must be above 0 and below 100, got 0"),
        ([*B, "--max-drawdown", "100"], "--max-drawdown must be above 0 and below 100, got 100"),
        ([*B, "--max-drawdown", "ten"], "argument --max-drawdown: invalid float value: 'ten'"),
        (["closes.csv", "--max-drawdown", "10"], "--max-drawdown only makes sense together with --backtest"),
        (["--scan", "scan", "--max-drawdown", "10"], "--max-drawdown cannot be combined with --scan"),
    ],
)
def test_usage_errors_exit_2(folder, capsys, argv, message):
    code, out, err = run(argv, capsys)
    assert (code, out) == (2, "")
    assert err.endswith(f"error: {message}\n")


def test_help_lists_it_after_max_hold_but_the_usage_line_does_not(folder, capsys):
    _, out, _ = run(["--help"], capsys)
    assert "--max-drawdown" not in out.split("\n\n", 1)[0]
    starts = [line.split()[0] for line in out.splitlines() if line.startswith("  --")]
    i = starts.index("--max-drawdown")
    assert starts[i - 1 : i + 2] == ["--max-hold", "--max-drawdown", "--breakeven"]


@pytest.mark.parametrize("scan", [False, True])
def test_every_option_name_that_worked_before_still_means_the_same_option(scan):
    # Before --max-drawdown the parser knew every option string it knows now except --max-drawdown and the
    # hidden aliases added with it. argparse takes an exact option string, or else a prefix of exactly one.
    parser = build_parser(scan=scan)
    known = parser._option_string_actions
    old = {name: action.dest for name, action in known.items() if name.startswith("--")}
    for new in ("--max-drawdown", "--ma", "--max", "--max-"):
        old.pop(new, None)
    checked = 0
    for name in old:
        for end in range(3, len(name) + 1):
            token = name[:end]
            matches = [n for n in old if n.startswith(token)]
            if token not in old and len(matches) != 1:
                continue  # was ambiguous (or not an option) before
            dest = old[token] if token in old else old[matches[0]]
            if dest == "help":
                continue
            action = known[token] if token in known else known[matches[0]]
            args = parser.parse_args(
                ([] if scan else ["x.csv"])
                + [token]
                + ([] if action.nargs == 0 else [action.choices[0] if action.choices else "3"])
            )
            default = parser.get_default(dest)
            assert getattr(args, dest) != default, (token, dest)
            checked += 1
    assert checked > 150  # every option, its shortened forms and the old hidden aliases
    assert build_parser().parse_args(["x.csv", "--max-d", "4.5"]).max_drawdown == 4.5


# --------------------------------------------------------------------------- --json


def json_backtest(argv, capsys):
    code, out, err = run([*argv, "--json"], capsys)
    assert (code, err) == (0, "")
    return __import__("json").loads(out)["backtest"]


# Keys of the backtest object for `B --json` without the option (captured before --max-drawdown existed).
BEFORE_KEYS = [
    "strategy", "params", "fill", "start_cash", "fee", "fee_pct", "slippage_pct", "position_size", "stop_loss_pct",
    "take_profit_pct", "trades", "buys", "sells", "fills", "total_costs", "round_trips", "winning_round_trips",
    "final_cash", "final_position", "final_price", "final_equity", "return_pct", "max_drawdown_pct", "benchmark",
]


@pytest.mark.parametrize(
    "argv, limit, halt_bar, skipped",
    [
        ([*B, "--max-drawdown", "16"], 16.0, 6, 1),
        ([*B, "--max-drawdown", "17"], 17.0, None, 0),
        (["rally.csv", *B[1:6], "--long", "3", "--max-drawdown", "12.5"], 12.5, 7, 1),
    ],
)
def test_json_has_the_drawdown_keys_and_matches_the_text_report(folder, capsys, argv, limit, halt_bar, skipped):
    b = json_backtest(argv, capsys)
    assert list(b) == [
        *BEFORE_KEYS[:10], "max_drawdown_limit_pct", *BEFORE_KEYS[10:13], "drawdown_halt_bar", "drawdown_skipped_buys",
        *BEFORE_KEYS[13:],
    ]
    assert (b["max_drawdown_limit_pct"], b["drawdown_halt_bar"], b["drawdown_skipped_buys"]) == (limit, halt_bar, skipped)
    _, text, _ = run(argv, capsys)
    assert [(f["bar"], f["side"], f"{f['price']:.2f}", f["reason"]) for f in b["fills"]] == fill_tails(text)
    state = "not triggered" if halt_bar is None else f"triggered at bar {halt_bar}, no buy fills after it"
    assert f"% below the peak account value at a close; {state}; {skipped} buy" in text
    assert f"\n  Drawdown:    halt at {limit:.2f}%" in text
    assert f"\n  End equity:  {b['final_equity']:,.2f}\n" in text
    assert f"\n    Max drawdown    {b['max_drawdown_pct']:>13.2f}%" in text


def test_json_keys_come_after_the_other_optional_keys(folder, capsys):
    (folder / "candles.csv").write_text(
        "date,open,high,low,close,volume\n"
        + "".join(f"2026-01-{d:02d},{c},{c},{c},{c},1000\n" for d, c in enumerate(RALLY, start=5))
    )
    argv = ["candles.csv", *B[1:6], "--long", "3", "--stop-loss", "50", "--risk-pct", "50", "--atr-period", "2",
            "--atr-stop", "--cooldown", "2", "--max-hold", "9", "--max-drawdown", "12.5"]
    keys = list(json_backtest(argv, capsys))
    assert keys[keys.index("max_hold_bars") :][:2] == ["max_hold_bars", "max_drawdown_limit_pct"]
    assert keys[keys.index("time_exits") :][:4] == ["time_exits", "drawdown_halt_bar", "drawdown_skipped_buys", "fills"]


def test_json_without_the_option_has_no_drawdown_keys(folder, capsys):
    assert list(json_backtest(B, capsys)) == BEFORE_KEYS


def test_export_gets_the_reason_column_with_the_drawdown_sale(folder, capsys):
    code, _, err = run(["rally.csv", *B[1:6], "--long", "3", "--max-drawdown", "12.5", "--export", "out.csv"], capsys)
    assert (code, err) == (0, "")
    rows = [line.split(",") for line in (folder / "out.csv").read_text().splitlines()]
    assert (rows[0][-1], [(r[0], r[4], r[-1]) for r in rows[1:] if r[4]]) == (
        "reason", [("5", "BUY", "signal"), ("8", "SELL", "drawdown")]
    )
