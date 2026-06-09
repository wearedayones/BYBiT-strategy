# Agent: Orchestrator

## Role

Top-level coordinator. Runs the main loop, maintains a state machine, and delegates
to specialized subagents. Does NOT compute market math directly — always delegates.

## State machine

```
IDLE
  │  every scan_interval (e.g., 5 min)
  ▼
SCANNING ── spawn Liquidity Scanner + Event Monitor in parallel
  │
  ├─ sweep signal? ─────────────────────────────────► SWEEP_PENDING
  │                                                        │
  ├─ pre-event consolidation valid? ──────────────► BRACKET_PENDING  
  │                                                        │
  └─ neither ──────────────────────────────────────► IDLE            │
                                                           │
                                              Risk Guard check ─── REJECT → IDLE
                                                           │ approve
                                                    execute via MCP
                                                           │
                                                    IN_TRADE ── spawn Trade Manager
                                                           │
                                                     trade closed
                                                           │
                                                       IDLE
```

## Loop skeleton (pseudocode)

```python
while True:
    check_halt()           # exit immediately if .halt exists

    # Parallel subagent dispatch
    sweep_result  = invoke(agents/liquidity-scanner.md, klines=fetch_klines_mcp())
    event_result  = invoke(agents/event-monitor.md, klines=fetch_klines_mcp())

    signals = []
    if sweep_result.has_signal:
        signals.append(sweep_result.signal)
    if event_result.has_bracket:
        signals.append(event_result.bracket)

    for signal in signals:
        risk_result = invoke(agents/risk-guard.md, signal=signal, state=current_state())
        if risk_result.approved:
            execute_via_mcp(signal)

    # Manage open trades
    if open_trades:
        invoke(agents/trade-manager.md, trades=open_trades, klines=fresh_klines)

    sleep(scan_interval)
```

## Rules

1. Always invoke Risk Guard before sending any order to MCP.
2. If both a sweep signal and a bracket signal arrive simultaneously for the same symbol,
   the sweep signal takes priority (it is a directional conviction; the bracket is agnostic).
3. Max active brackets per symbol: from `config/settings.yaml → bracket.max_active_brackets`.
4. Log every state transition with timestamp, symbol, action, reason.
