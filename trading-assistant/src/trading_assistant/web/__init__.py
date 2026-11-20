"""Local web page for the backtest. Start with ``python -m trading_assistant.web``."""

from .server import BacktestServer, create_server, main, serve

__all__ = ["BacktestServer", "create_server", "main", "serve"]
