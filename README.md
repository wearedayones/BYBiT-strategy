# Multi-Agent Liquidity Sweep & Event-Driven Bracket

Two complementary edges, one coherent system built on top of the Bybit MCP.

## The two edges

**Liquidity sweep** — crypto markets regularly hunt stop clusters before reversing.
Equal highs, equal lows, and swing extremes accumulate stops. When price wicks through
one of these levels and closes back on the originating side, the stops are cleared and
the order flow reverses. `engine/liquidity.py` detects the wick-through and rejection;
the Liquidity Scanner agent filters for confidence and freshness.

**Event bracket** — before funding resets (00:00/08:00/16:00 UTC) and major session opens,
price often consolidates in a tight range as participants square up. The breakout
direction is unpredictable — so we bracket it. `engine/bracket.py` detects the
consolidation and computes the bracket levels; `engine/events.py` owns the schedule.
When one side fills, the other is immediately cancelled.

## Architecture

```
agents/
  orchestrator.md       # state machine + decision hierarchy
  liquidity-scanner.md  # calls engine/liquidity.scan(); reports sweep signals
  event-monitor.md      # calls engine/events + engine/bracket; reports bracket specs
  trade-manager.md      # partial exits, trailing stops, bracket leg cancellation
  risk-guard.md         # cross-cutting veto; every order passes through here

engine/                 # deterministic pure Python — no LLM, no MCP
  liquidity.py          # swing detection, equal-level clustering, sweep detection, order blocks
  bracket.py            # consolidation detection, bracket level math, position sizing
  events.py             # funding + session event schedule, pre-event window detection
  risk.py               # all hard limits, daily loss tracking, HALT check

skills/sweep-bracket/
  SKILL.md              # router + agent invocation order
  workflows/scan.md     # sweep scan loop
  workflows/bracket.md  # bracket placement workflow
  workflows/unwind.md   # graceful shutdown

config/
  settings.yaml         # symbols, timeframes, sweep + bracket parameters
  risk.yaml             # hard limits (5% NAV, 3x leverage, 2% daily loss)

state/
  daily_pnl.json        # persisted daily P&L state (reset at 00:00 UTC)

scripts/
  kill_switch.sh        # HALT flag + immediate flatten (no agent dependency)
  start.sh              # prerequisite check + handoff
```

## Quick start

```bash
pip install -e ".[dev]"
pytest                          # verify engine

export BYBIT_API_KEY="..."
export BYBIT_API_SECRET="..."
export BYBIT_TESTNET="true"
bash scripts/start.sh           # hands off to agent
```

Emergency stop at any time: `bash scripts/kill_switch.sh`

## Hard limits (non-negotiable)

All enforced in `engine/risk.py`. The agent calls these; it never recomputes them.

| Limit | Value |
|---|---|
| Position size per leg | 5% of NAV |
| Max leverage | 3x |
| Daily loss limit | 2% of NAV → kill switch |
| Max concurrent positions | 4 legs |
| Min R:R | 1.5 |
| Max stop distance (sweep) | 1.5% |
| Max stop distance (bracket) | 2% |
