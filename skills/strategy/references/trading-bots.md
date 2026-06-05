# Reference: Bybit Trading Bots (Grid / DCA)

Use this when deciding whether to delegate execution to a Bybit-native bot (grid, DCA,
martingale) instead of running a custom strategy loop.

## When a native bot is the right call

- The edge is **mechanical and range-bound** (grid in a sideways regime) and does not
  need custom signal logic.
- You want the exchange to manage the ladder of orders rather than the live loop.

## When to keep it custom

- The thesis depends on signals the bot can't express (cross-asset, funding-aware,
  regime-switching). Then run `workflows/live-loop.md` with your promoted spec.

## The gate still applies

A grid/DCA configuration is a strategy with parameters (grid spacing, levels, range).
Backtest it through `engine/backtest.py` (or a grid-aware extension), validate, and gate
it before funding. Do not deploy a bot config that hasn't passed `acceptance.yaml`.

## MCP tools (conceptual)

- create / configure / stop a grid or DCA bot
- fetch bot status and realized PnL

## Risk

Grid/DCA bots hide tail risk: they average into losers. Stress the backtest hard
(`cost_multiplier`, regime split) — a strong sideways Sharpe can mask a brutal
trend-day drawdown that breaches `max_drawdown`.
