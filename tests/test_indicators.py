import pytest

from trading_assistant.indicators import ema, rsi, sma


def test_sma_warmup_and_values():
    out = sma([1, 2, 3, 4, 5], 3)
    assert out == [None, None, 2.0, 3.0, 4.0]


def test_sma_short_input_is_all_none():
    assert sma([1, 2], 3) == [None, None]


def test_ema_seeded_with_sma():
    out = ema([1, 2, 3, 4, 5], 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)
    alpha = 2 / 4
    assert out[3] == pytest.approx(alpha * 4 + (1 - alpha) * 2.0)


def test_rsi_all_gains_is_100():
    values = [float(i) for i in range(1, 20)]
    assert rsi(values, 5)[-1] == pytest.approx(100.0)


def test_rsi_all_losses_is_0():
    values = [float(20 - i) for i in range(20)]
    assert rsi(values, 5)[-1] == pytest.approx(0.0)


def test_rsi_warmup_length():
    out = rsi([1.0, 2.0, 1.5, 2.5, 2.0, 3.0], 3)
    assert out[:3] == [None, None, None]
    assert out[3] is not None


def test_invalid_window_raises():
    with pytest.raises(ValueError):
        sma([1, 2, 3], 0)
