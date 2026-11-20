"""Optional settings file for the command line (``--config FILE``).

The file is INI text read with ``configparser``:

    [cli]
    short = 10
    long = 30
    rsi_period = 14
    cash = 5000
    fee = 1
    fee_pct = 0.1
    slippage = 0.05
    position_size = 0.5
    fill = open
    stop_loss = 8
    take_profit = 20
    trailing_stop = 10
    risk_pct = 1
    atr_mult = 2
    atr_period = 14
    atr_stop = yes
    cooldown = 3
    min_hold = 2
    max_hold = 10
    max_drawdown = 20
    breakeven = 5
    max_losses = 3
    scale_out = 5
    add_on = 10
    max_adds = 2
    strategy = breakout
    stats = yes
    trade_list = yes
    explain = yes
    top = 10
    min_score = 1

    [strategy.breakout]
    window = 15

``[cli]`` may set ``short``, ``long``, ``rsi_period`` (whole numbers), ``cash``,
``fee``, ``fee_pct``, ``slippage``, ``position_size``, ``stop_loss``,
``take_profit``, ``trailing_stop``, ``risk_pct``, ``atr_mult`` (numbers),
``atr_period`` (a whole number), ``atr_stop`` (a yes/no value), ``cooldown``
(a whole number), ``min_hold`` (a whole number), ``max_hold`` (a whole number), ``max_drawdown`` (a
number), ``breakeven`` (a number), ``max_losses`` (a whole number), ``scale_out`` (a number), ``add_on`` (a number),
``max_adds`` (a whole number), ``fill``
(``close`` or ``open``), ``strategy`` (a registered strategy name), ``stats``
(a yes/no value), ``trade_list`` (a yes/no value), ``explain`` (a yes/no value; unlike ``stats`` it needs no
``--backtest``, and it is ignored with ``--scan``), and ``top`` and ``min_score`` (whole numbers, used only
with ``--scan``). Each key is the name of the command-line flag with ``_``
for ``-``. ``atr_mult`` and ``atr_period`` are used only when risk sizing or
the ATR stop is on (``risk_pct``/``atr_stop = yes`` in the file, or
``--risk-pct``/``--atr-stop``); otherwise they are ignored. ``cooldown`` is used
only when a stop is on (``stop_loss``, ``trailing_stop`` or ``atr_stop = yes`` in
the file, or the flags, or ``breakeven`` / ``--breakeven``) and is otherwise
ignored, but its range is still checked. ``min_hold`` needs no stop: with ``--backtest`` it is used unless
``--min-hold`` is given; ``max_hold`` likewise unless
``--max-hold`` is given; ``max_drawdown`` likewise unless ``--max-drawdown``
is given, ``breakeven`` unless ``--breakeven`` is given, ``max_losses``
unless ``--max-losses`` is given, and ``scale_out`` unless ``--scale-out`` is
given (it needs no other exit key), and ``add_on`` unless ``--add-on`` is given. ``max_adds`` is used
unless ``--max-adds`` is given, but only when ``add_on`` or ``--add-on`` is there; otherwise it is ignored,
but its range is still checked (like ``cooldown``). A number key
never takes ``nan`` or ``inf`` (``--take-profit inf``
works only as a flag). There is no key for the
scan folder or the report file. A ``[strategy.NAME]``
section sets parameters of that strategy (numbers only, keys the strategy
has). Nothing else is allowed:
an unknown section or key, a duplicate, a value that does not read as the right
kind of thing, or a file that cannot be read raises ``ConfigError`` naming the
file and, where it can be found, the line.

This module only reads and type-checks. Range rules (``short < long``,
``cash > 0``, ...) are applied by the command line afterwards, exactly as for
flags. Reading a file is always explicit: see ``cli.find_config_path``.
"""

import configparser

from .backtest import FILLS
from .strategies import get_strategy, strategy_names

CLI_SECTION = "cli"
STRATEGY_PREFIX = "strategy."

