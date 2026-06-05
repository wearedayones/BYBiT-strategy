# Reference: Bybit Linear Perpetual Futures

Use this when `spec.family` targets perpetual contracts (BTCUSDT, ETHUSDT, SOLUSDT, …).

## What makes perps different

- **Funding rate**: paid/received every 8 hours. Positive funding ⇒ longs pay shorts.
  `engine/backtest.py` already deducts funding via `CostParams.funding_rate_8h` and
  `_bars_per_8h(timeframe)`. A `carry` family strategy exploits persistent funding.
- **Mark price vs index price**: liquidations trigger off mark price, not last trade.
  Conservative backtests should assume fills at close and stops at mark.
- **Liquidation cascades**: in high leverage, stop runs feed on themselves. Keep
  `risk.leverage` modest; the hard cap is 5x and the schema enforces it.

## MCP tools you will call (conceptual — names per your MCP server)

- fetch klines / OHLCV for a symbol + timeframe
- fetch funding-rate history
- fetch tickers / mark price
- fetch account balance and open positions
- place / cancel orders (live mode only)

The MCP performs all of these. The agent never reconstructs this data by hand and
never computes Sharpe/PBO/DSR — that is `engine/`'s job.

## Sane defaults

- Timeframe `"15"` is a good research default: enough samples, manageable noise.
- Pull **at least 1 year** of klines so CPCV has enough bars per fold.
- Fees: VIP0 taker ≈ 5.5 bps, maker ≈ 2 bps; the gate re-runs at `cost_multiplier`× to test robustness.
