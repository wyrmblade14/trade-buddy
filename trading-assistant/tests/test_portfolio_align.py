"""Tests for trading_assistant.portfolio.align_tables.

Every expected value below is worked out by hand, not computed.
"""

import pytest

from trading_assistant.portfolio import align_tables


def test_partial_overlap_keeps_only_dates_every_symbol_has():
    #             01-02  01-05  01-06  01-07  01-08  01-09
    #   AAA        10     11     12     13     14     -
    #   BBB        20     -      22     23     24     25
    #   CCC        -      31     32     -      34     -
    # Shared by all three: 01-06 and 01-08. 01-07 is missing only from CCC
    # and is dropped for everyone (no filling in).
    # AAA loses 01-02, 01-05, 01-07 -> 3
    # BBB loses 01-02, 01-07, 01-09 -> 3
    # CCC loses 01-05               -> 1
    tables = {
        "AAA": (["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"],
                [10.0, 11.0, 12.0, 13.0, 14.0]),
        "BBB": (["2026-01-02", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"],
                [20.0, 22.0, 23.0, 24.0, 25.0]),
        "CCC": (["2026-01-05", "2026-01-06", "2026-01-08"],
                [31.0, 32.0, 34.0]),
    }

    dates, closes, lost = align_tables(tables)

    assert dates == ["2026-01-06", "2026-01-08"]
    assert closes == {"AAA": [12.0, 14.0], "BBB": [22.0, 24.0], "CCC": [32.0, 34.0]}
    assert lost == {"AAA": 3, "BBB": 3, "CCC": 1}


def test_no_shared_dates_returns_empty_lists_and_loses_every_bar():
    # Every pair shares a date, but no date is in all three:
    #   AAA and BBB share 01-05, BBB and CCC share 01-06, CCC and AAA share 01-02.
    tables = {
        "AAA": (["2026-01-02", "2026-01-05"], [10.0, 11.0]),
        "BBB": (["2026-01-05", "2026-01-06"], [21.0, 22.0]),
        "CCC": (["2026-01-02", "2026-01-06"], [30.0, 32.0]),
    }

    dates, closes, lost = align_tables(tables)

    assert dates == []
    assert closes == {"AAA": [], "BBB": [], "CCC": []}
    assert lost == {"AAA": 2, "BBB": 2, "CCC": 2}


def test_all_dates_match_loses_nothing():
    tables = {
        "AAA": (["2026-01-02", "2026-01-05", "2026-01-06"], [10.0, 11.0, 12.0]),
        "BBB": (["2026-01-02", "2026-01-05", "2026-01-06"], [20.0, 21.0, 22.0]),
    }

    dates, closes, lost = align_tables(tables)

    assert dates == ["2026-01-02", "2026-01-05", "2026-01-06"]
    assert closes == {"AAA": [10.0, 11.0, 12.0], "BBB": [20.0, 21.0, 22.0]}
    assert lost == {"AAA": 0, "BBB": 0}


def test_empty_input_gives_empty_results():
    assert align_tables({}) == ([], {}, {})


def test_duplicate_date_raises_rather_than_picking_a_close():
    tables = {"AAA": (["2026-01-02", "2026-01-02"], [10.0, 11.0])}
    with pytest.raises(ValueError, match=r"AAA: date '2026-01-02' appears more than once"):
        align_tables(tables)


def test_dates_and_closes_of_different_length_raise():
    tables = {"AAA": (["2026-01-02", "2026-01-05"], [10.0])}
    with pytest.raises(ValueError, match=r"AAA: 2 dates but 1 closes"):
        align_tables(tables)


def test_missing_dates_raise():
    # load_price_table returns dates=None for a file without a date column.
    tables = {"AAA": (None, [10.0, 11.0])}
    with pytest.raises(ValueError, match=r"AAA: no dates"):
        align_tables(tables)
