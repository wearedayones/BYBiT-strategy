# Skill: Liquidity Sweep & Event Bracket

## Purpose

Route incoming intent to the correct workflow for this strategy.

## Step 1 — Determine intent

| User intent | Route to |
|---|---|
| "Start / run the strategy" | `workflows/scan.md` + `workflows/bracket.md` (both active) |
| "Close everything / stop now" | `workflows/unwind.md` |
| "What's open / status" | Fetch MCP positions + read `state/daily_pnl.json` |
| "Explain a signal" | Describe the sweep or bracket that generated it (don't re-run) |

## Step 2 — Load config

Always load `config/settings.yaml` and `config/risk.yaml` at the start of any workflow.
Never hardcode thresholds.

## Step 3 — HALT check

Before anything else:
```python
from engine.risk import check_halt
if not check_halt().approved:
    print("System halted. Remove .halt to resume.")
    raise SystemExit(0)
```

## Agent invocation order (every loop)

1. **Risk Guard** — check HALT and daily loss (fail-fast)
2. **Liquidity Scanner** — sweep signals (parallel with step 3)
3. **Event Monitor** — bracket signals (parallel with step 2)
4. **Orchestrator** — combine signals, apply priority rules
5. **Risk Guard** — approve/reject each proposed action
6. **MCP** — execute approved orders
7. **Trade Manager** — manage all open positions

## Never

- Skip the Risk Guard
- Run engine math without MCP-fresh klines
- Place orders outside of an approved Risk Guard response
