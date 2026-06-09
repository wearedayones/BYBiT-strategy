# Workflow: Unwind

Graceful shutdown. Closes all open positions and cancels all pending orders
without triggering the HALT flag. Use this for a planned stop at end-of-day
or when manually pausing. Use `scripts/kill_switch.sh` for an emergency.

## Step 1 — Cancel all pending bracket orders

Via MCP: cancel every open stop-order for all symbols in `settings.symbols`.
Confirm each cancellation before proceeding.

## Step 2 — Close all open positions (market)

Via MCP: for each open position, place a reduceOnly market order to close.

## Step 3 — Wait for confirmation

Poll MCP positions until all are zero (max 30 seconds, 3 retries).
If any position remains open after retries, alert and set HALT flag manually.

## Step 4 — Update daily PnL state

```python
from engine.risk import record_trade_pnl
# Call once per closed trade with realised PnL
record_trade_pnl(pnl_delta=realised_pnl, nav_current=current_nav)
```

## Step 5 — Log

Final P&L summary: trades closed, total realised PnL, final NAV, timestamp.

## Unwind vs kill switch

| | Unwind | Kill switch |
|---|---|---|
| Sets HALT flag | No | Yes |
| Requires manual HALT removal | No | Yes |
| Speed | Careful (confirm each) | Immediate market orders |
| Use case | Planned stop | Emergency |
