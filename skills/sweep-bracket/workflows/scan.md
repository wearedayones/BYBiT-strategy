# Workflow: Sweep Scan

Runs on the primary timeframe scan interval (default: every 5 minutes).

## Inputs needed before starting

- Fresh klines from MCP for each symbol in `settings.symbols`
- Current open positions from MCP
- Current account NAV from MCP

## Step 1 — Quick risk pre-check

```python
from engine.risk import check_halt, check_daily_loss
halt = check_halt()
if not halt.approved: exit(0)
loss_check = check_daily_loss(nav, risk_config['daily_loss_limit_pct'])
if not loss_check.approved: trigger_kill_switch(loss_check.reason)
```

## Step 2 — Run Liquidity Scanner (per symbol)

For each symbol, invoke `agents/liquidity-scanner.md` with:
- klines (primary + HTF)
- settings from config

Collect all `has_signal: true` results.

## Step 3 — Prioritise signals

If multiple sweep signals exist, rank by `confidence` descending.
Cap at 2 new sweep trades per loop (avoid chasing).

## Step 4 — Size and validate each signal

For each signal:

```python
from engine.bracket import size_bracket_trade
from engine.risk import run_all_checks

# Use sweep-specific sizing (not bracket sizing)
from engine.risk import RiskCheck
stop_dist = abs(signal['entry_price'] - signal['stop_price'])
risk_amt = nav * risk_config['risk_per_trade_pct']
qty = risk_amt / stop_dist if stop_dist > 0 else 0.0

check = run_all_checks(
    entry_price=signal['entry_price'],
    stop_price=signal['stop_price'],
    qty=qty,
    rr=abs(signal['entry_price'] - signal['target1_price']) / stop_dist,
    account_nav=nav,
    open_positions=len(current_positions),
    limits=risk_config,
)
```

## Step 5 — Execute approved signals via MCP

For each approved signal, place a market order:
- direction = "Buy" if signal.direction == "long" else "Sell"
- qty = computed above
- Immediately place a stop-loss order at `stop_price`

## Step 6 — Log

Append to the trade log: symbol, direction, entry, stop, targets, qty, confidence, timestamp.
