# AGENTS.md — Multi-Agent Liquidity Sweep & Event-Driven Bracket

## Strategy overview

Two complementary edges, one coherent system:

1. **Liquidity sweep** — detect when price wicks through a stop-cluster (equal highs/lows,
   swing extremes) and reverses. Enter in the direction of the rejection.
2. **Event bracket** — before a scheduled event (funding reset, session open), detect a
   tight pre-event consolidation and place bracket stop-orders on both sides. The breakout
   direction is unknown; the bracket captures it.

The MCP handles all exchange I/O. `engine/` owns all math. The agents decide.

## Quick start

```bash
export BYBIT_API_KEY="..."
export BYBIT_API_SECRET="..."
export BYBIT_TESTNET="true"
bash scripts/start.sh
```

Kill switch: `bash scripts/kill_switch.sh [reason]`

## Agent roles

| Agent | File | Responsibility |
|---|---|---|
| **Orchestrator** | `agents/orchestrator.md` | State machine, routes to subagents, enforces decision hierarchy |
| **Liquidity Scanner** | `agents/liquidity-scanner.md` | Runs `engine/liquidity.scan()` on fresh klines; reports sweep signals |
| **Event Monitor** | `agents/event-monitor.md` | Watches the event schedule; detects pre-event consolidations |
| **Trade Manager** | `agents/trade-manager.md` | Manages open brackets and sweep trades; handles exits and adjustments |
| **Risk Guard** | `agents/risk-guard.md` | Cross-cutting; every trade action passes through it before execution |

**Decision hierarchy**: Risk Guard > Orchestrator > other agents.
The Risk Guard can veto any action. The Orchestrator can override sub-signals but not the Risk Guard.

## Hard risk limits — NON-NEGOTIABLE

| Parameter | Limit |
|---|---|
| max_position_pct per leg | 5% NAV |
| max_leverage | 3x |
| daily_loss_limit_pct | 2% NAV |
| max_concurrent_positions | 4 (all legs combined) |
| max_stop_pct (sweep) | 1.5% from entry |
| max_stop_pct (bracket) | 2% from entry |
| min_rr | 1.5 |

All of these are enforced in `engine/risk.py`. The agents never recompute them.

## HALT flag

Written atomically by `scripts/kill_switch.sh`. Every agent loop iteration begins:

```python
from engine.risk import check_halt
result = check_halt()
if not result.approved:
    raise SystemExit(0)
```

The agents never delete `.halt`. Only a human removes it.

## What agents MAY do

- Call MCP to fetch klines, account info, positions
- Call MCP to place / cancel orders (only after Risk Guard approval)
- Call `engine/liquidity`, `engine/bracket`, `engine/events`, `engine/risk` directly
- Read `config/`, `state/`
- Write `state/daily_pnl.json` (via `engine/risk.record_trade_pnl`)

## What agents MUST NOT do

- Compute risk, sizing, or level math themselves — always call `engine/`
- Place an order before `engine/risk.run_all_checks` returns approved
- Modify `engine/` source files
- Delete `.halt`
- Run `engine/liquidity` without fresh klines from MCP
