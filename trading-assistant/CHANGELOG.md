# Changelog

## 0.22.0 (2026-11-18)

### Added

- **Strategies in the walk-forward test**: `python -m trading_assistant.walkforward
  PRICES.csv --strategy NAME [--grid KEY=LIST ...] [--param KEY=VALUE ...]
  --train N --test N` walks forward any of the seven strategies instead of
  SMA crossover pairs. In each window every parameter set is backtested on
  the train bars only and the best one is run on the test bars only, with the
  same cash, costs, buy-and-hold comparison, summary and notes as the pairs.
  - `--grid KEY=LIST` (repeatable, once per parameter) lists the values of
    one parameter to try (`window=10,20,30`); every combination of the lists
    is tried. `--param KEY=VALUE` (repeatable) fixes a parameter to one
    number; a list is refused (`--param window takes one value, got '2,3';
    give a list of values with --grid window=2,3`). Parameters in neither
    keep their defaults; `--strategy` alone tries the defaults only.
  - The sets: each list once per distinct value, smallest first (order and
    repeats do not matter); values that compare equal are one value (`0,0.0`
    is tried once, as `0`; `0.0,-0.0` as `0.0`); every pick of one value per
    parameter, in the strategy's own parameter order. Each value is checked on
    its own first, and one bad value in a list is a usage error (exit 2); a set
    that only breaks a rule between two parameters (`short < long`,
    `oversold < overbought`, `entry < exit`) is skipped, as the pairs with
    `short >= long` are.
  - The chosen set has the highest train return; ties go to the smaller train
    drawdown, then to the smaller parameter values in the strategy's order
    (for `sma_cross` the pairs' own order). Nothing from the test block counts.
  - `--warmup` warms each test run up on `first_signal_bars - 1` bars before
    its block (`long`, `window`, `period + 1`, `window + 1` or
    `window + isqrt(window)`), fewer near the start of the data.
  - Checked by hand on 20 closes (`tests/data/wf20.csv`, dated 2026-05-01 to
    2026-05-20), `--strategy breakout --grid window=2,3 --train 8 --test 6
    --cash 1000`: window 1 picks `window=3` (train -16.60%, window 2 made
    -23.00%), test +0.00% with 0 trades, buy and hold -15.20%; window 2 picks
    `window=2` (train -14.20%, window 3 made -26.40%), test -6.60% with 2
    trades (66 @ 15, sold @ 14), buy and hold +22.80%; compounded test -6.60%
    and buy and hold +4.13%. And on `tests/data/wf.csv` with `momentum`,
    `--param window=4 --grid threshold=0,5 --train 4 --test 7 --warmup`:
    window 1 is warmed up on bars 0-3 only (4 of the 5 it needs), buys 76 @ 13
    on bar 9 and ends at 924 (-7.60%); window 2 gets its full 5 bars, buys 71
    @ 14 on bar 15 and ends at 1,000 (+0.00%, drawdown -6.63%); without
    `--warmup` neither trades.
- **Output with `--strategy`** (without it every output is as before):
  - Text: the header line says `each NAME parameter set`; a **Params** column
    (every parameter of the chosen set, `key=value` joined by commas, at least
    7 wide) replaces **Pair**. Whole values are written as whole numbers
    (`entry=-2`, `threshold=0`), other values as Python writes them. The
    no-trades note gives `no BUY signal on a test bar before its last, or too
    few test bars for a first signal` (with `--warmup`: `..., or, near the
    start of the data, too few bars before the block to warm up`) and ends
    `says nothing about the parameters.`; with `--warmup` the header line ends
    `with its signal warmed up on the bars just before each test block, so
    that it can signal on the first test bar`.
  - `--json` starts with `"strategy": NAME` (before `"warmup"`), and each
    window has `params` (the full set, numbers as they are: `-2.0`) where it
    had `short` and `long`.
  - `--csv` has one `param_KEY` column per parameter, in the strategy's order,
    where it had `short` and `long` (`3`, `0.5`, `-2.0` as Python writes them).
- **Usage errors (exit 2)**: `--short` or `--long` with any of the three
  options, whatever the strategy (`--short cannot be combined with
  --strategy, --grid or --param; give sma_cross's windows as --strategy
  sma_cross --grid short=LIST --grid long=LIST`); `--grid` or `--param`
  without `--strategy` (`--grid needs --strategy`); a malformed `--grid`
  (`--grid must look like KEY=LIST, got 'window'`, `--grid window needs a
  comma list of finite numbers, got 'x'`) or `--param` (the main command's
  messages: `--param must look like KEY=VALUE, got 'window'`, `--param window
  needs a number, got 'x'`, `--param threshold needs a finite number, got
  'nan'`); a key twice (`--grid window given more than once`) or in both
  (`window is in both --grid and --param; give only one`); an unknown
  parameter, any bad value in a list (`window must be a whole number of at
  least 1, got 0`, `oversold must be from 0 to 100, got 120`, `window must be
  at least 2 for a z-score, got 1`); no set that passes the strategy's checks
  (`no parameter combination for sma_cross passes its checks: short window
  must be smaller than long window`); an unknown strategy (argparse's
  `invalid choice`). With `--strategy`, `--short` and `--long` are not
  required; `--train` and `--test` still are.
- **`POST /api/walkforward` takes `strategy`, `grid` and `params`**: a name,
  and lists of the command's option texts (`["window=2,3"]`,
  `["threshold=0.5"]`); `null`, `""` (and `[]` for the lists) mean none. Every
  request the command refuses is a 400 with its message (28 cases compared);
  `short` or `long` given with them is that 400. The reply is exactly the
  command's `--json` object. Window values (`short`, `long`, `window`,
  `period`) are held to 500 (`--grid window must be at most 500, got 501`).
