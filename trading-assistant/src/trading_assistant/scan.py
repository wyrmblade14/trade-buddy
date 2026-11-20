"""Score every price file in a folder (``--scan FOLDER`` on the command line).

Only files directly inside the folder whose name ends in ``.csv`` (any
capitalisation) are read; subfolders and every other kind of file are
ignored. The file name without ``.csv`` is the symbol.

Each file is read exactly like the single-file command reads a price file
(``data.decode_price_bytes`` then ``data.parse_price_text``), and its closes
get ``signals.combined_score``. A file that cannot be read, has no ``close``
column, holds a value that is not a number or has no rows is skipped with a
one-line reason, and the scan carries on with the rest.

The table lists the highest score first; files with the same score are in
name order. ``min_score`` keeps only rows whose score is at or above it and
``top`` then keeps the first N of those, in the same order; the skipped list
is always shown in full. Without either the output is the plain scan table.
``scan_data`` gives the same information as a plain dict for ``--json``.
``report_markdown`` / ``write_report`` build and write the ``--report FILE``
Markdown report: title, date, settings, the shown rows, one sentence per row
explaining its score from its four parts, the skipped files and the
disclaimer.

This is a research aid. It does not place orders and it is not financial advice.
"""

import datetime
import inspect
import os
from dataclasses import dataclass, field

from .data import decode_price_bytes, parse_price_text
from .indicators import bollinger_bands, macd
from .signals import combined_score

PARTS = ("crossover", "rsi", "macd", "bollinger")
HEADERS = ("Symbol", "Bars", "Score", "Crossover", "RSI", "MACD", "Bollinger")


class ScanError(ValueError):
    """A folder problem that stops the whole scan (one-line message)."""


class ScanLimitError(ScanError):
    """A file over the caller's row limit (``scan_texts(max_bars=...)``); stops the whole scan."""


@dataclass(frozen=True)
class ScanRow:
    """One scored file: its symbol, file name, bar count, total score and the four parts."""

    symbol: str
    filename: str
    bars: int
    score: int
    parts: dict


@dataclass
class ScanResult:
    """Scored rows (best first) and ``(filename, reason)`` for every skipped file."""

    folder: str
    rows: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    paths: list = field(default_factory=list)  # every .csv file that was read


def price_files(folder, label="scan folder"):
    """``(symbol, filename, path)`` for every ``.csv`` file directly inside ``folder``, by file name.

    Raises ScanError when the folder does not exist, is not a folder, cannot
    be listed, or holds no ``.csv`` file. ``label`` names the folder in those
    messages (the portfolio command passes ``"portfolio folder"``).
    """
    if not os.path.exists(folder):
        raise ScanError(f"{label} {folder} does not exist")
    if not os.path.isdir(folder):
        raise ScanError(f"{label} {folder} is not a folder")
    try:
        names = os.listdir(folder)
    except OSError as exc:
        raise ScanError(f"cannot read {label} {folder}: {exc.strerror or exc}") from None
    found = []
    for name in sorted(names):
        symbol, ext = os.path.splitext(name)
        path = os.path.join(folder, name)
        if ext.lower() == ".csv" and os.path.isfile(path):
            found.append((symbol, name, path))
    if not found:
        raise ScanError(f"no .csv files directly inside {folder}")
    return found


def read_closes(path, name):
    """The closes of one price file, read like the single-file command reads it.

    ``name`` prefixes any error message. Raises ValueError for a bad file and
    OSError when it cannot be opened.
    """
    with open(path, "rb") as f:
        return parse_price_text(decode_price_bytes(f.read()), name)[1]


def _one_line(text):
    return " ".join(str(text).split())


def _score_files(result, entries, short, long, rsi_period, max_bars=None):
    """Score ``entries`` (``(symbol, filename, load)``, ``load()`` returning the closes) into ``result``.

    ``load`` raising OSError or ValueError, or returning no closes, skips the
    file with a one-line reason. Rows are sorted highest score first, then by
    symbol. Raises ScanError when no file could be scored and ScanLimitError
    when a file has more than ``max_bars`` rows.
    """
    for symbol, name, load in entries:
        try:
            closes = load()
        except OSError as exc:
            result.skipped.append((name, f"{name}: cannot read the file ({exc.strerror or exc})"))
            continue
        except ValueError as exc:
            result.skipped.append((name, _one_line(exc)))
            continue
        if not closes:
            result.skipped.append((name, f"{name}: no price rows found"))
            continue
        if max_bars is not None and len(closes) > max_bars:
            raise ScanLimitError(f"{name} has too many price rows ({len(closes):,}); the limit is {max_bars:,}")
        score, parts = combined_score(closes, short=short, long=long, rsi_period=rsi_period)
        result.rows.append(ScanRow(symbol, name, len(closes), score, parts))
    if not result.rows:
        count = len(entries)
        noun = "file" if count == 1 else "files"
        raise ScanError(f"none of the {count} .csv {noun} in {result.folder} could be scored ({count} skipped)")
    result.rows.sort(key=lambda row: (-row.score, row.symbol.casefold(), row.symbol, row.filename))
    return result