_INT_KEYS = ("short", "long", "rsi_period")
_FLOAT_KEYS = ("cash", "fee", "fee_pct", "slippage", "position_size", "stop_loss", "take_profit", "trailing_stop")
_SCAN_INT_KEYS = ("top", "min_score")  # whole numbers used only with --scan
# Risk sizing (--risk-pct, --atr-mult, --atr-period); listed after trailing_stop in the unknown-key message.
_RISK_FLOAT_KEYS = ("risk_pct", "atr_mult")
_RISK_INT_KEYS = ("atr_period",)
# yes/no keys; atr_stop (--atr-stop) is listed after atr_period in the unknown-key message, stats after strategy,
# trade_list (--trade-list) after stats, explain (--explain) after trade_list.
_BOOL_KEYS = ("atr_stop", "stats", "trade_list", "explain")
# --cooldown N (a whole number); listed after atr_stop in the unknown-key message.
_COOLDOWN_INT_KEYS = ("cooldown",)
# --min-hold N (a whole number); listed after cooldown in the unknown-key message.
_MIN_HOLD_INT_KEYS = ("min_hold",)
# --max-hold N (a whole number); listed after min_hold in the unknown-key message.
_MAX_HOLD_INT_KEYS = ("max_hold",)
# --max-drawdown PCT (a number); listed after max_hold in the unknown-key message.
_MAX_DRAWDOWN_FLOAT_KEYS = ("max_drawdown",)
# --breakeven PCT (a number); listed after max_drawdown in the unknown-key message.
_BREAKEVEN_FLOAT_KEYS = ("breakeven",)
# --max-losses N (a whole number); listed after breakeven in the unknown-key message.
_MAX_LOSSES_INT_KEYS = ("max_losses",)
# --scale-out PCT (a number); listed after max_losses in the unknown-key message.
_SCALE_OUT_FLOAT_KEYS = ("scale_out",)
# --add-on PCT (a number) and --max-adds N (a whole number); listed after scale_out in the unknown-key message.
_ADD_ON_FLOAT_KEYS = ("add_on",)
_ADD_ON_INT_KEYS = ("max_adds",)
_BOOL_VALUES = {
    "1": True, "yes": True, "true": True, "on": True,
    "0": False, "no": False, "false": False, "off": False,
}


class ConfigError(ValueError):
    """A settings file that cannot be read or holds something not allowed."""


def _find_line(text, section, key=None):
    """1-based line of ``key`` inside ``[section]`` (or of the header when ``key`` is None), else None."""
    current = None
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            if key is None and current == section:
                return number
        elif current == section and key is not None and line and line[0] not in "#;":
            name = line.replace(":", "=", 1).split("=", 1)[0].strip().lower()
            if name == key:
                return number
    return None


def _number(raw):
    """int when ``raw`` reads as one, else a finite float; ValueError otherwise."""
    try:
        return int(raw)
    except ValueError:
        pass
    value = float(raw)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError("not finite")
    return value


