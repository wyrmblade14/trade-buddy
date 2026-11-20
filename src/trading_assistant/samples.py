"""Built-in, seeded sample price series.

Every series is generated from a fixed seed with ``random.Random`` (Mersenne
Twister, whose output for a given seed is stable across Python versions), so
it comes out identical on every run and every machine. Noise is built from
sums of ``random()`` draws rather than ``gauss()`` to stay independent of any
change in the normal-variate algorithm.

Usage from the command line (writes a CSV the CLI can read):

    python -m trading_assistant.samples random_walk > random_walk.csv
    python -m trading_assistant.samples random_walk random_walk.csv
    python -m trading_assistant.samples --list

With ``--candles`` the same sample is written as a candle file (date, open,
high, low, close, volume) for ``--candles`` / ``--fill open`` in the CLI. The
closes are exactly those of the close-only file; open, high, low and volume
are derived from them with the same seeded, version-stable randomness, so the
candle file is identical on every run too.
"""

import argparse
import csv
import random
import sys
from datetime import date, timedelta
from functools import lru_cache

from .data import CANDLE_COLUMNS, Candle

SEED = 20240101
START_DATE = date(2023, 1, 2)


def _noise(rng):
    """Approximately standard-normal noise from 12 uniform draws."""
    return sum(rng.random() for _ in range(12)) - 6.0


def _business_dates(n, start=START_DATE):
    out = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _finish(prices):
    return [max(1.0, round(p, 2)) for p in prices]


def _trend(n, drift, vol, seed, lead_in=60):
    """``lead_in`` bars drifting gently the other way, then ``n - lead_in`` bars of trend."""
    rng = random.Random(seed)
    p = 100.0
    out = []
    for i in range(n):
        d = -drift / 3 if i < lead_in else drift
        p *= 1 + d + vol * _noise(rng)
        p = max(p, 1.0)
        out.append(p)
    return _finish(out)


def uptrend(n=200):
    """Short dip, then a steady rise with mild daily noise."""
    return _trend(n, drift=0.003, vol=0.008, seed=SEED + 1)


def downtrend(n=200):
    """Short rally, then a steady fall with mild daily noise."""
    return _trend(n, drift=-0.003, vol=0.008, seed=SEED + 2)


def sideways(n=150):
    """Choppy, mean-reverting market around 100 that never gets anywhere."""
    rng = random.Random(SEED + 3)
    p = 100.0
    out = []
    for _ in range(n):
        p += 0.25 * (100.0 - p) + 1.6 * _noise(rng)
        out.append(p)
    return _finish(out)


def random_walk(n=750):
    """Long, realistic-looking path: small drift, clustered volatility, rare jumps."""
    rng = random.Random(SEED + 4)
    p = 100.0
    vols = (0.006, 0.012, 0.024)
    regime = 1
    out = []
    for _ in range(n):
        if rng.random() < 0.02:
            regime = rng.randrange(len(vols))
        ret = 0.0003 + vols[regime] * _noise(rng)
        if rng.random() < 0.01:
            ret += rng.choice((-1, 1)) * rng.uniform(0.03, 0.08)
        p *= 1 + ret
        p = max(p, 1.0)
        out.append(p)
    return _finish(out)


SAMPLES = {
    "uptrend": ("Steady up trend", "200 bars: a 60-bar dip, then a rise of about 0.3% a day", uptrend),
    "downtrend": ("Steady down trend", "200 bars: a 60-bar rally, then a fall of about 0.3% a day", downtrend),
    "sideways": ("Choppy sideways", "150 bars, mean-reverting around 100", sideways),
    "random_walk": (
        "Long realistic random walk",
        "750 bars (about three years), seeded so it is identical every run",
        random_walk,
    ),
}


def sample_names():
    return list(SAMPLES)


def describe_samples():
    """List of dicts (name, label, description, bars) for menus."""
    return [
        {"name": name, "label": label, "description": desc, "bars": len(sample_table(name)[1])}
        for name, (label, desc, _) in SAMPLES.items()
    ]


