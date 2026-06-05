# Reference: Bybit Spot

Use this when researching spot markets rather than perpetuals.

## Differences from perps

- **No funding rate**: set `CostParams.funding_rate_8h = 0.0` when backtesting spot.
- **No leverage by default**: `risk.leverage = 1.0`. Borrowing/margin is a separate
  product; do not assume it.
- **Fee structure**: maker/taker still apply; rebates differ from derivatives.
- **No liquidation**: you can only lose what you hold, which changes risk sizing.

## MCP tools (conceptual)

- fetch spot klines / OHLCV
- fetch order book depth
- fetch account spot balances
- place / cancel spot orders (live mode only)

## Notes

- `mean_reversion` and `trend` families both work on spot; `carry` does not (no funding).
- Spot Sharpe tends lower than perps for the same edge because there is no leverage —
  size `max_position_pct` accordingly, still under the 10% hard cap.
