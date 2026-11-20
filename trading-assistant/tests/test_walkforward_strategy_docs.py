"""The docs of the walk-forward strategies against real output and the code.

Every ``python -m trading_assistant.walkforward`` example in README.md's "Walk-forward with a strategy" and
docs/cli.md's "Strategies in the walk-forward" is run and must print exactly the block after it; the error table,
the weight table and the limit messages there must match the code; every relative link and anchor in the docs
must resolve; the version must be the newest CHANGELOG entry's.
"""

import contextlib
import io
import re
import shlex
from pathlib import Path

from trading_assistant.walkforward import main as walkforward_main
from trading_assistant.web import server as web

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text()
CLI_MD = (ROOT / "docs" / "cli.md").read_text()


def section(text, heading):
    """From ``heading`` to the next heading of the same or a higher level (markdown headings only)."""
    start = text.index(heading)
    body = text.index("\n", start) + 1
    level = len(heading.split(" ")[0])
    end = re.search(r"^#{1,%d} " % level, text[body:], re.M)
    return text[start : body + end.start()] if end else text[start:]


def paragraph_run(text, start_marker, end_marker):
    """The text from ``start_marker`` up to ``end_marker``."""
    start = text.index(start_marker)
    return text[start : text.index(end_marker, start)]


README_PART = section(README, "### Walk-forward with a strategy")
CLI_PART = section(CLI_MD, "### Strategies in the walk-forward (`--strategy`, `--grid`, `--param`)")


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = walkforward_main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def test_every_command_example_prints_what_the_docs_show(monkeypatch, tmp_path):
    monkeypatch.chdir(ROOT)  # the examples name tests/data/... files
    pairs = []
    for part in (README_PART, CLI_PART):
        pairs += re.findall(r"```bash\n(python -m trading_assistant\.walkforward [^\n]+)\n```\n\n```\n(.*?)```", part, re.S)
    assert len(pairs) == 5  # README: 1; cli.md: the example, its --json, zscore_reversion, momentum with --warmup
    for command, shown in pairs:
        argv = shlex.split(command)[3:]
        assert run(argv) == (0, shown, ""), command
    # The --csv file printed after the --json example.
    csv_block = re.search(r"and the file `--csv windows.csv` writes.*?```\n(.*?)```", CLI_PART, re.S).group(1)
    assert pairs[2][0].endswith(" --json")
    code, out, _ = run([*shlex.split(pairs[2][0])[3:-1], "--csv", str(tmp_path / "windows.csv")])
    assert code == 0 and (tmp_path / "windows.csv").read_text() == csv_block
    assert f"Wrote 2 rows to {tmp_path / 'windows.csv'}\n" in out


def test_error_table_weights_and_limits_match_the_code():
    # The usage-error table: each command line (after the file, --train and --test) gives that message.
    table = paragraph_run(CLI_PART, "**Usage errors (exit 2)**", "**Shortened option names.**")
    rows = re.findall(r"^\| `([^`]+)` \| `([^`]+)`", table, re.M)
    assert len(rows) == 12
    for args, message in rows:
        code, out, err = run(["tests/data/wf20.csv", "--train", "8", "--test", "6", *shlex.split(args)])
        assert (code, out) == (2, "") and err.endswith(f"trading_assistant.walkforward: error: {message}\n"), args
    # The weight table.
    weights = dict(re.findall(r"^\| `(\w+)` \| `([^`]+)` \|", CLI_PART[CLI_PART.index("**Work limits.**"):], re.M))
    for name, (base, slope, key) in web.WALKFORWARD_BAR_WEIGHTS.items():
        assert weights[name] == f"n x ({base:g} + {slope:g} x {key})", name
    for name, (per_read, per_window_read) in web.WALKFORWARD_READ_WEIGHTS.items():
        expected = f"reads x {per_read:g}" + (f" + past x window x {per_window_read:g}" if per_window_read else "")
        assert weights[name] == expected, name
    assert len(weights) == 7
    # The limits and the two 413 messages, from the server itself.
    assert (web.MAX_WALKFORWARD_PARAMETER_SETS, web.MAX_WALKFORWARD_BAR_STEPS) == (10_000, 300_000)
    for payload in (
        {"sample": "sideways", "train": 40, "test": 20, "strategy": "momentum",
         "grid": ["window=" + ",".join(map(str, range(1, 101))), "threshold=" + ",".join(map(str, range(101)))]},
        {"sample": "random_walk", "strategy": "zscore_reversion", "grid": ["window=5,10,20"], "train": 240, "test": 60,
         "warmup": True},
    ):
        try:
            web.parse_walkforward_request(payload)
        except web.WebError as exc:
            assert exc.status == 413
            assert f'{{"ok": false, "error": "{exc.message}"}}' in CLI_PART
        else:
            raise AssertionError(payload)
    combos = web.grid_combinations("zscore_reversion", {"window": [5, 10, 20]})
    assert web._strategy_work("zscore_reversion", combos, 8, 230, 60, True) == 277_374
    assert "277,374 bar-steps with\n`train` 230" in CLI_PART


def slugs(markdown):
    """GitHub's heading anchors: lower case, punctuation but ``-`` and ``_`` dropped, spaces to ``-``, repeats numbered."""
    found, seen = set(), {}
    body = re.sub(r"^```.*?^```", "", markdown, flags=re.S | re.M)
    for heading in re.findall(r"^#{1,6}\s+(.*?)\s*$", body, re.M):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        found.add(slug if slug not in seen else f"{slug}-{seen[slug]}")
        seen[slug] = seen.get(slug, 0) + 1
    return found


def test_every_link_and_anchor_in_the_docs_resolves():
    files = [ROOT / "README.md", ROOT / "CHANGELOG.md", *sorted((ROOT / "docs").glob("*.md"))]
    checked, broken = 0, []
    for path in files:
        text = re.sub(r"```.*?```", "", path.read_text(), flags=re.S)
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if re.match(r"https?://|mailto:", target):
                continue
            checked += 1
            name, _, anchor = target.partition("#")
            dest = (path.parent / name).resolve() if name else path
            if not dest.exists() or (anchor and dest.suffix == ".md" and anchor not in slugs(dest.read_text())):
                broken.append((path.name, target))
    assert broken == [] and checked > 180


def test_version_is_the_newest_changelog_entry():
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
    newest = re.search(r"^## (\S+) \((\d{4}-\d\d-\d\d)\)", (ROOT / "CHANGELOG.md").read_text(), re.M)
    assert newest.group(1) == version == "0.22.0"