def scan_folder(folder, short=20, long=50, rsi_period=14):
    """Score every ``.csv`` file directly inside ``folder``.

    Returns a ScanResult whose rows are sorted highest score first, then by
    symbol. Raises ScanError for a folder problem (see ``price_files``) and
    when no file could be scored at all.
    """
    files = price_files(folder)
    result = ScanResult(folder=folder, paths=[path for _, _, path in files])
    entries = [(symbol, name, lambda path=path, name=name: read_closes(path, name)) for symbol, name, path in files]
    return _score_files(result, entries, short, long, rsi_period)


def scan_texts(files, short=20, long=50, rsi_period=14, label="the request", max_bars=None):
    """Score CSV texts held in memory: ``files`` maps a file name to its CSV text.

    Never reads the disk: the names are only labels. They are treated like
    the names in a folder: only names ending in ``.csv`` (any capitalisation)
    count, in name order, and the symbol is the name without ``.csv``. Each
    text is parsed like a price file (``data.parse_price_text``), so the rows,
    skipped files and reasons match ``scan_folder`` on the same files.
    ``label`` stands in for the folder in messages. Raises ScanError when
    there is no ``.csv`` name or no file could be scored, and ScanLimitError
    when a file has more than ``max_bars`` rows.
    """
    entries = []
    for name in sorted(files):
        symbol, ext = os.path.splitext(name)
        if ext.lower() == ".csv":
            text = files[name]
            entries.append((symbol, name, lambda text=text, name=name: parse_price_text(text, name)[1]))
    if not entries:
        raise ScanError(f"no .csv files in {label}")
    return _score_files(ScanResult(folder=label), entries, short, long, rsi_period, max_bars=max_bars)


def trim_rows(rows, min_score=None, top=None):
    """``(matched, shown)``: the rows with a score at or above ``min_score``, then the first ``top`` of them.

    ``rows`` must already be in table order; None means "no limit".
    """
    matched = [row for row in rows if min_score is None or row.score >= min_score]
    shown = matched if top is None else matched[:top]
    return matched, shown


def _signed(value):
    return f"{value:+d}" if value else "0"


def format_scan(result, min_score=None, top=None):
    """The text table for a ScanResult, then the skipped files (without the disclaimer).

    With ``min_score`` and/or ``top`` only the trimmed rows are listed (see
    ``trim_rows``) and the top line also counts the files found, the rows
    left by ``min_score`` and the rows shown. When nothing is left the table
    header is followed by a "no file matched" line.
    """
    trimming = min_score is not None or top is not None
    matched, shown = trim_rows(result.rows, min_score, top)
    table = [HEADERS] + [
        (row.symbol, str(row.bars), _signed(row.score)) + tuple(_signed(row.parts[p]) for p in PARTS)
        for row in shown
    ]
    widths = [max(len(line[i]) for line in table) for i in range(len(HEADERS))]
    top_line = f"Scan:    {result.folder}, {len(result.rows)} scored, {len(result.skipped)} skipped"
    if trimming:
        found = len(result.rows) + len(result.skipped)
        top_line = f"Scan:    {result.folder}, {found} found, {len(result.rows)} scored, {len(result.skipped)} skipped"
        if min_score is not None:
            top_line += f", {len(matched)} with score >= {min_score}"
        top_line += f", {len(shown)} shown" + (f" (top {top})" if top is not None else "")
    lines = [top_line]
    for line in table:
        cells = [line[0].ljust(widths[0])] + [cell.rjust(w) for cell, w in zip(line[1:], widths[1:])]
        lines.append("  ".join(cells).rstrip())
    if not shown:
        lines.append(f"  (no file matched: no score at or above {min_score})")
    if result.skipped:
        lines.append(f"Skipped: {len(result.skipped)}")
        lines += [f"  {reason}" for _, reason in result.skipped]
    return lines


def scan_data(result, min_score=None, top=None):
    """The ``--scan --json`` object for a ScanResult: the table's information as plain values.

    ``found``, ``scored`` and ``shown`` are counted like the table's top line
    (found = scored + skipped; shown = rows left after ``min_score`` and
    ``top``, which is all scored rows without them). ``results`` lists the
    shown rows in table order, each with ``symbol``, ``bars``, ``score`` and
    ``parts`` (crossover, rsi, macd, bollinger). ``skipped`` lists every
    skipped file, whatever the trimming, with ``symbol`` (the file name
    without .csv) and ``reason`` (the table's one-line reason).
    """
    _, shown = trim_rows(result.rows, min_score, top)
    return {
        "found": len(result.rows) + len(result.skipped),
        "scored": len(result.rows),
        "shown": len(shown),
        "results": [
            {
                "symbol": row.symbol,
                "bars": row.bars,
                "score": row.score,
                "parts": {part: row.parts[part] for part in PARTS},
            }
            for row in shown
        ],
        "skipped": [
            {"symbol": os.path.splitext(filename)[0], "reason": reason} for filename, reason in result.skipped
        ],
    }


