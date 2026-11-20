"""Trading assistant: indicators and signal suggestions from price history."""

from .indicators import ema, rsi, sma
from .signals import BUY, HOLD, SELL, crossover_signal, rsi_filter

__all__ = ["sma", "ema", "rsi", "crossover_signal", "rsi_filter", "BUY", "SELL", "HOLD"]
