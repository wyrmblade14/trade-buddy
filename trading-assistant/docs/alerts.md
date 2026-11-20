# Alerts

Check a file of simple rules against the last bar of a price file. Research
only: it prints which rules fired and never places orders.

```
python -m trading_assistant.alerts rules.txt prices.csv [--all]
```

## Rules file

One rule per line. `#` starts a comment that runs to the end of the line.
Blank lines are ignored.

```
<expr> <op> <expr>
```

- `op` is one of `<`, `<=`, `>`, `>=`, `crosses_above`, `crosses_below`.
- `expr` is a number (`105.5`, `-3`), `close`, or `sma(N)`, `ema(N)`, `rsi(N)`
  where `N` is a positive whole number. The indicators are the ones in
  `indicators.py`.

Examples:

```
# oversold
rsi(14) < 30
close crosses_above sma(50)     # trend turns up
close > 105.5
ema(12) crosses_below ema(26)
```

Rule text is read by a small tokenizer and parser. It is never run as code.

## Semantics

- `<`, `<=`, `>`, `>=` compare the two sides on the last bar.
- `a crosses_above b` fires when `a <= b` on the bar before the last and
  `a > b` on the last bar. `a crosses_below b` fires when `a >= b` before and
  `a < b` on the last bar.
- If a value needed for the rule does not exist yet (an indicator still
  warming up, or a cross with only one bar of data), the rule does not fire
  and its reason is "not enough data".

## Output

By default only fired rules are listed; `--all` lists every rule.

```
Alerts: 1 of 4 rules fired on the last of 750 bars (close 89.4500)
no     rsi(14) < 30  (left=57.6358 right=30.0000)
no     close crosses_above sma(50)  (left=89.4500 right=87.3828 prev_left=91.3800 prev_right=87.3506)
no     close > 105.5  (left=89.4500 right=105.5000)
FIRED  sma(200) > 0  (left=90.6188 right=0.0000)
Research aid only. Not financial advice.
```

`left` and `right` are the values on the last bar; `prev_left` and
`prev_right` (cross rules only) are the values on the bar before.

## Exit codes

- 0: success, whether or not any rule fired.
- 1: data problem. One `Error:` line on stderr: an unreadable rules or price
  file, no rules, or a bad rule, reported as `line N: ...` with the offending
  token.
- 2: usage problem (missing arguments).