- **Work limits for a strategy on the web**: at most **10,000 parameter sets**
  per request, counted from the lists before any set is built (413 `this
  walk-forward is too big for the web page (10,100 parameter sets; the limit
  is 10,000); use shorter --grid lists, or run python -m
  trading_assistant.walkforward`), and the work held to the SMA pairs' own
  **300,000 bar-steps** (one bar of an SMA crossover backtest, about 8
  microseconds where measured), counted as windows x (every set's train cost
  + the dearest set's test cost, with full warm-up when `warmup` is on). A
  backtest of `n` bars after `w` warm-up bars costs, in bar-steps:
  `sma_cross` `n x (1 + 0.005 x long)`, `breakout` `n x (0.5 + 0.004 x
  window)`, and for the strategies that work their indicator out again over
  every close so far, `reads = n x w + n x (n + 1) / 2` closes read:
  `rsi_reversion` `reads x 0.1`, `ema_cross` `reads x 0.03`, `momentum`
  `reads x 0.02`, `zscore_reversion` `reads x 0.17 + past x window x 0.024`
  and `hull_trend` `reads x 0.45 + past x window x 0.018` (`past`: the closes
  past the window, summed over the bars). The weights are 10% to 30% above
  what was measured (best of 2 to 7 runs: per bar about 7 + 0.04 x long
  microseconds for `sma_cross` and 3.5 + 0.025 x window for `breakout`; per
  close read 0.59 to 0.67 for `rsi_reversion`, 0.17 to 0.20 for `ema_cross`,
  0.13 to 0.15 for `momentum`; least-squares fits over windows 5 to 300 of
  1.04 + 0.148 per window-read for `zscore_reversion` and 2.76 + 0.113 for
  `hull_trend`). On 16 real walk-forwards of the seven strategies a request
  at the limit would take 1.0 to 4.9 seconds there (3 of the SMA pairs: 2.6
  to 3.6). On the 750-bar `random_walk` sample, `zscore_reversion` with
  `["window=5,10,20"]`, test 60 and warm-up is 277,374 bar-steps with train
  230 (200, about 2.2 seconds) and 301,867 with train 240 (413). The SMA
  pairs' count does not change.
- **Web page**: a **Strategy** dropdown in the "Walk-forward test" panel,
  filled from `/api/samples`. With `sma_cross` (or before the list loads) the
  panel sends exactly the request it sent before (six sets of fields,
  recorded from the 0.21.0 page). Another strategy hides the short and long
  window lists and shows one text field per parameter, holding its default:
  a value with a comma is sent in `grid`, another value that differs from the
  default in `params`. A reply with `strategy` gets the Params header and
  cells (`wfNum` writes the numbers as the command's text does), the
  strategy's header line and notes; a refused request shows the server's
  message (the 413 and 400 above checked).
- **Library**: `strategies.check_param_value`; `sweep.grid_combinations`
  (with `max_combinations` and `GridTooLarge`) and `sweep.sweep_grid`;
  `walkforward.walk_forward` and `run_walk_forward` take `strategy`, `grid`
  and `params` as new last parameters; `walkforward.check_blocks`,
  `parse_grid_item`, `parse_param_item`, `parse_strategy_options`,
  `check_strategy_options`, `csv_header`, `params_text`, `param_value_text`;
  `format_walk_forward`, `json_data` and `write_csv` take `strategy`;
  `web.server._strategy_work`, `WALKFORWARD_BAR_WEIGHTS`,
  `WALKFORWARD_READ_WEIGHTS` and `MAX_WALKFORWARD_PARAMETER_SETS`.
- **Docs**: "Walk-forward with a strategy" in the README and "Strategies in
  the walk-forward (`--strategy`, `--grid`, `--param`)" in
  [docs/cli.md](docs/cli.md#strategies-in-the-walk-forward---strategy---grid---param)
  (the example worked by hand, the output rules, the errors, the shortened
  names, the API fields, the limits and the weights); the architecture notes
  and the module docstrings describe it too. Every command in them was rerun
  and compared with its printed output.
- **Tests**: `test_walkforward_strategy.py` (10), `test_walkforward_strategy_cli.py`
  (12), `test_web_walkforward_strategy.py` (5),
  `test_web_walkforward_strategy_page.py` (6) and
  `test_walkforward_strategy_docs.py` (4), 37 tests, with
  `tests/data/wf20.csv` (the 20 closes, 291 bytes),
  `tests/data/wf_cli_before_strategy.json` (25 commands and 134
  shortened-option runs recorded with 0.21.0, 158,552 bytes),
  `tests/data/wf_api_before_strategy.json` (24 replies, 23,722 bytes) and
  `tests/data/wf_page_requests_before_strategy.json` (6 requests, 2,747 bytes).

### Existing results do not change

Without `--strategy`, `--grid` and `--param` (and the three API fields, or
with them `null`, `""` or `[]`) every output is exactly as in 0.21.0. This was
recorded from 0.21.0's code (`git HEAD`) and compared byte for byte: 25
walk-forward commands (text, `--json`, `--csv` and its file, `--warmup`,
`--help`, 10 usage errors and 3 data errors; stdout, stderr, exit code, files
written) and every prefix of every walk-forward option, old and new, with a
separate value and with `=` (134 runs), 24 `POST /api/walkforward` requests
(10 runs, 13 400s, one 413; status, `Content-Type` and body) and 6 request
bodies of the walk-forward panel. The only differences:

- The walk-forward `--help`: the description reads `Walk-forward test of the
  SMA crossover (or of --strategy): pick the best window pair (or parameter
  set) on each train block, then run it on the test block that follows.`, the
  three options are listed after `--csv` (12 lines), and argparse widens the
  option column for `--param KEY=VALUE`, so every option line is indented
  further. The usage line does not change, so every usage error prints what
  it printed before (it still shows `--short LIST --long LIST` as required).
- 38 of the 134 prefix runs: `-h 5`, `--h 5` to `--help 5` print the new help;
  `--s` and `--s=5` are still ambiguous, now `could match --short, --step,
  --st, --strategy`; `--=5` also lists `--st, --strategy, --grid, --param`;
  `--g` to `--grid` and `--p` to `--param` (18 runs) were `unrecognized
  arguments` and are the new options; `--str` to `--strategy` (12 runs) were
  `unrecognized arguments` and are now `--strategy`. `--st` still means
  `--step` (a hidden exact alias).
- Web page: `GET /` gains the dropdown and the parameter block (3 lines
  changed, 9 added; 26,096 to 26,756 bytes) and `GET /app.js` the dropdown
  code (7 lines changed, 83 added; 63,486 to 68,665 bytes). **The dropdown is
  a new full-width row before the window lists, so the panel's other fields
  move down.** `GET /style.css` does not change.
- `POST /api/walkforward` ignored `strategy`, `grid` and `params` in 0.21.0.
  Now a request with them gets the new behaviour: `{"strategy": "breakout"}`
  with `short` and `long` was run as SMA pairs and is a 400, and a
  `strategy`, `grid` or `params` of the wrong type is reported before any
  other field.
- Library: `walk_forward` and `run_walk_forward` have three new last
  parameters, so calls by position are unchanged; `check_settings` calls the
  new `check_blocks` (same messages); `walkforward.build_parser()` sets
  `parser.usage` (None in 0.21.0) to the 0.21.0 usage text, its `--short` and
  `--long` use a new action class (required unless one of the three options is
  given), and the namespace gains `strategy`, `grid_items` and `param_items`
  (and `grid` and `params` after `validate_args`). The dict
  `parse_walkforward_request` returns gains `strategy`, `grid` and `params`.
  `sweep.sweep` and the sweep command do not change.
- The version is 0.22.0 (`pyproject.toml`). No output prints the version.

### Not checked

- The page was run in Node with a stand-in for the browser, never in a real
  browser: the new row's look, narrow screens, keyboard order and screen
  readers are unchecked. The Pair/Params header switch needs the table's
  header row, which the older stand-in DOM does not have (the code skips the
  switch then); the new page tests add the row.
- Only `breakout` and `momentum` were worked out by hand; the other five
  strategies were checked against the engine's own sweep and backtest.
- Only Python 3.12 was run and `--help` only at 80 columns. The recorded
  usage errors and prefix runs are argparse's wording, so another Python
  version could change them and fail those tests.
- The weights come from timings on one machine that varied up to twice
  between runs; no test checks run time. Spaces inside `--grid` lists
  (`2, 3`) and very large grids on the command line were not run.

### Not covered yet

- **Run time.** The command has no limit on grid size or run time, and
  `rsi_reversion`, `ema_cross`, `momentum`, `zscore_reversion` and
  `hull_trend` slow down with the square of the block length (and with the
  window for the last two). On the web, the weights were set on one machine;
  on a machine twice as slow a request at the limit could take about 10
  seconds, pass `MAX_RUN_SECONDS` (503), and the abandoned run keeps a CPU
  busy.
- The work count treats every test block as fully warmed up, so near the
  start of the data it counts a little more than the run does.
- A grid of more than 10,000 sets is a 413 on the web even when no set would
  pass the strategy's checks (the command then says `no parameter
  combination ...`).
- `--json` and `--csv` do not record which grid was tried, and `--csv` still
  cannot show that warm-up was on; keep the command with the file.
- The Params cell writes whole values as whole numbers (`threshold=0` for
  `0.0`), so the text and the page cannot tell `0` from `0.0` (`--json` and
  `--csv` can).
- The page's parameter fields are plain text fields (no number keyboard on
  phones), show a default `0.0` as `0`, go back to the defaults when the
  strategy is switched, and after an error the previous results stay on
  screen under the message (as before for the SMA pairs).
- The usage line still shows `--short LIST --long LIST` as required; with
  `--strategy` they are refused instead. The hidden `--st` shows in the
  `ambiguous option` messages for `--s` and `--=X`.
- The 413 messages say `1 windows` for one window, as the SMA pairs' always
  did.
- An unknown `strategy` on the API is worded as argparse's `invalid choice`,
  with a value that is not a string shown as Python shows it
  (`invalid choice: 5`), while `/api/backtest` and `/api/portfolio` say
  `unknown strategy 'int'`.
- The sweep command still sweeps SMA pairs only.

### Changed tests

Only lines added, to take the new page code out before the pinned hashes are
compared; the pinned hashes are unchanged and no line was removed or changed:

- `test_web_atr_stop_page.py::test_nothing_else_changed_since_before_the_checkbox`,
  `test_web_risk_sizing_page.py::test_nothing_else_changed_since_before_these_controls`,
  `test_web_trailing_stop_page.py::test_nothing_else_on_the_page_changed` and
  `test_web_walkforward_warmup_page.py::test_box_is_the_last_setting_unticked_and_nothing_else_changed`:
  an "Undo the walk-forward panel's strategy picker" step, 20 lines each (80
  in all), placed before the older undo steps, whose patterns would otherwise
  also match the new code.

## 0.21.0 (2026-11-18)

### Added

- **Strategies in the portfolio engine** (`portfolio.run_portfolio(...,
  strategy=NAME, strategy_params=None)`, passed through by `run_files` and
  `run_texts`). Every symbol is run through `run_backtest` with the chosen
  strategy, on the same shared dates, with the same cash split (equal or
  `weights`), fees and buy-and-hold comparison. For `sma_cross` without
  `strategy_params` the call to `run_backtest` is exactly the one 0.20.0
  made; for `sma_cross` with `strategy_params` only `short` and `long` are
  allowed and replace the windows; any other strategy ignores `short` and
  `long` (the result's `short` and `long` are `None`). Checked on two files,
  AAA (10, 11, 12, 13, 12, 11, 10, 11, 13, 14) and BBB (20, 19, 18, 19, 21,
  22, 21, 19, 18, 20), on the 10 dates 2026-04-01 to 2026-04-10, cash 1000:
  - `breakout` with `window=3`: AAA buys 41 @ 12.00 on bar 4, sells @ 10.00 on
    bar 6 and buys 29 @ 14.00 on bar 9 (418.00); BBB buys 22 @ 22.00 on bar 5
    and sells @ 18.00 on bar 8 (412.00), the fills of the main command's
    `--backtest --strategy breakout --param window=3 --cash 500` on each
    file. Portfolio 830.00, -17.00%; its account value is 1,000 on bars 0-4,
    then 959, 896, 852, 830, 830, so the maximum drawdown is
    (830 - 1,000) / 1,000 = -17.00%; buy and hold +20.00%.
  - With weights AAA 60 and BBB 40: 828.00, -17.20%, buy and hold +24.00%.
  - The SMA crossover 2/3 on the same files: 912.00, -8.80% (AAA 1 trade,
    BBB 2), as in 0.20.0.
  Too few shared dates is a ValueError naming the strategy's real minimum:
  `only 10 dates shared by all 2 symbols; need at least 11 for breakout (window=9): 10 for its first signal + 1 to fill it`;
  for `sma_cross` the message is 0.20.0's (`... need at least 52 (long window 50 + 2)`).
- **`strategies.first_signal_bars(name, params)`**: the fewest closes with
  which a strategy can give a BUY or SELL on the last of them; the portfolio
  needs one more shared date, to fill it. `long + 1` for `sma_cross` and
  `ema_cross`, `window + 1` for `breakout` and `zscore_reversion`,
  `period + 2` for `rsi_reversion`, `window + 2` for `momentum` and
  `window + isqrt(window) + 1` for `hull_trend` (so 52, 28, 22, 22, 17, 23
  and 26 shared dates with the defaults; each checked to run at that count
  and fail one below). Checked against each strategy's own function on 301
  random series for each of 14 parameter sets: no bar before it ever
  signalled, and some series signalled on it.
- **`--strategy NAME` and `--param KEY=VALUE` on the portfolio command**,
  with the main command's meaning, checks and messages (the portfolio's
  `check_strategy` uses `cli.parse_param` and `strategies.resolve_params`):
  - `--param` alone adjusts `sma_cross`: `--param short=2 --param long=3`,
    with or without `--strategy sma_cross`, prints exactly what
    `--short 2 --long 3` prints (text, `--json` and the `--csv` file).
  - Usage errors (exit 2), with the main command's messages:
    `--param short=6 contradicts --short 5; give only one`,
    `--param short given more than once`,
    `--param must look like KEY=VALUE, got 'window'`,
    `--param window needs a number, got 'x'`,
    `unknown parameter 'period' for strategy 'breakout'; choose from: window`,
    `window must be a whole number of at least 1, got 0`,
    `short window must be smaller than long window` (`--param short=60`),
    and argparse's `argument --strategy: invalid choice: 'nope' (choose from ...)`.
    `--short 30 --param long=25` passes these checks, as in the main
    command, and is refused by the run (exit 1, the same message).
  - `--short` or `--long` with another strategy, even at its default, is a
    usage error: `--short only applies to --strategy sma_cross; set breakout's parameters with --param`.
  - With another strategy the title line names it and all its parameters,
    defaults included, as the `Backtest:` line of `--backtest` does
    (`breakout (window=3)`, `momentum (window=3, threshold=0.0)`); `--json`
    starts with a `title` key holding that line, and `summary` has
    `strategy` and `params` where it has `short` and `long`. The `--csv`
    columns do not change.
  - Both options are listed in `--help` but not in the usage line, which
    stays as it was. `--s` stays `--short` (a hidden exact alias, since
    `--strategy` would make it ambiguous).
- **`POST /api/portfolio` takes `strategy` and `params`.** `strategy` is read
  as `/api/backtest` reads it (missing, `null` or `""` is `sma_cross`; a
  number, `true`, a list or an object is `unknown strategy 'int'` (`'bool'`,
  `'list'`, `'dict'`) `; choose from: ...`; an unknown name `unknown strategy 'nope'; choose from: ...`).
  `params` is a list of `"KEY=VALUE"` strings, as `weights`: `null` or `[]`
  is none, anything else that is not a list of strings is
  `params must be a list of "KEY=VALUE" strings, like ["window=10"]`, and each
  string is checked by the command's own code with its messages. `short` or
  `long` counts as given when it is there and not `null` or `""`; given with
  another strategy it is the command's 400. Window parameters in `params`
  (`short`, `long`, `window`, `period`) are held to the page's limit of 500:
  `--param window must be at most 500, got 600`. With another strategy the
  reply is the command's `--json` object, `title` first; the 60/40 breakout
  request above replies with exactly the object of the command's
  `--strategy breakout --param window=3 --cash 1000 --weights AAA=60 BBB=40 --json`.
- **Web page: a "Strategy" dropdown in the "Portfolio backtest" panel**,
  filled from the same `/api/samples` list as the backtest form's. With
  `sma_cross` (or before the list loads) the panel sends exactly the request
  it sent before (three sets of field values, recorded by running the 0.20.0
  page in the same Node driver). Another strategy hides "Short SMA" and
  "Long SMA" and shows one number field per parameter, holding its default,
  as the backtest form does; only parameters filled in and different from
  their default are sent, so an untouched `threshold` reads
  `threshold=0.0` in the title, as in the command without `--param`. A reply
  with `title` shows it as the title line; otherwise the panel builds the
  line itself (`pfTitle`, unchanged). A refused value shows the server's
  message in the panel's error box (`window` 0, 2.5, 600 and 9 checked).
- **Library**: `portfolio.check_strategy`, `portfolio.check_strategy_windows`,
  `portfolio.title_line`, `portfolio.strategy_text`,
  `strategies.first_signal_bars` and `web.server._strategy_name` (shared by
  `/api/backtest` and `/api/portfolio`; `/api/backtest` behaves as before).
- **Docs**: a "Portfolio with a strategy" section in the README and a
  "Strategies in the portfolio (`--strategy`, `--param`)" section in
  [docs/cli.md](docs/cli.md#strategies-in-the-portfolio---strategy---param)
  with the AAA and BBB example worked out, the minimum-dates table, the
  errors and the API's value table (every `$` command in it rerun); the
  architecture notes, `docs/indicators.md` and the module docstrings
  describe it too.
- **Tests**: `test_portfolio_strategy.py` (27), `test_portfolio_strategy_cli.py`
  (18), `test_web_portfolio_strategy.py` (17) and
  `test_web_portfolio_strategy_page.py` (7), 69 tests, with
  `tests/data/portfolio_before_strategy.json` (13 engine runs recorded
  before the option existed, 74,291 bytes),
  `tests/data/portfolio_cli_before_strategy.json` (16 commands and 106
  shortened-option parses, 62,123 bytes),
  `tests/data/portfolio_api_before_strategy.json` (16 replies, 8,855 bytes)
  and `tests/data/portfolio_page_requests_before_strategy.json` (the 0.20.0
  panel's requests, 1,474 bytes).

### Existing results do not change

Without `--strategy` and `--param` (and the two API fields) every output is
exactly as in 0.20.0. This was compared with 0.20.0's code (`git HEAD`),
each version run on its own copy of the same files: 368 command runs (128
portfolio runs on eight folders, good, skipped, lost-date, repeated-date,
one-file, empty and missing, with fifteen option sets covering text,
`--json`, `--weights`, costs and usage and data errors; 4 with `--csv` and
2 with a refused `--csv`; `--help` and `-h`; every prefix of every
portfolio option, old and new, with a value, with `=` and alone, 162 runs;
23 main commands, including `--backtest --strategy`, `--config` with a
`[strategy.breakout]` section, `--scan`, `--export` and `--report`; 19 runs
of the sweep, walk-forward, drawdowns, Monte Carlo, summary, alerts,
journal, samples and web tools, and 30 of them with `--strategy`,
`--param` or `--st`; stdout, stderr, exit code and files written), 42 HTTP
requests to an old and a new server (`GET /`, `/style.css`, `/app.js`,
`/api/samples`, `/api/health`, a 404 and a 405; 6 to `/api/backtest`, 2 to
`/api/scan` and 2 to `/api/walkforward`, each also with `strategy` or
`params`; 25 to `/api/portfolio`; status, headers except `Date`, and body,
byte for byte), and library probes of both versions. The only differences
were the runs that use the new options and these:

- The portfolio's `--help` (also `-h` and `--h` to `--hel`; 12 runs, one
  text): the description's two lines are reworded
  (`Backtest the SMA crossover (or --strategy) on every .csv file in a folder,`)
  and 6 lines describing `--strategy` and `--param` are added after
  `--csv`, 31 lines to 37 at 80 columns. The usage line does not change, so
  every usage error prints what it printed before.
- `--st` to `--strategy` and `--p` to `--param` were
  `unrecognized arguments` (exit 2) in 0.20.0; they now mean the new
  options: `--st 5` is `argument --strategy: invalid choice: '5' (choose from ...)`,
  `--p 5` `--param must look like KEY=VALUE, got '5'`, and a bare `--st` or
  `--p` `argument --strategy: expected one argument` (`--param` for `--p`;
  still exit 2). `--s`
  still means `--short` and every other prefix sets the same option as in
  0.20.0 (115 of the 162 token runs are byte for byte the same; the others
  are these, the help and the next line).
- `ambiguous option: --=5 could match --help, --short, --long, ...` now
  also lists `--s` (after `--short`), `--strategy` and `--param` (still
  exit 2).
- Web page: `GET /` differs by the panel's description sentence
  (`Runs the SMA crossover (or the strategy you pick) on every file ...`),
  an id on the "Short SMA" and "Long SMA" cells and 8 new lines for the
  dropdown and the parameter block (3 lines changed, 8 added; `Content-Length`
  25,674 to 26,096); `GET /app.js` by the dropdown code (2 lines changed, 54
  added; `Content-Length` 60,532 to 63,486). **The dropdown is a new full-width row after the file picker (and the
  parameter block, hidden until another strategy is picked, a second one),
  so the panel's other fields move down.** `GET /style.css`, `/api/samples` and
  `/api/health` are unchanged.
- `POST /api/portfolio` ignored `strategy` and `params` in 0.20.0. Now a
  request with either gets the new behaviour: `{"params": "x"}` was a 200
  and is the list 400; `{"strategy": "breakout", "short": 5}` was run as
  the SMA crossover 5/50 and is the `--short only applies ...` 400;
  `{"strategy": "breakout", "params": ["window=3"]}` on the AAA and BBB files
  was `need at least 52 (long window 50 + 2)` and is now a 200. Error order:
  a field that cannot be read (`"short": "x"`) is still reported first, but
  a bad `strategy` or `params` now comes before the range checks (`"short":
  0`, `"cash": -1`) and the weights (`"weights": ["A=1"]`), and a `params`
  window over 500 before `"cash": 2e12`. `strategy` `"sma_cross"`, `null`
  or `""` and `params` `null` or `[]` get the 0.20.0 reply byte for byte.
  `/api/backtest`, `/api/scan` and `/api/walkforward` give the same replies,
  with or without the two keys.
- Library: `PortfolioResult` has two new last fields, `strategy`
  (`"sma_cross"`) and `strategy_params` (`{}`), so `repr()` and
  `dataclasses.asdict()` of every result end with them; the fields before
  keep their order. `run_portfolio`, `run_files` and `run_texts` take
  `strategy` and `strategy_params` as new last parameters, so calls by
  position are unchanged. `portfolio.build_parser()` has three new option
  strings (`--s`, `--strategy`, `--param`) and sets `parser.usage` (None in
  0.20.0) to the 0.20.0 usage text; `validate_args` adds `strategy`,
  `param`, `strategy_params` and, when `--short`/`--long` are given,
  `short_given`/`long_given` to the namespace. The dict
  `web.server.parse_portfolio_request` returns gains `strategy` and
  `strategy_params`. `format_portfolio` builds its first line with the new
  `title_line` (same text). The `portfolio` module also imports
  `DEFAULT_STRATEGY`, `_Given`, `parse_param`, `STRATEGIES`,
  `first_signal_bars`, `resolve_params` and `strategy_names`. `cli`,
  `backtest` and `trading_assistant.__all__` do not change.
- The version is 0.21.0 (`pyproject.toml`; the installed package reports
  0.21.0 after `scripts/setup_dev.sh`). No output prints the version.

### Not checked

- The page was run in Node with a stand-in for the browser, never in a real
  browser: the dropdown's look, the hidden fields, the new rows moving the
  other fields, narrow screens, keyboard order, screen readers and the dark
  theme are unchecked. In a real browser the dropdown's value after filling
  is `sma_cross`; the stand-in leaves it empty, which the code treats the
  same (both send the old request), but only the stand-in was run. Browsers
  read text that is not a number in a number field as empty, so `abc` in a
  parameter field would probably mean "the default" and never reach the
  server. An empty dropdown (when `/api/samples` fails) was not run.
- `first_signal_bars` was checked by sampling (301 random series per case,
  14 cases), not proved; the rules come from the indicator code.
- `--help` was checked at 80 columns only, and only Python 3.12 was run.
- The portfolio API and page were run only on small files (10 dates, and the
  150-date samples); no strategy other than `breakout` and `momentum` was
  run on the page.

### Not covered yet

- `rsi_reversion`, `zscore_reversion` and `hull_trend` work out their
  indicator again over all earlier bars on every bar, so their time grows
  with the square of the bars (and with the window for the last two: 0.8 s
  against 10 to 13.5 s for one 1000-bar file, window 2 against 500), times the
  number of files. On the web page a few 1000-bar files can pass the
  10-second limit (a 503), and the abandoned run keeps a CPU busy. A bar
  limit cannot be set cleanly (it depends on the window and the number of
  files, which only the 1 MB body limits); a work budget like the
  walk-forward's `MAX_WALKFORWARD_BAR_STEPS` (files x dates x dates, times
  the window for the last two) is the idea for a later release.
- A comment at the start of the portfolio code in the page script still
  describes the reply as "summary, skipped, disclaimer", without the new
  `title` (left as it is so the page's pinned hashes keep one undo step).
- The sweep and the walk-forward test still trade only the SMA crossover
  (`--strategy`: `unrecognized arguments`, exit 2); the docs say so only by
  describing them as SMA crossover tools. `--scan` refuses `--strategy` as
  a backtest option (`--strategy cannot be combined with --scan`); the docs
  name backtest options in general, not `--strategy`.
- `--short 30 --param long=25` is refused by the run (exit 1), not as a
  usage error, as in the main command.
- An unknown strategy is worded as in `/api/backtest` on the API and as
  argparse's `invalid choice` on the command line.
- The bare `--=X` error lists the hidden `--s`. The page's parameter fields
  have no `max` (like the backtest form's), and switching the strategy
  resets them to the defaults. The portfolio command reads no `--config`
  file, so no `[strategy.NAME]` section.

### Changed tests

Only lines added, to take the new page code out before the pinned hashes are
compared; the pinned hashes are unchanged and no line was removed or changed:

- `test_web_atr_stop_page.py::test_nothing_else_changed_since_before_the_checkbox`,
  `test_web_risk_sizing_page.py::test_nothing_else_changed_since_before_these_controls`,
  `test_web_trailing_stop_page.py::test_nothing_else_on_the_page_changed` and
  `test_web_walkforward_warmup_page.py::test_box_is_the_last_setting_unticked_and_nothing_else_changed`:
  an "Undo the portfolio panel's strategy picker" step, 13 lines each (52 in
  all).

## 0.20.0 (2026-11-17)

### Added

- **Add-ons in the engine** (`backtest.run_backtest(..., add_on_pct=PCT,
  max_adds=N)`; `add_on_pct` above 0, default None = off; `max_adds` a whole
  number of at least 1, 1 when only `add_on_pct` is given, and a ValueError
  without it). While a position is held, a close `PCT` % or more above the
  fill price of the latest buy into the position sets off an add-on buy on
  the next bar, at most `N` per position. Rules, each checked on a small case
  (most on `up.csv` in [docs/cli.md](docs/cli.md#add-ons): closes 10, 9, 8,
  9, 11, 12, 13, 14, 15, 14, 13, 12, `short=1`, `long=2`, cash 1000, position
  size 0.5: BUY 45 @ 11 on bar 4, SELL on bar 10; 1,090.00 without it):
  - The level is measured from the latest buy's recorded fill price,
    slippage included (with 1 % slippage the buy records 11.11, so a close of
    12.15 no longer sets it off and the add-on moves from bar 6 to bar 7:
    1,028.72 against 1,087.00 with the fee alone). It is compared in floating
    point: after a buy at 11, `10` needs a close above 12.10; a close of
    exactly 12.10 does not set it off (11 x 1.1 is 12.100000000000001), 12.11
    does (989.70 against 993.80).
  - It fills on the next bar at that bar's fill price (close, or open with
    open fills), with slippage and fees, and its fill's reason is `add_on`
    (`10`: 36 @ 14 on bar 7, 1,054.00; `20`: 33 @ 15 on bar 8, 1,024.00;
    `50`: never, 1,090.00). It can fill below the level when the next bar
    falls (42 @ 11.80 after a close of 12.50, 1,009.90).
  - Sized like any buy: all the cash, `position_size` (capped by the cash),
    or `risk_pct` with the ATR of the bar that set it off, never of the bar
    it fills on (7 shares on a candle file where the fill bar's ATR would
    give 8). With all-cash sizing it gets 0 shares: counted in the new
    `add_on_skipped_buys` (not in `risk_skipped_buys`), not one of the `N`,
    and the latest buy price stays, so the next close is checked again (`10`
    all-in: 3 skipped, the run is the one without it, 1,180.00).
  - Every buy into the position becomes the latest buy, a signal buy too,
    but only add-ons count towards `N` (a signal buy while held, then an
    add-on with `N` 1: 1,101.60). Spacing: `position_size` 0.25 on 10, 8, 9,
    10, 11.5, 12, 13, 14, 15, 17, 16, 16.5: `N` 1 gives 1,257.00, 2
    1,285.50, 3 1,292.00 (the third add-on is bought on the close that gives
    the SELL, one bar before the sale).
  - Dropped, not delayed and not counted: when the close that set it off is a
    BUY or SELL signal (a SELL also when `min_hold` holds the sale back:
    1,057.20), and when another fill takes its bar. With close fills it
    comes after everything else on the bar: a stop, target, trailing, ATR or
    breakeven stop reached during the bar, the signal fill, a scale-out, a
    time exit and a drawdown sale (`max_hold` 3: the time exit takes bar 7,
    1,135.00). With open fills it fills at the open, after the signal fill, a
    gap through a stop or target, the time exit and the drawdown sale at the
    open, and before the bar's range, which is then not checked (one fill per
    bar). So with open fills no stop acts on the bar it fills on: a bar whose
    low goes through the stop sells nothing (1,308.00 where the run without
    the add-on is stopped out at 975.01), which flatters the result.
  - It raises the average entry price: the stop, target, breakeven (armed
    stays armed: 90 @ 11.11, a round trip of 0.00), ATR stop and scale-out
    levels follow it. It is part of the position's round trip (one round
    trip, its shares and cost included) and restarts neither `min_hold` nor
    `max_hold` (`max_hold` 4: the add-on on bar 7, the time exit on bar 8,
    1,216.00).
  - After a drawdown halt the halt's sale takes the bar and the add-on is
    dropped uncounted; only when the fees refuse that sale does the add-on
    get its turn, and it is then counted in `drawdown_skipped_buys` (fee 600:
    1 skipped, 40.00). The losing-streak halt and the cooldown only start
    when nothing is held, so they never meet an add-on.
  `BacktestResult` records `add_on_pct`, `max_adds` and
  `add_on_skipped_buys`; `n_add_on_buys` counts the add-on fills.
  `has_exits` is true with it (fills and the export carry a reason),
  `has_price_exits` is not. The report, only with the option, adds a line
  right after `Scale out:` (or where it would be):
  `Add-ons:     up to 1 per position, a buy on the next bar after a close 10.00% or more above the latest buy price, when nothing else fills on that bar; 1 add-on buy, 0 skipped (0 shares)`.
- **`--add-on PCT` and `--max-adds N` on the command line.** `--add-on` is
  above 0, decimals allowed, no upper limit: `0` or `-1` is
  `--add-on must be above 0, got 0`, `nan` `--add-on must be above 0, got
  nan`, `inf` `--add-on must be a finite number, got inf`, a word argparse's
  `invalid float value` (all exit 2). `--max-adds` is a whole number of at
  least 1 (`0`: `--max-adds must be a whole number of at least 1, got 0`;
  `2.5`: `invalid int value`), and without `--add-on` it is
  `--max-adds only makes sense together with --add-on`. Without `--backtest`
  either is `... only makes sense together with --backtest`, and with
  `--scan` `... cannot be combined with --scan` (all exit 2). They need no
  stop and no candle file: a close-only file works, and so does `--resample`.
  `--help` lists both after `--scale-out` (the usage line does not). `--ad`
  to `--add-o` are short for `--add-on` and `--max-a` to `--max-add` for
  `--max-adds`. See [docs/cli.md](docs/cli.md#add-ons).
- **`--json` with `--add-on`**: the backtest object gets `add_on_pct` and
  `max_adds` right after `scale_out_pct` (or the exit setting before it) and
  `add_on_buys` and `add_on_skipped_buys` right after `scale_out_exits` (or
  `breakeven_exits`, `risk_skipped_buys`, or `sells`), before the cooldown
  keys, in the order of the report's lines; only with the option. The
  `up.csv` cases give the text report's numbers.
- **`--export` with `--add-on`** gets the `reason` column, with `add_on` on
  the add-on buys.
- **Config keys `add_on`** (a number, read like `scale_out`, but needing no
  candle file) **and `max_adds`** (a whole number, read like `max_hold`).
  `add_on = 0` (or `-1`) is the flag's usage error (exit 2); `abc`, `5%`,
  `1,6` or `true` is `Error: FILE line N: add_on needs a number, got 'abc'`,
  and `nan` or `inf` `... needs a finite number, got 'nan'` (exit 1).
  `max_adds = 0` is the flag's usage error (exit 2); `2.5`, `2.0`, `abc` or
  `true` is `... max_adds needs a whole number, got '2.5'` (exit 1). Each flag
  wins over its key. `max_adds` is used only when `add_on` or `--add-on` is
  there; without either it is ignored quietly, like `cooldown` without a stop,
  and like `cooldown` its range is still checked (`max_adds = 0` alone is
  exit 2). Without `--backtest`, and with `--scan`, both are ignored (a value
  of the wrong kind is still the config error). From a file they give
  byte for byte the flags' text and `--json`.
- **`POST /api/backtest` takes `add_on` and `max_adds`.** `add_on` is read
  exactly like `scale_out` (`10`, `"10"`, `" 10 "`; `"1,6"` is 16; `null`
  or `""` off; `true`, text, a list or an object is `add_on must be a
  number...`; `NaN`, `Infinity`, `"nan"`, `"inf"` is `add_on must be a
  finite number`), `max_adds` exactly like `max_hold` (`2`, `2.0`, `"2"`;
  `2.5`, `"2.0"`, `"abc"`, `true` is `max_adds must be a whole number...`),
  then the command's rules and messages (`cli.check_add_on`): `add_on` 0 or
  below, `max_adds` below 1, and `max_adds` without `add_on` are 400s. They
  need no candle data. When `add_on` is sent, `params` echoes `add_on` and
  `max_adds` (1 when not sent, `null` or `""`; the other settings never echo
  a default) right after `scale_out`; `summary` gets the four `--json` keys
  right after the scale-out keys; trades carry `reason`, the columns end with
  `reason`, and `report` is the command's report line for line.
- **Web page: "Add-on (%)" and "Max adds" fields** after "Max drawdown (%)",
  each with a hint. Each is sent only when filled in (`add_on`, then
  `max_adds`, right after `max_drawdown`); a Max adds without an Add-on is
  sent anyway and the server's message shown. They need no candle data: never
  greyed out or cleared, and the close-only hint does not name them. With the
  option the **Trades** card adds `, N add-on buys, M add-ons skipped` right
  after the scale-out count (`2 buys, 1 sells, 1 add-on buys, 0 add-ons
  skipped`; all-in `1 buys, 1 sells, 0 add-on buys, 3 add-ons skipped`). A
  bad value shows the server's message.
- **Library**: `cli.check_add_on(add_on, max_adds)`, `cli.summarise(...,
  add_on_pct=None, max_adds=None)`, `BacktestResult.add_on_pct`,
  `max_adds`, `add_on_skipped_buys` and `n_add_on_buys`.
- **Docs**: an "Add-ons" section in [docs/cli.md](docs/cli.md#add-ons) with
  the `up.csv` outputs, three tables of small runs (every row rerun through
  the command line), the spacing arithmetic and the value tables for the
  flag, the config keys and the API; README, the architecture notes and the
  module docstrings describe it too.
- **Tests**: `test_add_on.py` (12), `test_cli_add_on.py` (7),
  `test_cli_add_on_json.py` (3), `test_config_add_on.py` (5),
  `test_web_add_on.py` (31) and `test_web_add_on_page.py` (8), 66 tests, with
  `tests/data/before_add_on.json` (36 engine runs recorded before the option
  existed, 5,700 bytes) and `tests/data/cli_before_add_on.json` (25 commands
  and 496 shortened-option runs recorded before it existed, 84,845 bytes).

### Existing results do not change

Without `--add-on` and `--max-adds` (and the two config keys and API fields)
every output is exactly as in 0.19.0. This was compared with 0.19.0's code,
each version run on its own with the same input files: 287 engine runs
(three price series, seven strategies, both fills, nine mixes of costs,
position size, stops, target, trailing and ATR stops, risk sizing,
breakeven, scale-out, cooldown, holding times and both halts; fills, daily
rows, round trips, report, statistics, export, trade list, skip counts and
the buy-and-hold curve, floats exactly), 35 main commands (text, `--json`,
`--export`, `--stats`, `--trade-list`, `--chart`, `--explain`,
`--resample`, `--candles`, `--scan`, `--report`, usage and data errors,
`--help`, and the new names; stdout, stderr, exit code and files), every
name and prefix of every option (248 tokens, each with a value, alone, and
with `--scan`: 744 runs), 31 runs of the other tools (the sweep,
walk-forward, portfolio, Monte Carlo, drawdowns, summary, samples, alerts,
journal and web tools: a run, `--help`, and `--add-on` and `--max-adds`), 72
config runs (8 files, each with text, `--json`, a flag, no `--backtest` and
`--scan`, on a close-only and a candle file), 28 HTTP requests (`GET /`,
`/style.css`, `/app.js`, `/api/samples`, `/api/health`, a 404 and a 405; 15
to `/api/backtest`, including the new fields as `null` and `""`; 2 each to
`/api/scan`, `/api/walkforward` and `/api/portfolio`, with and without the
new fields; status, headers and body, byte for byte), 21 library probes, and
the backtest form's script in Node, old and new, with the new fields left
empty, given the same 13 sets of inputs (identical requests, cards, report
and trades table). The only differences were the runs that use the new
options and the ones listed here:

- `--help` (also through `--h`, `--he` and `--hel`, and with `--scan`): 35
  lines describing `--add-on` and `--max-adds` are added after the
  `--scale-out` block (checked at 80 columns), none changed. The usage line
  does not change, so usage errors print exactly what they printed before.
- `--add-on`, `--max-adds` and their prefixes `--ad` to `--add-o` and
  `--max-a` to `--max-add` were `unrecognized arguments` (exit 2) in 0.19.0;
  they now mean the new options. So `up.csv --add-on 10` (no `--backtest`) is
  now `--add-on only makes sense together with --backtest`, `--max-adds 2`
  with `--backtest` `--max-adds only makes sense together with --add-on`,
  `--scan FOLDER --add-on 10` `--add-on cannot be combined with --scan`
  instead of `unrecognized arguments: --add-on`, and a bare `--ad` `argument
  --add-on: expected one argument` (all still exit 2); `--ad 3` with
  `--backtest` now runs.
- `ambiguous option: --a could match --atr-mult, --atr-period, --atr-stop`
  is now `... --atr-stop, --add-on` (still exit 2). `--ma`, `--max` and
  `--max-` still mean `--max-hold` (hidden exact aliases since 0.12.0), and
  every other name and prefix sets the same option as in 0.19.0 (702 of the
  744 token runs are byte for byte the same; the 42 others are the tokens
  above).
- Config files: `add_on` and `max_adds` were `unknown key ... in [cli]`
  (exit 1) in 0.19.0, also without `--backtest` and with `--scan`. Now they
  are read: with `--backtest` `add_on` runs the add-ons; `max_adds` alone is
  ignored (the run is the one without it); without `--backtest` and with
  `--scan` both are ignored. For every other unknown key the list of allowed
  keys gains `add_on, max_adds` after `scale_out`
  (`... max_losses, scale_out, add_on, max_adds, fill, ...`).
- `POST /api/backtest` ignored `add_on` and `max_adds` in 0.19.0. Now:
  - a request with `add_on` gets the add-ons, with `add_on` and `max_adds`
    at the end of `params` (before `trade_list` and `explain`), the four keys
    in `summary`, the `reason` on every trade, the `reason` column and the
    `Add-ons:` report line;
  - `add_on` 0 or below, a non-number, `NaN` or infinity, `max_adds` below 1
    or not a whole number, and `max_adds` without `add_on` were answered as
    if absent and are now 400s;
  - error order: a field that cannot be read (`"add_on": "x"`,
    `"max_adds": "x"`) is now reported before an error in `trade_list`,
    `explain`, `fill`, a later range check (`stop_loss: 200`) or the prices
    (`source`, `sample`, `csv`); errors in the windows, `cash`, the fees,
    `strategy`, `params` and the number fields read before it (`scale_out:
    "y"`) still come first. A range error (`"add_on": 0`, `"max_adds": 0`)
    comes after the other range checks (`stop_loss: 200`, `max_losses: 0`
    still win) but before the prices (`"source": "x"` with `"add_on": 0` was
    the `source` error and is now the `add_on` one).
  `null`, `""` or no key get the 0.19.0 reply byte for byte. `/api/scan`,
  `/api/walkforward` and `/api/portfolio` still ignore both keys (byte for
  byte the same replies).
- Web page: `GET /` differs by the two new fields (10 lines added, nothing
  removed; `Content-Length` 24,877 to 25,674), and `GET /app.js` by 9 lines
  added (8 in the request code: 4 comment lines and the two send blocks; 1
  Trades card line; `Content-Length` 59,749 to 60,532). **The fields are two
  new cells in the settings grid after "Max drawdown (%)", so the close-only
  hint after them moves two cells later.** `GET /style.css`, `/api/samples`
  and `/api/health` are unchanged, and so are the list of candle-only
  controls and the close-only hint's text.
- Library: `BacktestResult` has three new last fields, `add_on_pct` (None),
  `max_adds` (None) and `add_on_skipped_buys` (0), after `scale_out_pct`, so
  `repr()` and `dataclasses.asdict()` of every result now end with them; the
  37 fields before keep their order. `BacktestResult.has_exits` is also true
  with `add_on_pct`, and `Trade.reason` can be `add_on`. `run_backtest` and
  `cli.summarise` take `add_on_pct` and `max_adds` as new last parameters,
  so calls by position are unchanged. The `cli` module has the new
  `check_add_on` (also imported by `web.server`), `config` the new
  `_ADD_ON_FLOAT_KEYS` and `_ADD_ON_INT_KEYS`, `web.server.LATER_SETTINGS`
  gains `"add_on"` and `"max_adds"` after `"scale_out"` (before
  `"trade_list"`), and the dict `web.server.parse_request` returns has
  `add_on` and `max_adds` only when `add_on` is sent. `build_parser()` has two
  new option strings. Inside `run_backtest` the buy code moved into two
  helpers shared by signal buys and add-ons (sizing and booking); the 287
  runs above give the same floats. `trading_assistant.__all__` does not
  change.
- The version is 0.20.0 (`pyproject.toml`; the installed package reports
  0.20.0 after `scripts/setup_dev.sh`). No output prints the version.

### Not checked

- The page was run in Node with a stand-in for the browser, never in a real
  browser: the look of the two fields and their hints, the close-only hint
  moving two grid cells, the longer Trades card line, narrow screens,
  keyboard order, screen readers and the dark theme are unchecked. Browsers
  read text that is not a number in a number field as empty, so typing
  `ten` or `inf` there would probably send nothing; the stand-in sends the
  text and shows the server's message (tested). With a value in the fields
  only a pasted close-only CSV (`up.csv`) was run on the page; not a candle
  CSV, a built-in sample, an uploaded file or open fills (the API was run
  with a candle CSV; not with a sample or open fills).
- `--help` was checked at 80 columns only, and only Python 3.12 was run.
- A drawdown sale refused by the fees was checked only on a made-up series
  (a fee of 600 on a 1,000 account).

### Not covered yet

- With open fills an add-on fills at the open and no stop, target or
  scale-out acts on that bar, even when the bar's low goes through the stop;
  results with `--fill open` and add-ons are flattered by that. There is no
  option to check the bar's range after an add-on at the open.
- The level is compared in floating point, so a close exactly on it can fall
  just short (12.10 after a buy at 11 with `10`).
- With the default all-cash sizing an add-on almost never gets shares; there
  is no separate size for add-ons.
- The sweep, walk-forward, portfolio, Monte Carlo, drawdowns and summary
  commands do not take the options (`unrecognized arguments`, exit 2), the
  buy-and-hold comparison has no add-ons, and `tests/test_paths_agree.py`
  does not include them (the tests above compare each path instead).
- There is no value that switches off a config file's `add_on` for one run
  (`--add-on 0` is out of range); a large `--add-on` never buys, but the
  report still shows its line. The Trades card count reads `1 add-on buys`
  (no singular, like the card's other counts); the report line says
  `1 add-on buy`.

### Changed tests

Only the lines that pin output this release changes on purpose:

- `test_cli_atr_stop.py::test_help_only_changes_the_atr_options`: the list of
  `--help` entries gains `--add-on` and `--max-adds` after `--scale-out`
  (one line).
- `test_cli_scale_out.py::test_help_adds_only_the_scale_out_block_after_max_losses`:
  the expected list of `--help` entries gains them after `--scale-out`, and
  they are left out of the comparison with the old blocks (two lines).
- `test_cli_trade_list.py`: `test_every_shortened_option_name_means_what_it_meant`
  (both modes) checks `--a` against its new message and allows the new
  prefixes `--ad` to `--add-on` and `--max-a` to `--max-adds` (two lines
  changed, two added); `test_help_lists_it_after_stats_and_the_usage_line_is_unchanged`
  also takes the two new blocks out before comparing with the old help (one
  line added).
- `test_config_atr_stop.py` (`NEW_KEY_LIST`),
  `test_config_backtest_keys.py::test_unknown_key_message_lists_the_new_keys`,
  `test_config_risk_sizing.py` (`NEW_KEY_LIST` and the two unknown-key runs in
  `OLD_RUNS`) and
  `test_config_trailing_stop.py::test_unknown_key_message_now_lists_trailing_stop`:
  the pinned unknown-key list gains `add_on, max_adds` after `scale_out`
  (one line each, six in all).
- `test_web_atr_stop_page.py`: `SKIPPED_JS` (the Trades card code) gains the
  add-on line (one line added), and
  `test_nothing_else_changed_since_before_the_checkbox` also takes out the
  two fields and their send code before hashing (three lines added).
  `test_web_risk_sizing_page.py::test_nothing_else_changed_since_before_these_controls`,
  `test_web_trailing_stop_page.py::test_nothing_else_on_the_page_changed` and
  `test_web_walkforward_warmup_page.py::test_box_is_the_last_setting_unticked_and_nothing_else_changed`
  also take out the fields, the send code and the Trades card line (four
  lines added each). The pinned hashes are unchanged. No line of an existing
  test was removed except the eleven one-line replacements above.

## 0.19.0 (2026-11-16)

### Added

- **`--explain`**, a switch, off by default: one sentence on its own line
  right after the `Signal:` line (before `RSI:`) saying why the signal is
  what it is. Each point below was checked on a small case (see
  [docs/cli.md](docs/cli.md#signal-explanation---explain)):
  - The sentence's first word is the `Signal:` line's decision: both come
    from `signals.crossover_signal` on the same closes and the same
    `--short`/`--long` windows (150 random command-line runs: the `Signal:`
    word, the first word and `crossover_signal` never disagreed).
  - It gives the short SMA against the long SMA on the last bar, then on the
    bar before, and says why: `crossed above` (BUY), `crossed below` (SELL),
    `stayed above` / `stayed below ..., so there is no new crossover`,
    `ended level with ..., so there is no crossover`, or, with fewer than
    `--long` + 1 bars, `a crossover needs at least N bars and there are M`
    (`there is 1` for one bar; `n/a` where there is no average yet). A HOLD
    sentence never says "crossed".
  - Each bar's pair has 2 decimals, or as many more as it takes to tell two
    different averages apart (`10.004 against 10.002`); equal ones keep 2
    (`10.00 against 10.00`). A difference that is only rounding in the
    arithmetic shows in full: `0.2, 0.1, 1.1, 0.3, 0.1, 0.1, 0.1` with
    `--short 1 --long 3` is a BUY, `0.1000000000000001 against
    0.1000000000000000` (the signal did this before too; now it shows).
  - `c.csv` with `--short 1 --long 3`: all 11 rows HOLD (`stayed above`,
    12.20 against 11.73, 12.00 against 11.00), the first 4 BUY (9.00 against
    8.67 after 8.00 against 9.00), the first 7 SELL (10.00 against 11.00
    after 12.00 against 10.67), the first 3 HOLD (`needs at least 4 bars and
    there are 3`).
  - It follows the `Signal:` line, not `--strategy` or `--param`: with
    `--param short=1 --param long=3` and no `--short`/`--long` the backtest
    trades SMA 1/3 while the sentence explains the default 20/50 line. With
    `--resample` it explains the resampled bars (`c.csv` weekly: 2 bars).
  - It needs no `--backtest` and no candle file, and works with
    `--backtest`, `--strategy`, `--resample`, `--candles`, `--chart`,
    `--stats`, `--trade-list` and `--export` (the export file is the same
    with or without it). `--scan` with it is a usage error,
    `--explain cannot be combined with --scan` (exit 2). It is listed in
    `--help` after `--chart`, not in the usage line.
- **`--json` with `--explain`**: `explanation`, the same sentence, right
  after `signal` (a top-level key, also with `--backtest`).
- **Config key `explain`** (yes/no, the words `stats` takes): `yes` turns
  the sentence on in any single-file run (no `--backtest` needed); `no`
  leaves the flag as written, so `--explain` wins over `explain = no`. With
  `--scan` it is ignored, also `yes` (unlike the flag). A word that is not
  yes/no is `Error: FILE line N: explain needs yes or no, got 'maybe'`
  (exit 1), with `--scan` too. It works through `TRADING_ASSISTANT_CONFIG`
  as well.
- **`POST /api/backtest` takes `explain`**, read exactly like `atr_stop`
  and `trade_list`: JSON `true` turns it on; `false`, `null`, `""` or no key
  leave it off; any string, any number, a list or an object is a 400
  (`explain must be true or false, got 'yes'`, `..., got 1`, or without
  `got` for a list or an object). It needs no candle data. With `true`:
  - `report` gets the sentence right after its `Signal:` line, so it is the
    command's `--backtest --explain` output line for line (checked on
    `c.csv` and its first 4, 7 and 3 rows, with `trade_list` too, and on the
    `random_walk` sample with and without sample candles);
  - the reply gets `explanation` right after `report`: `decision`,
    `sentence`, `last_bar` and `previous_bar` (each
    `{"short": ..., "long": ...}`, unrounded, `null` without enough bars).
  It is echoed in `params` when sent (`true` or `false`), right after
  `trade_list`. The API has no `--resample`, so it explains the closes as
  sent.
- **Web page: an "Explain signal" box** right after the "Trade list" box,
  with a hint. Ticked, the page sends `"explain": true` (right after
  `trade_list`); unticked, exactly the old request. It needs no candle data:
  never greyed out or unticked, and the close-only hint does not name it.
  The page shows the reply's text report as it is, so the sentence appears
  once, under `Signal:` in the **Text report** panel; nothing else on the
  page changes, and an unticked run (also after a ticked one) shows no
  sentence. A rejected request shows the API's message as for any field.
- **Library**:
  - `signals.explain_crossover(closes, short=20, long=50)` (the sentence)
    and `signals.explain_crossover_data(closes, short=20, long=50)` (the
    decision, the sentence and the two pairs of SMAs, as a dict), both from
    one computation that calls `crossover_signal` itself. Both raise
    `ValueError` for bad windows, as `crossover_signal` does, and for a close
    that is not a finite number.
  - `cli.report_lines` takes a new last parameter, `explanation=None` (the
    2nd); `cli.report_data` a new last parameter, `explanation=None` (the
    5th, after `trade_list`); `cli.analyse` a new keyword-only
    `explanation=None`. `None` leaves each exactly as before.
- **Tests**: `test_explain_crossover.py` (8), `test_cli_explain.py` (12),
  `test_config_explain.py` (6), `test_web_explain.py` (8) and
  `test_web_explain_page.py` (7), 41 tests. No new files in `tests/data/`.

### Existing results do not change

Without `--explain` (or `explain`) every output is exactly as in 0.18.0.
This was compared with 0.18.0's code, each version run on its own with the
same input files: 81 main commands (text, `--json`, `--backtest` with every
option, `--resample`, `--candles`, `--chart`, `--export`, `--scan`,
`--report`, config files, data and usage errors, `--help`, and every new
name; stdout, stderr, exit code and files), 27 commands of the other tools
(the sweep, walk-forward, portfolio, Monte Carlo, drawdowns, summary,
samples, alerts, journal and web tools, their `--help`, and the first six
with `--explain`), every name and prefix of every option of the main command (241
tokens, with a price file and with `--scan`), 19 library probes, 33 HTTP
requests (`GET /`, `/style.css`, `/app.js`, `/api/samples`, `/api/health`, a
404 and a 405; 17 to `/api/backtest`, 3 each to `/api/scan`,
`/api/walkforward` and `/api/portfolio`, with and without an `explain` key;
status, headers and body, byte for byte) and the backtest form's script in
Node, old and new, unticked, given the same 6 sets of inputs (identical
requests and display). The only differences were the runs that use the new
names and the ones listed here:

- `--help` of the main command: five lines describing `--explain` are added
  after `--chart` (checked at 80 columns). The usage line does not change,
  so usage errors print exactly what they printed before.
- `--expl`, `--expla`, `--explai` and `--explain` were `unrecognized
  arguments` (exit 2) in 0.18.0; they all mean `--explain` now. With
  `--scan` they are still exit 2, now `--explain cannot be combined with
  --scan` instead of `unrecognized arguments: --explain`. `--explain=1` is
  still exit 2, now `argument --explain: ignored explicit argument '1'`
  instead of `unrecognized arguments: --explain=1`. `--e`, `--ex` and
  `--exp`, which argparse would now find ambiguous, are hidden exact aliases
  of `--export`: they set the same option and give the same messages as in
  0.18.0 (`--expo` is unchanged). `--explian` is still `unrecognized
  arguments`. Every other name and prefix sets the same option as in 0.18.0.
- Config files: `explain` was `unknown key 'explain' in [cli]` (exit 1) in
  0.18.0, also with `--scan`. Now `explain = yes`/`no` is accepted (with
  `--scan` the scan runs and prints its table), and any other value is
  `explain needs yes or no, got ...` (exit 1). For every other unknown key the
  message's list of allowed keys gains `explain` after `trade_list`
  (`... stats, trade_list, explain, top, min_score`).
- `POST /api/backtest` ignored an `explain` key in 0.18.0:
  - `"explain": true` got the plain reply and now gets the sentence line in
    `report`, `explanation` after `report` and `"explain": true` at the end of
    `params`;
  - `"explain": false` now gets the plain reply with `"explain": false` added
    at the end of `params` (nothing else differs);
  - `"yes"`, `"true"`, `1`, `0`, lists and objects were answered as if
    absent and are now 400s;
  - a request with a bad `explain` and an error in `fill`, in a range of a
    later setting (`stop_loss: 200`, `slippage: 100`, `cooldown` without a
    stop, ...) or in the prices (`source`, `sample`, `csv`) now gets the
    `explain` error instead of that one; errors in the windows, `cash`, the
    fees, `strategy`, `params`, a number field that cannot be read
    (`stop_loss: "abc"`) or `trade_list` still come first.
  `null`, `""` or no key get the 0.18.0 reply byte for byte. `/api/scan`,
  `/api/walkforward` and `/api/portfolio` still ignore an `explain` key
  (`true` and `"yes"` alike; byte for byte the same replies).
- Web page: `GET /` differs by the new box (7 lines added, nothing removed),
  `GET /app.js` by 5 lines added in the backtest form's request code (4
  comment lines and the send line), and so their `Content-Length`.
  `GET /style.css`, `/api/samples` and `/api/health` are unchanged. **The
  box is a new cell in the settings grid after "Trade list", so every field
  after it (Cooldown, Max losses, Min hold, Max hold, Max drawdown and the
  close-only hint) moves one cell later** on the page.
- Library: the new functions and parameters above. Called as in 0.18.0, by
  name or by position, `report_lines`, `report_data` and `analyse` give
  exactly the same results. A call to `report_data` with one positional
  argument more than 0.18.0 took was a `TypeError` and now sets
  `explanation`. The `cli` module has a new name, `explain_crossover`
  (imported from `signals`), and `signals` a new module name, `math` (an
  import); `trading_assistant.__all__` does not change. The dict
  `web.server.parse_request` returns has a new `explain` entry (`False` when
  off), and `web.server.LATER_SETTINGS` ends with `"explain"`.
- Existing tests changed (with the reason), nothing else in them:
  - `test_cli_atr_stop.py`, `test_cli_cooldown_unchanged.py`,
    `test_cli_risk_sizing.py`, `test_cli_scale_out.py` and
    `test_cli_trade_list.py` (its help test): they compare `--help` with the
    text of an older version after taking out the options added since; they
    now take out the `--explain` block too (or expect `--explain` after
    `--chart` in the list of options).
  - `test_cli_trade_list.py` (`test_every_shortened_option_name_means_what_it_meant`,
    both modes): it allowed no new option name prefix; it now allows exactly
    `--expl`, `--expla`, `--explai` and `--explain`, checks they mean
    `--explain`, and checks `--e`, `--ex` and `--exp` still mean `--export`.
  - `test_config_atr_stop.py`, `test_config_backtest_keys.py`,
    `test_config_risk_sizing.py` (three lines), `test_config_trailing_stop.py`
    and `test_scan.py`: the pinned unknown-key message gains `explain`.
  - `test_web_atr_stop_page.py`, `test_web_risk_sizing_page.py`,
    `test_web_trailing_stop_page.py` and
    `test_web_walkforward_warmup_page.py`: they hash the page as it was after
    taking out the pieces added since; they now take out the new box and its
    send line too (the same two lines each).
- The version is 0.19.0 (`pyproject.toml`; the installed package reports
  0.19.0 after `scripts/setup_dev.sh`). No output prints the version.

### Not checked

- The page was run in Node with a stand-in for the browser, never in a real
  browser: the look of the box and its hint, the fields moving one grid cell,
  the long sentence in the text report (it does not wrap there; the report
  scrolls sideways, as for long fill lines), narrow screens, keyboard order,
  screen readers and the dark theme are unchecked. With the box ticked only
  pasted CSVs were run on the page, not a built-in sample or an uploaded
  file (the API was run with a sample).
- `--help` was checked at 80 columns only.
- Only Python 3.12 was run.

### Not covered yet

- The sentence explains the SMA crossover of the `Signal:` line only, not
  the strategy traded by `--backtest` (`--strategy`, `--param`), and not the
  RSI line.
- On the page the sentence is inside the collapsed Text report panel; there
  is no signal card of its own.
- The sweep, walk-forward, portfolio, Monte Carlo, drawdowns and summary
  commands do not take `--explain` (`unrecognized arguments`, exit 2), and
  the API has no `--resample`.

## 0.18.0 (2026-11-16)

### Added

- **`--warmup` for the walk-forward command**, a switch, off by default. The
  pair is still chosen on the train bars only, by the same sweep, so every
  window gets the same pair and train return as without it. Each window's test
  run is then warmed up on the chosen pair's `long` bars just before its test
  block, and still trades and is scored on the test block only. Rules, each
  checked on a small case (`tests/data/wf.csv`, 18 closes; see
  [docs/cli.md](docs/cli.md#--warmup)):
  - Same pairs with and without it, on three settings; changing every bar
    from the first test block on never moved window 1's choice.
  - The warm-up is `closes[test_start - long:test_start]` with each window's
    own chosen `long`: `--short 1,2 --long 3,4,5 --train 9 --test 3` chooses
    1/3, 1/5, 1/3 and warms up on 3, 5 and 3 bars. With `long` at most
    `--train` these are the last `long` bars of the train block; a larger
    `long` reaches back before it (`--short 1 --long 5 --train 3 --test 7`,
    window 2: bars 5-9 for train bars 7-9).
  - Near the start of the data, with fewer than `long` bars before a test
    block, whatever bars there are, back to bar 0, are used: that same run's
    window 1 (test from bar 3) gets bars 0-2, 3 of 5. Its buy signal on bar 7
    needs bar 2, so it trades (+8.30 %) where it did not without the switch.
  - The warm-up bars only feed the signal. The run starts flat with fresh
    cash on the first test bar; signals are only worked out on test bars, so
    a crossing on the last warm-up bar is not acted on (checked on
    `run_backtest` with 4 warm-up bars, where the crossing on bar 7 was
    visible: no fill on bar 8), and a crossing on the first test bar fills on
    the second. A 1-bar test block still never trades; a 2-bar one can.
  - Every figure is measured on the test block alone; buy and hold does not
    change. Example: `--short 1 --long 3 --train 12 --test 6 --cash 1000`
    goes from 0 trades, +0.00 % to 1 trade (76 shares bought at 13.00 on bar
    14), +7.60 %, drawdown -6.60 %, end equity 1,076.00; buy and hold +40.00 %
    both ways. With `--test 4` the same trade, +7.60 %, drawdown 0.00 %.
  - The text says so in two places, only with the switch: the header line
    ends `then traded and scored on the test bars after them, with its moving
    averages warmed up on up to long bars just before each test block`
    (instead of `then run on the test bars after them`), and the no-trades
    note gives `no BUY crossover on a test bar before its last, or, near the
    start of the data, fewer than long bars before the block to warm up` as
    its reasons (instead of `no crossover, or fewer than long + 2 test bars to
    warm up`).
  - It takes no value: `--warmup 5` (`unrecognized arguments: 5`) and
    `--warmup=5` (`argument --warmup: ignored explicit argument '5'`) are
    usage errors, exit 2.
- **`--json` with `--warmup`**: the object gets `"warmup": true` as its
  **first** key, before `windows`, because it says how every number after it
  was made (as the text's header line does). It is only there with the
  switch, never as `"warmup": false`; the other keys, their order and the
  window and summary fields do not change. The numbers match the text of the
  same run (the text rounds them to 2 decimals).
- **`--csv` with `--warmup`** writes the same columns and one row per window,
  with the warmed-up numbers. **The CSV cannot show that warm-up was on**:
  nothing in the file tells a warmed-up run from a cold one
  (`1,0,12,12,18,1,3,0.0000,0.0000,0.0000,0,40.0000` without,
  `1,0,12,12,18,1,3,0.0000,7.6000,-6.5972,1,40.0000` with). Keep the command,
  or its text or `--json` output, with the file.
- **Library**:
  - `backtest.run_backtest` takes a new last parameter, `warmup_closes`
    (the 29th, after `scale_out_pct`; default `None`): closes of the bars just before `closes[0]`, which only
    the signal sees. Bar numbers, fills, cash, the equity curve, drawdown,
    round trips and the buy-and-hold benchmark are counted on `closes` alone;
    the exits, ATR, highs, lows and opens do not use them. `None` and `[]`
    leave the run exactly as before. A non-positive warm-up price raises
    `ValueError` (`warm-up bar 1: price must be positive, got -2`).
  - `walkforward.walk_forward` and `walkforward.run_walk_forward` take a new
    last parameter, `warmup=False` (the 10th, after `fee_pct`). `walk_forward` raises `ValueError` for
    anything but `True` or `False` (`warmup must be True or False, got 1`;
    `None` too). Without warm-up the test backtest is called exactly as
    before, with no `warmup_closes` keyword at all.
  - `walkforward.format_walk_forward` and `walkforward.json_data` take a new
    last parameter, `warmup=False` (the 3rd, after `summary`; the header and
    note wording; the first key). All five new parameters can be given by
    name or by position. New constants `walkforward.HEADER_RUN`, `HEADER_RUN_WARMUP`,
    `NO_TRADES_REASON` and `NO_TRADES_REASON_WARMUP` hold the wording.
- **`POST /api/walkforward` takes `warmup`**, read exactly like
  `/api/backtest`'s `atr_stop` and `trade_list`: JSON `true` turns it on;
  `false`, `null`, `""` or no key leave it off; any string (`"true"`,
  `"yes"`), any number (`1`, `0`, `1.5`), a list or an object is a 400
  (`warmup must be true or false, got 'yes'`, `..., got 1`, or without `got`
  for a list or an object). A `short`, `long`, `train`, `test`, `step`,
  `cash`, `fee` or `fee_pct` that cannot be read at all (`train: "x"`) is
  still reported first; a bad `warmup` comes before the range and pairing
  rules (`train: 0`, `cash: -1`, no pair with short < long) and before
  anything about the prices (a bad `source`, `sample` or `csv`). With
  `true` the run is warmed up and the reply is the `--warmup --json` object,
  `"warmup": true` first; its numbers equal the command's. The bar-step limit
  does not change. The dict `web.server.parse_walkforward_request` returns
  has a new `warmup` entry (False when off).
- **Web page: a "Warm up" box** in the "Walk-forward test" panel, its last
  setting (after "Cost % of trade value", before "Run walk-forward"), with a
  hint. Ticked, the panel sends `"warmup": true` (after the other fields);
  unticked, exactly the old request. When the reply has `"warmup": true`
  (exactly `true`: a reply with `1`, `"true"`, `"yes"`, `0`, `false` or
  `null` is shown as one without it) the panel shows the command's `--warmup`
  header line above the windows, in a line it does not otherwise show, and
  uses the warm-up wording in the no-trades note; any other reply leaves the
  line hidden and empty, also after a run that showed it. A rejected request
  shows the API's message in the panel's error box, as for any other field.
  The panel's introduction text is static and was left as it is: its "The
  numbers are exactly those of `python -m trading_assistant.walkforward
  --json`" is only exact when the box is unticked (ticked, they are those of
  `--json --warmup`). The panel has no CSV download.
- **Tests**: `test_walkforward_warmup.py` (5), `test_walkforward_warmup_cli.py`
  (5), `test_web_walkforward_warmup.py` (6) and
  `test_web_walkforward_warmup_page.py` (7), 23 tests, with
  `tests/data/wf.csv` and three files recorded from 0.17.0 before each step:
  `wf_before_warmup.json` (the engine's rows), `wf_cli_before_warmup.json`
  (four commands: text, `--json`, `--csv` with a fee, and an overlapping
  `--step`; stdout, stderr and the CSV file) and `wf_api_before_warmup.json`
  (the raw reply of one request).

### Existing results do not change

Without `--warmup` (or `warmup`) every walk-forward result, text, `--json`
object, `--csv` file and API reply is exactly as in 0.17.0, and so is
everything else. This was compared with 0.17.0's code, each version run on
its own with the same input files: 53 walk-forward commands (text, `--json`,
`--csv`, `--step`, fees, seven data errors, ten usage errors (one of them no
arguments at all), `--help`, and
every prefix of `--warmup` with and without `--json`; stdout, stderr, exit
code and files), every name and prefix of every walk-forward option (50
names, each with and without a following value), 17 probes calling
`walk_forward`, `run_walk_forward`, `summarize`, `format_walk_forward`,
`json_data`, `split_window` and `write_csv` with their defaults, 86 `run_backtest` runs (`c.csv`
and 300 bars of the `random_walk` candles, every strategy, six mixes of
costs, sizing, fills and every exit option; the whole result), 42 commands
of the other tools (the main command line with `--backtest`, `--json`,
`--stats`, `--trade-list`, `--export`, `--resample`, `--chart`, `--scan`
and `--report`; the sweep, portfolio, Monte Carlo, drawdowns, summary,
alerts, samples, journal and web tools; their `--help`), 38 HTTP requests
(`GET /`, `/style.css`, `/app.js`, `/api/samples`, `/api/health`, a 404 and a
405; 23 to `/api/walkforward`, 4 to `/api/backtest`, 2 each to `/api/scan`
and `/api/portfolio`, with and without a stray `warmup` key; status, headers
and body, byte for byte) and the walk-forward panel's script in Node, old and
new, unticked, given the same 10 sets of inputs (identical requests and
display). The only differences were the runs that use the new option and
the ones listed here:

- `--help` of the walk-forward command: the usage line's last two lines
  change from `[--fee AMOUNT] [--fee-pct PCT] [--json]` / `[--csv OUT]` to
  `[--fee AMOUNT] [--fee-pct PCT] [--warmup]` / `[--json] [--csv OUT]`, and
  three lines describing `--warmup` are added after `--fee-pct` (checked at
  80 columns). **The same usage line is printed with every usage error**
  (exit 2), so those errors' stderr differs in the same two lines even
  without `--warmup`; the error messages themselves do not change.
- `--w`, `--wa`, `--war`, `--warm`, `--warmu` and `--warmup` were
  `unrecognized arguments` (exit 2) in 0.17.0; they all mean `--warmup` now
  (argparse takes any unique prefix, as `--tr` means `--train`). `--warmup
  --warmup` is accepted too. A value after one of them (`--w 7`) is still
  exit 2, now `unrecognized arguments: 7`. `--wamup` is still `unrecognized
  arguments: --wamup`. Every other name and prefix sets the same option as
  in 0.17.0 (or gives the same error message), and every parse without one
  of these names has `warmup` False.
- `POST /api/walkforward` ignored a `warmup` key in 0.17.0: `"warmup": true`
  got the cold reply and now gets the warmed-up one, `"true"`, `"yes"`, `1`,
  `0`, `[]` and `{}` were answered as if absent and are now 400s, and a
  request with a bad `warmup` and a range, pairing or prices error
  (`train: 0`, `cash: -1`, no pair with short < long, a bad `source`,
  `sample` or `csv`) now gets the `warmup` error instead of that one (for
  example `--train must be at least 1`); a field that cannot be read at all
  (`train: "x"`) still comes first. `false`, `null`, `""` or no
  key get the 0.17.0 reply byte for byte. `/api/backtest`, `/api/scan` and
  `/api/portfolio` still ignore a `warmup` key (byte for byte the same
  replies).
- Web page: `GET /` differs by the new box (7 lines) and the hidden header
  line (1 line), nothing removed; `GET /app.js` by 22 lines added and 4
  changed, all in the walk-forward panel (the send line, `wfWarmupLine`, the
  note wording and the header line in `renderWf`). `GET /style.css`,
  `/api/samples` and `/api/health` are unchanged. The box is the panel's last
  setting, so no existing field moves on the grid.
- Library: the new parameters and constants above. Called as in 0.17.0,
  by name or by position, `run_backtest` and the four walk-forward functions
  give exactly the same results (19 positional calls compared, every one of
  `run_backtest`'s 28 old parameters by position among them). A call with one
  positional argument more than 0.17.0 took was a `TypeError` and now sets
  the new parameter (`walk_forward(closes, [1], [3], 12, 6, None, 1000, 0.0,
  0.0, True)` runs with warm-up).
- Existing tests changed (with the reason): the three page tests that hash
  the page as it was (`test_web_atr_stop_page.py`,
  `test_web_risk_sizing_page.py`, `test_web_trailing_stop_page.py`) undo the
  new box, the header line and the script's warm-up pieces before hashing
  (the same five lines and one import each; the pieces are listed once, in
  `test_web_walkforward_warmup_page.py`). No other test changed.
- The version is 0.18.0 (`pyproject.toml`; the installed package reports
  0.18.0 after `scripts/setup_dev.sh`). No output prints the version.

### Not checked

- The page was run in Node with a stand-in for the browser, never in a real
  browser: the look of the box and of the long header line and how it wraps,
  narrow screens, keyboard order, screen readers, the dark theme, and that
  the `hidden` attribute really hides the line are unchecked. With the box
  ticked only a pasted `wf.csv` was run: not a built-in sample and not an
  uploaded file (the unticked comparison used both samples and `wf.csv`).
- `--help` and the usage line were checked at 80 columns only; at other
  widths they wrap differently in both versions.
- Only Python 3.12 was run.

### Not covered yet

- Only the walk-forward command has a warm-up. The sweep, the portfolio
  command, the Monte Carlo tool, the drawdowns tool and the main command line
  do not take `--warmup` (`unrecognized arguments`, exit 2, as before), and
  the train blocks are never warmed up (the pair is chosen on the train bars
  only, by design).
- The CSV has no column or line that records warm-up.
- The walk-forward test is for the SMA crossover only, with or without
  warm-up.

## 0.17.0 (2026-11-15)

### Added

- **Trade list in the library**: `backtest.trade_list(result)` returns one
  dict per row and `backtest.format_trade_list(result)` the text table. Both
  are built after the run from `result.round_trips` and `result.trades` and
  change nothing on the result; the engine (`run_backtest`, `RoundTrip`,
  `BacktestResult`) is unchanged. Rules, each checked on a small case (most on
  `c.csv` in [docs/cli.md](docs/cli.md#trade-list), `short=1`, `long=2`, cash
  1000: BUY 90 @ 11 on bar 4, SELL @ 10 on bar 7, BUY 75 @ 12 on bar 9, last
  close 12.20):
  - Only completed round trips are rows, in order: the rows are
    `result.round_trips` themselves, so their number and their wins (profit
    after costs above 0) are those of the `Round trips:` line. A round trip
    at exactly 0.00 is not a win (checked on a series where 80 shares are
    bought and sold at 10.00, and on the 7 round trips at 0.00 among the 123
    runs below). Checked on 123 runs (every strategy and every exit option,
    on `c.csv` and the `random_walk` sample): the same number of rows and
    wins as `n_round_trips` and `n_winning_round_trips`, each row equal to its
    round trip, and start cash plus every row's P/L equal to the end equity.
  - Columns: entry bar (the buy that opened the position), exit bar (the
    sale that completed it), bars held (exit less entry), shares (every share
    bought into the position: 87 for a 45-share buy plus a 42-share buy with
    `position_size=0.5, min_hold=5`), outlay (cash spent on the buys, fees
    included: 991.00 with a fee of 1), proceeds (net cash from the sales, fees
    taken off), P/L (proceeds less outlay), return (P/L divided by the outlay,
    in percent: -90 / 990 = -9.09 %) and reason (why the sale that completed
    it happened: `signal`, `stop`, `target`, `trail`, `atr`, `breakeven`,
    `time` or `drawdown`; with a 10 % stop, `stop`, 4 -> 6, 891.00, -99.00,
    -10.00 %).
  - A `--scale-out` partial sale is inside its round trip's proceeds, not a
    row (`5`: 519.75 + 450.00 = 969.75, P/L -20.25, -2.05 %, and the reason
    is `signal`, the sale that completed it).
  - A position still held at the end is one extra row, marked unrealized:
    no exit bar, bars held counted to the last bar (9 -> 10: 1), and its
    proceeds are any partial sale's net cash plus the shares still held at the
    last close with no selling costs (75 x 12.20 = 915.00, +15.00, +1.67 %;
    with a fee of 1 still 915.00, as `End equity:` counts it). Its reason is
    `scale_out` when part of it has been sold (`scale_out_pct=1`: 79 bought,
    39 sold @ 12.12, 472.68 + 40 x 12.20 = 960.68), otherwise none. It is
    rebuilt from the fills after the last round trip's exit bar; if they do
    not add up to the shares held, `trade_list` raises ValueError.
  - A sale the fees refuse completes nothing: with a fee of 495 the bar 7
    sale is refused and the position stays open (45 shares, 990.00, 549.00,
    -441.00); with `max_hold=3` as well the time exit is refused on bar 7 too
    and goes through on bar 8, for 0.00 (-990.00, -100.00 %).
  - The table: a title line, a header, one line per row (the open row's `#`
    and exit say `open`, its reason `-` when it has none, and it ends
    `(unrealized: marked at the last close, no selling costs)`), and a footer
    that repeats the `Round trips:` numbers, plus `, 1 open (unrealized)`
    when there is an open row (`1 completed, 0 made money (0%), 1 open
    (unrealized)`; `0 completed, 1 open (unrealized)`). No trades: the one
    line `Trade list: no trades`.
- **`--trade-list` on the command line**, a switch. It prints the table after
  the report: after the `Exported:` line and the "Risk and return" block when
  `--export` and `--stats` are given, before `--chart`. The reason column is
  shown even when no exit option is on. It needs `--backtest`
  (`--trade-list only makes sense together with --backtest`, exit 2) and
  cannot be combined with `--scan` (`--trade-list cannot be combined with
  --scan`, exit 2). It needs no candle file, so it works on a close-only file
  and with `--resample`. `--help` lists it after `--stats` (the usage line
  does not). See [docs/cli.md](docs/cli.md#trade-list).
- **`--json` with `--trade-list`**: the backtest object gets `trade_list`, the
  last key (after `stats` and `export`): one object per row with `open`,
  `entry_bar`, `exit_bar` (`null` for the open row), `bars_held`, `shares`,
  `outlay`, `proceeds`, `pnl`, `return_pct` and `reason` (`null` where the
  table shows `-`); `[]` with no trades. `round_trips` and
  `winning_round_trips` do not change. Numbers are unrounded (the open row of
  `--scale-out 5` has `proceeds` `988.1999999999999`). Over 14 backtest
  commands (56 rows) every object, formatted as the table formats it, equals
  its text row, and the rest of the object equals the JSON without the
  option. `cli.trade_list_data(result)` builds the array (for `--json` and the
  API), with the keys in `cli.TRADE_LIST_KEYS`; `cli.report_data` takes a new
  last parameter, `trade_list=False`.
- **Config key `trade_list`** in `[cli]`, a yes/no switch read like `stats`:
  `yes`, `true`, `on` or `1` (any case) turns it on; `no`, `false`, `off` or
  `0` leaves it as the command line has it, so `--trade-list` wins over
  `trade_list = no` (the table is printed). Any other value, or none, is the
  config error `Error: FILE line N: trade_list needs yes or no, got 'maybe'`
  (exit 1), also without `--backtest` and with `--scan`, where a valid value
  is ignored. From a file, `c.csv` gives byte for byte the flag's text and
  `--json`.
- **`POST /api/backtest` takes `trade_list`**, read exactly like `atr_stop`
  (the API has no `stats` field; `atr_stop` is its only other switch): JSON
  `true` turns it on; `false`, `null`, `""` or no key leave it off; any
  string (`"true"`, `"yes"`), any number (`1`, `0`, `1.5`), a list or an
  object is a 400 (`trade_list must be true or false, got 'yes'`, `..., got
  1`, or without `got` for a list or object). It needs no candle data, so it
  works on a close-only CSV. It is echoed in `params` only when sent (`true`
  or `false`), right after `scale_out` (or where it would be). With `true`
  the `report` ends with the command's table (the `report` is still the
  command line's text line for line) and the reply ends with `trade_list`,
  the `--json` array; `summary.round_trips` and `winning_round_trips` do not
  change. On `c.csv` and on a close-only CSV the rows equal `--json`'s.
- **Web page: a "Trade list" box** right after the "ATR stop" box, with a
  hint. Ticked, the page sends `"trade_list": true` (right after
  `max_drawdown`, or where it would be); unticked, exactly the old request
  (the old and new script, given the same six sets of inputs, sent byte for
  byte the same requests and showed the same reports). It needs no candle
  data: never greyed out or unticked, and the close-only hint does not name
  it. When the reply has `trade_list`, a **Trade list** panel after the
  Trades table shows it with the text table's columns and cells and its
  footer; the open row reads `open` and ends with the unrealized note; with
  no trades it says "No trades.". The numbers are formatted the way Python
  formats them in the text report: an exact half goes to the even digit
  (an outlay of 990.125 shows 990.12, as in the text, where `toFixed` would
  show 990.13; checked on 105 values against Python). Without `trade_list`
  in the reply the panel stays hidden, also after a run that showed it. A
  rejected request shows the server's message in the error box.
- **Tests**: `test_trade_list.py` (137), `test_cli_trade_list.py` (65),
  `test_config_trade_list.py` (9), `test_web_trade_list.py` (8) and
  `test_web_trade_list_page.py` (9), 228 tests, with
  `tests/data/cli_before_trade_list.json` (37 commands: 28 that must not
  change and 9 that were rejected before and now mean `--trade-list`; the
  `--help` text and
  what every option name and abbreviation resolved to, recorded from 0.16.0;
  79,511 bytes).

### Existing results do not change

Every run without the trade list gives exactly the same result, report,
`--json` object and `--export` file as in 0.16.0, from the command line, from
a config file and from `POST /api/backtest`, and the web page with the box
unticked sends exactly the request it sent before. This was compared with
0.16.0's code: 112 engine runs (`c.csv` and 300 bars of the `random_walk`
sample, every strategy, eight mixes of costs, sizing, fills and every exit
option; the whole result, report, statistics and export rows), 27 commands
(text, `--json`, `--export`, `--stats`, `--chart`, `--resample`, `--scan`,
`--report`, short option names, usage errors, `--help`; stdout, stderr,
exit code and files), 24 config runs (6 files, each with `--backtest`,
`--json`, no `--backtest` and `--scan`), every option name and abbreviation
of both parsers, 24 HTTP requests (12 to `/api/backtest`, including 400s and
`trade_list` as `null` and `""`; two each to `/api/scan`, `/api/walkforward`
and `/api/portfolio`, one of each with `trade_list`; and 6 `GET`s; byte for
byte) and the page script in Node. The only differences were the runs that
use the new option and the ones listed here:

- `--help` lists `--trade-list` with its description after `--stats` (11
  lines added, none changed). The usage line is unchanged.
- Abbreviations: `--trad` to `--trade-lis` now mean `--trade-list` (before
  they were `unrecognized arguments`, exit 2). `--tr` and `--tra`, which
  meant `--trailing-stop` and would now be ambiguous, still mean it through
  new hidden exact aliases (like `--b`, `--t` and `--sc`); their errors still
  name `--trailing-stop`. Of the names and abbreviations per parser (228
  before, 235 now), every one that set an option sets the same one, and the
  12 ambiguous ones give the same messages.
- The config error for an unknown `[cli]` key lists the new key after
  `stats`: `... strategy, stats, trade_list, top, min_score`. A file with a
  `trade_list` key was this error before; it is now read.
- `POST /api/backtest` used to ignore a `trade_list` key; a request that
  already sent `"trade_list": true` now gets the trade list, and one that sent
  `"yes"` or `1` now gets a 400. A request without it (or with `null` or
  `""`) gets byte for byte the reply it got before; with `false` only
  `params` differs (the echo). `/api/scan`, `/api/walkforward` and
  `/api/portfolio` still ignore it (byte for byte the same replies).
- Web page: `GET /` differs by the new box (7 lines) and the hidden Trade
  list panel (17 lines); `GET /app.js` by the box's 3-line send block and
  the panel's 46-line block (nothing removed). `GET /style.css`,
  `/api/samples` and `/api/health` are unchanged. The close-only hint and
  the list of candle-only controls do not change. The new box sits after the
  ATR stop box, so Cooldown and every field after it move one place along the
  form's grid.
- Library: new `backtest.trade_list`, `backtest.format_trade_list`,
  `cli.trade_list_data` and `cli.TRADE_LIST_KEYS`; `cli.report_data` has a
  new last parameter `trade_list` (default False); `build_parser()` has three
  new option strings, `--trade-list` and the hidden `--tr` and `--tra`;
  `config._BOOL_KEYS` gains `trade_list`; `web.server.LATER_SETTINGS` gains
  `"trade_list"` at the end, after `"scale_out"` (it orders the echo in
  `params`), and the dict `_parse_later_settings` returns has a
  `trade_list` entry (False when not sent).
- Existing tests changed (with the reasons): the four `--help` tests that pin
  the option list or the old help text (`test_cli_atr_stop.py`,
  `test_cli_cooldown_unchanged.py`, `test_cli_risk_sizing.py`,
  `test_cli_scale_out.py`) now also expect or cut out the `--trade-list`
  block; seven lines in five config tests that pin the unknown-key message
  (`test_config_atr_stop.py`, `test_config_backtest_keys.py`,
  `test_config_risk_sizing.py` three lines, `test_config_trailing_stop.py`,
  `test_scan.py`) gain `trade_list, `; the three page tests that hash the
  page as it was (`test_web_atr_stop_page.py`,
  `test_web_risk_sizing_page.py`, `test_web_trailing_stop_page.py`) undo the
  new box and panel before hashing (the same five lines each). No other test
  changed.
- The version is 0.17.0 (`pyproject.toml`; the installed package reports
  0.17.0 after `scripts/setup_dev.sh`).

### Not checked

- The page was run in Node with a stand-in for the browser, never in a real
  browser: the layout of the box and the panel, the fields after the box
  that moved one place, narrow screens, keyboard order, screen readers and
  the dark theme are unchecked. Where the box lands on the grid was worked out
  from the CSS only.
- On the page the box was ticked with a pasted `c.csv` (no other option,
  scale-out 5, stop loss 10, a fee of 0.125, cash 5) and a pasted close-only
  CSV; unticked with `c.csv` and the `uptrend` sample. Not run with the box
  ticked: a built-in sample, an uploaded file, another strategy, and the CSV
  download of such a run. A bad reply was checked with a bad window, since
  the page only ever sends `true`.
- `--help` was checked at 80 columns only.
- Only Python 3.12 was run.

### Not covered yet

- The sweep, the walk-forward test, the portfolio command, the Monte Carlo
  tool and the drawdowns tool do not take it: `--trade-list` there is
  `unrecognized arguments` (exit 2). `/api/scan`, `/api/walkforward` and
  `/api/portfolio` ignore a `trade_list` key.
- `--export` has no trade list file, and the trade list has no dates (bars
  only).
- `tests/test_paths_agree.py` does not include the trade list; the tests
  above compare each path instead.

## 0.16.0 (2026-11-15)

### Added

- **Scale-out in the engine** (`backtest.run_backtest(...,
  scale_out_pct=PCT)`, above 0, default None = off; needs highs and lows).
  Once per position, half the shares held are sold when a bar's high reaches
  the entry price plus `PCT` %, and the rest stays open. Rules, each checked
  on a small case (most on `c.csv` in
  [docs/cli.md](docs/cli.md#scale-out), with `short=1`, `long=2`, cash 1000:
  BUY 90 @ 11 on bar 4, bar 5's high 12, the strategy's SELL due on bar 7;
  925.00 without it):
  - On a bar after the entry bar whose high reaches the level, half the
    shares held, rounded down, are sold at the level (`5`: 45 @ 11.55 on bar
    5; `9`: 45 @ 11.99), or at the bar's open when it opens at or above it (a
    gap: bar 5 opening at 11.80 sells 45 @ 11.80, 1,007.40; without opens the
    level is used). The fill's reason is `scale_out`. `10` (12.10) is never
    reached: 925.00.
  - Rounded down: 91 shares sell 45. With 1 share nothing is sold and the
    position is not marked, so it can scale out after a later buy (1 share,
    then a second one: the bar after sells 1 @ 13.75).
  - At most once per position: a later buy into the position cannot make it
    scale out again (`--min-hold 5` keeps the bar 7 SELL from firing, the bar
    9 buy adds 44, bar 10's high 12.40 reaches the new level 12.07, no second
    sale; 1,087.55), and the next position can (a bar 10 high of 12.70 sells
    40 @ 12.60 from the bar 9 position).
  - The entry price is the average cost of the shares still held: the
    partial sale does not move it (the 10 % stop stays at 9.90 and sells the
    other 45 on bar 6, 991.45; the 5 % breakeven stop sells them at 11.00,
    1,041.75), and a later buy averages with the shares still held, not with
    the ones sold (100 @ 10, 50 sold, 50 bought @ 12.50: entry 11.25, and a
    20 % stop at 9.00 sells them, where the average of every share bought
    would have put it at 8.67).
  - One fill per bar, and any other fill wins: a target the bar also reaches
    sells everything (`5` with an 8 % target: 90 @ 11.88, 1,097.00); so does a
    signal SELL due on that bar (close fills and open fills), and a signal
    BUY due then fills instead (and moves the level). With close fills it
    comes after the bar's range and the signal fill, and before the time exit
    and the drawdown sale, which then wait for the next bar (`max_hold=1`:
    the time exit sells on bar 6, 995.95; a drawdown halt's sale waits a bar
    the same way). With open fills the signal fill and, when due, a gap
    through a stop or target, the time exit and the drawdown sale at the open
    come first (`max_hold=1`: the time exits at the opens of bars 5 and 10,
    1,131.20).
  - Not a round trip: its proceeds go into the round trip the rest completes
    (`5`: one round trip, 519.75 + 450.00 - 990.00 = -20.25). `max_losses=1`
    halts on the bar that completes the round trip, not on the partial sale
    (`9`: halt on bar 7, 999.55), and judges the whole round trip (`9` with a
    5 % stop: the rest alone lost 24.75 but the round trip made +19.80, no
    halt, 1,036.60).
  - Fees and slippage apply to it (fee 1: round trip -23.25, 991.95;
    slippage 1 %: 971.62). A partial sale the fees refuse is not made, the
    position is not marked, and it is tried again on later bars.
  - It starts no cooldown and `min_hold` does not hold it back.
  On `c.csv`: `5`: 995.95; `9`: 1,016.15; `10`: 925.00; `5` with a 10 % stop:
  991.45. `BacktestResult` records `scale_out_pct`, and
  `n_scale_out_exits` counts the partial sales. `has_exits` is true with it
  (so fills and the export carry a reason); `has_price_exits` is not (there is
  no `Exits:` part for it). The report, only with the option, adds a line
  right after `Exits:` (or where it would be):
  `Scale out:   half the shares held (rounded down), once per position, when a high reaches 5.00% above the average entry; 1 partial sell, not counted as round trips`.
- **`--scale-out PCT` on the command line**: above 0, decimals allowed, no
  upper limit. `--scale-out 0` (or `-1`, `nan`) is
  `--scale-out must be above 0, got 0`; `--scale-out inf` is
  `--scale-out must be a finite number, got inf` (as for `--breakeven`);
  `--scale-out abc` argparse's `argument --scale-out: invalid float value:
  'abc'`; without `--backtest` `--scale-out only makes sense together with
  --backtest`; with `--resample` `--scale-out cannot be combined with
  --resample yet`; with `--scan` (or `--sc`) `--scale-out cannot be combined
  with --scan` (all exit 2). It reads the file as a candle file (a close-only
  file is exit 1) and needs no other exit option. `--help` lists it after
  `--max-losses` (the usage line does not). `--scal` to `--scale-ou` are
  short for it. See [docs/cli.md](docs/cli.md#scale-out).
- **`--json` with `--scale-out`**: the backtest object gets `scale_out_pct`
  right after `breakeven_pct` (or the exit setting before it) and
  `scale_out_exits` (the number of partial sales) right after
  `breakeven_exits` (or `risk_skipped_buys`, or `sells`), before the cooldown
  keys. Both are there only with the option. The four `c.csv` cases give the
  same numbers as the text report.
- **`--export` with `--scale-out`** gets the `reason` column, with
  `scale_out` on the partial sales; `position` shows the shares left. The
  file is the same with or without `--json`.
- **Config key `scale_out`** (a number) in `[cli]`, with the flag's rules,
  read like `breakeven`: `scale_out = 0` (or `-1`) is the usage error
  `--scale-out must be above 0, got 0` (exit 2); `scale_out = abc`, `5%`,
  `1,6`, `true` or an empty value is the config error
  `Error: FILE line N: scale_out needs a number, got 'abc'`, and `nan`, `inf`
  or `-inf` `... needs a finite number, got 'inf'` (exit 1). It reads the
  price file as a candle file and cannot be combined with `--resample`.
  `--scale-out` on the command line wins and the file's value is then not
  used at all (`scale_out = 5` with `--scale-out 9` runs with 9, as do `0`,
  `-3` and `2.5`). Without `--backtest`, and with `--scan`, it is ignored,
  even `0`; a value that is not a finite number is still the config error
  there. It is not a stop: a config `cooldown` is not used with it alone. The
  four `c.csv` cases from a config file are byte-identical to the flag runs,
  in text and with `--json`.
- **`POST /api/backtest` takes `scale_out`**, read exactly like `breakeven`
  (24 values sent to both behave the same): `5`, `5.0`, `"5"`, `" 5 "` or
  `"5.0"` is 5; `null`, `""` or no key leave it off; `true`, `false`,
  `"abc"`, a list or an object is a 400 (`scale_out must be a number...`);
  `NaN`, `Infinity`, `-Infinity`, `"nan"` or `"inf"` is a 400 (`scale_out
  must be a finite number`); `0`, `-1`, `"0"` or `"-0.5"` is a 400 with the
  command's `--scale-out must be above 0, got 0`; `"1,5"` is 15, as for every
  number field. It needs candle data (a close-only CSV is the candle
  reader's 400; a sample uses its candles) and is not a stop (`cooldown` with
  it alone is the usual 400). It is echoed in `params` only when sent, right
  after `max_losses`; with it, `summary` has `scale_out_pct` and
  `scale_out_exits` right after the breakeven keys, trades carry a `reason`,
  the columns end with `reason`, and the `report` is the command line's
  report line for line. The four `c.csv` cases give the command's `--json`
  numbers.
- **Web page: a "Scale out (%)" field** after "Breakeven (%)", with a hint.
  Sent as `scale_out` (right after `breakeven`) only when filled in. Like
  the stops it needs candle data: greyed out and blanked for a close-only
  CSV, and the close-only hint ends with the new sentence "The scale-out
  needs them too.". With the option the **Trades** card adds
  `, N partial sells by scale-out` right after the breakeven count
  (`2 buys, 2 sells, 1 partial sells by scale-out`; with a breakeven stop,
  `2 buys, 2 sells, 1 sold at breakeven, 1 partial sells by scale-out`;
  `0 partial sells by scale-out` when it never sold). A bad value shows the
  server's message in the error box.
- **Library**: `cli.summarise(..., scale_out_pct=None)`,
  `BacktestResult.scale_out_pct`, `BacktestResult.n_scale_out_exits`.
- **Tests**: `test_scale_out.py` (91), `test_cli_scale_out.py` (71),
  `test_cli_scale_out_json.py` (18), `test_config_scale_out.py` (66),
  `test_web_scale_out.py` (5) and `test_web_scale_out_page.py` (5), 256
  tests, with `tests/data/before_scale_out.json` (the 0.15.0 engine output of
  26 runs on `c.csv` and the `random_walk` sample, 45,840 bytes) and
  `tests/data/cli_before_scale_out.json` (26 0.15.0 commands, plus the
  three outputs that change on purpose).

### Existing results do not change

Every run without the scale-out gives exactly the same result, report,
`--json` object and `--export` file as in 0.15.0, from the command line, from
a config file and from `POST /api/backtest`, and the web page with the field
empty sends exactly the request it sent before. This was compared with
0.15.0's code: 378 engine runs (three price series, every strategy, both
fills, nine mixes of costs, position size, stop, target, trailing stop, ATR
stop, risk sizing, breakeven stop, cooldown, minimum and maximum holding
times, drawdown halt and losing-streak halt; 19,660 fills; fills, daily rows,
round trips, report, statistics, export and skip counts, floats exactly), 33
commands (text, `--json`, `--export`, `--stats`, `--chart`, `--resample`,
stops, short option names, `--scan`, `--report`, usage errors, `--help`;
stdout, stderr, exit code and export and report files), the `--help` and a
`--scale-out` run of the seven other tools, every option name and
abbreviation of both parsers (224 each), 54 config runs (9 files, each with
text, `--json`, no `--backtest`, `--scan`, a flag and a close-only file) and
28 HTTP requests (16 to `/api/backtest`, including 400s, an unknown key and
`scale_out` as `null` and `""`; two each to `/api/scan`, `/api/walkforward`
and `/api/portfolio`, one of each with `scale_out`; and 6 `GET`s; byte for
byte). The only differences were the runs that use the new option and the
ones listed here:

- `--help` lists `--scale-out PCT` with its description after `--max-losses`
  (14 lines added, none changed). The usage line is unchanged.
- Abbreviations: `--scal` to `--scale-ou` now mean `--scale-out` (before they
  were `unrecognized arguments`, exit 2). `--sc` and `--sca`, which meant
  `--scan` and would now be ambiguous, still mean `--scan` through new hidden
  exact aliases (like `--b`, `--m` and `--co`); their errors still name
  `--scan`, and the ten `--scan` commands tried give byte for byte the old
  output. Of the 224 option names and abbreviations per parser, the 190 that
  set an option set the same one, and the 28 that were ambiguous are still
  errors. One of those messages changes:
  `ambiguous option: --s could match --short, --slippage, --stop-loss, --strategy, --stats, --scan`
  is now
  `ambiguous option: --s could match --short, --slippage, --stop-loss, --scale-out, --strategy, --stats, --scan, --sc, --sca`
  (argparse lists the hidden aliases too, as it lists `--co` for `--c`).
- The config error for an unknown `[cli]` key lists the new key after
  `max_losses`: `... breakeven, max_losses, scale_out, fill, ...` (the only
  difference among the config runs without the key). A file with a
  `scale_out` key was this error before; it is now read.
- `POST /api/backtest` used to ignore a `scale_out` key (even `0`); a
  request that already sent one now gets the scale-out, or a 400 for a bad
  value. A request without it (or with `null` or `""`) gets byte for byte the
  reply it got before. `/api/scan`, `/api/walkforward` and `/api/portfolio`
  still ignore it (byte for byte the same replies).
- Web page: `GET /` differs by the new field (5 lines) and the close-only
  hint, which gains the sentence "The scale-out needs them too." at its end
  (its first sentence is unchanged). The new field sits after Breakeven, so
  Risk % and every field after it move one place along the form's grid.
  `GET /app.js` differs by `'scale_out'` at the end of the list of candle-only
  controls, the field's 5-line send block and the Trades card line. Unlike
  the Min hold and Max losses fields (0.14.0 and 0.15.0), the close-only hint
  text and the list of candle-only controls do change, because this field
  needs candle data. The **Trades**
  card of a reply without the new keys, the request of an empty field,
  `GET /style.css`, `/api/samples` and `/api/health` are unchanged.
- Library: `BacktestResult` has a new last field, `scale_out_pct` (default
  None), after `loss_skipped_buys`, so `repr()` and `dataclasses.asdict()`
  of every result now include it at the end; the 36 fields before it keep
  their order. `BacktestResult.has_exits` is also true with it.
  `run_backtest` and `cli.summarise` take `scale_out_pct` as a new last
  parameter. `RoundTrip.proceeds` now includes a partial sale's proceeds
  (the same value when there is none). `Trade.reason` can be `scale_out`.
  The engine keeps each position's average entry price as it is bought
  instead of working it out from everything bought; the floats are the same
  in all 378 runs above. `web.server.LATER_SETTINGS` gains `"scale_out"` at
  the end, after `"max_losses"` (it orders the echo in `params`, which has
  `scale_out` only when it is sent). `build_parser()` has three new option
  strings, `--scale-out` and the hidden `--sc` and `--sca`.
- The version is 0.16.0 (`pyproject.toml`; the installed package reports
  0.16.0 after `scripts/setup_dev.sh`).

### Not checked

- The page was run in Node with a stand-in for the browser, never in a real
  browser: the layout of the new field and its hint, the fields after it
  that moved one place, the longer close-only hint, keyboard order, screen
  readers and the dark theme are unchecked. Browsers normally read text that
  is not a number in a number field as empty, so typing `ten` or `inf` there
  would probably send nothing and run without the option, with no error; the
  stand-in sends the text and shows the server's message (tested). The form
  has `novalidate`, so `0` and `-1` reach the server and its message is shown
  (tested in Node).
- On the page, runs with a value were made with a pasted `c.csv` (5, 9, 10,
  5 with a stop loss, 5 with a breakeven stop, and the bad values 0, -1,
  `ten`, `inf`) and a pasted close-only CSV; an empty field with `c.csv` and
  the `uptrend` sample. Not run on the page with a value: a built-in sample,
  an uploaded file, open fills, and the charts, trades table, "Risk and
  return" table and CSV download of a run with partial sales. Those all show
  what the server returns, which the API tests cover (the `random_walk`
  sample with `scale_out` was run through the API: 4 partial sales).
- A partial sale the fees refuse was checked only on a made-up series (prices
  near 1 with a fee of 10), not through the command line.
- The three paths read a value differently at one edge, as for `breakeven`:
  `nan` is exit 2 from the flag and exit 1 from a config file; `1,6` is an
  error from the flag and a config file, and 16 from the API, which drops
  commas in number strings.

### Not covered yet

- The sweep, the walk-forward test, the portfolio command, the Monte Carlo
  tool and the drawdowns tool do not take it: `--scale-out` there is
  `unrecognized arguments` (exit 2), and none of them passes it to the
  engine. The buy-and-hold comparison has none.
- `tests/test_paths_agree.py` does not include the scale-out; the tests
  above compare each path instead.
- It always sells half, once per position, at one level: there is no choice
  of the fraction and no second level.
- There is no value that switches off a config file's `scale_out` for one
  run (`--scale-out 0` is out of range); a large `--scale-out` never sells,
  but the report still shows its line.
- The report and `--json` count partial sales but do not show them per round
  trip; the statistics (profit factor, average win and loss) see one round
  trip with all its sales.
- The page shows the setting only through the **Trades** card's count and
  the report's `Scale out:` line; there is no card with the setting itself,
  and the **Exits** card does not list it. The count reads `1 partial sells`
  (no singular, like the card's `1 buys` and `1 sells`); the report line
  says `1 partial sell`.

### Changed tests

- `test_cli_atr_stop.py::test_help_only_changes_the_atr_options`: the list of
  `--help` entries gains `--scale-out` after `--max-losses` (one line).
- `test_cli_max_losses.py::test_help_lists_it_after_breakeven_but_the_usage_line_does_not`:
  the entry after `--max-losses` in `--help` is now `--scale-out`, not
  `--export` (one line).
- `test_config_atr_stop.py` (`NEW_KEY_LIST`),
  `test_config_backtest_keys.py::test_unknown_key_message_lists_the_new_keys`,
  `test_config_risk_sizing.py` (`NEW_KEY_LIST` and the two unknown-key runs in
  `OLD_RUNS`) and
  `test_config_trailing_stop.py::test_unknown_key_message_now_lists_trailing_stop`:
  the expected unknown-key list gains `scale_out` after `max_losses` (one
  line each).
- The pinned list of candle-only controls gains `'scale_out'` at the end (one
  line each) in `test_web_atr_stop_page.py`,
  `test_web_cooldown_page.py`, `test_web_max_drawdown_page.py`,
  `test_web_max_hold_page.py`, `test_web_min_hold_page.py`,
  `test_web_risk_sizing_page.py` and `test_web_trailing_stop_page.py` (in
  `test_web_atr_stop_page.py` on the assert line, which now adds it to the
  unchanged `NEW_CONTROLS`).
- `test_web_atr_stop_page.py`: `SKIPPED_JS` (the Trades card code) gains the
  scale-out line, and `test_nothing_else_changed_since_before_the_checkbox`
  also removes the Scale out field, the hint sentence, its send block and
  `'scale_out'` from the list before hashing (and then makes the list swap
  the new entry had kept from matching).
  `test_web_risk_sizing_page.py::test_nothing_else_changed_since_before_these_controls`
  and `test_web_trailing_stop_page.py::test_nothing_else_on_the_page_changed`
  also undo the field, the hint sentence, the send block, the Trades card
  line and the list entry. The three pinned hashes are unchanged.

## 0.15.0 (2026-11-15)

### Added

- **Losing-streak halt in the engine** (`backtest.run_backtest(...,
  max_losses=N)`, a whole number, default 0 = off; needs only the closes).
  After `N` losing round trips in a row no buy can fill for the rest of the
  run. Rules, each checked on a small case (most on `losses.csv` in
  [docs/cli.md](docs/cli.md#max-losses), closes 10, 9, 8, 9, 11, 12, 10, 9,
  8, 9, 10, 11, 10, 9, 10, 12, 13, with `short=1`, `long=2`, cash 1000:
  BUY 90 @ 11 on bar 4, SELL @ 9 on bar 7 (-180.00), BUY 82 @ 10 on bar 10,
  SELL @ 9 on bar 13 (-82.00), BUY 61 @ 12 on bar 15, 799.00):
  - A round trip loses when its profit after costs is below 0. Every
    completed round trip counts, whatever sold it: the strategy, a stop
    (`c.csv`, 10 % stop on bar 6, -99.00, with close and with open fills), a
    target (`take_profit_pct=5` with a 60 fee: -73.25), a time exit
    (`max_hold=2`: -90.00 on bar 6) or a drawdown sale (SMA 1/3 on closes 10,
    10, 10, 10, 11, 20, 19, 18.5, 15, 14, 16, 16, 17 with
    `max_drawdown_limit_pct=5`: -75.00 on bar 7).
  - Any other round trip resets the streak: a win (loss, win, loss, loss with
    `N=2` halts on the fourth sale, bar 15, not the third), and also one at
    exactly 0.00 (loss, 0.00, loss with `N=2` never halts). Costs count: the
    same 0.00 round trip with a 1.00 fee loses 2.00 and halts on bar 9.
  - A sale the fees refuse completes no round trip and does not count (fee
    495: the 45 shares are kept, no halt, 595.00).
  - When the streak reaches `N` with a sale on bar `h`, every buy due from
    bar `h + 1` on is dropped and counted in `loss_skipped_buys`, even one
    that would have got 0 shares; `breakout` (`window=1`) is counted on every
    bar it signals (5). A BUY signal on the last bar is not counted. A buy the
    drawdown halt also blocks is counted in `drawdown_skipped_buys` only; one
    that also falls in a cooldown, or that risk sizing would have given 0
    shares, is counted here only.
  - Every sale closes the whole position, so nothing is held when the halt
    starts and nothing is sold because of it.
  On `losses.csv`: `N=1` halts on bar 7, 2 skipped, 820.00; `N=2` on bar 13,
  1 skipped, 738.00; `N=3` never halts, 799.00. `BacktestResult` records
  `max_losses`, `loss_halt_bar` (None if it never triggered) and
  `loss_skipped_buys`. It makes no fills of its own, so `has_exits` and
  `has_price_exits` are unchanged by it and the fills and the export get no
  reason because of it. The report, only with the option, adds a line right
  before `Round trips:` (after `Drawdown:`):
  `Max losses:  halt after 2 losing round trips in a row; triggered at bar 13, no buy fills after it; 1 buy skipped`.
- **`--max-losses N` on the command line**: a whole number of at least 1.
  `--max-losses 0` (or `-2`) is `--max-losses must be a whole number of at
  least 1, got 0`; `--max-losses 2.5`, `2.0` or `two` argparse's
  `argument --max-losses: invalid int value: '2.5'`; without `--backtest`
  `--max-losses only makes sense together with --backtest`; with `--scan`
  `--max-losses cannot be combined with --scan` (all exit 2). It needs no stop
  and no candle file: a close-only file works, and so does `--resample`.
  `--help` lists it after `--breakeven` (the usage line does not). `--max-l`
  to `--max-losse` are short for it. See
  [docs/cli.md](docs/cli.md#max-losses).
- **`--json` with `--max-losses`**: the backtest object gets `max_losses`
  right after `max_drawdown_limit_pct` (or where that key would be), and
  `loss_halt_bar` (`null` when it never triggered) and `loss_skipped_buys`
  right after `drawdown_skipped_buys` (or where that key would be), just
  before `fills`. All three are there only with the option. The three
  `losses.csv` cases give the same numbers as the text report.
- **`--export` with `--max-losses`** is unaffected: the same columns, one row
  per bar, and a bar whose buy was skipped is a row without an action.
- **Config key `max_losses`** (a whole number) in `[cli]`, with the flag's
  rules, read like `max_hold`: `max_losses = 0` (or `-1`) is the usage error
  `--max-losses must be a whole number of at least 1, got 0` (exit 2);
  `max_losses = 2.5`, `2.0`, `abc` or `true` is the config error
  `Error: FILE line N: max_losses needs a whole number, got '2.5'` (exit 1).
  `--max-losses` on the command line wins and the file's value is then not
  used at all (`max_losses = 1` with `--max-losses 2` runs with 2,
  `max_losses = 2` with `--max-losses 1` with 1, `max_losses = 0` with
  `--max-losses 2` with 2). Without `--backtest`, and with `--scan`, it is
  ignored, even `0`; a value that is not a whole number is still the config
  error there. The three `losses.csv` cases from a config file are
  byte-identical to the flag runs, in text and with `--json`.
- **`POST /api/backtest` takes `max_losses`**, read exactly like `max_hold`
  and `min_hold` (16 values sent to all three behave the same): `2`, `2.0`,
  `"2"` or `" 2 "` is 2; `null`, `""` or no key leave it off; `true`,
  `false`, `2.5`, `"2.0"`, `"abc"`, a list or an object is a 400
  (`max_losses must be a whole number...`); `0`, `-1` or `"0"` is a 400 with
  the command's `--max-losses must be a whole number of at least 1, got 0`.
  It needs no candle data, so a close-only CSV works. It is echoed in
  `params` only when sent, right after `breakeven`; with it, `summary` has
  `max_losses`, `loss_halt_bar` and `loss_skipped_buys` right before
  `round_trips` (after the drawdown keys), and the `report` is the command
  line's report line for line. Trades get no `reason` and the columns do not
  change because of it. The three `losses.csv` cases give the command's
  `--json` numbers.
- **Web page: a "Max losses" field** after "Cooldown (bars)", before "Min
  hold (bars)", with a hint. Sent as `max_losses` (right after `min_hold`)
  only when filled in. It needs no candle data: never greyed out or blanked,
  also for a close-only CSV, and the close-only hint does not name it. With
  the option the **Trades** card adds `, N buys skipped by losing streak`
  last (`1 buys, 1 sells, 2 buys skipped by losing streak`; `3 buys, 2
  sells, 0 buys skipped by losing streak` when nothing was skipped). A bad
  value shows the server's message in the error box.
- **Library**: `cli.check_max_losses`, `cli.summarise(..., max_losses=0)`,
  `BacktestResult.max_losses`, `BacktestResult.loss_halt_bar`,
  `BacktestResult.loss_skipped_buys`.
- **Tests**: `test_max_losses.py` (38), `test_cli_max_losses.py` (35),
  `test_config_max_losses.py` (30), `test_web_max_losses.py` (23) and
  `test_web_max_losses_page.py` (7), 133 tests, with
  `tests/data/c_before_max_losses.json` (the 0.14.0 engine output of nine
  runs), `tests/data/cli_before_max_losses.json` (nine 0.14.0 commands) and
  `tests/data/config_before_max_losses.json` (eight 0.14.0 config runs).

### Existing results do not change

Every run without the losing-streak halt gives exactly the same result,
report, `--json` object and `--export` file as in 0.14.0, from the command
line, from a config file and from `POST /api/backtest`, and the web page with
the field empty sends exactly the request it sent before. This was compared
with 0.14.0's code: 252 engine runs (two samples, every strategy, both fills,
nine mixes of costs, position size, stop, target, trailing stop, ATR stop,
risk sizing, breakeven stop, cooldown, minimum and maximum holding times and
drawdown halt; 6,023 fills; fills, daily rows, round trips, report,
statistics, export and skip counts), 31 commands (text, `--json`, `--export`,
`--stats`, `--chart`, `--resample`, stops, short option names, `--scan`,
usage errors, `--help`; stdout, stderr, exit code and export files), 30
config runs (6 files, each with text, `--json`, no `--backtest`, `--scan` and
a flag) and 21 API requests (12 to `/api/backtest`, including 400s and an
unknown key, one each to `/api/scan`, `/api/walkforward` and
`/api/portfolio`, and 6 `GET`s; byte for byte). The only differences were the
commands that use the new option and the ones listed here:

- `--help` lists `--max-losses N` with its description after `--breakeven`
  (9 lines added, none changed). The usage line is unchanged.
- Abbreviations: `--max-l` to `--max-losse` now mean `--max-losses` (before
  they were `unrecognized arguments`). `--ma`, `--max`, `--max-` and
  `--max-h` still mean `--max-hold` and `--max-d` still `--max-drawdown`.
  Every option name and abbreviation argparse took in 0.14.0 (204 in the
  main parser and 204 in the `--scan` parser) still sets the same option,
  and none of the 12 that were ambiguous is a prefix of `--max-losses`.
- The config error for an unknown `[cli]` key lists the new key after
  `breakeven`: `... max_drawdown, breakeven, max_losses, fill, ...` (the only
  difference among the 30 config runs). A file with a `max_losses` key was
  this error before; it is now read.
- `POST /api/backtest` used to ignore a `max_losses` key (even `0`); a
  request that already sent one now gets the losing-streak halt, or a 400 for
  a bad value. A request without it (or with `null` or `""`) gets byte for
  byte the reply it got before. `/api/scan`, `/api/walkforward` and
  `/api/portfolio` still ignore it.
- Web page, with the field empty: the new field and its hint sit after the
  Cooldown field, so the Min hold, Max hold and Max drawdown fields and the
  close-only hint each move one place along the form's grid (`GET /` and
  `GET /app.js` differ only by the field, its send block and the Trades card
  line). The close-only hint text, the script's list of candle-only controls,
  the **Trades** card of a reply without the new keys and the stylesheet are
  unchanged.
- Library: `BacktestResult` has three new last fields, `max_losses` (default
  0), `loss_halt_bar` (default None) and `loss_skipped_buys` (default 0),
  after `min_hold_skipped_sells`, so `repr()` and `dataclasses.asdict()` of
  every result now include them at the end; the 33 fields before them keep
  their order. `run_backtest` and `cli.summarise` take `max_losses` as a new
  last parameter. `web.server.LATER_SETTINGS` gains `"max_losses"` at the end,
  after `"breakeven"` (it orders the echo in `params`, which has `max_losses`
  only when it is sent).
- The version is 0.15.0 (`pyproject.toml`; the installed package reports
  0.15.0 after `scripts/setup_dev.sh`).

### Not checked

- The page was run in Node with a stand-in for the browser, never in a real
  browser: the layout of the new field and its hint, the shifted fields after
  it, keyboard order, screen readers and the dark theme are unchecked.
  Browsers normally read text that is not a number in a number field as
  empty, so typing `abc` there would probably send nothing and run without
  the option, with no error (as for Min hold and Max hold); that was not
  tried. The form has `novalidate`, so `0` and `2.5` reach the server and its
  message is shown (tested in Node).
- On the page only a pasted close-only CSV was run with a value (1, 2, 3, 0
  and 2.5), plus two empty-field runs (the close-only CSV and a sample). Not
  run on the page with a value: a built-in sample, a candle CSV, other fields
  at the same time (for example the **Trades** card with both the drawdown
  and the losing-streak counts), open fills, and the charts, trades table,
  "Risk and return" table and CSV download of a halted run. Those all show
  what the server returns, which the API tests cover.
- The three paths read a value differently at one edge, as for `max_hold`
  and `min_hold`: `2.0` is exit 2 from the flag and exit 1 from a config
  file, while the API takes the JSON number `2.0` as 2 (and refuses the
  string `"2.0"`). All three take Python's `+2` and `1_6` (16). Unlike its
  number fields, the API does not drop commas here: `"1,6"` is a 400.

### Not covered yet

- The sweep, the walk-forward test, the portfolio command, the Monte Carlo
  tool and the drawdowns tool do not take it: `--max-losses` there is
  `unrecognized arguments` (exit 2), and none of them passes it to the
  engine. The buy-and-hold comparison has none.
- `tests/test_paths_agree.py` does not include the losing-streak halt; the
  tests above compare each path instead.
- There is no value that switches off a config file's `max_losses` for one
  run; a large `--max-losses` never triggers, but the report still shows its
  line.
- The page shows the setting only through the **Trades** card's count and
  the report's `Max losses:` line; there is no card with the setting itself.
  That count reads `1 buys skipped` (no singular, like the card's `1 buys`
  and `1 sells`); the report line says `1 buy skipped`.

### Changed tests

- `test_cli_atr_stop.py::test_help_only_changes_the_atr_options`: the list of
  `--help` entries gains `--max-losses` after `--breakeven` (one line).
- `test_config_atr_stop.py` (`NEW_KEY_LIST`),
  `test_config_backtest_keys.py::test_unknown_key_message_lists_the_new_keys`,
  `test_config_risk_sizing.py` (`NEW_KEY_LIST` and the two unknown-key runs in
  `OLD_RUNS`) and
  `test_config_trailing_stop.py::test_unknown_key_message_now_lists_trailing_stop`:
  the expected unknown-key list gains `max_losses` after `breakeven` (one
  line each).
- `test_web_atr_stop_page.py`: `SKIPPED_JS` (the Trades card code) gains the
  losing-streak line, and `test_nothing_else_changed_since_before_the_checkbox`
  also removes the Max losses field and its send block before hashing.
  `test_web_risk_sizing_page.py::test_nothing_else_changed_since_before_these_controls`
  and `test_web_trailing_stop_page.py::test_nothing_else_on_the_page_changed`
  also undo the field, its send block and the Trades card line. The three
  pinned hashes are unchanged.

## 0.14.0 (2026-11-14)

### Added

- **Minimum holding time in the engine** (`backtest.run_backtest(...,
  min_hold=N)`, a whole number, default 0 = off; needs only the closes). A
  signal sell due before the position has been held `N` bars is skipped.
  Rules, each checked on a small case (most on `closes.csv`, the closes of
  `candles11.csv` in [docs/cli.md](docs/cli.md#min-hold), with `short=1`,
  `long=2`, cash 1000: BUY 90 @ 11 on bar 4, the strategy's SELL due on bar
  7):
  - The clock is the one `max_hold` uses: it starts on the bar `e` of the buy
    that opened the position, and a later buy into the position does not
    restart it. A signal sell due on bar `t` is skipped when `t - e < N`.
    (`breakout` with `window=1` and `position_size=0.5` buys on bars 4 and 5;
    with `N=3` its bar 7 sell fills, 3 bars after the first buy, where
    counting from bar 5 would have skipped it.)
  - A skipped sell is dropped, not delayed: it is not tried again when the
    window ends. The SMA crossover, which signals SELL only on the bar of the
    crossing, then holds (`N=4`: the 90 shares are held to the end, 1,108.00).
    A strategy that keeps signalling sells on its next SELL due at or after
    `e + N` (on closes 10, 11, 12, 11, 10, 9, 9 with `breakout`, `window=1`,
    the sells due on bars 4, 5 and 6: `N=3` skips the bar 4 one and sells on
    bar 5, `N=4` skips two and sells on bar 6).
  - A sell is counted (`min_hold_skipped_sells`) only when it would otherwise
    have filled: shares are held and nothing sold them earlier on that bar.
    Nothing held (the time exit of `max_hold=2` sold on bar 6): not counted.
    With close fills the bar's range comes first, so a stop that sells during
    the bar the signal sell is due on leaves nothing to count (a 10 % stop
    reached on bar 7: 0 counted, as without the option). With open fills the
    signal comes first at the open, so it is skipped and counted, and then the
    stop sells later in the same bar (1 counted; without the option the signal
    sells at the open, 925.00, with it the stop sells @ 9.90, 916.00).
  - It is counted before the fees are looked at: with a 495 fee the bar 7
    sell would be refused (cash 10 + 450 - 495 is below 0) and is still
    counted.
  - A skipped sell makes no fill, so the bar is still free for the time exit
    and the drawdown sale. After a drawdown halt this changes a fill's
    reason: with `max_drawdown_limit_pct=5` (halt on bar 6) the bar 7 sale is
    `signal`; with `min_hold=6` as well the signal sell is skipped and the
    drawdown sale sells the same 90 shares on bar 7 at the same 10.00, as
    `drawdown` (end equity 910.00 both ways).
  - Every other exit still sells inside the window: on `c.csv` with
    `min_hold=6` (window to bar 9) the stop (bar 6, 10.45), target (bar 5,
    11.55), trailing stop (bar 6, 10.80), ATR stop (bar 6, 9.5625),
    breakeven stop (bar 6, 11.00) and time exit (bar 6, 10.00) give exactly
    the fills they give without it.
  - `N=1` is accepted and skips nothing (a signal sell is never due on the
    bar its position was bought). `N` at or above `max_hold` is allowed; the
    time exit then sells first (`N=4`, `max_hold=2`: time exit on bar 6,
    925.00, 0 counted).
  On `closes.csv`: without it and with `N=1` or `3`, 925.00; with `N=4`, one
  trade, 1 skipped, 1,108.00; with `N=4` and `max_hold=2`, 925.00.
  `BacktestResult` records `min_hold` and `min_hold_skipped_sells`. It makes
  no fills, so `has_exits` and `has_price_exits` are unchanged by it and the
  fills and the export get no reason because of it. The report, only with
  the option, adds a line right before `Max hold:` (or where it would be):
  `Min hold:    4 bars after a position's first buy before a signal sell can fill; 1 signal sell skipped`.
- **`--min-hold N` on the command line**: a whole number of at least 1.
  `--min-hold 0` (or `-1`) is `--min-hold must be a whole number of at least 1,
  got 0`; `--min-hold 1.5`, `4.0`, `abc` or `inf` argparse's
  `argument --min-hold: invalid int value: '1.5'`; without `--backtest`
  `--min-hold only makes sense together with --backtest`; with `--scan`
  `--min-hold cannot be combined with --scan` (all exit 2). It needs no stop
  and no candle file: a close-only file works, and so does `--resample` (`N`
  counts the resampled bars). `--help` lists it between `--cooldown` and
  `--max-hold` (the usage line does not). `--min-h` to `--min-hol` are short
  for it. See [docs/cli.md](docs/cli.md#min-hold).
- **`--json` with `--min-hold`**: the backtest object gets `min_hold_bars`
  right before `max_hold_bars` (or where that key would be) and
  `min_hold_skipped_sells` right before `time_exits` (or where that key would
  be). Both are there only with the option. The four `closes.csv` cases give
  the same numbers as the text report.
- **`--export` with `--min-hold`** is unaffected: no `reason` column is added,
  there is one row per bar as always, and a bar whose sell was skipped is a
  row without an action. With `N=3` (nothing skipped) the file is byte for
  byte the one without the option, and with `N=4` and `--max-hold 2` the one
  with `--max-hold 2` alone.
- **Config key `min_hold`** (a whole number) in `[cli]`, with the flag's
  rules: it needs no stop and no candle file. `min_hold = 0` (or `-1`) is the
  usage error `--min-hold must be a whole number of at least 1, got 0` (exit
  2); `min_hold = 1.5`, `4.0` or `abc` is the config error
  `Error: FILE line N: min_hold needs a whole number, got '1.5'` (exit 1).
  `--min-hold` on the command line wins and the file's value is then not used
  at all (`min_hold = 3` with `--min-hold 4` runs with 4, `min_hold = 0` with
  `--min-hold 4` too), so `--min-hold 1` turns a file's `min_hold` off for one
  run (the report still has a `Min hold:` line). Without `--backtest`, and
  with `--scan`, it is ignored, even `0`; a value that is not a whole number
  is still the config error there. The four `closes.csv` cases from a config
  file are byte-identical to the flag runs, in text and with `--json`.
- **`POST /api/backtest` takes `min_hold`**, read exactly like `max_hold` (17
  values sent to both behave the same): `4`, `4.0`, `"4"` or `" 4 "` is 4;
  `null`, `""` or no key leave it off; `true`, `false`, `4.5`, `"4.0"`,
  `"abc"`, `"inf"`, a list or an object is a 400 (`min_hold must be a whole
  number...`); `0`, `-1`, `0.0` or `"0"` is a 400 with the command's
  `--min-hold must be a whole number of at least 1, got 0`. It needs no candle
  data, so a close-only CSV works. It is echoed in `params` only when sent,
  right after `cooldown` (before `max_hold`); with it, `summary` has
  `min_hold_bars` and `min_hold_skipped_sells` right before the max hold keys
  (or where they would be), and the `report` is the command line's report line
  for line. Trades get no `reason` and the columns do not change because of
  it. The four `closes.csv` cases give the command's `--json` numbers.
- **Web page: a "Min hold (bars)" field** after "Cooldown (bars)", before "Max
  hold (bars)", with a hint. Sent as `min_hold` only when filled in. It needs
  no candle data: never greyed out or blanked, also for a close-only CSV, and
  the close-only hint does not name it. With the option the **Trades** card
  adds `, N signal sells skipped by min hold` after the cooldown count and
  before the max hold count (`1 buys, 0 sells, 1 signal sells skipped by min
  hold`; with a maximum holding time too, `2 buys, 1 sells, 0 signal sells
  skipped by min hold, 1 sold by max hold`). A bad value shows the server's
  message in the error box.
- **Library**: `cli.check_min_hold`, `cli.summarise(..., min_hold=0)`,
  `BacktestResult.min_hold`, `BacktestResult.min_hold_skipped_sells`.
- **Tests**: `test_min_hold.py` (54), `test_cli_min_hold.py` (18),
  `test_config_min_hold.py` (12), `test_web_min_hold.py` (23) and
  `test_web_min_hold_page.py` (8), 115 tests, with
  `tests/data/c_before_min_hold.json` (the 0.13.0 engine output of twelve
  runs) and `tests/data/closes_json_before_min_hold.json` (the 0.13.0
  `--json` of two runs).

### Existing results do not change

Every run without the minimum holding time gives exactly the same result,
report, `--json` object and `--export` file as in 0.13.0, from the command
line, from a config file and from `POST /api/backtest`, and the web page with
the field empty sends exactly the request it sent before. This was compared
with 0.13.0's code: 420 engine runs (two samples, every strategy, both fills,
15 mixes of costs, position size, stop, target, trailing stop, ATR stop, risk
sizing, breakeven stop, cooldown, maximum holding time and drawdown halt;
9,202 fills; fills, daily rows, round trips, report, statistics, export and
skip counts), 36 commands (text, 12 with `--json`, `--export`, `--stats`,
`--chart`, `--resample`, stops, short option names, `--scan`, usage errors;
stdout, stderr, exit code and export files), 96 config runs (12 files, each
with text, `--json`, `--scan` and `--resample`) and 23 API requests (20 to
`/api/backtest`, including 400s and an unknown key, and one each to
`/api/scan`, `/api/walkforward` and `/api/portfolio`; byte for byte). The
only visible differences outside the new option:

- `--help` lists `--min-hold N` with its description, between `--cooldown`
  and `--max-hold` (9 lines added, none changed). The usage line is
  unchanged.
- Abbreviations: `--min-h` to `--min-hol` now mean `--min-hold` (before they
  were `unrecognized arguments`). `--mi`, `--min` and `--min-`, which meant
  `--min-score` and would now be ambiguous, still mean `--min-score` through
  new hidden exact aliases (like `--m`, `--b` and `--ma`); their errors still
  name `--min-score`. Every option name and abbreviation argparse took in
  0.13.0 (212 in the main parser and 212 in the `--scan` parser) was parsed
  with both versions: the 196 that set an option set the same option to the
  same value, and the 12 that were ambiguous give the same error.
- The config error for an unknown `[cli]` key lists the new key after
  `cooldown`: `... atr_stop, cooldown, min_hold, max_hold, max_drawdown, ...`
  (this is the only difference among the 96 config runs). A file with a
  `min_hold` key was this error before; it is now read.
- `POST /api/backtest` used to ignore a `min_hold` key (even `0`); a request
  that already sent one now gets the minimum holding time, or a 400 for a bad
  value. A request without it (or with `null` or `""`) gets byte for byte the
  reply it got before. `/api/scan`, `/api/walkforward` and `/api/portfolio`
  still ignore it.
- Web page, with the field empty: the new field and its hint sit after the
  Cooldown field, so the Max hold and Max drawdown fields and the close-only
  hint each move one place along the form's grid. The close-only hint text,
  the script's list of candle-only controls, the **Trades** card of a reply
  without the new keys and the stylesheet are unchanged.
- Library: `BacktestResult` has two new last fields, `min_hold` and
  `min_hold_skipped_sells` (defaults 0), after `breakeven_pct`, so `repr()`
  and `dataclasses.asdict()` of every result now include them at the end; the
  31 fields before them keep their order. `run_backtest` and `cli.summarise`
  take `min_hold` as a new last parameter. `web.server.LATER_SETTINGS` gains
  `"min_hold"` between `"cooldown"` and `"max_hold"` (it orders the echo in
  `params`, which has `min_hold` only when it is sent).
- The version is 0.14.0 (`pyproject.toml`; the installed package reports
  0.14.0).

### Not checked

- The page was run in Node with a stand-in for the browser, never in a real
  browser: the layout of the new field and its hint, the shifted fields
  after it, keyboard order and screen readers are unchecked. Browsers
  normally read text that is not a number in a number field as empty, so
  typing `abc` there would probably send nothing and run without the option,
  with no error (as for Max hold); that was not tried. The form has
  `novalidate`, so `0` and `1.5` reach the server and its message is shown
  (tested in Node).
- The three paths read a value differently at one edge, as for `max_hold`:
  `4.0` is exit 2 from the flag (`invalid int value: '4.0'`) and exit 1 from
  a config file, while the API takes the JSON number `4.0` as 4 (and refuses
  the string `"4.0"`).

### Not covered yet

- The sweep, the walk-forward test, the portfolio command, the Monte Carlo
  tool and the drawdowns tool do not take it: `--min-hold` there is
  `unrecognized arguments` (exit 2), they have no config file, and none of
  them passes it to the engine (Monte Carlo gets its backtest through
  `drawdowns.backtest_from_args`). The buy-and-hold comparison has none.
- `tests/test_paths_agree.py` does not include the minimum holding time; the
  tests above compare each path instead.
- The page shows the setting only through the **Trades** card's count and
  the report's `Min hold:` line; there is no card with the setting itself.
  That count reads `1 signal sells` (no singular, like the card's `1 buys`
  and `1 sells`); the report line says `1 signal sell`.

### Changed tests

- `test_cli_atr_stop.py::test_help_lists_atr_stop_between_atr_period_and_export`
  and `test_cli_cooldown_unchanged.py::test_help_only_adds_the_cooldown_block_after_atr_stop`:
  the option after `--cooldown` in `--help` is now `--min-hold`, not
  `--max-hold` (one line each).
- `test_cli_atr_stop.py::test_help_only_changes_the_atr_options`: the list of
  `--help` entries gains `--min-hold` before `--max-hold` (one line).
- `test_config_atr_stop.py` (`NEW_KEY_LIST`),
  `test_config_backtest_keys.py::test_unknown_key_message_lists_the_new_keys`,
  `test_config_risk_sizing.py` (`NEW_KEY_LIST` and the two unknown-key runs in
  `OLD_RUNS`) and
  `test_config_trailing_stop.py::test_unknown_key_message_now_lists_trailing_stop`:
  the expected unknown-key list gains `min_hold` after `cooldown` (one line
  each).
- `test_web_atr_stop_page.py`: `SKIPPED_JS` (the Trades card code) gains the
  min hold line, and `test_nothing_else_changed_since_before_the_checkbox`
  also removes the Min hold field and its send block before hashing.
  `test_web_risk_sizing_page.py::test_nothing_else_changed_since_before_these_controls`
  and `test_web_trailing_stop_page.py::test_nothing_else_on_the_page_changed`
  also undo the field, its send block and the Trades card line. The three
  pinned hashes are unchanged.

## 0.13.0 (2026-11-13)

### Added

- **Breakeven stop in the engine** (`backtest.run_backtest(...,
  breakeven_pct=PCT)`, above 0, no upper limit, default None = off; needs
  the highs and lows). Once the trade has gone `PCT` % in its favour, a stop
  moves up to the entry price. Rules, each checked on a small case (most on
  `tests/data/c.csv`, the 11-bar candle file of
  [docs/cli.md](docs/cli.md#breakeven-stop)):
  - When a bar is over, its high is compared with the entry price (the
    average price paid) plus `PCT` %; at or above it (a high exactly at the
    trigger counts) the position is armed until it is sold. The entry bar's
    own high never counts, with close fills or with open fills, and the bar
    that arms it is never sold by it: the stop first acts on the next bar.
  - Once armed, a bar whose low reaches the entry price sells the whole
    position at the entry price, or at the bar's open when the opens are
    given and it opens at or below it (a gap; an open exactly at the level
    sells at the level). Without the opens the level is used. The fill's
    reason is `breakeven`. The level is exactly the entry price, with no
    allowance for fees or slippage, so such a sale still loses the costs
    (1 % slippage: bought at 11.11, sold at 11.11 x 0.99).
  - A later buy into the position moves the level with the average price: an
    armed stop stays armed and follows the new average (sold at
    (500 + 499.2) / 98), and an unarmed one measures `PCT` from the new
    average (a high above the first entry's trigger but below the new one
    does not arm it).
  - It is a stop like `stop_pct`, `trail_pct` and `atr_stop`: of the levels in
    use the highest is used, on a tie `stop`, then `trail`, then `atr`, then
    `breakeven` (a trail level exactly at the entry price sells as `trail`).
    Once armed it is always above the stop loss and the ATR stop; only the
    trail can be higher. It wins over the target when one bar touches both.
  - With `take_profit_pct` at or below `PCT` it is allowed but can never act:
    the bar whose high would arm it has reached the target, which sells the
    position. The only exception is a later buy into the position: with close
    fills a lower-priced one lowers the average after the bar's target check,
    and with open fills any later buy (a higher-priced one too) takes its
    bar's one fill at the open, so that bar's target check is skipped. Both
    were run and sell as `breakeven`.
  - It starts a cooldown, like `stop`, `trail` and `atr`. On a bar where
    `max_hold` is due, a breakeven sale during the bar comes first with close
    fills; with open fills the time exit at the open comes first (as for the
    other stops). A breakeven sale on the bar after a drawdown halt keeps its
    reason.
  On `c.csv` (`short=1`, `long=2`, cash 1000): without the option BUY 90 @
  11 (bar 4), signal SELL @ 10 (bar 7), BUY 75 @ 12 (bar 9), end 925.00; with
  5 or 9 the bar 6 low sells at 11.00 (`breakeven`), the bar 9 buy takes 83 @
  12 and the run ends at 1,016.60; with 10 (trigger 12.10) it never arms and
  the run is as without it; with 5 and `cooldown=3` the bar 9 buy is skipped
  and the run ends in cash at 1,000.00.
  `BacktestResult` records `breakeven_pct` and counts the sales in the new
  property `n_breakeven_exits`; `has_price_exits` and `has_exits` are true with
  it. The report's `Exits:` line, only with the option, shows
  `breakeven at entry once a later high is 5.00% above it`, with a note when
  other exits are on (`(breakeven wins if a bar touches both)` with a target,
  `(the higher of trail and breakeven is used, trail on a tie)`,
  `(the highest of stop, trail, atr and breakeven is used, in that order on a tie)`);
  with a cooldown the `Cooldown:` line reads
  `3 bars after a stop, trail, atr or breakeven exit; 1 buy skipped`.
- **`--breakeven PCT` on the command line**: above 0, decimals allowed, no
  upper limit. `--breakeven 0` (or `-1`, or `nan`) is
  `--breakeven must be above 0, got 0`, `--breakeven five` argparse's
  `argument --breakeven: invalid float value: 'five'`, without `--backtest`
  `--breakeven only makes sense together with --backtest`, with `--resample`
  `--breakeven cannot be combined with --resample yet` and with `--scan`
  `--breakeven cannot be combined with --scan` (all exit 2). Like the other
  stops it reads a candle file: a close-only file is exit 1. `--breakeven
  inf` is `--breakeven must be a finite number, got inf` (exit 2): unlike
  `--take-profit`, the flag refuses it, as the config key and the API do
  (`--breakeven=-inf` gets the "above 0" message; written as `--breakeven -inf`
  argparse reads `-inf` as an option and says `expected one argument`, as
  for `--take-profit -inf` in 0.12.0). It counts as a stop for `--cooldown`:
  `--breakeven 5 --cooldown 3` is accepted. `--help` lists it after
  `--max-drawdown` (the usage line does not), and its text names the
  exception for `--take-profit`: "at or above --take-profit it can never act,
  unless a later buy into the position moves the average (a lower-priced one
  with close fills, any one with --fill open)". See
  [docs/cli.md](docs/cli.md#breakeven-stop).
- **`--json` with `--breakeven`**: the backtest object gets `breakeven_pct`
  right after the other exit settings (`atr_stop`, `trailing_stop_pct` or
  `take_profit_pct`, before `cooldown_bars`) and `breakeven_exits` (its sales)
  right after `sells` or `risk_skipped_buys` (before `cooldown_skipped_buys`).
  Both are there only with the option; fills say `"reason": "breakeven"`.
  The four `c.csv` cases give the same numbers as the text report.
- **`--export` with `--breakeven`**: the file gets the `reason` column, as
  with any stop, with `breakeven` on its sales.
- **Config key `breakeven`** (a number) in `[cli]`, with the flag's rules: it
  reads a candle file, cannot be combined with `--resample`, and counts as a
  stop for a config `cooldown` and for `--cooldown`. `breakeven = 0` (or a
  negative number) is the usage error `--breakeven must be above 0, got 0`
  (exit 2); `breakeven = 5%` is the config error
  `Error: FILE line N: breakeven needs a number, got '5%'` and
  `breakeven = nan` or `inf` `... needs a finite number, got 'nan'` (exit 1);
  like the flag, the file does not take `inf`.
  `--breakeven` on the command line wins and the file's value is then not
  used at all (`breakeven = 5` with `--breakeven 9` runs with 9, `breakeven =
  0` with `--breakeven 9` too). Without `--backtest`, and with `--scan`, it is
  ignored, even `0`; a value that is not a finite number is still the config
  error. The four `c.csv` cases from a config file are byte-identical to the
  flag runs, in text and with `--json`. Also with `--breakeven` on the
  command line, a config `cooldown` is now used (it counts as a stop).
- **`POST /api/backtest` takes `breakeven`**, read exactly like
  `take_profit`: `5`, `5.0`, `"5"` or `" 5 "` is 5; `null`, `""` or no key
  leave it off; `true`, `false`, `"abc"`, a list or an object is a 400
  (`breakeven must be a number...`), and `NaN`, `Infinity`, `-Infinity`,
  `"nan"` or `"inf"` a 400 (`breakeven must be a finite number`), so the API
  never takes infinity. As for every number key, commas are dropped from a
  string (`"1,6"` is 16). Then the command's rule: `0` or `-1` is a 400 with
  `--breakeven must be above 0, got 0`. It needs candle data (a close-only
  CSV is the same 400 as for `stop_loss`) and counts as a stop for `cooldown`.
  It is echoed in `params` only when sent, right after `max_drawdown`; with
  it, `summary` has `breakeven_pct` and `breakeven_exits` right after `sells`
  (after `risk_skipped_buys`, before the cooldown keys), trades carry a
  `reason`, `columns`/`rows`/`csv` get the `reason` column, and the `report`
  is the command line's report line for line. The four `c.csv` cases give the
  command's `--json` numbers and its `--export` file.
- **Web page: a "Breakeven (%)" field** after "Trailing stop %", with a hint.
  Sent as `breakeven` only when filled in. Like the other stops it needs
  candle data: greyed out and blanked for a close-only CSV, and the
  close-only hint names it. With the option the **Trades** card adds
  `, N sold at breakeven` right after the risk sizing count (with a cooldown
  too: `1 buys, 1 sells, 1 sold at breakeven, 1 skipped by cooldown`). A bad
  value shows the server's message in the error box.
- **Library**: `cli.summarise(..., breakeven_pct=None)`,
  `BacktestResult.breakeven_pct`, `BacktestResult.n_breakeven_exits`.
- **Tests**: `test_breakeven.py`, `test_cli_breakeven.py`,
  `test_web_breakeven.py` and `test_web_breakeven_page.py` (111 tests), and
  the candle file `tests/data/c.csv` with `tests/data/c_before_breakeven.json`
  (the 0.12.0 output of nine `c.csv` runs with the other exits).

### Existing results do not change

Every run without the breakeven stop gives exactly the same result, report,
`--json` object and `--export` file as in 0.12.0, from the command line, from
a config file and from `POST /api/backtest`, and the web page with the field
empty sends exactly the request it sent before. This was compared with
0.12.0's code: 392 engine runs (two samples, every strategy, both fills, and
14 mixes of position size, stop, trailing stop, target, ATR stop, risk
sizing, cooldown, maximum holding time, drawdown halt, slippage and fees;
fills, daily rows, round trips, report, statistics and export), 40 commands
(text, 14 with `--json`, `--export`, `--chart`, `--stats`, config files,
short option names, `--resample`, `--scan`, `--take-profit inf`, usage and
data errors; stdout, stderr, exit code and export files; the one difference
is the line numbers in the traceback of `--take-profit inf --json`, see Not
covered yet), 45 config runs and 19 API requests (17 to `/api/backtest`, one
each to `/api/scan` and `/api/walkforward`; byte for byte). The only visible
differences outside the new option:

- `--help` lists `--breakeven PCT` with its description, between
  `--max-drawdown` and `--export`. No other option's help changed, and the
  usage line is unchanged.
- Abbreviations: `--br` to `--breakeve` now mean `--breakeven`. `--b`, which
  meant `--backtest` and would now be ambiguous, still means `--backtest`
  through a new hidden exact alias (like `--m`, `--t`, `--re`, `--co` and
  `--ma`); its errors still name `--backtest`. All 192 option names that
  worked in 0.12.0 in the main parser and all 192 in the `--scan` parser
  (full names, every abbreviation argparse took, and the hidden aliases) were
  parsed with both versions and set the same option, and the 24 names that
  were ambiguous give the same error.
- The config error for an unknown `[cli]` key lists the new key after
  `max_drawdown`: `... max_hold, max_drawdown, breakeven, fill, ...`. A file
  with a `breakeven` key was this error before; it is now read.
- `POST /api/backtest` used to ignore a `breakeven` key; a request that
  already sent one now gets the breakeven stop, or a 400 for a bad value. A
  request without it (or with `null` or `""`) gets byte for byte the reply it
  got before.
- Web page, with the field empty: the new field and its hint; the close-only
  hint now reads "Fill price, stop loss, take profit, trailing stop,
  breakeven, risk sizing, the ATR stop and the cooldown need open/high/low
  columns ..."; and the script's list of candle-only controls includes it.
  The **Trades** card of a reply without the new keys is unchanged, and so is
  the stylesheet.
- Library: `BacktestResult` has a new last field, `breakeven_pct` (default
  None), after `drawdown_skipped_buys`, so `repr()` and
  `dataclasses.asdict()` of every result now include it at the end; the
  fields before it keep their order. `run_backtest` and `cli.summarise` take `breakeven_pct` as a new
  last parameter. `has_price_exits` and `has_exits` are unchanged without the
  option; `Trade.reason` can be `breakeven`. `web.server.LATER_SETTINGS` ends
  with `"breakeven"`, and the private `backtest._exits_note` has a new last
  parameter.
- The version is 0.13.0 (`pyproject.toml`; the installed package reports
  0.13.0).

### Not checked

- The page was run in Node with a stand-in for the browser, never in a real
  browser: the layout of the new field and its hint, the longer close-only
  hint and **Trades** line, keyboard order and screen readers are unchecked.
  Browsers normally read text that is not a number in a number field as
  empty, so typing `ten` or `inf` there would probably send nothing (no stop,
  no error); that was not tried. The form has `novalidate`, so `0` and `-1`
  reach the server and its message is shown (tested in Node).
- The three paths read a value differently at the edges, as for their other
  number settings (see [docs/cli.md](docs/cli.md#breakeven-values)): `nan`
  is exit 2 from the flag, exit 1 from a config file and a 400 from the API,
  and so is `inf`; `1,6` is an error from the flag and the config file but 16
  from the API.

### Not covered yet

- The sweep, the walk-forward test, the portfolio command and the Monte Carlo
  tool have no breakeven stop, and the buy-and-hold comparison has none. The
  web page's **Exits** card does not show it (the text report's `Exits:` line
  and the trades table do).
- The `--cooldown` error for no stop at all, its `--help` text and the page's
  cooldown hint still name only the stop loss, trailing stop and ATR stop,
  although the breakeven stop counts as a stop for the cooldown.
- `tests/test_paths_agree.py` does not include the breakeven stop; the tests
  above compare each path instead.
- `--take-profit inf --json` still stops with a Python traceback (`Out of
  range float values are not JSON compliant: inf`, exit 1, nothing on
  stdout), as in 0.12.0: `--take-profit` takes `inf` and `take_profit_pct` is
  written to the JSON (only the traceback's line numbers differ from
  0.12.0's). The text report works. `--breakeven` avoids it by refusing
  `inf`.

### Changed tests

- `test_cli_atr_stop.py::test_help_only_changes_the_atr_options`: `--help`
  now lists `--breakeven` right after `--max-drawdown` (one line).
- `test_cli_max_drawdown.py::test_help_lists_it_after_max_hold_but_the_usage_line_does_not`:
  the option after `--max-drawdown` in `--help` is now `--breakeven`, not
  `--export` (one line).
- `test_config_atr_stop.py` (`NEW_KEY_LIST`),
  `test_config_backtest_keys.py::test_unknown_key_message_lists_the_new_keys`,
  `test_config_risk_sizing.py` (`NEW_KEY_LIST` and the two unknown-key runs in
  `OLD_RUNS`) and
  `test_config_trailing_stop.py::test_unknown_key_message_now_lists_trailing_stop`:
  the expected unknown-key list gains `breakeven` after `max_drawdown` (one
  line each).
- `test_web_atr_stop_page.py`: `SKIPPED_JS` (the Trades card code) gains the
  breakeven line, `NEW_HINT` and `NEW_CONTROLS` gain `breakeven`, and
  `test_nothing_else_changed_since_before_the_checkbox` also removes the
  Breakeven field and its send block before hashing.
  `test_web_risk_sizing_page.py::test_nothing_else_changed_since_before_these_controls`
  and `test_web_trailing_stop_page.py::test_nothing_else_on_the_page_changed`
  also undo the field, its send block, its entry in the candle-only controls,
  the hint text and the Trades card line. The three pinned hashes are
  unchanged. The pinned close-only hint and list of candle-only controls
  gain `breakeven` in `test_web_cooldown_page.py`,
  `test_web_max_drawdown_page.py`, `test_web_max_hold_page.py`,
  `test_web_risk_sizing_page.py` and `test_web_trailing_stop_page.py` (two
  lines each).

## 0.12.0 (2026-11-13)

### Added

- **Drawdown halt in the engine** (`backtest.run_backtest(...,
  max_drawdown_limit_pct=PCT)`, above 0 and below 100, default None = off).
  After every bar the account value at the close (cash plus the shares at the
  close, after that bar's fill and its costs) is compared with the highest
  account value at a close so far, the first bar's included. When it is `PCT`
  % or more below that peak, on bar `h`, the run halts; the check stops once
  it has triggered. Rules, each checked on a small case:
  - From bar `h + 1` to the end no buy can fill. A buy due then is dropped,
    not delayed, and counted in `BacktestResult.drawdown_skipped_buys` before
    the cooldown and sizing rules look at it: it is counted even if it would
    have got 0 shares, and then in neither `cooldown_skipped_buys` nor
    `risk_skipped_buys`. A strategy that keeps signalling is counted on every
    bar it signals (`breakout` with `window=1`: 5 skips). A BUY signal on the
    last bar has no bar to fill on and is not counted.
  - A position still held is sold whole on bar `h + 1` at that bar's fill
    price (its close, or its open with `fill="open"`), with slippage and fees.
    The fill's reason is `drawdown`.
  - That sale is made only when nothing else sells on the bar, in the order
    the time exit uses. With close fills: a stop, trail, ATR stop or target
    reached during the bar, then the signal fill, then the time exit, then the
    drawdown sale at the close. With open fills: the signal fill at the open,
    then a gap through a stop or target at the open, then the time exit, then
    the drawdown sale at the open; a stop or target reached only later in the
    bar does not beat it. A signal, stop, trail, ATR stop, target or time sale
    on that bar keeps its own reason.
  - It starts no cooldown. Once the run has halted every later buy is blocked
    anyway, so a cooldown could not change anything; a buy that falls in a
    cooldown from an earlier stop and after the halt is counted once, as a
    drawdown skip.
  - A drawdown sale the fees would make impossible (cash below zero) is tried
    again on each later bar; a position still held at the end is not sold.
  - The peak and the percentage are those of `drawdown_curve_pct`, so the
    report's `Max drawdown` and the export's `drawdown_pct` column; a bar's
    low is not used. Up to bar `h` the run is the run without the option, so
    it halts exactly when that run's `Max drawdown` would first reach `PCT`:
    on `closes.csv` (`Max drawdown` -16.514 %) 16.51 halts and 16.52 does
    not, and an exact 12.5 % fall halts at 12.5.
  `BacktestResult` records `max_drawdown_limit_pct`, `drawdown_halt_bar` (the
  bar `h`, None if it never triggered) and `drawdown_skipped_buys`.
  `has_exits` is also true with the option, so fills carry a reason in the
  report, the export and the web reply. The report adds, only with the
  option, a line just before `Round trips:`:
  `Drawdown:    halt at 16.00% below the peak account value at a close; triggered at bar 6, no buy fills after it; 1 buy skipped`
  (`not triggered` when it never did; `1 buy`, `0 buys` in the singular and
  plural). With only the drawdown halt there is no `Exits:` line.
- **`--max-drawdown PCT` on the command line**: above 0 and below 100,
  decimals allowed. It needs `--backtest` but no stop and no candle file: a
  close-only file works, `--resample` is allowed, and `--fill open` reads the
  candle file as it already did. `--max-drawdown 0` (or `100`, or `-5`) is
  `--max-drawdown must be above 0 and below 100, got 0`, `--max-drawdown ten`
  argparse's `argument --max-drawdown: invalid float value: 'ten'`, without
  `--backtest` `--max-drawdown only makes sense together with --backtest`,
  and with `--scan` `--max-drawdown cannot be combined with --scan` (all
  exit 2). `--help` lists it after `--max-hold`; the usage line does not. See
  [docs/cli.md](docs/cli.md#max-drawdown).
- **`--json` with `--max-drawdown`**: the backtest object gets
  `max_drawdown_limit_pct` right after `max_hold_bars` (or `cooldown_bars`,
  or the exit settings) and `drawdown_halt_bar` (`null` when the halt never
  triggered) and `drawdown_skipped_buys` right after `time_exits` (or
  `cooldown_skipped_buys`, `risk_skipped_buys` or `sells`). All three are
  there only with the option. The limit is not called `max_drawdown_pct`
  because that key already holds the drawdown the run had. The drawdown
  sale's fill has `"reason": "drawdown"`.
- **`--export` with `--max-drawdown`**: the file gets the `reason` column, as
  with a stop, with `drawdown` on the drawdown sale's row. There is no column
  for the halt or the skipped buys.
- **Config key `max_drawdown`** (a number) in `[cli]`, used like `max_hold`:
  with `--backtest`, with or without a stop, also with a close-only file and
  with `--resample`. `max_drawdown = 0` (or `100`) is the usage error
  `--max-drawdown must be above 0 and below 100, got 0` (exit 2);
  `max_drawdown = 10%` is the config error
  `Error: FILE line N: max_drawdown needs a number, got '10%'` and
  `max_drawdown = nan` (or `inf`) `... needs a finite number, got 'nan'`
  (exit 1). `--max-drawdown` on the command line wins, and then the file's
  value is not used at all (`max_drawdown = 0` with `--max-drawdown 16` runs
  with 16; `16` in the file with `--max-drawdown 17` runs with 17). Without
  `--backtest`, and with `--scan`, it is ignored, even `0`; a value that is
  not a number is still the config error.
- **`POST /api/backtest` takes `max_drawdown`**, read like the other number
  keys (`stop_loss`): `16`, `16.0`, `"16"` or `" 16 "` is 16; `null`, `""` or
  no key leave it off; `true`, `false`, `"abc"`, `"16%"`, a list or an object
  is a 400 (`max_drawdown must be a number...`), and `NaN`, `Infinity`,
  `"nan"` or `"inf"` a 400 (`max_drawdown must be a finite number`). As for
  every number key, commas are dropped from a string, so `"1,6"` is 16 and
  `"16,5"` is 165 (a 400 for the range). Then the command's own
  `cli.check_max_drawdown`: `0`, `"0"`, `100` or `-5` is a 400 with the
  flag's message. It needs no stop and no candle data. It is echoed in
  `params` only when sent, right after `max_hold`; with it, `summary` has the
  three `--json` keys right after `sells` (after the other optional keys when
  those are there), trades carry a `reason`, `columns`/`rows`/`csv` get the
  `reason` column, and the `report` has the `Drawdown:` line.
- **Web page: a "Max drawdown (%)" field** after the Max hold field, with a
  hint. Sent as `max_drawdown` only when filled in. It needs no candle data:
  it is never greyed out or blanked for a close-only CSV, and the close-only
  hint does not name it. With the option the **Trades** card adds
  `, N skipped by drawdown` (after `, N sold by max hold` when both are
  there). A bad value shows the server's message in the error box.
- **Library**: `cli.summarise(..., max_drawdown_limit_pct=None)`,
  `cli.check_max_drawdown(max_drawdown)`.
- **Tests**: `test_max_drawdown.py`, `test_cli_max_drawdown.py`,
  `test_config_max_drawdown.py`, `test_web_max_drawdown.py` and
  `test_web_max_drawdown_page.py` (61 tests).

### Existing results do not change

Every run without the drawdown halt gives exactly the same result, report,
`--json` object and `--export` file as in 0.11.0, from the command line, from
a config file and from `POST /api/backtest`, and the web page with the field
empty sends exactly the request it sent before and shows the same cards. This
was compared with 0.11.0's code: 3,360 engine runs (two samples, every
strategy, both fills, and mixes of position size, stop, trailing stop,
target, ATR stop, cooldown, maximum holding time, slippage and fees; fills,
daily rows, round trips, report, statistics and export), 34 commands (text,
`--json`, `--export`, `--chart`, `--stats`, config files, short option names,
usage and data errors; stdout, stderr, exit code and export files), 16 config
runs and 14 API requests (byte for byte). The only visible differences
outside the new option:

- `--help` lists `--max-drawdown PCT` with its description, between
  `--max-hold` and `--export`. No other option's help changed, and the usage
  line is unchanged.
- Abbreviations: `--max-d` to `--max-drawdow` now mean `--max-drawdown`. `--ma`,
  `--max` and `--max-`, which meant `--max-hold` and would now be ambiguous,
  still mean `--max-hold` through new hidden exact aliases (like `--m`, `--t`,
  `--re` and `--co`); their errors still name `--max-hold`. All 184 option
  names that worked in 0.11.0 (full names, every abbreviation argparse took,
  and the hidden aliases, in the main and the `--scan` parser) were checked
  and mean the same option.
- The config error for an unknown `[cli]` key lists the new key after
  `max_hold`: `... cooldown, max_hold, max_drawdown, fill, ...`. A file with a
  `max_drawdown` key was this error before; it is now read.
- `POST /api/backtest` used to ignore a `max_drawdown` key; a request that
  already sent one now gets the drawdown halt, or a 400 for a bad value. A
  request without it (or with `null` or `""`) gets byte for byte the reply it
  got before.
- Web page: the new field and its hint are the only change with the field
  empty. The close-only hint, the list of candle-only controls and the
  **Trades** card of a reply without the new keys are unchanged.
- Library: `BacktestResult` has three new last fields,
  `max_drawdown_limit_pct` (default None), `drawdown_halt_bar` (None) and
  `drawdown_skipped_buys` (0), so `repr()` and `dataclasses.asdict()` of every
  result now include them. `BacktestResult.has_exits` is unchanged without
  the option and now also true with it; `Trade.reason` can be `drawdown`.
  `web.server.LATER_SETTINGS` ends with `"max_drawdown"`.
- The version is 0.12.0 (`pyproject.toml`; the installed package reports
  0.12.0).

### Not checked

- The page was run in Node with a stand-in for the browser, never in a real
  browser: the layout of the new field and its hint, how the longer
  **Trades** line fits its card, keyboard order and screen readers are
  unchecked. Browsers normally read text that is not a number in a number
  field as empty, so typing `ten` there would probably send nothing (no halt,
  no error); that was not tried, nor was typing `16,5` with a decimal comma.
  The form has `novalidate`, so `0` reaches the server and its message is
  shown (tested in Node).
- The three paths read a value differently at the edges, as their other
  number settings do: `nan` is exit 2 (a range error) from the flag, exit 1
  from a config file and a 400 from the API; `1,6` is an error from the flag
  and the config file but 16 from the API. All three take Python's number
  spellings such as `1e1` and `1_6`. See
  [docs/cli.md](docs/cli.md#max-drawdown-values).
- The halt is checked on the account value at the closes only. A run whose
  account value falls further between the halt bar's close and the sale on
  the next bar (a gap down, for example) ends with a `Max drawdown` deeper
  than `PCT`; nothing limits that loss.

### Not covered yet

- The sweep, the walk-forward test, the portfolio command and the Monte Carlo
  tool have no drawdown halt, and the buy-and-hold comparison never halts.
  The web page's **Exits** card does not show it (the text report's
  `Drawdown:` line and the trades table do).
- `tests/test_paths_agree.py` does not include the drawdown halt; the tests
  above compare each path instead.

### Changed tests

- `test_cli_atr_stop.py::test_help_only_changes_the_atr_options`: `--help`
  now lists `--max-drawdown` right after `--max-hold` (one line).
- `test_config_atr_stop.py` (`NEW_KEY_LIST`),
  `test_config_backtest_keys.py::test_unknown_key_message_lists_the_new_keys`,
  `test_config_risk_sizing.py` (`NEW_KEY_LIST` and the two unknown-key runs in
  `OLD_RUNS`) and
  `test_config_trailing_stop.py::test_unknown_key_message_now_lists_trailing_stop`:
  the expected unknown-key list gains `max_drawdown` after `max_hold` (one
  line each).
- `test_web_atr_stop_page.py`: `SKIPPED_JS` (the Trades card code) gains the
  drawdown line, and `test_nothing_else_changed_since_before_the_checkbox`
  also undoes the Max drawdown field and its send block before hashing.
  `test_web_risk_sizing_page.py::test_nothing_else_changed_since_before_these_controls`
  and `test_web_trailing_stop_page.py::test_nothing_else_on_the_page_changed`
  also undo the field, its send block and the Trades card line. The three
  page-hash tests still compare with the same old hashes.


## 0.11.0 (2026-11-12)

### Added

- **Maximum holding time in the engine** (`backtest.run_backtest(..., max_hold=N)`,
  a whole number, default 0 = off). The whole position is sold on bar
  `e + N`, `e` being the bar of the buy that opened it, at that bar's fill
  price (its close, or its open with `fill="open"`), so it is held exactly
  `N` bars in either fill mode. The fill's reason is `time`. Slippage and
  fees apply as to any sell. It needs only the closes (and the opens for open
  fills): no stop, no highs or lows. Rules, each checked on a small case:
  - The clock runs from the buy that opened the position; a later buy into
    it does not restart it.
  - A time exit never takes a bar that already has a fill: if a signal buy
    or sell, or a stop, trail, ATR stop or target sale fills on bar `e + N`,
    that fill happens (a signal sell is labelled `signal`) and the time exit
    waits for the next bar without a fill.
  - With close fills the bar's range (stops, target) comes first, then the
    signal fill at the close, then the time exit at the close.
  - With open fills the signal fill at the open comes first, then a gap
    through a stop or the target at the open (sold at the open with the
    stop's or target's reason; a gap stop then starts the cooldown as
    usual), then the time exit at the open. A stop or target reached only
    later in the bar does not beat it.
  - A time exit starts no cooldown. After it the strategy buys again on its
    next BUY signal.
  - A time exit the fees would make impossible (cash below zero) is tried
    again on each later bar.
  - A position still open at the end is not sold, as before.
  `BacktestResult.max_hold` records `N`, `BacktestResult.n_time_exits` counts
  the `time` sells, and the new `BacktestResult.has_price_exits` is what
  `has_exits` meant before (a stop, target, trailing stop or ATR stop).
  `has_exits` is now also true with a maximum holding time, so fills then
  carry a reason in the report, `--export` and the web reply. The report adds,
  only with the option, a line after `Cooldown:` (or `Exits:`):
  `Max hold:    2 bars after a position's first buy, then sold at the bar's fill price; 1 time exit`
  (`1 bar`, `0 time exits` in the singular and plural). With only a maximum
  holding time there is no `Exits:` line.
- **`--max-hold N` on the command line** (a whole number of at least 1). It
  needs `--backtest` but no stop and no candle file: a close-only file works,
  `--resample` is allowed (`N` counts the resampled bars), and `--fill open`
  reads the candle file as it already did. `--max-hold 0` (or `-3`) is
  `--max-hold must be a whole number of at least 1, got 0`, `--max-hold 1.5`
  argparse's `argument --max-hold: invalid int value: '1.5'`, without
  `--backtest` `--max-hold only makes sense together with --backtest`, and
  with `--scan` `--max-hold cannot be combined with --scan` (all exit 2).
  See [docs/cli.md](docs/cli.md#max-hold).
- **`--json` with `--max-hold`**: the backtest object gets `max_hold_bars`
  right after `cooldown_bars` (or the exit settings without it) and
  `time_exits` right after `cooldown_skipped_buys` (or `risk_skipped_buys`,
  or `sells`). Both are there only with `--max-hold`. Fills it causes have
  `"reason": "time"`.
- **`--export` with `--max-hold`**: the file gets the `reason` column, as with
  a stop, with `time` on the time exits' rows.
- **Config key `max_hold`** (a whole number) in `[cli]`. Used with
  `--backtest`, with or without a stop, also with a close-only file and with
  `--resample`. `max_hold = 0` is the usage error
  `--max-hold must be a whole number of at least 1, got 0` (exit 2);
  `max_hold = 1.2` is the config error
  `Error: FILE line N: max_hold needs a whole number, got '1.2'` (exit 1).
  `--max-hold` on the command line wins, and then the file's value is not
  used at all (so `max_hold = 0` with `--max-hold 2` runs with 2, as for
  `cooldown`). Without `--backtest`, and with `--scan`, it is ignored, even
  `0`, like every backtest key.
- **`POST /api/backtest` takes `max_hold`**, read exactly like `cooldown`:
  `2`, `2.0`, `"2"` or `" 2 "` is 2; `null`, `""` or no key leave it off;
  `true`, `false`, `1.5`, `"1.5"`, `"abc"`, a list or an object is a 400
  (`max_hold must be a whole number...`). Then the command's own
  `cli.check_max_hold`: `0`, `"0"` or `-1` is a 400 with the flag's message.
  It needs no stop and no candle data, so it works on a close-only CSV. It is
  echoed in `params` only when sent, right after `cooldown`; with it,
  `summary` has `max_hold_bars` and `time_exits` (the `--json` keys) right
  after `sells` (after `risk_skipped_buys` and the cooldown keys when those
  are there), trades carry a `reason`, `columns`/`rows`/`csv` get the
  `reason` column, and the `report` has the `Max hold:` line.
- **Web page: a "Max hold (bars)" field** after the Cooldown field, with a
  hint. Sent as `max_hold` only when filled in. Unlike the stops it needs no
  candle data: it is never greyed out or blanked for a close-only CSV, and
  the close-only hint does not name it. With a maximum holding time the
  **Trades** card adds `, N sold by max hold`. A bad value shows the server's
  message in the error box.
- **Library**: `cli.summarise(..., max_hold=0)`, `cli.check_max_hold(max_hold)`.
- **Tests**: `test_max_hold.py`, `test_cli_max_hold.py`,
  `test_config_max_hold.py`, `test_web_max_hold.py` and
  `test_web_max_hold_page.py` (83 tests).

### Existing results do not change

Every run without a maximum holding time gives exactly the same result,
report, `--json` object and `--export` file as in 0.10.0, from the command
line, from a config file and from `POST /api/backtest`, and the web page with
the field empty sends exactly the request it sent before and shows the same
cards. This was compared with 0.10.0's code: 168 engine runs (every sample,
strategy and setting mix), 27 commands in text and `--json` (stdout, stderr,
exit code and export files), 60 config runs (the 12 with an unknown key
differ only in the key list, below), 17 API requests and 12 page runs. The only visible differences outside the new option:

- `--help` lists `--max-hold N` with its description, between `--cooldown`
  and `--export`. No other option's help changed. The usage line (at the top
  of `--help` and of every usage error) is unchanged and does not list it.
- Abbreviations: `--ma`, `--max`, `--max-`, `--max-h`, `--max-ho` and
  `--max-hol` now mean `--max-hold`. Before, they were "unrecognized
  arguments" (exit 2); now, for example, `prices.csv --ma` is
  `argument --max-hold: expected one argument` and `--scan DIR --ma 1` is
  `--max-hold cannot be combined with --scan` (both exit 2). `--m` used to
  mean `--min-score` (its only match) and still does, through a new hidden
  exact alias (`--m`, like `--t`, `--re` and `--co`); its errors still name
  `--min-score`. No "ambiguous option" message changed, and no abbreviation
  that worked before changed its meaning (all 177 were checked against
  0.10.0).
- The config error for an unknown `[cli]` key lists the new key after
  `cooldown`: `... atr_stop, cooldown, max_hold, fill, ...`. A file with a
  `max_hold` key was this error before; it is now read.
- `POST /api/backtest` used to ignore a `max_hold` key; a request that
  already sent one now gets the maximum holding time, or a 400 for a bad
  value. A request without it (or with `null` or `""`) gets byte for byte the
  reply it got before.
- Web page: the new field and its hint are the only change with the field
  empty. The close-only hint, the list of candle-only controls and the
  **Trades** card of a reply without the new keys are unchanged.
- Library: `BacktestResult` has a new last field `max_hold` (default 0), so
  `repr()` and `dataclasses.asdict()` of every result now include
  `max_hold=0`. `BacktestResult.has_exits` is unchanged without a maximum
  holding time and now also true with one; `Trade.reason` can be `time`.
  `web.server.LATER_SETTINGS` ends with `"max_hold"`.
- The version is 0.11.0 (`pyproject.toml`; the installed package reports
  0.11.0).

### Not checked

- The page was run in Node with a stand-in for the browser, never in a real
  browser: the layout of the new field and its hint, keyboard order and
  screen readers are unchecked. Browsers normally read text that is not a
  number in a number field as empty, so typing `abc` there would probably
  send nothing (no maximum holding time, no error); that was not tried. The
  form has `novalidate`, so `0` or `1.5` reach the server and its message is
  shown (tested in Node).
- For a value that is not a whole number the API answers
  `max_hold must be a whole number, got 1.5`, as for `cooldown`, not the
  flag's argparse text. The API takes a JSON `2.0` as 2, where
  `--max-hold 2.0` is a usage error.
- A time exit the fees make impossible is retried on later bars; this was
  checked by hand once, no test pins it.
- When a bar with open fills gaps through a stop exactly at the open the
  time exit is due at, the stop wins (same price, the stop's reason, and a
  cooldown if one is set). This is one hand-worked case
  (`test_max_hold.py`); the opposite choice would change only the reason and
  the cooldown.

### Not covered yet

- The sweep, the walk-forward test, the portfolio command and the Monte Carlo
  tool have no maximum holding time, and the buy-and-hold comparison never
  exits, so it has none. The web page's **Exits** card does not show it (the
  text report's `Max hold:` line and the trades table do).
- `tests/test_paths_agree.py` does not include the maximum holding time; the
  tests above compare each path instead.

### Changed tests

- `test_cli_atr_stop.py::test_help_lists_atr_stop_between_atr_period_and_export`
  and `::test_help_only_changes_the_atr_options`, and
  `test_cli_cooldown_unchanged.py::test_help_only_adds_the_cooldown_block_after_atr_stop`:
  `--help` now lists `--max-hold` right after `--cooldown` (one line each;
  the last test's removed span, `--cooldown` up to `--export`, already takes
  in the new block).
- `test_config_atr_stop.py` (`NEW_KEY_LIST`),
  `test_config_backtest_keys.py::test_unknown_key_message_lists_the_new_keys`,
  `test_config_risk_sizing.py` (`NEW_KEY_LIST` and the two unknown-key runs in
  `OLD_RUNS`) and
  `test_config_trailing_stop.py::test_unknown_key_message_now_lists_trailing_stop`:
  the expected unknown-key list gains `max_hold` after `cooldown` (one line
  each).
- `test_web_atr_stop_page.py`: `SKIPPED_JS` (the Trades card code) gains the
  time-exit line, and `test_nothing_else_changed_since_before_the_checkbox`
  also undoes the Max hold field and its send block before hashing.
  `test_web_risk_sizing_page.py::test_nothing_else_changed_since_before_these_controls`
  and `test_web_trailing_stop_page.py::test_nothing_else_on_the_page_changed`
  also undo the field, its send block and the Trades card line. The three
  page-hash tests still compare with the same old hashes.


## 0.10.0 (2026-11-12)

### Added

- **Cooldown in the engine** (`backtest.run_backtest(..., cooldown=N)`, a
  whole number, default 0 = off): after a `stop`, `trail` or `atr` sell on
  bar `t`, no buy can fill on bars `t + 1` to `t + N`. A `target` or `signal`
  sell starts no cooldown. A buy due on a blocked bar is **dropped, not
  delayed**, and counted in `BacktestResult.cooldown_skipped_buys`, before any
  sizing rule looks at it: it is counted even if it would have got 0 shares,
  and then not also in `risk_skipped_buys`. Consequences, each checked on a
  small case:
  - A crossover strategy (`sma_cross`, `ema_cross`, ...) signals BUY only on
    the bar it crosses, so a crossing whose buy falls in the cooldown is lost:
    the strategy stays out until its next crossing, however long after the
    cooldown. A strategy that keeps signalling (`breakout`) buys again as soon
    as a BUY is due after the cooldown.
  - A BUY signal on the exit bar's close is due on bar `t + 1`, the first
    blocked bar. A buy due on the exit bar itself is never a cooldown skip:
    with close fills the exit comes first and cancels it (one fill per bar, as
    before); with open fills it fills at the open, no exit is checked on that
    bar, and so no cooldown starts there.
  - A BUY signal on the last bar has no bar to fill on and is never counted.
  `BacktestResult.cooldown` records `N`.
- **`--cooldown N` on the command line** (a whole number of at least 1). It
  needs `--backtest` and one of `--stop-loss`, `--trailing-stop` or
  `--atr-stop` (from the command line or the config file); otherwise it is a
  usage error (exit 2):
  `--cooldown only makes sense together with --backtest`, or
  `--cooldown only makes sense together with --stop-loss, --trailing-stop or --atr-stop`
  (`--take-profit` alone is not enough). `--cooldown 0` is
  `--cooldown must be a whole number of at least 1, got 0` and `--cooldown 1.5`
  argparse's `argument --cooldown: invalid int value: '1.5'` (both exit 2). It
  cannot be combined with `--scan` (exit 2). The report adds, right after
  `Exits:` and only with the option,
  `Cooldown:    3 bars after a stop, trail or atr exit; 1 buy skipped`
  (`1 bar`, `0 buys` in the singular and plural). See
  [docs/cli.md](docs/cli.md#cooldown).
- **`--json` with `--cooldown`**: the backtest object gets `cooldown_bars`
  right after the exit settings (after `atr_stop`, `trailing_stop_pct` or
  `take_profit_pct`, the last of those present) and `cooldown_skipped_buys`
  right after `sells` (after `risk_skipped_buys` when that is there). Both are
  there only with `--cooldown`.
- **Config key `cooldown`** (a whole number) in `[cli]`. Used only with
  `--backtest` and when a stop is on: `stop_loss`, `trailing_stop` or
  `atr_stop = yes` in the file, or `--stop-loss`, `--trailing-stop` or
  `--atr-stop`. Without a stop it is ignored without an error (like
  `atr_mult` and `atr_period`), and the run prints exactly what it prints
  without the key. Unlike them, `cooldown = 0` is still the usage error
  `--cooldown must be a whole number of at least 1, got 0` (exit 2), with or
  without a stop; `cooldown = 1.5` is the config error
  `Error: FILE line N: cooldown needs a whole number, got '1.5'` (exit 1).
  Without `--backtest` (and with `--scan`) it is ignored, even `0`, like every
  backtest key. `--cooldown` on the command line wins over the file, and a
  stop from the file counts for the flag. The flag without any stop stays a
  usage error.
- **`POST /api/backtest` takes `cooldown`**, read like the other whole-number
  keys (`atr_period`): `3`, `3.0`, `"3"` or `" 3 "` is 3; `null`, `""` or no
  key leave it off; `true`, `false`, `1.5`, `"1.5"`, `"abc"`, a list or an
  object is a 400 (`cooldown must be a whole number...`). Then the command's
  own `cli.check_cooldown` with its messages: no stop, or a value below 1, is
  a 400 with the flag's message, and a close-only CSV gets the stop's 400. It
  is echoed in `params` only when sent, right after `atr_stop`; with it,
  `summary` has `cooldown_bars` and `cooldown_skipped_buys` (the `--json`
  keys) right after `sells` (or `risk_skipped_buys`), and the `report` has the
  `Cooldown:` line.
- **Web page: a "Cooldown (bars)" field** after the ATR stop box, with a hint.
  Sent as `cooldown` only when filled in. A candle-only control like the
  stops: greyed out and cleared for a close-only CSV. With a cooldown the
  **Trades** card adds `, N skipped by cooldown`. A bad value or no stop shows
  the server's message in the error box.
- **Library**: `cli.summarise(..., cooldown=0)`,
  `cli.check_cooldown(cooldown, stops)`.
- **Tests**: `test_cooldown.py`, `test_cli_cooldown.py`,
  `test_cli_cooldown_unchanged.py`, `test_cli_cooldown_json.py`,
  `test_config_cooldown.py`, `test_web_cooldown.py` and
  `test_web_cooldown_page.py`.

### Existing results do not change

Every run without a cooldown gives exactly the same result, report, `--json`
object and `--export` file as in 0.9.0, from the command line, from a config
file and from `POST /api/backtest`, and the web page with the field empty
sends exactly the request it sent before. `--export` has no cooldown column
in any run. The only visible differences outside the new option:

- `--help` lists `--cooldown N` with its description, between `--atr-stop`
  and `--export`. No other option's help changed. The usage line (at the top
  of `--help` and of every usage error) is unchanged and does not list it.
- Abbreviations: `--coo`, `--cool`, ... `--cooldow` now mean `--cooldown`
  (before, they were "unrecognized arguments", exit 2). `--co` used to mean
  `--config` and still does, through a new hidden exact alias (`--co`, like
  `--t` and `--re`); its errors still name `--config`. `--c` was already an
  "ambiguous option" (exit 2) and still is, but its message now also lists
  `--cooldown` and the alias:
  `ambiguous option: --c could match --cash, --cooldown, --config, --co, --chart, --candles`
  (before: `--cash, --config, --chart, --candles`). No abbreviation that
  worked before changed its meaning.
- The config error for an unknown `[cli]` key lists the new key after
  `atr_stop`: `... atr_period, atr_stop, cooldown, fill, ...`. A file with a
  `cooldown` key was this error before; it is now read.
- `POST /api/backtest` used to ignore a `cooldown` key; a request that
  already sent one now gets the cooldown, or a 400 for a bad value, no stop or
  a close-only CSV. A request without it (or with `null` or `""`) gets byte
  for byte the reply it got before.
- Web page: the hint for a close-only CSV now names the cooldown: "Fill price,
  stop loss, take profit, trailing stop, risk sizing, the ATR stop and the
  cooldown need open/high/low columns ...".

### Not checked

- The page was run in Node with a stand-in for the browser, never in a real
  browser: the layout of the new field and its hint, keyboard order and
  screen readers are unchecked. Browsers normally read text that is not a
  number in a number field as empty, so typing `abc` there would probably
  send nothing (no cooldown, no error); that was not tried.
- For a value that is not a whole number the API answers
  `cooldown must be a whole number, got 1.5`, as for `atr_period`, not the
  flag's argparse text. The API takes a JSON `3.0` as 3, where
  `--cooldown 3.0` is a usage error.

### Not covered yet

- The sweep, the walk-forward test, the portfolio command and the Monte Carlo
  tool have no cooldown, and the buy-and-hold comparison never exits, so it
  has none. `--export` has no cooldown column. The web page's **Exits** card
  does not show the cooldown (the text report does).
- `tests/test_paths_agree.py` does not include the cooldown; the tests above
  compare each path instead.

### Changed tests

- `test_cli_atr_stop.py::test_help_lists_atr_stop_between_atr_period_and_export`
  and `::test_help_only_changes_the_atr_options`: `--help` now lists
  `--cooldown` between `--atr-stop` and `--export` (one line each).
- `test_config_atr_stop.py` (`NEW_KEY_LIST`),
  `test_config_backtest_keys.py::test_unknown_key_message_lists_the_new_keys`,
  `test_config_risk_sizing.py` (`NEW_KEY_LIST` and the two unknown-key runs in
  `OLD_RUNS`) and
  `test_config_trailing_stop.py::test_unknown_key_message_now_lists_trailing_stop`:
  the expected unknown-key list gains `cooldown` (one line each).
- `test_web_atr_stop_page.py` (`NEW_HINT`, `NEW_CONTROLS`, `SKIPPED_JS`),
  `test_web_risk_sizing_page.py::test_candle_only_like_stop_loss_and_hint_names_risk_sizing`
  and `test_web_trailing_stop_page.py::test_candle_only_like_stop_loss_and_hint_names_it`:
  the expected control list and hint gain the cooldown, and the Trades card
  code its count. The three page-hash tests
  (`test_web_atr_stop_page.py::test_nothing_else_changed_since_before_the_checkbox`,
  `test_web_risk_sizing_page.py::test_nothing_else_changed_since_before_these_controls`
  and `test_web_trailing_stop_page.py::test_nothing_else_on_the_page_changed`)
  now also undo the cooldown field before hashing; they still compare with the
  same old hashes.

## 0.9.0 (2026-11-11)

### Added

- **ATR stop in the engine** (`backtest.run_backtest(..., atr_stop=True)`):
  sells the position when a bar's low reaches the average entry price less
  `atr_mult x ATR(atr_period)`, the ATR taken on the signal bar of the buy
  that opened the position and kept for the whole position (a later buy
  moves the level with the average price, not the distance). It shares
  `atr_mult` and `atr_period` with risk sizing. A buy signal with no usable
  ATR (none yet, or 0) is skipped and counted in `risk_skipped_buys`. Fills
  it causes have the reason `atr`; the report's `Exits:` line shows
  `atr N x ATR(P) below entry`; with the stop loss and trailing stop the
  highest level is used, on a tie the stop, then the trail, then atr. The
  ATR is only worked out when `atr_stop` or `risk_pct` is on. With
  `risk_pct` as well, the buy that opens a position is sized on the distance
  the stop sells at; a gap, slippage, fees or a later buy into the position
  (sized on its own signal bar's ATR while the stop keeps the first distance)
  can still lose more than the risk.
- **`--atr-stop` on the command line**: a switch that turns the ATR stop on,
  with the distance from `--atr-mult N` (default 2) and `--atr-period N`
  (default 14). `--atr-mult` and `--atr-period` now work with `--risk-pct`,
  with `--atr-stop`, or with both. Like `--risk-pct` it needs `--backtest`,
  reads the file as a candle file and cannot be combined with `--resample`
  yet (or with `--scan`). A skipped buy without `--risk-pct` shows
  `Skipped:     1 buy (ATR stop: no usable ATR on the signal bar)`. See
  [docs/cli.md](docs/cli.md#atr-stop).
- **`--json` with `--atr-stop`**: the backtest object gets `"atr_stop": true`
  right after `trailing_stop_pct` (or `take_profit_pct` without it), with the
  other exit settings; `atr_mult` and `atr_period` (defaults filled in) in
  the place they already had with risk sizing, right after `risk_pct` (or
  `position_size` without it); and `risk_skipped_buys` right after `sells`.
  Each is there only when it applies: `atr_stop` only with `--atr-stop`, the
  other three with `--risk-pct` or `--atr-stop`. Fills it causes have
  `"reason": "atr"`.
- **Config key `atr_stop`** (yes/no, like `stats`): `atr_stop = yes` turns the
  ATR stop on with `--backtest`, reads the price file as a candle file and
  cannot go with `--resample`; without `--backtest`, and with `--scan`, it is
  ignored. `no` leaves the ATR stop as the command line has it, so
  `--atr-stop` wins over `atr_stop = no`. A value that is not a yes/no word is
  `Error: FILE line N: atr_stop needs yes or no, got '...'` (exit 1). The
  file's `atr_mult` and `atr_period` now count when risk sizing or the ATR
  stop is on, from the file or the command line (before: only with risk
  sizing), and are still ignored quietly otherwise; a flag wins over the file
  for each key.
- **`POST /api/backtest` takes `atr_stop`** (JSON `true` or `false`; the
  command's `--atr-stop`). `true` turns the ATR stop on, needs candle data
  (a sample's candles or a candle CSV; a close-only CSV is a 400 with the
  command's message) and lets `atr_mult` and `atr_period` count without
  `risk_pct`, checked by the same `cli.check_risk` with the command's
  messages. `false`, `null`, `""` or no key leave it off; any other value is
  a 400 `atr_stop must be true or false, got ...`. It is echoed in `params`
  only when sent, right after `atr_period`; with `risk_pct` or `atr_stop` on,
  `summary.risk_skipped_buys` is there right after `sells`; its sells have
  the trade `reason` `atr`.
- **Web page: an "ATR stop" box** after the ATR period field, a candle-only
  control like the stops: greyed out and unticked for a close-only CSV (whose
  hint now reads "Fill price, stop loss, take profit, trailing stop, risk
  sizing and the ATR stop need open/high/low columns ..."). Ticked, the page
  sends `"atr_stop": true`, with the ATR multiplier and period fields when
  filled in (they now count with Risk % or the box; their labels already fit
  both, and the box's hint says so). The trades table shows `atr` for its
  sells, and the **Trades** card adds `, N skipped` whenever the reply has a
  skipped-buy count (with Risk % or the ATR stop).

### Existing results do not change

Every run without `atr_stop` gives exactly the same result, report and
export as before. With `risk_pct` and `atr_stop` together the "Risk sizing:"
line no longer says "no stop is placed": it ends "(the ATR stop sells at this
distance, as of the buy that opened the position, below the average entry
price; a gap, slippage, fees or a later buy can lose more)". And
`atr_mult`/`atr_period` are now recorded on the result when either option is on.

On the command line, every command that worked before prints exactly the
same, with the same exit code, and `--json` without `--atr-stop` prints
exactly the JSON it printed before. The only visible differences outside the new
option:

- `--help` lists `--atr-stop` with its description, between `--atr-period`
  and `--export`. The help of `--risk-pct` and `--atr-mult` now says what
  changes with `--atr-stop` (where a stop comes from, and that a gap,
  slippage, fees or a later buy can lose more), and `--atr-period` gains a
  sentence at the end about it. The usage line (at the
  top of `--help` and of every usage error) is unchanged and does not list it.
- A config file that worked before gives exactly the same output, except
  with `--atr-stop` on the command line: its `atr_mult` and `atr_period`
  are now used there (so `atr_mult = 0` in such a file is now the usage error
  `--atr-mult must be above 0, got 0`, as with `risk_pct`). The config error
  for an unknown `[cli]` key lists the new key after `atr_period`:
  `... risk_pct, atr_mult, atr_period, atr_stop, fill, ...`.
- Web page: with the box unticked or untouched, the page sends exactly the
  request it sent before. Two visible changes: the close-only-CSV hint names
  the ATR stop, and with Risk % the **Trades** card now also shows the
  skipped-buy count (`1 buys, 1 sells, 0 skipped`), which before was only in
  the text report.
- `POST /api/backtest`: a request without `atr_stop` (or with `null` or
  `""`) gets byte for byte the reply it got before. The server used to ignore
  an `atr_stop` key, so a request that already sent one now gets the ATR stop
  (`true`), the old reply plus `"atr_stop": false` in `params` (`false`), or
  a 400 (any other value).
- `--atr-mult` or `--atr-period` without `--risk-pct` (and now without
  `--atr-stop`) is still a usage error (exit 2), but the message now reads
  `--atr-mult only makes sense together with --risk-pct or --atr-stop`
  (likewise for `--atr-period`). `POST /api/backtest` shares this check, so its
  400 reply for `atr_mult` or `atr_period` without `risk_pct` has the same
  new text.
- Abbreviations: `--atr-s`, `--atr-st` and `--atr-sto` now mean `--atr-stop`
  (before, they were "unrecognized arguments", exit 2). `--a`, `--at`, `--atr`
  and `--atr-` were already "ambiguous option" (exit 2) and still are; the
  message now also lists `--atr-stop`. No abbreviation that worked before
  changed its meaning.

## 0.8.0 (2026-11-11)

### Existing results do not change

**Without risk sizing, every run gives exactly the same results as in
0.7.0**: the same report, `--json` object, `--export` file, error messages and
exit codes from the command line and from a config file (except the one
message below), and the same replies from `POST /api/backtest`; the web page
sends the same request as before when its new fields are empty. The only
visible differences outside the new feature:

- `--help` lists `--risk-pct PCT`, `--atr-mult N` and `--atr-period N` with
  their descriptions. The usage line (at the top of `--help` and of every
  usage error) is unchanged and does not list them.
- Abbreviations: `--ri`, `--risk` and the other prefixes of `--risk-pct` now
  mean `--risk-pct`, `--atr-m...` means `--atr-mult` and `--atr-p...` means
  `--atr-period` (before, they were "unrecognized arguments", exit 2).
  `--a`, `--at`, `--atr` and `--atr-` are now "ambiguous option" (still
  exit 2). `--r` was already ambiguous and still is (exit 2), but its message
  now also lists `--risk-pct`. No abbreviation that worked before changed its
  meaning.
- The config error for an unknown `[cli]` key lists the new keys after
  `trailing_stop`: `... take_profit, trailing_stop, risk_pct, atr_mult,
  atr_period, fill, ...`.
- `POST /api/backtest` used to ignore `risk_pct`, `atr_mult` and `atr_period`;
  it now uses them, so a request that already sent them gets risk-sized
  numbers, or a 400 for a bad value, for `atr_mult`/`atr_period` without
  `risk_pct`, or for `risk_pct` with a close-only CSV.
- The web page's hint for a close-only CSV now names risk sizing too:
  "Fill price, stop loss, take profit, trailing stop and risk sizing need
  open/high/low columns ...".

### Added

- **Indicator** `indicators.atr(highs, lows, closes, period=14)`: Wilder's
  average true range. The true range of bar 0 is high - low; after that the
  largest of high - low, |high - previous close| and |low - previous close|.
  The first value (index `period - 1`) is the mean of the first `period` true
  ranges, then `(previous * (period - 1) + true range) / period`. `None`
  before that, all `None` with fewer bars than `period`; `ValueError` for a
  bad period, lists of different lengths or a high below its low.
- **Risk sizing** `--risk-pct PCT` (needs `--backtest`; above 0, at most
  100), with `--atr-mult N` (above 0, default 2) and `--atr-period N` (a
  whole number of at least 1, default 14), which need `--risk-pct`. Each buy
  gets `PCT` % of the account value at the fill divided by
  `atr_mult x ATR(atr_period)`, the ATR taken on the bar the buy signal came
  on (never the fill bar), rounded down, capped by the cash and by
  `--position-size` (the smaller size wins). **It only sets the number of
  shares: no stop is placed, and a loss can be larger than `PCT` %.** It works
  next to `--stop-loss`, `--take-profit` and `--trailing-stop`, which remain
  the exits. A buy it gives 0 shares (no ATR yet on the signal bar, an ATR of
  0, or risk under one share) is skipped and counted; a buy skipped only for
  lack of cash is not. Like `--stop-loss` it reads a candle file (a close-only
  file is exit 1) and cannot be combined with `--resample` (exit 2).
- **Report**: a `Risk sizing:` line, for example
  `Risk sizing: 2.00% of account value at risk per buy, stop distance 2 x ATR(3) (this only sets the number of shares; no stop is placed)`,
  and, when buys were skipped,
  `Skipped:     1 buy (risk sizing gave 0 shares: no usable ATR on the signal bar, or risk under 1 share)`.
- **`--json`**: `backtest.risk_pct`, `atr_mult` and `atr_period` (defaults
  filled in) right after `position_size`, and `backtest.risk_skipped_buys`
  right after `sells`, only when risk sizing is used.
- **Config keys** `risk_pct`, `atr_mult` (numbers) and `atr_period` (a whole
  number) in `[cli]`, with the flags' rules: used only with `--backtest`,
  `risk_pct` reads a candle file and not with `--resample`, same ranges; a
  flag wins over the file for its own key. `atr_mult` and `atr_period` in the
  file are ignored without an error when `risk_pct` is not set by the file or
  the flag.
- **Web API**: `POST /api/backtest` takes `risk_pct`, `atr_mult` and
  `atr_period`, checked by the command's own `cli.check_risk` (a 400 with the
  command's one-line message), with candle data. They are echoed in `params`
  after `trailing_stop` only when sent; with `risk_pct`, `summary` has
  `risk_skipped_buys` after `sells`. The numbers equal the command's `--json`.
- **Web page**: "Risk % per buy", "ATR multiplier" (placeholder
  "2 (default)") and "ATR period" ("14 (default)") after "Trailing stop %".
  Empty Risk % means not used and nothing is sent; the ATR fields are sent
  only with it. Greyed out and cleared for a close-only CSV, like the stop
  loss. Risk sizing shows in the text report.
- **Library**: `run_backtest(..., risk_pct=None, atr_mult=2.0, atr_period=14)`;
  `BacktestResult.risk_pct`, `atr_mult`, `atr_period` (`None` without risk
  sizing) and `risk_skipped_buys` (0); `cli.summarise(..., risk_pct=None,
  atr_mult=2.0, atr_period=14)`; `cli.check_risk(risk_pct, atr_mult,
  atr_period)`.
- **Tests**: `test_atr.py`, `test_risk_sizing.py`,
  `test_risk_sizing_report.py`, `test_cli_risk_sizing.py`,
  `test_cli_risk_json.py`, `test_config_risk_sizing.py`,
  `test_web_risk_sizing.py` and `test_web_risk_sizing_page.py`.

### Not checked

- Fees and slippage are not part of the risk amount, and a share count capped
  by the cash or `--position-size` risks less than the `Risk sizing:` line
  says.
- The ATR uses the highs, lows and closes as they are; the candle file check
  is the only check on them.
- `--atr-mult inf` is accepted by the command and skips every buy (the config
  file and the web API refuse it); an `--atr-period` longer than the file
  skips every buy.

### Not covered yet

- The buy-and-hold comparison stays all-in. The sweep, the walk-forward test,
  the portfolio command and the Monte Carlo tool have no risk sizing.
  `--export` has no risk columns. The web page shows risk sizing only in the
  text report, not on a card.
- `tests/test_paths_agree.py` does not include risk sizing; the tests above
  compare each path instead.

### Changed tests

- `test_config_backtest_keys.py::test_unknown_key_message_lists_the_new_keys`
  and `test_config_trailing_stop.py::test_unknown_key_message_now_lists_trailing_stop`:
  the expected unknown-key message gains the three keys.
- `test_web_trailing_stop_page.py::test_candle_only_like_stop_loss_and_hint_names_it`
  and `::test_nothing_else_on_the_page_changed`: the expected candle control
  list and hint text gain risk sizing, and the page comparison also removes
  the new risk fields and script before hashing.

## 0.7.0 (2026-11-09)

### Existing results do not change

**Without a trailing stop, every run gives exactly the same results as in
0.6.0**: the same report, `--json` object, `--export` file, error messages and
exit codes from the command line and from a config file, and the same replies
from `POST /api/backtest`; the web page sends the same request as before when
its new field is empty. The only visible differences outside the new feature:

- `--help` lists `--trailing-stop PCT` with its description. The usage line
  (at the top of `--help` and of every usage error) is unchanged and does not
  list it.
- Abbreviations: `--tr`, `--trailing` and the other prefixes of
  `--trailing-stop` now mean `--trailing-stop` (before, they were
  "unrecognized arguments", also exit 2). `--t` still means `--take-profit`.
- The config error for an unknown `[cli]` key lists the new key after
  `take_profit`: `... stop_loss, take_profit, trailing_stop, fill, ...`.
- `POST /api/backtest` used to ignore a `trailing_stop` key; it now uses it,
  and a bad value is a 400.
- The web page's hint for a close-only CSV now names the trailing stop too:
  "Fill price, stop loss, take profit and trailing stop need open/high/low
  columns ...".

### Added

- **Trailing stop** `--trailing-stop PCT` (needs `--backtest`; above 0 and
  below 100): while shares are held, each bar after the entry bar is checked
  against the highest high since entry less `PCT` %. The highest high starts
  at the entry price (the average price paid) and takes in the highs of the
  bars after the entry bar up to the bar before the one being checked, never
  the checked bar's own high. A bar whose low reaches the level is sold at the
  level; one that opens at or below it is sold at its open. Each new position
  starts a new highest high. Slippage and fees apply. The fill's reason is
  `trail`. Like `--stop-loss` it reads a candle file (a close-only file is
  exit 1) and cannot be combined with `--resample` (exit 2).
- **With the other exits**: with `--stop-loss` the higher of the two levels is
  used (the stop on a tie); either wins over `--take-profit` on a bar that
  touches both. The report's `Exits:` line gains
  `trail X.XX% below the highest high since entry` and a note for each
  combination, for example `(the higher of stop and trail is used)` or
  `(trail wins if a bar touches both)`; the stop and target note is unchanged.
- **Report and export**: a run with only a trailing stop gets the reason on
  each fill line and the `reason` column in `--export`, like a stop or target.
- **`--json`**: `backtest.trailing_stop_pct` (for example `10.0`), right after
  `take_profit_pct`, only when a trailing stop is used.
- **Config key** `trailing_stop` in `[cli]`, a number with the flag's rules:
  used only with `--backtest`, reads a candle file, not with `--resample`,
  above 0 and below 100; a `--trailing-stop` flag wins over it.
- **Web API**: `POST /api/backtest` takes `trailing_stop`, with the command
  line's rules and messages (for example 400
  `--trailing-stop must be between 0 and 100 (both exclusive), got 0`) and
  candle data (a sample's candles, or a pasted CSV read as a candle file). It
  is echoed in `params` after `take_profit` only when given, and the numbers
  equal the command's `--json`.
- **Web page**: a "Trailing stop %" field after "Take profit %", empty by
  default (not used), greyed out like the stop loss for a close-only CSV. The
  trades table shows `trail` as it shows `stop` and `target`.
- **Library**: `run_backtest(..., trail_pct=None)`; `BacktestResult.trail_pct`;
  `has_exits` is also true for a trailing stop; `Trade.reason` can be
  `"trail"`; `cli.summarise(..., trail_pct=None)`.
- **Tests**: `test_trailing_stop.py`, `test_trailing_stop_report.py`,
  `test_cli_trailing_stop.py`, `test_cli_trailing_json.py`,
  `test_config_trailing_stop.py`, `test_web_trailing_stop.py` and
  `test_web_trailing_stop_page.py`.

### Not covered yet

- The web page's Exits card lists only the stop loss and take profit; a
  trailing stop shows in the trades table and the text report.
- The sweep, the walk-forward test and the portfolio command have no trailing
  stop (nor a stop or target).
- `tests/test_paths_agree.py` does not include the trailing stop; the tests
  above compare the flag, the config key, the API and the page instead.

### Changed

- The portfolio command's folder errors name the folder correctly:
  `Error: portfolio folder PATH does not exist` (and `... is not a folder`,
  `cannot read portfolio folder ...`) instead of `scan folder`. Exit codes are
  unchanged, and `--scan` keeps its `scan folder` wording.

### Documentation

- The **portfolio backtest** was missing from the README, the docs and this
  changelog: `python -m trading_assistant.portfolio FOLDER [--short N]
  [--long N] [--cash] [--fee] [--fee-pct] [--weights SYMBOL=PCT ...] [--json]
  [--csv OUT]`, `POST /api/portfolio` and the web page's "Portfolio backtest"
  panel. They are now described in the README and in
  [docs/cli.md](docs/cli.md). Their behaviour is not changed in this release.
- The README's layout list gains `walkforward.py`, `portfolio.py`,
  `account.py` and `data.py`; `docs/architecture.md` gains `portfolio.py` and
  `account.py`.
- Stops, targets and the trailing stop are documented together, with which
  options need candle data.

## 0.6.0 (2026-11-07)

Nothing that existed in 0.5.0 changes: the main command, `--scan`, the sweep,
the other tools, `POST /api/backtest` and `POST /api/scan` give the same
output, errors and exit codes. Everything below is new; the web page only
gains a panel.

### Added

- **Walk-forward test** `python -m trading_assistant.walkforward PRICES.csv
  --short LIST --long LIST --train N --test N [--step N] [--cash] [--fee]
  [--fee-pct] [--json] [--csv OUT]`: in each rolling window the sweep's best
  SMA pair is picked on the train bars only and backtested on the test bars
  after them, next to buy and hold on the same bars. The text shows one row per
  window, the compounded and mean test returns, compounded buy and hold, the
  windows beating buy and hold and the windows without trades, with a note when
  the test blocks are not contiguous or a window made no trades. `--json`
  prints `windows`, `summary`, `overfit_warning` and `disclaimer`; `--csv`
  writes one row per window. Exit codes as the sweep's (0, 1 data, 2 usage).
- **Library** `trading_assistant.walkforward`: `split_window`, `walk_forward`,
  `summarize`, `format_walk_forward`, `run_walk_forward`, `json_data`.
- **Web API** `POST /api/walkforward`: the same settings plus `sample` or
  `csv`; the reply is exactly the `--json` object. One request may ask for at
  most 300,000 bar-steps (413 above that).
- **Web page**: a "Walk-forward test" panel showing the same table, summary,
  notes, overfit line and disclaimer as the command.
- **Tests**: `test_walkforward_windows.py`, `test_walkforward_cli.py`,
  `test_web_walkforward.py` and `test_web_walkforward_page.py`, which check the
  command, the API and the page against each other on the same data.

## 0.5.0 (2026-11-06)

### Existing results do not change

**Running the tool on a single price file gives exactly the same results as
in 0.4.0**: the same report, the same `--json` object, the same backtest
numbers, charts, exports, error messages and exit codes. The web page's
backtest and `POST /api/backtest` are unchanged too. Everything below is new
and only runs when you ask for it. The only visible differences outside the
new features are wording:

- `--help` and the usage line printed with a usage error list the new options
  (`--scan FOLDER`, `--min-score N`, `--top N`, `--report FILE`).
- The config error for an unknown `[cli]` key lists the two new keys at the
  end: `... fill, strategy, stats, top, min_score`.
- Abbreviations: `--sc`/`--sca` now mean `--scan`, `--m` means
  `--min-score`, `--to` means `--top` and `--rep` means `--report` (before,
  they were "unrecognized arguments", also exit 2). `--t` still means
  `--take-profit` and `--re` still means `--resample`, with the same messages
  as before.

### Added

- **Indicators**: `macd(values, fast=12, slow=26, signal=9)` returns the MACD
  line, the signal line and the histogram, built on the existing `ema`;
  `bollinger_bands(values, window=20, num_std=2.0)` returns the lower, middle
  (SMA) and upper bands, with the deviation divided by the window size. Both
  return lists as long as the input, with `None` where there is not enough
  history.
- **Combined score** `signals.combined_score(closes, short=20, long=50,
  rsi_period=14)`: the sum of four parts on the last bar, each +1, 0 or -1
  (crossover: short SMA above / below the long SMA; RSI under 30 / over 70;
  MACD histogram above / below 0; last close below the lower / above the upper
  Bollinger band), a whole number from -4 to 4, returned with each part's
  contribution. A part without enough history counts 0. The existing
  `crossover_signal` is unchanged.
- **`--scan FOLDER`**: scores every `.csv` file directly inside a folder
  (not subfolders; other files ignored; the file name without `.csv` is the
  symbol) with the combined score, following `--short`, `--long` and
  `--rsi-period`, and prints a table, highest score first and equal scores in
  name order. Files that cannot be read (bad number, no `close` column, no
  rows, unreadable) are skipped and listed with a one-line reason after the
  table; they do not stop the scan. A missing folder, a folder with no `.csv`
  file, or a folder where nothing could be scored is one error line and exit
  1. `--scan` with a price file, `--backtest` or a backtest option,
  `--chart`, `--candles` or `--resample` is a usage error (exit 2).
- **`--min-score N`** and **`--top N`** (with `--scan`): keep only the rows
  scoring `N` or more, then the first `N` rows. The top line then also counts
  the files found, the rows left and the rows shown; the skipped list is
  always complete; nothing left is not an error (exit 0).
- **`--scan ... --json`**: one JSON object and nothing else, with `found`,
  `scored`, `shown`, `results` (symbol, bars, score and the four `parts`) and
  `skipped` (symbol and reason).
- **`--report FILE`** (with `--scan`): also writes a Markdown report (title,
  date, settings, the shown rows, one sentence per row explaining its score
  from its four parts, the skipped files, the disclaimer). The screen output
  does not change. A report path that is a folder, in a missing folder or one
  of the scanned price files is refused before anything is printed.
- **Config keys** `top` and `min_score` in `[cli]`, used only with `--scan`
  (ignored in other runs, like the backtest keys without `--backtest`). Flags
  win over the file; a value that is not a whole number is a config error
  naming the file (exit 1); `top = 0` is a usage error in a scan (exit 2).
  There is no key for the scan folder or the report file.
- **Web API** `POST /api/scan`: `{"files": {"NAME.csv": "csv text", ...}}`
  plus optional `min_score`, `top`, `short`, `long`, `rsi_period`, checked
  with the command line's rules. It never reads the server's disk. The reply
  is exactly the `--scan --json` object; errors are
  `{"ok": false, "error": "..."}` with the same limits as the backtest.
- **Web page**: a "Scan several files" panel to pick several CSV files, set
  the minimum score, the rows to keep and the windows, and see the ranked
  table with the four parts and the skipped files with their reasons, with the
  research-aid line visible. No inline scripts or styles.
- **Agreement tests** (`tests/test_scan_agreement.py`): four sets of files and
  seven setting combinations through the scan table, `--json`, a config file
  and `POST /api/scan`, which must give the same counts, ranking, scores,
  parts and skipped files.

### Notes

- A completely flat series scores RSI -1 (the RSI is 100 when there are no
  losses), and a perfectly straight line can score MACD -1 instead of 0
  because rounding leaves its histogram about -2e-15. Both come from the
  existing indicators and are documented in [docs/cli.md](docs/cli.md).

## 0.4.0 (2026-11-04)

### Changed (backtest results can differ from 0.3.0)

- **Stops and targets respect gaps.** When open prices are known, a bar that
  *opens* at or beyond the stop or target level now fills at that open
  instead of at the level the price jumped over. A gap down through a stop is
  therefore a worse fill than before, and a gap up through a target a better
  one. A bar that only touches a level during the bar still fills exactly at
  the level, and runs without such gaps give the same numbers as before. See
  "Stops, targets and gaps" in [docs/cli.md](docs/cli.md).
- **`--stop-loss` / `--take-profit` read the open prices** with the default
  close fills too (they already read the candle file for highs and lows), so
  the gap rule above applies without `--fill open`.
- **Buy and hold pays what the strategy pays.** The benchmark now buys on the
  first bar at that bar's fill price (its open with `--fill open`, its close
  otherwise), with the same `--slippage` added before fees. With close fills
  and no slippage it is unchanged. It stays all-in: `--position-size`, stops
  and targets never apply to it. Before, it always bought at the first close
  without slippage, which flattered it next to a strategy that paid for both.
- `run_buy_and_hold()` takes optional `fill`, `opens` and `slippage_pct`
  (defaults give the old result); `run_backtest()` passes its own settings.

### Added

- **Backtest options** (all need `--backtest`): `--fill open|close`,
  `--slippage PCT`, `--position-size FRACTION`, `--stop-loss PCT` and
  `--take-profit PCT`, plus `--candles` to read a
  `date,open,high,low,close,volume` file. Each fill records why it happened
  (`signal`, `stop` or `target`) in the report and the `--export` CSV.
  `python -m trading_assistant.samples NAME --candles` writes a sample as a
  candle file.
- **`--json`**: the report as one JSON object on stdout and nothing else
  (bars, last close, signal, RSI; with `--backtest` the settings, every fill,
  final and return figures and a benchmark object; with `--stats` the
  statistics, `null` where the text says `n/a`). Text and JSON are built from
  the same analysis call. Errors are unchanged (stderr, exit 1 or 2).
  `--json` with `--chart` is a usage error.
- **Config file keys** `slippage`, `position_size`, `fill`, `stop_loss` and
  `take_profit` in `[cli]`, with the same rules as the flags (backtest only,
  flags win over the file, out-of-range values are usage errors, a value of
  the wrong kind is a config error). `fill = open`, `stop_loss` or
  `take_profit` read the price file as a candle file, exactly like the flags.
- **Web API**: `POST /api/backtest` accepts `slippage`, `position_size`
  (a fraction), `fill`, `stop_loss` and `take_profit`, checked with the command
  line's rules and passed to the same analysis code. `fill: "open"`, a stop or
  a target use the built-in sample's candles, or read a pasted CSV as a candle
  file (a CSV without the candle columns is rejected with a one-line message).
  Settings that were given are echoed in the reply's `params`; with a stop or
  target each trade has a `reason` and `columns` gains `reason`. Requests
  without the new settings get exactly the same reply as before.
- **Web page controls** for slippage, position size (entered as a percentage
  of the account, e.g. `50`), fill price, stop loss and take profit. Fill,
  stop loss and take profit are greyed out while a pasted CSV has no
  `open`/`high`/`low` columns. The results show the fill, sizing and exit
  settings as cards, and the trades table has a Reason column.
- **Agreement tests** (`tests/test_paths_agree.py`): three candle files times
  sixteen setting combinations run through command-line flags, a config file
  and the web API, checked against the engine: same fills, final equity,
  buy-and-hold equity and statistics, and the web report equal to the command
  line's report line for line.

### Fixed

- The web server writes each request's log line (including 404s) before it
  sends the response, so a client that has its response can rely on the line
  being in the log. The line format is unchanged.

## 0.3.0 (2026-11-02)

- Indicators: WMA, DEMA, TEMA, Hull moving average, rate of change, momentum,
  rolling standard deviation, z-score, Chande momentum oscillator, TRIX, KAMA
  and linear regression slope.
- Strategies: `ema_cross`, `momentum`, `zscore_reversion` and `hull_trend`,
  available on the command line and on the web page.
- `python -m trading_assistant.drawdowns`: drawdown periods with peak, trough
  and recovery dates.
- `python -m trading_assistant.montecarlo`: seeded bootstrap of strategy returns.
- Rolling return, volatility, Sharpe ratio and drawdown (`rolling.py`).
- `python -m trading_assistant.alerts`: price and indicator rules checked on the last bar.
- `python -m trading_assistant.journal`: paper-trade journal with FIFO profit and loss.
- `python -m trading_assistant.summary`: summary of a price file.
- `--chart` prints a text chart of closes; `--config FILE` reads defaults from an INI file.
- Documentation in `docs/`: CLI reference, indicators, analysis, alerts, journal.
- The sample CSV files in the project root were removed; examples use
  `python -m trading_assistant.samples` to write a price file.

## 0.2.0 (2026-11-02)

- Backtest with trading fees (fixed and percentage) and CSV export of every bar.
- Buy-and-hold comparison alongside the strategy result.
- Forgiving CSV input (byte order mark, header case and spacing, line endings).
- Seeded sample price series.
- Local web page for running backtests in the browser.
- Strategy registry: `sma_cross`, `rsi_reversion`, `breakout`, chosen with
  `--strategy` and `--param` or the strategy picker on the web page.
- Risk and return statistics (`--stats` on the command line, a table on the web page).
- Weekly and monthly resampling (`--resample`).
- Parameter sweep (`python -m trading_assistant.sweep`).
- `python -m trading_assistant` as a shorter form of `python -m trading_assistant.cli`.

## 0.1.0

- SMA, EMA and RSI indicators.
- SMA crossover signal (BUY, SELL, HOLD).
- Command line interface.
