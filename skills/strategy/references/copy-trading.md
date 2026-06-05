# Reference: Bybit Copy-Trading

Use this when the goal is to replicate another trader's signals rather than generate
your own.

## Concept

You follow a signal provider; the exchange mirrors their entries/exits into your
account at a configured copy ratio. The MCP exposes the copy-trading endpoints.

## What still applies

- **The gate still rules.** A provider you intend to follow is a *strategy*: capture
  their historical trade stream, treat it as an equity curve, and run it through
  `engine/validation.py` + `engine/gate.py` before allocating real capital.
- **Hard risk limits are unchanged.** Copy ratio must keep per-position exposure under
  `max_position_pct` (10%) and effective leverage under 5x.
- **Decay monitoring matters more.** Providers degrade or change style; `check_decay`
  in `engine/gate.py` should run on the live copy-trading equity curve.

## MCP tools (conceptual)

- list / inspect signal providers and their track records
- start / stop following a provider, set copy ratio
- fetch the copied position and order stream

## Correlated drawdown warning

Following multiple providers does not diversify if they crowd the same trades. Treat
the *combined* copied book as one strategy when checking regime stability and drawdown.
