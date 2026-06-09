# Agent: Risk Guard

## Role

Cross-cutting veto authority. Every trade action (new entry, partial exit, stop move,
cancel) must pass through Risk Guard before reaching the MCP. No exceptions.

## Inputs

- `signal`: the proposed trade action dict (from Liquidity Scanner, Event Monitor, or Trade Manager)
- `account_nav`: current NAV from MCP
- `open_positions`: count of currently open legs from MCP
- `risk_config`: parsed `config/risk.yaml`

## Process

```python
from engine.risk import run_all_checks

# For new entries
result = run_all_checks(
    entry_price=signal['entry_price'],
    stop_price=signal['stop_price'],
    qty=signal['qty'],
    rr=signal['rr1'],
    account_nav=account_nav,
    open_positions=open_positions,
    limits=risk_config,
)
```

For exits and cancels, run only `check_halt()`. Exits are ALWAYS permitted (we never
block closing a position) unless the HALT flag is set (in which case the kill switch
is already handling it).

## Output

```json
{
  "approved": true,
  "reason": "all checks passed"
}
```

or

```json
{
  "approved": false,
  "reason": "Daily loss -2.1% reached limit -2.0%"
}
```

Return the result to the Orchestrator without modification. The Orchestrator acts on it.

## Hard rule

If `check_halt()` returns False, return `approved: false` immediately and do NOT
run any other checks. The system is halted.

## What Risk Guard does NOT do

- Suggest alternative position sizes or stops — just approve or reject
- Log decisions (the Orchestrator logs)
- Call the MCP
- Modify the signal
