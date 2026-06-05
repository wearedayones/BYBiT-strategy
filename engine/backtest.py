"""
Deterministic backtesting engine.

Rules:
- No random state. Same inputs always produce same outputs.
- No external calls. All math is numpy/pandas only.
- Signal generation dispatched on spec.family via spec.parameters.
"""
from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np
import pandas as pd

from strategies.spec import StrategySpec


@dataclasses.dataclass
class CostParams:
    maker_fee: float = 0.0002       # 2 bps — Bybit VIP0 maker
    taker_fee: float = 0.00055      # 5.5 bps — Bybit VIP0 taker
    slippage_bps: float = 5.0       # half-spread estimate for limit misses
    funding_rate_8h: float = 0.0001 # typical perpetual funding (positive = longs pay)
    use_market_orders: bool = True

    @property
    def entry_cost(self) -> float:
        base = self.taker_fee if self.use_market_orders else self.maker_fee
        return base + self.slippage_bps * 1e-4

    @property
    def exit_cost(self) -> float:
        return self.taker_fee + self.slippage_bps * 1e-4


@dataclasses.dataclass
class BacktestResult:
    equity_curve: pd.Series
    trade_log: list[dict[str, Any]]
    summary: dict[str, float]


def ohlcv_to_dataframe(klines: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(klines)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def compute_signals(df: pd.DataFrame, spec: StrategySpec) -> pd.Series:
    """Return a Series of {-1, 0, 1} with the same index as df."""
    p = spec.parameters
    signals = pd.Series(0, index=df.index, dtype=int)

    if spec.family == "trend":
        fast = int(p.get("fast_period", 10))
        slow = int(p.get("slow_period", 30))
        ma_fast = df["close"].rolling(fast).mean()
        ma_slow = df["close"].rolling(slow).mean()
        signals = np.sign(ma_fast - ma_slow).fillna(0).astype(int)

    elif spec.family == "mean_reversion":
        period = int(p.get("bb_period", 20))
        n_std = float(p.get("bb_std", 2.0))
        mid = df["close"].rolling(period).mean()
        std = df["close"].rolling(period).std()
        upper = mid + n_std * std
        lower = mid - n_std * std
        signals[df["close"] < lower] = 1
        signals[df["close"] > upper] = -1

    elif spec.family == "carry":
        # Proxy: persistent price rise implies positive funding (longs pay) → go short for carry
        funding_thresh = float(p.get("funding_thresh", 0.0002))
        lookback = int(p.get("lookback", 3))
        ret = df["close"].pct_change(lookback)
        signals[ret > funding_thresh] = -1
        signals[ret < -funding_thresh] = 1

    # stat_arb and volatility families are stubs; extend by populating spec.parameters
    return signals


def run_backtest(
    klines: list[dict],
    spec: StrategySpec,
    cost_params: CostParams | None = None,
    initial_capital: float = 10_000.0,
) -> BacktestResult:
    if cost_params is None:
        cost_params = CostParams()

    df = ohlcv_to_dataframe(klines)
    signals = compute_signals(df, spec)
    bars_per_8h = _bars_per_8h(spec.timeframe)

    position = 0.0
    entry_price = 0.0
    entry_ts: Any = None
    capital = initial_capital
    equity: list[float] = []
    trade_log: list[dict[str, Any]] = []
    funding_counter = 0

    for i in range(len(df)):
        row = df.iloc[i]
        ts = df.index[i]
        price = float(row["close"])
        sig = int(signals.iloc[i])
        funding_counter += 1

        # Funding payment every 8h
        if funding_counter >= bars_per_8h and position != 0:
            funding_cost = abs(position) * price * cost_params.funding_rate_8h
            capital -= funding_cost if position > 0 else -funding_cost * 0.5
            funding_counter = 0

        # Exit on signal flip or signal → 0
        if position != 0 and (sig == 0 or np.sign(sig) != np.sign(position)):
            pnl = position * (price - entry_price)
            cost = abs(position) * price * cost_params.exit_cost
            net = pnl - cost
            capital += net
            trade_log.append({
                "entry_ts": entry_ts, "exit_ts": ts,
                "direction": "long" if position > 0 else "short",
                "entry_price": entry_price, "exit_price": price,
                "pnl": net,
                "return_pct": net / (abs(position) * entry_price),
                "exit_reason": "signal",
            })
            position = 0.0

        # Enter new position
        if sig != 0 and position == 0:
            size = (capital * spec.risk.max_position_pct * spec.risk.leverage) / price
            capital -= size * price * cost_params.entry_cost
            position = size if sig == 1 else -size
            entry_price = price
            entry_ts = ts

        # Stop-loss / take-profit
        if position != 0 and entry_price > 0:
            ret = (price - entry_price) / entry_price * np.sign(position)
            hit: str | None = None
            if ret <= -spec.risk.stop_loss_pct:
                hit = "stop_loss"
            elif ret >= spec.risk.take_profit_pct:
                hit = "take_profit"
            if hit:
                pnl = position * (price - entry_price)
                cost = abs(position) * price * cost_params.exit_cost
                net = pnl - cost
                capital += net
                trade_log.append({
                    "entry_ts": entry_ts, "exit_ts": ts,
                    "direction": "long" if position > 0 else "short",
                    "entry_price": entry_price, "exit_price": price,
                    "pnl": net,
                    "return_pct": net / (abs(position) * entry_price),
                    "exit_reason": hit,
                })
                position = 0.0

        equity.append(capital)

    equity_curve = pd.Series(equity, index=df.index, dtype=float)
    return BacktestResult(
        equity_curve=equity_curve,
        trade_log=trade_log,
        summary=_compute_summary(equity_curve, trade_log, initial_capital),
    )


def _bars_per_8h(timeframe: str) -> int:
    return {"1": 480, "5": 96, "15": 32, "60": 8, "240": 2, "D": 1}.get(timeframe, 32)


def _compute_summary(
    equity: pd.Series,
    trade_log: list[dict],
    initial_capital: float,
) -> dict[str, float]:
    returns = equity.pct_change().dropna()
    ann = _annualisation_factor(equity)
    sharpe = float(returns.mean() / returns.std() * math.sqrt(ann)) if returns.std() > 0 else 0.0
    rolling_max = equity.cummax()
    max_dd = float(abs(((equity - rolling_max) / rolling_max).min()))
    wins = [t for t in trade_log if t.get("pnl", 0) > 0]
    return {
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "n_trades": float(len(trade_log)),
        "win_rate": len(wins) / len(trade_log) if trade_log else 0.0,
        "total_return": float((equity.iloc[-1] - initial_capital) / initial_capital),
        "final_capital": float(equity.iloc[-1]),
    }


def _annualisation_factor(equity: pd.Series) -> float:
    if len(equity) < 2:
        return 252.0
    delta_s = (equity.index[-1] - equity.index[0]).total_seconds()
    if delta_s <= 0:
        return 252.0
    bars_per_year = (365.25 * 24 * 3600) / (delta_s / len(equity))
    return float(bars_per_year)
