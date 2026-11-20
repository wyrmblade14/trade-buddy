# Paper-trade journal

A manual record of trades you made on paper, kept in a CSV file you name. It
only reads and writes that file. It does not connect to anything.

## File format

```
date,symbol,side,qty,price,fee,note
2026-01-02,AAPL,buy,10,100.0,1.0,
2026-01-05,AAPL,buy,10,110.0,1.0,"add, more"
```

- `date`: `YYYY-MM-DD`, a real calendar date.
- `symbol`: one word, stored upper-case.
- `side`: `buy` or `sell`.
- `qty`: positive whole number.
- `price`: positive number.
- `fee`: zero or more (empty counts as 0).
- `note`: free text (quoted if it holds a comma).

Rows are replayed in file order. A file with a bad row is a data error that
names the line, for example `Error: j.csv: line 4: bad side 'hold'; use buy or
sell`.

## Commands

```
python -m trading_assistant.journal FILE add --date D --symbol S --side buy|sell --qty Q --price P [--fee F] [--note TEXT]
python -m trading_assistant.journal FILE list [--symbol S]
python -m trading_assistant.journal FILE summary [--mark SYMBOL=PRICE ...]
```

- `add` appends a row and creates the file with a header if it is missing.
  The whole file is checked first; a sell larger than the open quantity is
  rejected with exit 1 and the file is left unchanged (no shorting).
- `list` prints the trades, optionally for one symbol.
- `summary` prints, per symbol, the open quantity, average cost, realized P&L,
  and (when a `--mark` price is given for an open symbol) unrealized P&L, then
  totals. Marks for symbols with no trades are noted on stderr and ignored.
  Open symbols without a mark are left out of the unrealized total, and the
  totals line says how many.

Exit codes: 0 success; 1 data problem (unreadable file, bad row with its line
number, oversell); 2 usage problem (bad option value, missing command).

## FIFO rules

- Each buy is a lot. A buy's fee is added to the lot's cost and spread evenly
  over its shares.
- A sell uses the oldest lots first and may use part of a lot. Its fee is
  subtracted from its proceeds.
- Realized P&L = proceeds (after fee) minus the cost of the shares sold.
- Average cost = cost of the open shares (fees included) / open quantity.
- Unrealized P&L = open quantity x mark price minus the open cost.

## Worked example

```
journal.csv add: buy 10 @ 100 fee 10     lot A cost 1010 (101 per share)
                 buy 10 @ 110 fee 20     lot B cost 1120 (112 per share)
                 sell 15 @ 120 fee 6
```

The sell takes all 10 shares of lot A and 5 of lot B. Proceeds are
15 x 120 - 6 = 1794. Cost is 10 x 101 + 5 x 112 = 1570. Realized P&L is +224.
Open: 5 shares costing 560, average cost 112. With `--mark AAA=125`, unrealized
P&L is 5 x 125 - 560 = +65.

```
Symbol   Open qty     Avg cost     Realized         Mark   Unrealized
AAA             5     112.0000      +224.00     125.0000       +65.00
Total realized +224.00, unrealized +65.00
Research aid only. Not financial advice.
```
