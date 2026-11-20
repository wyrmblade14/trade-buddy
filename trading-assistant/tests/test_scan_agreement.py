"""The scan gives the same answer every way it can be asked.

For several sets of files and several setting combinations, the same files
and settings go to:

* the command line table (``--scan FOLDER`` with flags), read back from the text;
* the command line JSON (``--scan FOLDER --json`` with flags);
* the command line with the settings only in a config file (``--config``), as JSON
  and as a table;
* the web API (``POST /api/scan`` with the files' text in the body).

All of them must give the same counts, the same ranking with the same
scores and parts, and the same skipped files with the same reasons.
Everything is written to pytest temp folders.
"""

import json
import random
import threading

import pytest

from trading_assistant.cli import DISCLAIMER
from trading_assistant.cli import main as cli_main
from trading_assistant.samples import SAMPLES, sample_table
from trading_assistant.web import server as web

PARTS = ("crossover", "rsi", "macd", "bollinger")


# --------------------------------------------------------------------------- file sets


def csv_text(closes, header="date,close", newline="\n"):
    rows = [header] + [f"2026-{i // 28 + 1:02d}-{i % 28 + 1:02d},{c}" for i, c in enumerate(closes)]
    return newline.join(rows) + newline


def hand_worked_set():
    """The hand-worked 60-bar series (scores +2, +1, 0, 0, -2) plus two broken files."""
    rise_flat_jump = [100.0 + i for i in range(50)] + [149.0] * 9 + [155.0]
    return {
        "DOWN.csv": csv_text(rise_flat_jump),
        "UP.csv": csv_text([300.0 - c for c in rise_flat_jump]),
        "LOW.csv": csv_text([100.0 + i for i in range(43)] + [141.0 - i for i in range(17)]),
        "zeta.csv": csv_text([100.0] * 59 + [110.0]),
        "Alpha.csv": csv_text([100.0] * 59 + [90.0]),
        "bad.csv": "date,close\n2026-01-01,10\n2026-01-02,abc\n",
        "noclose.csv": "date,price\n2026-01-01,10\n",
    }


def random_walk_set():
    """Twelve seeded random walks of different lengths (some too short for every indicator)."""
    rng = random.Random(20260302)
    files = {}
    for n, length in enumerate([30, 45, 60, 60, 75, 90, 120, 150, 200, 250, 300, 400]):
        price, closes = 100.0, []
        for _ in range(length):
            price = max(1.0, price * (1 + rng.gauss(0.0005, 0.02)))
            closes.append(round(price, 2))
        files[f"W{n:02d}.csv"] = csv_text(closes)
    files["empty_rows.csv"] = "date,close\n"
    return files


def edge_case_set():
    """Names, encodings and layouts the readers must treat the same way."""
    base = [100.0 + (i % 7) - 3 * (i % 3) + i * 0.2 for i in range(80)]
    return {
        "Caps.CSV": csv_text(base),  # capital extension: counted, symbol "Caps"
        "bom_crlf.csv": "\ufeff" + csv_text(base[::-1], header="Date, Close ", newline="\r\n"),
        "extra_cols.csv": "Volume,date,Note,close\n" + "".join(f"{i * 10},2026-01-{i % 28 + 1:02d},n{i},{c}\n" for i, c in enumerate(base[:70])),
        "twin_b.csv": csv_text(base[5:]),  # twin_a and twin_b tie, listed in name order
        "twin_a.csv": csv_text(base[5:]),
        "Twin_C.csv": csv_text(base[5:]),  # same score again, capital T sorts by name ignoring case
        "late_bad.csv": csv_text(base[:40]) + "2026-03-01,n/a\n",
        "empty.csv": "",
        "dup_close.csv": "date,close,Close\n2026-01-01,1,2\n",
        "notes.txt": "ignored: not a .csv file",
        "prices.csv.bak": "date,close\nx,abc\n",
    }


def sample_set():
    """The built-in sample series as files."""
    files = {}
    for name in SAMPLES:
        dates, closes = sample_table(name)
        files[f"{name}.csv"] = "date,close\n" + "".join(f"{d},{c:.2f}\n" for d, c in zip(dates, closes))
    return files


FILE_SETS = {
    "hand": hand_worked_set,
    "walks": random_walk_set,
    "edges": edge_case_set,
    "samples": sample_set,
}

# (flags, config [cli] keys, web settings) for the same settings
SETTINGS = {
    "defaults": {},
    "min0": {"min_score": 0},
    "top3": {"top": 3},
    "min-1_top2": {"min_score": -1, "top": 2},
    "windows": {"short": 5, "long": 12, "rsi_period": 7},
    "small_windows_min1": {"short": 2, "long": 5, "rsi_period": 2, "min_score": 1},
    "nothing_matched": {"min_score": 4, "top": 1},
}

FLAG = {"short": "--short", "long": "--long", "rsi_period": "--rsi-period", "min_score": "--min-score", "top": "--top"}


# --------------------------------------------------------------------------- the four ways


@pytest.fixture(autouse=True)
def no_config_env(monkeypatch):
    monkeypatch.delenv("TRADING_ASSISTANT_CONFIG", raising=False)


@pytest.fixture(scope="module")
def base_url():
    server = web.BacktestServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def write_folder(tmp_path, files):
    folder = tmp_path / "prices"
    folder.mkdir(parents=True)
    for name, text in files.items():
        (folder / name).write_bytes(text.encode("utf-8"))
    return folder


def flags_for(settings):
    out = []
    for key, value in settings.items():
        out += [FLAG[key], str(value)]
    return out


def run_cli(argv, capsys):
    code = cli_main(argv)
    out, err = capsys.readouterr()
    assert code == 0 and err == "", err
    return out