def load_config(path):
    """Read ``path`` and return ``{"cli": {key: value}, "strategy": {name: {param: number}}}``.

    Only the keys present in the file appear. ``cli`` values are int, float,
    str or bool as listed in the module docstring. Raises ConfigError (a
    ValueError) with a one-line message starting with the file name.
    """
    try:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    except OSError as exc:
        raise ConfigError(f"cannot read config {path}: {exc.strerror or exc}") from None
    except UnicodeDecodeError:
        raise ConfigError(f"cannot read config {path}: not valid UTF-8 text") from None

    def fail(message, section=None, key=None):
        line = _find_line(text, section, key) if section is not None else None
        where = f"{path} line {line}" if line else str(path)
        raise ConfigError(f"{where}: {message}")

    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        parser.read_string(text, source=str(path))
    except configparser.ParsingError as exc:
        lineno = getattr(exc, "lineno", None) or (exc.errors[0][0] if getattr(exc, "errors", None) else None)
        where = f"{path} line {lineno}" if lineno else str(path)
        raise ConfigError(f"{where}: not valid INI text") from None
    except configparser.Error as exc:
        lineno = getattr(exc, "lineno", None)
        where = f"{path} line {lineno}" if lineno else str(path)
        raise ConfigError(f"{where}: {exc.message.splitlines()[0]}") from None

    if parser.defaults():
        fail("the [DEFAULT] section is not supported", "DEFAULT")

    out = {"cli": {}, "strategy": {}}
    for section in parser.sections():
        items = parser[section]
        if section == CLI_SECTION:
            for key, raw in items.items():
                out["cli"][key] = _cli_value(key, raw, fail, section)
        elif section.startswith(STRATEGY_PREFIX):
            name = section[len(STRATEGY_PREFIX):]
            if name not in strategy_names():
                fail(f"unknown strategy {name!r}; choose from: {', '.join(strategy_names())}", section)
            known = get_strategy(name)[1]
            params = {}
            for key, raw in items.items():
                if key not in known:
                    fail(f"unknown parameter {key!r} for strategy {name!r}; choose from: {', '.join(known)}", section, key)
                try:
                    params[key] = _number(raw.strip())
                except ValueError:
                    fail(f"{key} needs a number, got {raw.strip()!r}", section, key)
            out["strategy"][name] = params
        else:
            fail(f"unknown section [{section}]; use [cli] or [strategy.NAME]", section)
    return out


def _cli_value(key, raw, fail, section):
    raw = raw.strip()
    if (
        key in _INT_KEYS or key in _SCAN_INT_KEYS or key in _RISK_INT_KEYS or key in _COOLDOWN_INT_KEYS
        or key in _MIN_HOLD_INT_KEYS or key in _MAX_HOLD_INT_KEYS or key in _MAX_LOSSES_INT_KEYS
        or key in _ADD_ON_INT_KEYS
    ):
        try:
            return int(raw)
        except ValueError:
            fail(f"{key} needs a whole number, got {raw!r}", section, key)
    if (
        key in _FLOAT_KEYS or key in _RISK_FLOAT_KEYS or key in _MAX_DRAWDOWN_FLOAT_KEYS or key in _BREAKEVEN_FLOAT_KEYS
        or key in _SCALE_OUT_FLOAT_KEYS or key in _ADD_ON_FLOAT_KEYS
    ):
        try:
            value = float(raw)
        except ValueError:
            fail(f"{key} needs a number, got {raw!r}", section, key)
        if value != value or value in (float("inf"), float("-inf")):
            fail(f"{key} needs a finite number, got {raw!r}", section, key)
        return value
    if key == "fill":
        if raw not in FILLS:
            fail(f"unknown fill {raw!r}; choose from: {', '.join(FILLS)}", section, key)
        return raw
    if key == "strategy":
        if raw not in strategy_names():
            fail(f"unknown strategy {raw!r}; choose from: {', '.join(strategy_names())}", section, key)
        return raw
    if key in _BOOL_KEYS:
        if raw.lower() not in _BOOL_VALUES:
            fail(f"{key} needs yes or no, got {raw!r}", section, key)
        return _BOOL_VALUES[raw.lower()]
    allowed = ", ".join(
        _INT_KEYS + _FLOAT_KEYS + _RISK_FLOAT_KEYS + _RISK_INT_KEYS + ("atr_stop",) + _COOLDOWN_INT_KEYS + _MIN_HOLD_INT_KEYS
        + _MAX_HOLD_INT_KEYS
        + _MAX_DRAWDOWN_FLOAT_KEYS + _BREAKEVEN_FLOAT_KEYS + _MAX_LOSSES_INT_KEYS + _SCALE_OUT_FLOAT_KEYS
        + _ADD_ON_FLOAT_KEYS + _ADD_ON_INT_KEYS
        + ("fill", "strategy", "stats", "trade_list", "explain")
        + _SCAN_INT_KEYS
    )
    fail(f"unknown key {key!r} in [cli]; choose from: {allowed}", section, key)
