# Workflow: Event Bracket

Runs on the same loop as scan.md. The Event Monitor determines whether we're in a
pre-event window; if so, this workflow prepares and places the bracket.

## Step 1 — Check event window

Invoke `agents/event-monitor.md`. If `has_bracket: false`, return immediately.

## Step 2 — Prevent duplicate brackets

Before placing, check if a bracket for the same symbol+event_time already exists
in the open positions / order book (via MCP). If so, skip.

## Step 3 — Size both legs

```python
from engine.bracket import size_bracket_trade

long_leg = size_bracket_trade(
    direction="long", levels=bracket_levels,
    account_nav=nav,
    risk_pct=risk_config['risk_per_trade_pct'],
    max_position_pct=risk_config['max_position_pct'],
    leverage=risk_config['max_leverage'],
)
short_leg = size_bracket_trade(
    direction="short", levels=bracket_levels, ...
)
```

## Step 4 — Risk Guard approval (both legs)

Run `run_all_checks` for each leg independently. Both must be approved.
If either fails, do not place either (a partial bracket creates undefined risk).

## Step 5 — Place bracket orders via MCP

Place two stop-orders:
- `buy_stop` order: type=Stop, side=Buy, trigger=buy_entry, qty=long_leg.position_size
- `sell_stop` order: type=Stop, side=Sell, trigger=sell_entry, qty=short_leg.position_size

Record both order IDs with the event metadata.

## Step 6 — Hand to Trade Manager

Register the bracket (both order IDs, levels, event_time) with the Trade Manager.
The Trade Manager will:
- Cancel the losing side when one fills
- Cancel both if neither fills within 30 min of the event time

## Step 7 — Log

Symbol, event_name, event_time, buy_entry, sell_entry, range_height, order_ids, timestamp.
