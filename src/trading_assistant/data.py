"""Reading and checking price CSV files.

The CSV must have a header row with a `close` column; a `date` column is
optional. ``load_price_table`` reads a file from disk, ``read_price_table``
reads an open file-like object (the web page uses it for uploaded text) and
``parse_price_text`` does the actual work on a string. ``load_closes`` is a
shortcut that returns only the closes.

The parser is forgiving about presentation (byte order mark, header
capitalisation and spacing, line endings, spaces around values) and strict
about content: a missing or duplicated `close` column or a value that is not
a number raises ValueError with a message that says what was found and what
is expected. OSError from opening a file propagates unchanged.

The command line module re-exports these names, so
``from trading_assistant.cli import load_price_table`` keeps working.

``load_candles`` reads a candle file (date, open, high, low, close, volume)
and returns one ``Candle`` record per row. It is as forgiving about
presentation as the close-only reader and stricter about content: every
number must be finite and written plainly (no ``1_000`` separators), prices
must be positive, the volume must not be negative, the date must not be blank,
dates must be in ascending order with no repeats, and each row's open and
close must lie inside its low..high range (so a high below the low is
rejected too).
"""

import csv
from dataclasses import dataclass

CSV_EXAMPLE = "a header row like 'date,close' followed by rows like '2026-01-02,101.5'"


def _normalise_header(name):
    return name.strip().lstrip("\ufeff").strip().lower()


def parse_price_text(text, name):
    """Parse CSV text and return ``(dates, closes)``.

    Forgiving about presentation, strict about content:

    * a leading byte order mark is ignored;
    * header names are matched ignoring surrounding spaces and capitalisation
      (``Close``, `` CLOSE `` and ``close`` are all the close column);
    * spaces around values are ignored; any line ending style is accepted.

    A wrong format raises ValueError whose message says what was found and
    what is expected. ``name`` (normally the file path) prefixes the message.
    """
    text = text.lstrip("\ufeff")
    reader = csv.DictReader(text.splitlines())
    raw_fields = reader.fieldnames or []
    if not raw_fields:
        raise ValueError(f"{name} has no 'close' column (the file is empty); expected {CSV_EXAMPLE}")

    columns = {}
    for field in raw_fields:
        if field is None:
            continue
        key = _normalise_header(field)
        columns.setdefault(key, []).append(field)
    found = ", ".join(repr(f) for f in raw_fields if f is not None)

    if "close" not in columns:
        raise ValueError(f"{name} has no 'close' column (found columns: {found}); expected {CSV_EXAMPLE}")
    if len(columns["close"]) > 1:
        dupes = ", ".join(repr(f) for f in columns["close"])
        raise ValueError(f"{name} has more than one 'close' column ({dupes}); expected exactly one")
    close_key = columns["close"][0]
    date_key = columns["date"][0] if len(columns.get("date", [])) == 1 else None

    closes = []
    dates = [] if date_key is not None else None
    for row in reader:
        raw = row.get(close_key)
        value = "" if raw is None else raw.strip()
        try:
            closes.append(float(value))
        except ValueError:
            # reader.line_num is 1-based and counts the header line.
            raise ValueError(
                f"{name} line {reader.line_num}: invalid close value {value!r} (expected a number like 101.5)"
            ) from None
        if dates is not None:
            dates.append((row.get(date_key) or "").strip())
    return dates, closes


def read_price_table(fileobj, name):
    """Parse CSV text from an open file-like object (see ``parse_price_text``)."""
    return parse_price_text(fileobj.read(), name)


def decode_price_bytes(data):
    """Decode CSV bytes: UTF-8 (with or without BOM), falling back to Latin-1 so that
    a stray non-UTF-8 byte in a date label never stops the numbers being read."""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def load_price_table(path):
    """Read a CSV file and return ``(dates, closes)``.

    ``closes`` is a list of floats from the `close` column. ``dates`` is the
    list of strings from the `date` column, or None if the file has no such
    column. Raises ValueError if the header has no `close` column or a row
    holds a value that is not a number. OSError (e.g. FileNotFoundError)
    propagates unchanged when the file cannot be opened.
    """
    with open(path, "rb") as f:
        return parse_price_text(decode_price_bytes(f.read()), path)


def load_closes(path):
    """Read the `close` column of a CSV file as a list of floats.

    See ``load_price_table`` for the errors raised.
    """
    return load_price_table(path)[1]


CANDLE_COLUMNS = ("date", "open", "high", "low", "close", "volume")

CANDLE_EXAMPLE = (
    "a header row like 'date,open,high,low,close,volume' "
    "followed by rows like '2026-01-02,100.5,103.0,99.5,101.5,12000'"
)


