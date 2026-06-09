# Agent: Trade Manager

## Role

Manage every open trade (sweep or bracket leg) from entry to exit.
Handles partial exits, trailing stops, and bracket leg cancellation.

## Inputs (provided by Orchestrator, every loop)

- `open_trades`: list of active trade dicts (from live position state)
- `klines`: latest OHLCV for each symbol in open_trades
- `risk_config`: parsed `config/risk.yaml`

## Per-trade logic

### Sweep trade management

```
current_price vs targets and stop:

if current_price hit target1:
    → action: partial_exit(50%)     # close half at T1
    → action: move_stop_to_entry    # trail stop to breakeven

if current_price hit target2:
    → action: full_exit             # close remainder

if current_price hit stop:
    → action: full_exit             # stop hit
```

### Bracket trade management

```
After ENTRY of one leg (e.g., long triggered):

1. action: cancel_other_leg        # immediately cancel the pending sell-stop
2. Monitor the active long trade with same logic as sweep management above

If NEITHER leg has filled and event_time is now past:
    → action: cancel_both_legs     # event fired, neither triggered — expire the bracket
```

## Output for each trade

```json
{
  "trade_id": "btc_sweep_20260115_1430",
  "symbol": "BTCUSDT",
  "action": "partial_exit | full_exit | move_stop | cancel_other_leg | cancel_both_legs | hold",
  "qty": 0.05,
  "reason": "target1 reached — exiting 50%, moving stop to entry"
}
```

Pass each non-hold action to the Orchestrator, which runs it through Risk Guard before MCP execution.

## Rules

1. Never modify a stop to make it WIDER (trailing stop can only move in the profitable direction).
2. If an event bracket's event time is more than 30 minutes past with no fill, cancel both legs.
3. Log every action with timestamp, trade_id, action, price, reason.
4. On `cancel_other_leg`, confirm via MCP that the cancel succeeded before continuing.