def parse_table(text):
    """Read the --scan text table back into (counts, rows, reasons)."""
    lines = text.splitlines()
    assert lines[-1] == DISCLAIMER
    counts = {}
    for piece in lines[0].split(", ")[1:]:
        words = piece.split()
        if words[1] in ("found", "scored", "skipped", "shown"):
            counts[words[1]] = int(words[0])
    assert lines[1].split() == ["Symbol", "Bars", "Score", "Crossover", "RSI", "MACD", "Bollinger"]
    rows, i = [], 2
    while lines[i] != DISCLAIMER and not lines[i].startswith(("Skipped:", "  (no file matched")):
        symbol, bars, score, *parts = lines[i].split()
        rows.append((symbol, int(bars), int(score), tuple(int(p) for p in parts)))
        i += 1
    reasons = [line[2:] for line in lines[i:] if line.startswith("  ") and not line.startswith("  (no file")]
    counts.setdefault("found", counts["scored"] + counts["skipped"])
    counts.setdefault("shown", len(rows))
    return counts, rows, reasons


def from_json(data):
    """(counts, rows, reasons, skipped symbols) from a --scan --json object or a web reply."""
    counts = {"found": data["found"], "scored": data["scored"], "skipped": len(data["skipped"]), "shown": data["shown"]}
    rows = [(r["symbol"], r["bars"], r["score"], tuple(r["parts"][p] for p in PARTS)) for r in data["results"]]
    return counts, rows, [s["reason"] for s in data["skipped"]], [s["symbol"] for s in data["skipped"]]


def post_scan(base_url, files, settings):
    from urllib.request import Request, urlopen

    body = json.dumps({"files": files, **settings}).encode()
    req = Request(base_url + "/api/scan", data=body, method="POST", headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=30) as resp:
        assert resp.status == 200
        return json.loads(resp.read())


def all_four(tmp_path, capsys, base_url, files, settings):
    folder = write_folder(tmp_path, files)
    flags = flags_for(settings)
    table = parse_table(run_cli(["--scan", str(folder), *flags], capsys))
    as_json = from_json(json.loads(run_cli(["--scan", str(folder), "--json", *flags], capsys)))
    ini = tmp_path / "settings.ini"
    ini.write_text("[cli]\n" + "".join(f"{k} = {v}\n" for k, v in settings.items()))
    config_json = from_json(json.loads(run_cli(["--scan", str(folder), "--json", "--config", str(ini)], capsys)))
    config_table = parse_table(run_cli(["--scan", str(folder), "--config", str(ini)], capsys))
    # the page sends the text of each picked file; the names are only labels
    sent = {p.name: p.read_bytes().decode("utf-8") for p in sorted(folder.iterdir())}
    from_web = from_json(post_scan(base_url, sent, settings))
    return table, as_json, config_json, config_table, from_web


# --------------------------------------------------------------------------- agreement


@pytest.mark.parametrize("settings_name", list(SETTINGS))
@pytest.mark.parametrize("set_name", list(FILE_SETS))
def test_cli_table_json_config_and_web_agree(tmp_path, capsys, base_url, set_name, settings_name):
    files = FILE_SETS[set_name]()
    settings = SETTINGS[settings_name]
    table, as_json, config_json, config_table, from_web = all_four(tmp_path, capsys, base_url, files, settings)

    # JSON from flags, JSON from the config file and the web reply are identical, skipped symbols included
    assert as_json == config_json == from_web
    # the two tables (flags and config) are identical and say the same as the JSON
    assert table == config_table
    counts, rows, reasons, symbols = as_json
    assert table == (counts, rows, reasons)
    # every reason starts with the file name, and the symbol is that name without .csv
    assert len(symbols) == len(reasons)
    assert all(reason.startswith(symbol + ".") for symbol, reason in zip(symbols, reasons))

    # and the ranking follows the rule: highest score first, then name ignoring case
    assert rows == sorted(rows, key=lambda r: (-r[2], r[0].casefold(), r[0]))
    assert all(r[2] == sum(r[3]) and all(p in (-1, 0, 1) for p in r[3]) for r in rows)
    if "min_score" in settings:
        assert all(r[2] >= settings["min_score"] for r in rows)
    if "top" in settings:
        assert len(rows) <= settings["top"]
    assert counts["found"] == counts["scored"] + counts["skipped"]


def test_the_sets_cover_what_they_should(tmp_path, capsys, base_url):
    """Sanity check that the agreement cases are not trivially empty."""
    seen_scores, seen_parts, skipped_total = set(), {p: set() for p in PARTS}, 0
    for make in FILE_SETS.values():
        _, as_json, *_ = all_four(tmp_path / make.__name__, capsys, base_url, make(), {})
        counts, rows, reasons, _ = as_json
        skipped_total += len(reasons)
        for _, _, score, parts in rows:
            seen_scores.add(score)
            for name, value in zip(PARTS, parts):
                seen_parts[name].add(value)
    assert len(seen_scores) >= 4
    assert all(values == {-1, 0, 1} for values in seen_parts.values()), seen_parts
    assert skipped_total >= 6


def test_edge_case_names_and_ties(tmp_path, capsys, base_url):
    _, as_json, *_ = all_four(tmp_path, capsys, base_url, edge_case_set(), {})
    counts, rows, reasons, symbols = as_json
    names = [r[0] for r in rows]
    assert "Caps" in names and "notes" not in names and "prices.csv" not in names
    twins = [n for n in names if n.lower().startswith("twin")]
    assert twins == ["twin_a", "twin_b", "Twin_C"]  # same score, name order ignoring case
    assert counts["found"] == 9  # the .txt and .bak files are not counted
    assert symbols == ["dup_close", "empty", "late_bad"]
