"""Plain-text price chart: ASCII only, no colours.

``line_chart`` draws one ``*`` per column on a grid, with the highest value
labelled on the first row and the lowest on the last. Optional single-letter
markers (``B`` for a buy, ``S`` for a sell) replace the ``*`` of the column that
holds the bar. This is a quick look at the shape of the data, not a precise plot.
"""

import math


def _columns(n, width):
    """For ``n`` bars return a list of ``(first, last)`` bar indexes, one pair per column.

    With ``n <= width`` every bar is its own column. Otherwise the bars are
    split into ``width`` consecutive buckets of near-equal size (bucket ``c``
    holds bars ``c*n//width`` up to but excluding ``(c+1)*n//width``).
    """
    if n <= width:
        return [(i, i) for i in range(n)]
    cols = []
    for c in range(width):
        lo = c * n // width
        hi = (c + 1) * n // width
        cols.append((lo, hi - 1))
    return cols


def line_chart(values, width=60, height=12, markers=None):
    """Return the chart for ``values`` as a list of text lines.

    ``values`` is a non-empty list of finite numbers. When there are more than
    ``width`` bars they are reduced to ``width`` columns by taking the last
    value of each bucket; with fewer, each bar gets a column. ``markers`` maps a
    bar index to a one-character string (the CLI uses ``"B"`` and ``"S"``); the
    marker replaces the ``*`` in the column that holds the bar, and when two
    markers land in one column the later bar wins.

    The grid has ``height`` rows. A value sits on row
    ``round((v - min) / (max - min) * (height - 1))`` counted from the bottom; a
    flat series sits on the middle row. The first row is labelled with the
    maximum and the last with the minimum (two decimals), followed by an axis
    line. Raises ValueError for no values, a non-finite value, ``width < 1``,
    ``height < 2``, a marker index outside the series, or a marker that is not
    one character.
    """
    values = list(values)
    if not values:
        raise ValueError("line_chart needs at least one value")
    if any(not math.isfinite(v) for v in values):
        raise ValueError("line_chart needs finite values")
    if width < 1:
        raise ValueError("width must be at least 1")
    if height < 2:
        raise ValueError("height must be at least 2")
    n = len(values)
    for index, mark in (markers or {}).items():
        if not 0 <= index < n:
            raise ValueError(f"marker index {index} is outside the series (0 to {n - 1})")
        if not isinstance(mark, str) or len(mark) != 1:
            raise ValueError(f"marker for bar {index} must be one character, got {mark!r}")

    cols = _columns(n, width)
    sampled = [values[last] for _, last in cols]
    lo, hi = min(sampled), max(sampled)
    grid = [[" "] * len(cols) for _ in range(height)]
    column_of = {}
    for c, (first, last) in enumerate(cols):
        for i in range(first, last + 1):
            column_of[i] = c
    rows = []
    for v in sampled:
        if hi == lo:
            rows.append((height - 1) // 2)
        else:
            rows.append(int(round((v - lo) / (hi - lo) * (height - 1))))
    for c, row in enumerate(rows):
        grid[height - 1 - row][c] = "*"
    for index in sorted(markers or {}):
        c = column_of[index]
        grid[height - 1 - rows[c]][c] = markers[index]

    top, bottom = f"{hi:.2f}", f"{lo:.2f}"
    pad = max(len(top), len(bottom))
    lines = []
    for r, cells in enumerate(grid):
        label = top if r == 0 else bottom if r == height - 1 else ""
        lines.append(f"{label:>{pad}} |{''.join(cells).rstrip()}")
    lines.append(f"{'':>{pad}} +{'-' * len(cols)}")
    return lines