def report_date():
    """Today's date for the report (a function so tests can fix it)."""
    return datetime.date.today()


def _defaults(fn, *names):
    params = inspect.signature(fn).parameters
    return tuple(params[name].default for name in names)


# combined_score always calls macd() and bollinger_bands() with their defaults.
MACD_SETTINGS = _defaults(macd, "fast", "slow", "signal")
BOLLINGER_SETTINGS = _defaults(bollinger_bands, "window", "num_std")

_MD_SPECIAL = set("\\`*_[]<>|#")


def _md(text):
    """Escape the characters Markdown would read as formatting."""
    return "".join("\\" + ch if ch in _MD_SPECIAL else ch for ch in str(text))


def explain_row(row, short=20, long=50, rsi_period=14):
    """One plain sentence saying why ``row`` scored what it did, built only from its four parts."""
    crossover = {
        1: f"the {short}-bar average is above the {long}-bar average",
        -1: f"the {short}-bar average is below the {long}-bar average",
        0: f"the {short}-bar and {long}-bar averages are level or there is not enough history",
    }
    rsi_text = {
        1: f"the {rsi_period}-bar RSI is under 30",
        -1: f"the {rsi_period}-bar RSI is over 70",
        0: f"the {rsi_period}-bar RSI is from 30 to 70 or there is not enough history",
    }
    macd_text = {
        1: "the MACD histogram is above 0",
        -1: "the MACD histogram is below 0",
        0: "the MACD histogram is at 0 or there is not enough history",
    }
    bollinger = {
        1: "the last close is below the lower Bollinger band",
        -1: "the last close is above the upper Bollinger band",
        0: "the last close is inside or on the Bollinger bands or there is not enough history",
    }
    p = row.parts
    return (
        f"{_md(row.symbol)} scored {_signed(row.score)}: "
        f"{crossover[p['crossover']]} (crossover {_signed(p['crossover'])}), "
        f"{rsi_text[p['rsi']]} (RSI {_signed(p['rsi'])}), "
        f"{macd_text[p['macd']]} (MACD {_signed(p['macd'])}) and "
        f"{bollinger[p['bollinger']]} (Bollinger {_signed(p['bollinger'])})."
    )


def report_markdown(result, disclaimer, short=20, long=50, rsi_period=14, min_score=None, top=None, today=None):
    """The ``--report`` Markdown text for a ScanResult.

    The rows are the ones the screen shows (``trim_rows``), in the same order;
    the skipped list is always complete. ``today`` defaults to ``report_date()``.
    """
    today = report_date() if today is None else today
    _, shown = trim_rows(result.rows, min_score, top)
    fast, slow, signal = MACD_SETTINGS
    window, num_std = BOLLINGER_SETTINGS
    found = len(result.rows) + len(result.skipped)
    lines = [
        f"# Scan report: {_md(result.folder)}",
        "",
        f"Date: {today.isoformat()}",
        "",
        "## Settings",
        "",
        f"- Folder: {_md(result.folder)}",
        f"- Crossover: {short}-bar against {long}-bar simple moving average "
        "(above scores +1, below scores -1)",
        f"- RSI: {rsi_period} bars (under 30 scores +1, over 70 scores -1)",
        f"- MACD: {fast} / {slow} / {signal} (histogram above 0 scores +1, below 0 scores -1)",
        f"- Bollinger: {window} bars, {num_std:g} deviations "
        "(close below the lower band scores +1, above the upper band scores -1)",
        f"- Min score: {'none' if min_score is None else min_score}",
        f"- Top: {'none' if top is None else top}",
        f"- Files: {found} found, {len(result.rows)} scored, {len(result.skipped)} skipped, {len(shown)} shown",
        "",
        "## Results",
        "",
        "| " + " | ".join(HEADERS) + " |",
        "|---|" + "---:|" * (len(HEADERS) - 1),
    ]
    for row in shown:
        cells = [_md(row.symbol), str(row.bars), _signed(row.score)] + [_signed(row.parts[p]) for p in PARTS]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    if shown:
        lines += [f"- {explain_row(row, short, long, rsi_period)}" for row in shown]
    else:
        lines.append(f"No file matched: no score at or above {min_score}.")
    lines += ["", "## Skipped", ""]
    if result.skipped:
        lines += [f"- {_md(reason)}" for _, reason in result.skipped]
    else:
        lines.append("None.")
    lines += ["", disclaimer, ""]
    return "\n".join(lines)


def write_report(path, text):
    """Write the report text to ``path`` (UTF-8). OSError propagates."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