@dataclass(frozen=True)
class Candle:
    """One bar of a candle file: the date label, the four prices and the volume."""

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def parse_candle_text(text, name):
    """Parse candle CSV text and return a list of ``Candle`` records, one per row.

    As forgiving about presentation as ``parse_price_text`` (byte order mark,
    header capitalisation and spacing, any column order, extra columns, blank
    lines, any line ending style, spaces around values) and strict about
    content. A row is rejected, with a ValueError whose message names the line
    and what is wrong, when:

    * ``open``, ``high``, ``low``, ``close`` or ``volume`` is not a number,
      is ``nan`` or infinite, or uses ``_`` separators (``1_000``);
    * a price is not positive, or the volume is negative;
    * the ``date`` is blank, repeats an earlier date, or comes before the
      previous row's date (dates are compared as text, which is date order
      for the ``YYYY-MM-DD`` dates the rest of the tool expects);
    * ``high`` is lower than ``low``, or ``open`` or ``close`` lies outside
      the row's low..high range.

    The header must hold each of the six candle columns exactly once;
    ``name`` (normally the file path) prefixes every message.
    """
    text = text.lstrip("\ufeff")
    reader = csv.DictReader(text.splitlines())
    raw_fields = reader.fieldnames or []
    if not raw_fields:
        raise ValueError(f"{name} has no candle header (the file is empty); expected {CANDLE_EXAMPLE}")

    columns = {}
    for field in raw_fields:
        if field is None:
            continue
        key = _normalise_header(field)
        columns.setdefault(key, []).append(field)
    found = ", ".join(repr(f) for f in raw_fields if f is not None)

    missing = [column for column in CANDLE_COLUMNS if column not in columns]
    if missing:
        wanted = ", ".join(repr(c) for c in missing)
        plural = "s" if len(missing) > 1 else ""
        raise ValueError(
            f"{name} has no {wanted} column{plural} (found columns: {found}); expected {CANDLE_EXAMPLE}"
        )
    for column in CANDLE_COLUMNS:
        if len(columns[column]) > 1:
            dupes = ", ".join(repr(f) for f in columns[column])
            raise ValueError(f"{name} has more than one {column!r} column ({dupes}); expected exactly one")
    keys = {column: columns[column][0] for column in CANDLE_COLUMNS}

    candles = []
    previous_date = None
    previous_line = None
    for row in reader:
        # reader.line_num is 1-based and counts the header line.
        line = reader.line_num
        date = (row.get(keys["date"]) or "").strip()
        if not date:
            raise ValueError(f"{name} line {line}: missing date (expected a value like 2026-01-02)")
        if previous_date is not None:
            if date == previous_date:
                raise ValueError(f"{name} line {line}: date {date!r} repeats the date on line {previous_line}")
            if date < previous_date:
                raise ValueError(
                    f"{name} line {line}: date {date!r} is before the previous date {previous_date!r} "
                    f"on line {previous_line} (dates must be in ascending order)"
                )
        previous_date, previous_line = date, line
        values = {}
        for column in CANDLE_COLUMNS[1:]:
            raw = row.get(keys[column])
            value_text = "" if raw is None else raw.strip()
            try:
                value = float(value_text)
            except ValueError:
                raise ValueError(
                    f"{name} line {line}: invalid {column} value {value_text!r} (expected a number like 101.5)"
                ) from None
            if "_" in value_text:
                # float() accepts 1_000; a price file should not.
                raise ValueError(
                    f"{name} line {line}: invalid {column} value {value_text!r} "
                    f"(expected a number like 101.5, without '_' separators)"
                )
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError(
                    f"{name} line {line}: invalid {column} value {value_text!r} (expected a finite number)"
                )
            if column == "volume":
                if value < 0:
                    raise ValueError(f"{name} line {line}: volume must not be negative, got {value:g}")
            elif not value > 0:
                raise ValueError(f"{name} line {line}: {column} must be positive, got {value:g}")
            values[column] = value
        high, low = values["high"], values["low"]
        if high < low:
            raise ValueError(f"{name} line {line}: high {high:g} is lower than the low {low:g}")
        for column in ("open", "close"):
            if not low <= values[column] <= high:
                raise ValueError(
                    f"{name} line {line}: {column} {values[column]:g} is outside "
                    f"the low..high range {low:g}..{high:g}"
                )
        candles.append(Candle(date=date, **values))
    return candles


def read_candle_table(fileobj, name):
    """Parse candle CSV text from an open file-like object (see ``parse_candle_text``)."""
    return parse_candle_text(fileobj.read(), name)


def load_candles(path):
    """Read a candle CSV file and return a list of ``Candle`` records, one per row.

    The bytes are decoded like the close-only reader's (``decode_price_bytes``).
    Raises ValueError for a bad header or row (see ``parse_candle_text``).
    OSError (e.g. FileNotFoundError) propagates unchanged when the file cannot
    be opened.
    """
    with open(path, "rb") as f:
        return parse_candle_text(decode_price_bytes(f.read()), path)