@lru_cache(maxsize=None)
def _cached_table(name):
    _, _, generator = SAMPLES[name]
    closes = generator()
    return tuple(_business_dates(len(closes))), tuple(closes)


def sample_table(name):
    """Return ``(dates, closes)`` lists for a sample. Raises ValueError for an unknown name."""
    if name not in SAMPLES:
        raise ValueError(f"unknown sample {name!r}; choose one of: {', '.join(SAMPLES)}")
    dates, closes = _cached_table(name)
    return list(dates), list(closes)


def sample_csv_rows(name):
    dates, closes = sample_table(name)
    return [("date", "close")] + [(d, f"{c:.2f}") for d, c in zip(dates, closes)]


@lru_cache(maxsize=None)
def _cached_candles(name):
    dates, closes = sample_table(name)
    # A string seed is hashed with SHA-512, so it is as stable as an integer seed.
    rng = random.Random(f"{SEED}:{name}:candles")
    out = []
    previous = closes[0]
    for day, close in zip(dates, closes):
        # Open: last close plus a small overnight gap; first bar opens near its own close.
        open_ = max(1.0, round(previous * (1 + 0.002 * _noise(rng)), 2))
        # High and low: a random wick above and below the open..close body.
        high = round(max(open_, close) * (1 + abs(0.004 * _noise(rng))), 2)
        low = round(min(open_, close) * (1 - abs(0.004 * _noise(rng))), 2)
        high = max(high, open_, close)
        low = max(0.01, min(low, open_, close))
        # Volume: around a million shares, heavier on big moves.
        move = abs(close / previous - 1)
        volume = int(round(1_000_000 * (0.6 + 0.8 * rng.random()) * (1 + 20 * move)))
        out.append(Candle(date=day, open=open_, high=high, low=low, close=close, volume=float(volume)))
        previous = close
    return tuple(out)


def sample_candles(name):
    """Return the sample as a list of ``data.Candle`` records, one per bar.

    The closes and dates are exactly those of ``sample_table``. Raises
    ValueError for an unknown name.
    """
    if name not in SAMPLES:
        raise ValueError(f"unknown sample {name!r}; choose one of: {', '.join(SAMPLES)}")
    return list(_cached_candles(name))


def sample_candle_csv_rows(name):
    rows = [CANDLE_COLUMNS]
    for c in sample_candles(name):
        rows.append((c.date, f"{c.open:.2f}", f"{c.high:.2f}", f"{c.low:.2f}", f"{c.close:.2f}", str(int(c.volume))))
    return rows


def write_sample_csv(name, fileobj, candles=False):
    """Write the sample as ``date,close`` CSV to an open text file.

    With ``candles`` true, write a ``date,open,high,low,close,volume`` candle
    file instead (see ``sample_candles``).
    """
    writer = csv.writer(fileobj, lineterminator="\n")
    writer.writerows(sample_candle_csv_rows(name) if candles else sample_csv_rows(name))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="trading_assistant.samples",
        description="Write a built-in seeded sample price series as CSV.",
    )
    parser.add_argument("name", nargs="?", help="sample name (see --list)")
    parser.add_argument("output", nargs="?", help="output file (default: stdout)")
    parser.add_argument("--list", action="store_true", help="list the available samples")
    parser.add_argument(
        "--candles",
        action="store_true",
        help="write a candle file (date, open, high, low, close, volume) instead of date,close",
    )
    args = parser.parse_args(argv)

    if args.list:
        for info in describe_samples():
            print(f"{info['name']:<12s} {info['bars']:>5d} bars  {info['label']} - {info['description']}")
        return 0
    if not args.name:
        parser.error("a sample name is required (see --list)")
    try:
        if args.output:
            with open(args.output, "w", newline="") as f:
                write_sample_csv(args.name, f, candles=args.candles)
        else:
            write_sample_csv(args.name, sys.stdout, candles=args.candles)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: cannot write {args.output}: {exc.strerror or exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
