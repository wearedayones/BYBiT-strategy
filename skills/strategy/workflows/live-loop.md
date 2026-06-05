# Workflow: Live Loop (pre-close execution)

Runs on a schedule, timed just before candle close. The MCP executes; it never decides.

## Step 0 — HALT check (mandatory first step)

```python
import os
if os.path.exists(".halt"):
    print("HALT flag set — skipping all execution.")
    raise SystemExit(0)
```

The agent never deletes `.halt`. Only a human removes it.

## Step 1 — Load promoted strategies

```python
import json
from pathlib import Path
promoted = [json.loads(f.read_text()) for f in Path("strategies/promoted").glob("*.json")]
if not promoted:
    print("No promoted strategies. Exiting.")
    raise SystemExit(0)
```

Live mode loads **only** from `strategies/promoted/`. It never instantiates a spec
from the agent's context window.

## Step 2 — Daily loss limit

Via MCP, fetch account NAV and today's PnL. If daily PnL ≤ −`daily_loss_limit_pct`
(2%) of NAV, run `bash scripts/kill_switch.sh daily_loss_limit` and exit.

## Step 3 — Pull positions and klines (MCP)

For each promoted strategy: fetch its current position and the latest N klines for
`strategy.symbol` / `strategy.timeframe`.

## Step 4 — Trade-validator subagent

For each strategy, invoke `subagents/trade-validator.md` with the klines, current
position, and spec. It returns `{action, size_pct, confidence, reason}`.

## Step 5 — Hard-limit gate (final check)

Before any order, verify against the NON-NEGOTIABLE limits:
- `size_pct ≤ strategy.risk.max_position_pct` (and ≤ 10% absolute)
- effective leverage ≤ `strategy.risk.leverage` (and ≤ 5x absolute)
- block new `buy`/`sell` if the daily loss limit is being approached

Cap or veto the subagent's output here. The subagent is advisory only.

## Step 6 — Execute via MCP

For `action` in `buy | sell | flatten`, call the MCP to place a market order
(symbol, side, qty). `hold` does nothing.

## Step 7 — Log

Append `timestamp, strategy_name, action, size, price, order_id` to the live trade log.
