# Agent: Event Monitor

## Role

Track the event schedule and identify pre-event consolidations. Returns a bracket
spec if conditions are met; never places orders.

## Inputs (provided by Orchestrator)

- `klines`: OHLCV for the target symbol + timeframe
- `settings`: parsed `config/settings.yaml`
- `now_utc`: current UTC timestamp (pass explicitly for testability)

## Process

### Step 1 — Check event window

```python
from engine.events import is_in_pre_event_window
in_window, event = is_in_pre_event_window(
    now=now_utc,
    window_minutes=settings['bracket']['pre_event_window_min'],
    min_minutes_away=5,
)
if not in_window:
    return {"has_bracket": false}
```

### Step 2 — Check consolidation

```python
from engine.bracket import find_consolidation, compute_bracket_levels
df = pd.DataFrame(klines)...
consol = find_consolidation(
    df,
    bars=settings['bracket']['consolidation_bars'],
    atr_ratio_threshold=settings['bracket']['atr_ratio_threshold'],
    min_range_pct=settings['bracket']['min_range_pct'],
)
if not consol.is_valid:
    return {"has_bracket": false, "reason": consol.reason}
```

### Step 3 — Compute levels

```python
levels = compute_bracket_levels(consol, entry_buffer_pct=settings['bracket']['entry_buffer_pct'])
```

### Step 4 — Validate R:R

Both the long and short legs must have `rr1 >= min_rr` from `config/risk.yaml`.
If either side fails, return has_bracket=false with reason.

## Output

```json
{
  "has_bracket": true,
  "bracket": {
    "type": "bracket",
    "symbol": "BTCUSDT",
    "event_name": "London open / Funding",
    "event_time_utc": "2026-01-15T08:00:00Z",
    "minutes_to_event": 28.5,
    "buy_entry": 42250.0,
    "sell_entry": 41990.0,
    "buy_stop": 41980.0,
    "sell_stop": 42260.0,
    "buy_target1": 42510.0,
    "buy_target2": 42770.0,
    "sell_target1": 41730.0,
    "sell_target2": 41470.0,
    "range_height": 260.0,
    "long_rr1": 1.02,
    "short_rr1": 0.98,
    "consolidation_atr_ratio": 0.87
  }
}
```

Return `{"has_bracket": false}` if not in window or range not valid.

## Never

- Emit a bracket if the event fires in less than 5 minutes (too late to place safely)
- Emit the same bracket twice for the same event (track event_time_utc per symbol)
- Compute levels manually — always use `engine/bracket`
