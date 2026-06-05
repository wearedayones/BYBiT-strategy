# Workflow: Research

**All 8 steps are mandatory. Do not skip or reorder.** The agent decides; the MCP
fetches data; `engine/` computes every number that defines truth.

## Step 1 — Write the thesis

Before any code, write a thesis of at least ~50 words answering:
- What market inefficiency are you exploiting?
- Which regime does it depend on (trending / ranging / high-vol / low-vol)?
- Why does the edge persist (structure, flows, funding, behavior)?

Generic theses ("buy low sell high", lorem ipsum) are **rejected by `strategies/spec.py`**.

## Step 2 — Build the StrategySpec

Construct a `StrategySpec` that passes validation:

```python
from strategies.spec import StrategySpec, RiskParams
spec = StrategySpec(
    thesis="<your thesis>",
    name="ema_cross_btc_v1",
    family="trend",                 # trend | mean_reversion | carry | stat_arb | volatility
    symbol="BTCUSDT",
    timeframe="15",
    parameters={"fast_period": 10, "slow_period": 30},
    entry_logic="Long when 10-period MA crosses above 30-period MA on close",
    exit_logic="Exit on reverse cross or stop/take-profit",
    risk=RiskParams(stop_loss_pct=0.02, take_profit_pct=0.04,
                    max_position_pct=0.05, leverage=2.0),
)
```

## Step 3 — Pull klines via MCP

Call the MCP to fetch **at least 1 year** of OHLCV for `spec.symbol` / `spec.timeframe`.
Normalize to a list of dicts with keys: `ts, open, high, low, close, volume`.

## Step 4 — Backtest

```python
from engine.backtest import run_backtest, CostParams
result = run_backtest(klines, spec)
base_sharpe = result.summary["sharpe"]
```

Also run a stressed backtest for the robustness check:

```python
import yaml
acc = yaml.safe_load(open("config/acceptance.yaml"))
stressed = run_backtest(klines, spec, cost_params=CostParams(
    taker_fee=0.00055 * acc["cost_multiplier"],
    slippage_bps=5.0 * acc["cost_multiplier"],
))
stressed_sharpe = stressed.summary["sharpe"]
```

## Step 5 — Validate (CPCV + DSR + PBO + regime/robustness)

Build a `returns_matrix` of shape `(T, N)` from **N parameter variants** of the spec
(e.g., a small grid around `fast_period`/`slow_period`) — PBO requires `N ≥ 2`.
`n_trials` is the global trial counter from `strategies/candidates.jsonl` (trial-aware DSR).

```python
from engine.validation import validate_strategy
val = validate_strategy(
    equity_curve=result.equity_curve,
    returns_matrix=returns_matrix,
    n_trials=n_trials,
    base_sharpe=base_sharpe,
    stressed_sharpe=stressed_sharpe,
    acceptance=acc,
)
```

> Note: `validate_strategy` runs CPCV on the equity-curve returns from the full
> backtest. For higher fidelity, re-run `run_backtest` on each CPCV fold's klines
> separately and feed those fold Sharpes in via the `backtest_fn` injection point.

## Step 6 — Gate

```python
from engine.gate import run_gate
gate = run_gate(
    strategy_name=spec.name, symbol=spec.symbol, family=spec.family,
    oos_sharpe=val.cpcv.mean_oos_sharpe,
    max_drawdown=result.summary["max_drawdown"],
    n_trades_oos=int(result.summary["n_trades"]),
    validation=val,
)
```

## Step 7 — If PASS, promote

If `gate.action` is `promote` or `replace_champion`:
- Write `spec` JSON to `strategies/promoted/{spec.name}.json`, including `oos_sharpe`,
  `max_drawdown`, `dsr`, `pbo`, and the promotion timestamp.
- Append a `status: "promoted"` line to `strategies/candidates.jsonl`.
- Report the promoted spec.

## Step 8 — Always log to candidates.jsonl

Whether passed or rejected, append one JSON line:

```json
{"name": "...", "family": "...", "symbol": "...", "timeframe": "...",
 "status": "rejected", "oos_sharpe": 0.31, "max_drawdown": 0.22, "n_trades_oos": 47,
 "dsr": 0.41, "pbo": 0.61, "cpcv_mean_sharpe": 0.29,
 "failure_reasons": ["PBO 0.61 > ceiling 0.45"], "trial_number": 3,
 "timestamp": "2026-01-15T14:23:01Z", "thesis": "..."}
```

If within `research_budget`, adjust **parameters** (not the thesis) and return to Step 2.
If the thesis itself was wrong, write a new thesis. If the budget is exhausted, stop and report.
