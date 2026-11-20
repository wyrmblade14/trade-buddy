"""Turn daily bars into weekly or monthly bars.

Usage from Python:

    dates, closes = resample(dates, closes, "weekly")

A bar belongs to the group of its ISO year and ISO week (weekly) or its
calendar year and month (monthly). Each group is reduced to its last date and
last close, so the output is in the same order as the input. Note that the ISO
year can differ from the calendar year in late December and early January:
2025-12-29 is in ISO week 1 of 2026.
"""

from datetime import date

PERIODS = ("weekly", "monthly")


def _group_key(day, period):
    if period == "weekly":
        iso = day.isocalendar()
        return (iso[0], iso[1])
    return (day.year, day.month)


def resample(dates, closes, period):
    """Return ``(dates, closes)`` with one bar per week or month.

    ``dates`` are ``YYYY-MM-DD`` strings in strictly ascending order, one per
    close. ``period`` is "weekly" or "monthly". Raises ValueError for an
    unknown period, for lists of different length, and, naming the 1-based
    data row, for a date that cannot be parsed or is not after the previous one.
    """
    if period not in PERIODS:
        raise ValueError(f"unknown period {period!r}; choose one of: {', '.join(PERIODS)}")
    if len(dates) != len(closes):
        raise ValueError(f"{len(dates)} dates but {len(closes)} closes")

    out_dates = []
    out_closes = []
    last_key = None
    previous = None
    for row, (text, close) in enumerate(zip(dates, closes), start=1):
        try:
            day = date.fromisoformat(text.strip())
        except ValueError:
            raise ValueError(f"row {row}: invalid date {text!r} (expected YYYY-MM-DD)") from None
        if previous is not None and day <= previous:
            raise ValueError(
                f"row {row}: date {day.isoformat()} is not after the previous date {previous.isoformat()}"
            )
        previous = day
        key = _group_key(day, period)
        if key == last_key:
            out_dates[-1] = day.isoformat()
            out_closes[-1] = close
        else:
            out_dates.append(day.isoformat())
            out_closes.append(close)
            last_key = key
    return out_dates, out_closes
