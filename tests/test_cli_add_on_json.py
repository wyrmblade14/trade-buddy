"""--json with --add-on: backtest.add_on_pct and max_adds (right after scale_out_pct, or where it would be) and
add_on_buys and add_on_skipped_buys (right after scale_out_exits, or where it would be), only when --add-on is
given: the order of the text report's lines, where "Add-ons:" follows "Scale out:".

up.csv cases (arithmetic in test_add_on.py): --position-size 0.5 --add-on 10: 1 add-on buy, 0 skipped, 1054.00;
--add-on 20: 1 and 0, 1024.00; --add-on 10 with all-cash sizing: 0 add-on buys, 3 skipped, 1180.00. Runs without
the option are checked against tests/data/cli_before_add_on.json by test_cli_add_on.py (its --json runs
included).
"""

import json
import re

from test_cli_add_on import BEFORE_FULL, CB, UPB, folder, run  # noqa: F401  (folder is a fixture)

ADD_ON_KEYS = ["add_on_pct", "max_adds", "add_on_buys", "add_on_skipped_buys"]


def text_numbers(out):
    """The figures the text report and the JSON object share, read from the text report."""
    lines = out.splitlines()
    get = lambda label: next(line for line in lines if line.startswith(label)).split(":", 1)[1].strip()  # noqa: E731
    trades, buys, sells = map(int, re.match(r"(\d+) \((\d+) buy, (\d+) sell\)", get("  Trades:")).groups())
    rt = re.match(r"(\d+) completed(?:, (\d+) made money)?", get("  Round trips:")).groups()
    add_on = re.search(r"up to (\d+) per position, .* close ([\d.]+)% .*; (\d+) add-on buys?, (\d+) skipped",
                       get("  Add-ons:")).groups()
    fills = [(int(m[0]), m[1], int(m[2]), float(m[3].replace(",", "")), m[4]) for m in
             re.findall(r"bar (\d+)\s+(BUY|SELL)\s+(\d+) @\s+([\d,.]+) .*  (\w+)$", out, re.M)]
    return {
        "trades": trades, "buys": buys, "sells": sells, "round_trips": int(rt[0]), "winning": int(rt[1] or 0),
        "max_adds": int(add_on[0]), "add_on_pct": float(add_on[1]), "add_on_buys": int(add_on[2]),
        "add_on_skipped_buys": int(add_on[3]), "fills": fills,
        "final_equity": float(get("  End equity:").replace(",", "")), "return_pct": float(get("  Return:")[:-1]),
    }


def json_numbers(b):
    return {
        "trades": b["trades"], "buys": b["buys"], "sells": b["sells"], "round_trips": b["round_trips"],
        "winning": b["winning_round_trips"], "max_adds": b["max_adds"], "add_on_pct": b["add_on_pct"],
        "add_on_buys": b["add_on_buys"], "add_on_skipped_buys": b["add_on_skipped_buys"],
        "fills": [(f["bar"], f["side"], f["shares"], round(f["price"], 2), f["reason"]) for f in b["fills"]],
        "final_equity": round(b["final_equity"], 2), "return_pct": round(b["return_pct"], 2),
    }


def test_up_csv_json_matches_the_text_report(folder):
    cases = [
        (["--position-size", "0.5", "--add-on", "10"], (1, 0, 1054.0)),
        (["--position-size", "0.5", "--add-on", "20"], (1, 0, 1024.0)),
        (["--add-on", "10"], (0, 3, 1180.0)),
    ]
    for extra, (buys, skipped, equity) in cases:
        code, text, err = run(UPB + extra)
        assert (code, err) == (0, "")
        code, out, err = run(UPB + extra + ["--json"])
        assert (code, err) == (0, "")
        b = json.loads(out)["backtest"]
        assert (b["add_on_buys"], b["add_on_skipped_buys"], b["final_equity"]) == (buys, skipped, equity), extra
        assert json_numbers(b) == text_numbers(text), extra
        # The plain run's keys, with the four new ones where scale_out_pct and scale_out_exits would be.
        plain_argv = UPB + (["--position-size", "0.5"] if "--position-size" in extra else []) + ["--json"]
        plain = run(plain_argv)[1]
        keys = list(json.loads(plain)["backtest"])
        i, j = keys.index("take_profit_pct") + 1, keys.index("sells") + 1
        assert list(b) == [*keys[:i], "add_on_pct", "max_adds", *keys[i:j], "add_on_buys", "add_on_skipped_buys",
                           *keys[j:]], extra
        # Apart from those keys, the fills' reasons and the numbers they change, nothing else is new.
        assert b["max_adds"] == 1 and b["add_on_pct"] == float(extra[-1])


def test_key_positions_next_to_the_other_options_and_max_adds(folder):
    argv = CB + ["--scale-out", "5", "--cooldown", "2", "--stop-loss", "20", "--max-hold", "6", "--position-size",
                 "0.5", "--add-on", "5", "--max-adds", "2", "--json", "--trade-list"]
    code, out, err = run(argv)
    assert (code, err) == (0, "")
    keys = list(json.loads(out)["backtest"])
    i = keys.index("scale_out_pct")
    assert keys[i: i + 4] == ["scale_out_pct", "add_on_pct", "max_adds", "cooldown_bars"]
    i = keys.index("scale_out_exits")
    assert keys[i: i + 4] == ["scale_out_exits", "add_on_buys", "add_on_skipped_buys", "cooldown_skipped_buys"]
    b = json.loads(out)["backtest"]
    assert b["max_adds"] == 2 and b["add_on_pct"] == 5.0
    assert b["add_on_buys"] == sum(f["reason"] == "add_on" for f in b["fills"])
    assert keys[-1] == "trade_list"  # still the last key
    # Each count is the text report's.
    text = run([a for a in argv if a not in ("--json", "--trade-list")])[1]
    line = next(x for x in text.splitlines() if x.startswith("  Add-ons:"))
    assert line.endswith(f"; {b['add_on_buys']} add-on buy{'' if b['add_on_buys'] == 1 else 's'}, "
                         f"{b['add_on_skipped_buys']} skipped (0 shares)")
    assert "up to 2 per position" in line


def test_never_triggered_add_on_only_adds_the_four_keys(folder):
    # --add-on 50 never triggers on up.csv: the object is the plain run's plus the four keys, nothing else.
    plain = json.loads(run(UPB + ["--position-size", "0.5", "--json"])[1])
    with_it = json.loads(run(UPB + ["--position-size", "0.5", "--add-on", "50", "--json"])[1])
    b = with_it["backtest"]
    assert [b[k] for k in ADD_ON_KEYS] == [50.0, 1, 0, 0]
    for k in ADD_ON_KEYS:
        del b[k]
    assert with_it == plain
    # And the plain run is the one recorded before the options existed.
    assert run(UPB + ["--position-size", "0.5", "--json"])[1] == BEFORE_FULL[" ".join(UPB + ["--position-size", "0.5", "--json"])]["out"]
