import pytest

from trading_assistant.cli import main
from trading_assistant.signals import BUY, HOLD, SELL, crossover_signal, rsi_filter


def test_hold_when_not_enough_history():
    assert crossover_signal([1.0] * 10, short=2, long=5) == HOLD


def test_buy_on_upward_cross():
    # Flat then a jump: short SMA crosses above long SMA on the last bar.
    closes = [10.0] * 5 + [9.0, 9.0, 9.0, 9.0, 20.0]
    assert crossover_signal(closes, short=2, long=5) == BUY


def test_sell_on_downward_cross():
    closes = [10.0] * 5 + [11.0, 11.0, 11.0, 11.0, 1.0]
    assert crossover_signal(closes, short=2, long=5) == SELL


def test_short_must_be_less_than_long():
    with pytest.raises(ValueError):
        crossover_signal([1.0] * 10, short=5, long=5)


def test_rsi_filter_labels():
    rising = [float(i) for i in range(1, 30)]
    value, label = rsi_filter(rising, period=5)
    assert value == pytest.approx(100.0)
    assert label == "overbought"


def test_cli_prints_signal(tmp_path, capsys):
    path = tmp_path / "prices.csv"
    closes = [10.0] * 60 + [30.0]
    path.write_text("date,close\n" + "\n".join(f"d{i},{c}" for i, c in enumerate(closes)) + "\n")
    assert main([str(path), "--short", "2", "--long", "5"]) == 0
    out = capsys.readouterr().out
    assert "Signal:" in out
    assert "Not financial advice" in out
