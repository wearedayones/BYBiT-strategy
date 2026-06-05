# Strategy Skill — Router

The agent decides *how to think*; the MCP fetches data and executes; `engine/` owns
every number that defines truth. This skill routes a request to the right workflow.

## Step 1 — Classify intent

- `research`  — find / test a new strategy
- `live`      — production loop executing signals for promoted strategies
- `status`    — report on promoted strategies and live performance

## Step 2A — Research path

1. Pick a **strategy family**: `trend | mean_reversion | carry | stat_arb | volatility`.
2. Load the matching reference:
   - `references/futures.md` — perpetual futures (BTCUSDT, ETHUSDT, …)
   - `references/spot.md` — spot markets
   - `references/copy-trading.md` — replicating a signal provider
   - `references/trading-bots.md` — delegating to a grid/DCA bot
3. Follow `workflows/research.md` — **all 8 steps are mandatory**.

## Step 2B — Live path

1. **Check the HALT flag first**: if `.halt` exists, stop immediately.
2. Follow `workflows/live-loop.md` precisely.

## Step 2C — Status path

Report per promoted strategy: name, family, symbol, OOS Sharpe, promotion date, and
90-day live Sharpe (run `engine.gate.check_decay` to flag decayed strategies).

## Permissions by mode

| Action                        | research | live |
|-------------------------------|----------|------|
| MCP: fetch klines             | yes      | yes  |
| MCP: fetch account/positions  | yes      | yes  |
| MCP: place orders             | **no**   | yes  |
| Run engine/backtest.py        | yes      | no   |
| Run engine/validation.py      | yes      | no   |
| Run engine/gate.py            | yes      | no   |
| Write strategies/promoted/    | yes*     | no   |
| Write strategies/candidates.jsonl | yes  | no   |

\* only after `engine/gate.py` returns `promote` or `replace_champion`.

## Never

- Compute trading math (Sharpe, drawdown, PBO, DSR) yourself — always call `engine/`.
- Run unvalidated strategies live — `strategies/promoted/` only.
- Weaken risk limits, delete `.halt`, or edit `engine/` and `strategies/spec.py`.
