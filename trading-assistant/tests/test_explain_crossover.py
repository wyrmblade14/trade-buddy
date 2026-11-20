"""explain_crossover: one sentence that starts with the crossover_signal decision and never contradicts it."""

import random
import re

import pytest

from trading_assistant.indicators import sma
from trading_assistant.signals import crossover_signal, explain_crossover

HAND = [10, 9, 8, 9, 11, 12, 10, 10, 11, 12, 12.2]


@pytest.mark.parametrize(
    "closes, short, long, expected",
    [
        # Hand-checked cases on HAND with short 1, long 3.
        (
            HAND[:4], 1, 3,
            "BUY because the 1-bar SMA crossed above the 3-bar SMA: 9.00 against 8.67 on the last bar, "
            "after 8.00 against 9.00 on the bar before.",
        ),
        (
            HAND[:7], 1, 3,
            "SELL because the 1-bar SMA crossed below the 3-bar SMA: 10.00 against 11.00 on the last bar, "
            "after 12.00 against 10.67 on the bar before.",
        ),
        (
            HAND, 1, 3,
            "HOLD because the 1-bar SMA stayed above the 3-bar SMA, so there is no new crossover: "
            "12.20 against 11.73 on the last bar and 12.00 against 11.00 on the bar before.",
        ),
        (
            HAND[:3], 1, 3,
            "HOLD because a crossover needs at least 4 bars and there are 3: "
            "8.00 against 9.00 on the last bar and 9.00 against n/a on the bar before.",
        ),
        # Stays below: 8 vs 9, then 7 vs 8.
        (
            [10, 9, 8, 7], 1, 3,
            "HOLD because the 1-bar SMA stayed below the 3-bar SMA, so there is no new crossover: "
            "7.00 against 8.00 on the last bar and 8.00 against 9.00 on the bar before.",
        ),
        # Equal on the last bar (10 vs (10+10)/2), below before it: not a SELL, not a BUY.
        (
            [12, 10, 10], 1, 2,
            "HOLD because the 1-bar SMA ended level with the 2-bar SMA, so there is no crossover: "
            "10.00 against 10.00 on the last bar and 10.00 against 11.00 on the bar before.",
        ),
        # A real cross that looks level at 2 decimals (10.004 vs 10.002) gets a third decimal.
        (
            [10.5, 10, 10.004], 1, 2,
            "BUY because the 1-bar SMA crossed above the 2-bar SMA: 10.004 against 10.002 on the last bar, "
            "after 10.00 against 10.25 on the bar before.",
        ),
    ],
    ids=["buy", "sell", "hold-above", "hold-too-few", "hold-below", "hold-level", "buy-extra-decimals"],
)
def test_explain_crossover_sentence(closes, short, long, expected):
    assert explain_crossover(closes, short, long) == expected
    assert expected.split()[0] == crossover_signal(closes, short, long)


HOLD_KINDS = ("needs at least", "stayed above", "stayed below", "ended level")
LAST_PAIR = re.compile(r"(\S+) against (\S+) on the last bar")


def test_explanation_never_contradicts_the_signal_on_random_series():
    rng = random.Random(20260101)
    seen = set()
    for _ in range(4000):
        short = rng.randint(1, 4)
        long = rng.randint(short + 1, 7)
        n = rng.randint(0, 14)
        kind = rng.choice(["ints", "near_ties", "around_zero"])
        if kind == "ints":  # small integers: many exactly level averages
            closes = [float(rng.randint(8, 11)) for _ in range(n)]
        elif kind == "near_ties":  # crosses that can look level at 2 decimals
            closes = [10 + rng.choice([-1, 1]) * rng.randint(0, 9) / 1000 for _ in range(n)]
        else:  # signs around zero (-0.00 vs 0.00 must not hide the order)
            closes = [rng.uniform(-0.01, 0.01) for _ in range(n)]

        signal = crossover_signal(closes, short, long)
        sentence = explain_crossover(closes, short, long)
        assert sentence.split()[0] == signal, sentence
        if signal == "HOLD":
            assert "crossed" not in sentence, sentence
        else:
            assert f"crossed {'above' if signal == 'BUY' else 'below'}" in sentence, sentence

        # The printed last-bar numbers keep the order of the real averages.
        cur_short, cur_long = sma(closes, short)[-1:] or [None], sma(closes, long)[-1:] or [None]
        cur_short, cur_long = cur_short[0], cur_long[0]
        shown_short, shown_long = LAST_PAIR.search(sentence).groups()
        if cur_short is None or cur_long is None:
            assert "n/a" in (shown_short, shown_long)
        else:
            real = (cur_short > cur_long) - (cur_short < cur_long)
            shown = (float(shown_short) > float(shown_long)) - (float(shown_short) < float(shown_long))
            assert shown == real, sentence
            if "." in shown_short and len(shown_short.split(".")[1]) > 2:
                seen.add("extra decimals")
        seen.add(signal)
        seen.update(kind for kind in HOLD_KINDS if signal == "HOLD" and kind in sentence)

    # Every kind of sentence was produced at least once.
    assert {"BUY", "SELL", "extra decimals", *HOLD_KINDS} <= seen, seen
