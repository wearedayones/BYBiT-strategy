# AGENTS.md — Bybit Quant Agent

The MCP executes; it never decides. `engine/` owns every number that defines truth.
The agent's job is the *thinking* (which strategy, which workflow) — not the math, and
not the order plumbing.

## Quick start

```bash
bash scripts/research.sh      # research mode — generate & validate strategies
bash scripts/trade.sh         # live mode — run promoted strategies only
bash scripts/kill_switch.sh   # emergency: HALT flag + flatten everything
```

## Modes

### research
Generates, backtests, validates, and gates strategies. **Places no real orders.**
Reads `config/settings.yaml` (`mode: research`) and routes via `skills/strategy/SKILL.md`.
Writes to `strategies/candidates.jsonl` and — only on gate pass — `strategies/promoted/`.

### live
Monitors positions and executes signals from **promoted strategies only**.
If `strategies/promoted/` is empty, the agent does nothing and exits.
Checks the HALT flag first on every loop iteration.

## MCP authentication

```bash
export BYBIT_API_KEY="..."
export BYBIT_API_SECRET="..."
export BYBIT_TESTNET="true"     # "false" for mainnet
```

The MCP server endpoint is set in `config/settings.yaml → mcp_server`. The MCP handles
klines, market data, account, positions, order placement, websocket streams, and
copy-trading. The agent calls the MCP for all of it and reconstructs none of it by hand.

## Hard risk limits — NON-NEGOTIABLE

The LLM cannot override these. They are enforced in `strategies/spec.py` Pydantic
validators **and** re-checked in `skills/strategy/workflows/live-loop.md` Step 5.

| Parameter             | Hard limit  |
|-----------------------|-------------|
| max_leverage          | 5x          |
| max_position_pct      | 10% of NAV  |
| daily_loss_limit_pct  | 2% of NAV   |

If the daily loss limit is hit, the agent MUST trigger the kill switch immediately and
stop all activity for the calendar day.

## Kill switch

Trigger: `bash scripts/kill_switch.sh [reason]`

What it does, in order (it does **not** depend on the agent cooperating):
1. Writes the `.halt` flag atomically to the project root.
2. Cancels all open orders via direct REST (`scripts/_flat_positions.py`).
3. Market-closes all positions via direct REST.
4. Logs timestamp and reason to `.halt.log`.

How the agent checks it (every live iteration):

```python
import os
if os.path.exists(".halt"):
    raise SystemExit(0)   # do nothing — no orders, no signals, no decisions
```

The agent never deletes `.halt`. Only a human removes it to resume trading.

## The agent MAY

- Call MCP tools to fetch klines, account info, and positions.
- Call MCP tools to place orders — **live mode, promoted strategies only**.
- Run `engine/backtest.py`, `engine/validation.py`, `engine/gate.py`.
- Read/write `strategies/candidates.jsonl` and `strategies/promoted/`.
- Read `config/`.

## The agent MUST NOT

- Compute trading math (Sharpe, drawdown, PBO, DSR) itself — always call `engine/`.
- Run unvalidated strategies in live mode — `promoted/` only.
- Override or weaken risk limits.
- Delete the `.halt` file.
- Edit `engine/backtest.py`, `engine/validation.py`, `engine/gate.py`, or `strategies/spec.py`.
- Place orders in research mode, or ignore the HALT flag.

## Rule that survives the minimalism

> **Live mode loads ONLY `strategies/promoted/`.** It never instantiates a strategy
> from the agent's context window. If `promoted/` is empty, the agent exits cleanly.
> The moment the gate's math runs through the LLM or an external tool, "it passed"
> stops meaning anything — so `engine/` stays pure Python with tests.
