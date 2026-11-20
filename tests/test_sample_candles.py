"""Tests for writing the built-in samples as candle files
(``python -m trading_assistant.samples NAME --candles``).

The closes of a sample's candle file are exactly the closes of its close-only
file, the other columns are derived deterministically, and the strict candle
reader accepts every file. The existing close-only output is unchanged.
"""

import io

import pytest

from trading_assistant.cli import main as cli_main
from trading_assistant.data import CANDLE_COLUMNS, Candle, load_candles, parse_candle_text
from trading_assistant.samples import SAMPLES, sample_candles, sample_table, write_sample_csv
from trading_assistant.samples import main as samples_main


# --------------------------------------------------------------------------- records


@pytest.mark.parametrize("name", list(SAMPLES))
def test_sample_candles_share_dates_and_closes_with_the_close_only_sample(name):
    dates, closes = sample_table(name)
    candles = sample_candles(name)
    assert len(candles) == len(closes)
    assert [c.date for c in candles] == dates
    assert [c.close for c in candles] == closes


@pytest.mark.parametrize("name", list(SAMPLES))
def test_sample_candles_are_valid_candles(name):
    for c in sample_candles(name):
        assert isinstance(c, Candle)
        assert 0 < c.low <= min(c.open, c.close) <= max(c.open, c.close) <= c.high
        assert c.volume >= 0 and c.volume == int(c.volume)
        assert all(round(v, 2) == v for v in (c.open, c.high, c.low, c.close))


@pytest.mark.parametrize("name", list(SAMPLES))
def test_sample_candles_are_not_flat(name):
    candles = sample_candles(name)
    assert any(c.open != c.close for c in candles)
    assert all(c.high > c.low for c in candles)
    assert len({c.volume for c in candles}) > len(candles) // 2  # volume varies


@pytest.mark.parametrize("name", list(SAMPLES))
def test_sample_candles_are_deterministic(name):
    assert sample_candles(name) == sample_candles(name)
    first = sample_candles(name)
    first[0] = None  # the returned list is a copy
    assert sample_candles(name)[0] is not None


def test_sample_candles_snapshot_values():
    # Frozen first candles: the files must come out the same on every run and machine.
    assert sample_candles("uptrend")[0] == Candle("2023-01-02", 100.44, 100.71, 99.84, 100.44, 711891.0)
    assert sample_candles("downtrend")[0] == Candle("2023-01-02", 100.65, 101.22, 100.38, 100.82, 1381296.0)
    assert sample_candles("sideways")[0] == Candle("2023-01-02", 97.79, 98.48, 97.39, 98.09, 836987.0)
    assert sample_candles("random_walk")[0] == Candle("2023-01-02", 100.94, 101.39, 100.78, 100.91, 1103459.0)
    assert sample_candles("random_walk")[1] == Candle("2023-01-03", 100.99, 102.04, 100.00, 100.75, 824209.0)


def test_unknown_sample_raises():
    with pytest.raises(ValueError, match="unknown sample 'x'"):
        sample_candles("x")


# --------------------------------------------------------------------------- CSV


@pytest.mark.parametrize("name", list(SAMPLES))
def test_candle_csv_is_accepted_by_the_strict_reader_and_round_trips(name):
    buf = io.StringIO()
    write_sample_csv(name, buf, candles=True)
    text = buf.getvalue()
    assert text.startswith(",".join(CANDLE_COLUMNS) + "\n")
    assert parse_candle_text(text, name) == sample_candles(name)


def test_candle_csv_first_rows(tmp_path):
    buf = io.StringIO()
    write_sample_csv("random_walk", buf, candles=True)
    assert buf.getvalue().splitlines()[:3] == [
        "date,open,high,low,close,volume",
        "2023-01-02,100.94,101.39,100.78,100.91,1103459",
        "2023-01-03,100.99,102.04,100.00,100.75,824209",
    ]


def test_close_only_csv_is_unchanged():
    buf = io.StringIO()
    write_sample_csv("sideways", buf)
    assert buf.getvalue().startswith("date,close\n2023-01-02,98.09\n")
    default, explicit = io.StringIO(), io.StringIO()
    write_sample_csv("sideways", default)
    write_sample_csv("sideways", explicit, candles=False)
    assert default.getvalue() == explicit.getvalue()


# --------------------------------------------------------------------------- command line


def test_samples_cli_candles_writes_a_file_the_cli_reads_as_candles(tmp_path, capsys):
    out = tmp_path / "walk.csv"
    assert samples_main(["random_walk", str(out), "--candles"]) == 0
    assert capsys.readouterr() == ("", "")
    assert load_candles(str(out)) == sample_candles("random_walk")
    assert cli_main([str(out), "--candles", "--short", "5", "--long", "20"]) == 0
    assert "Bars:    750" in capsys.readouterr().out


def test_samples_cli_candles_to_stdout(capsys):
    assert samples_main(["uptrend", "--candles"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("date,open,high,low,close,volume\n2023-01-02,100.44,100.71,99.84,100.44,711891\n")
    assert parse_candle_text(out, "stdout") == sample_candles("uptrend")


def test_samples_cli_without_candles_is_unchanged(capsys):
    assert samples_main(["uptrend"]) == 0
    assert capsys.readouterr().out.startswith("date,close\n2023-01-02,100.44\n")


def test_candle_sample_backtests_identically_to_the_close_only_sample(tmp_path, capsys):
    closes_path, candles_path = tmp_path / "c.csv", tmp_path / "k.csv"
    assert samples_main(["sideways", str(closes_path)]) == 0
    assert samples_main(["sideways", str(candles_path), "--candles"]) == 0
    argv = ["--short", "5", "--long", "20", "--backtest", "--stats"]
    assert cli_main([str(closes_path)] + argv) == 0
    from_closes = capsys.readouterr()
    assert cli_main([str(candles_path), "--candles"] + argv) == 0
    assert capsys.readouterr() == from_closes


def test_candle_sample_supports_fill_open(tmp_path, capsys):
    path = tmp_path / "k.csv"
    assert samples_main(["sideways", str(path), "--candles"]) == 0
    assert cli_main([str(path), "--short", "5", "--long", "20", "--backtest", "--fill", "open"]) == 0
    out = capsys.readouterr().out
    assert "next-bar open fills" in out


def test_samples_cli_candles_list_and_errors(capsys):
    assert samples_main(["--list", "--candles"]) == 0
    assert "random_walk" in capsys.readouterr().out
    assert samples_main(["nope", "--candles"]) == 1
    assert "unknown sample" in capsys.readouterr().err
    with pytest.raises(SystemExit) as excinfo:
        samples_main(["--help"])
    assert excinfo.value.code == 0
    assert "--candles" in capsys.readouterr().out
