"""Shared fixtures and synthetic-data helpers for the test suite."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.spec import RiskParams, StrategySpec


_DEFAULT_THESIS = (
    "Momentum in crypto perpetuals persists for several bars after a moving-average "
    "crossover because of high retail participation and reflexive positioning, "
    "especially in trending regimes where funding pressure reinforces the move."
)


def make_spec(family: str = "trend", **overrides) -> StrategySpec:
    defaults = dict(
        thesis=_DEFAULT_THESIS,
        name="test_strategy",
        family=family,
        symbol="BTCUSDT",
        timeframe="15",
        parameters={"fast_period": 5, "slow_period": 15},
        entry_logic="Long when 5-period MA crosses above 15-period MA on close",
        exit_logic="Exit when MA crosses back or stop/take-profit triggers",
        risk=RiskParams(
            stop_loss_pct=0.02,
            take_profit_pct=0.05,
            max_position_pct=0.05,
            leverage=1.0,
        ),
    )
    defaults.update(overrides)
    return StrategySpec(**defaults)


def make_klines(n: int = 200, base_price: float = 40000.0, trend: float = 0.0001) -> list[dict]:
    """Synthetic OHLCV with a deterministic gentle trend (seeded RNG)."""
    ts_start = 1_700_000_000_000
    interval_ms = 15 * 60 * 1000
    rng = np.random.default_rng(42)
    price = base_price
    klines: list[dict] = []
    for i in range(n):
        price = max(price * (1 + trend) + rng.normal(0, price * 0.002), 1.0)
        klines.append({
            "ts": ts_start + i * interval_ms,
            "open": price * (1 - 0.0005),
            "high": price * (1 + abs(rng.normal(0, 0.001))),
            "low": price * (1 - abs(rng.normal(0, 0.001))),
            "close": price,
            "volume": rng.uniform(100, 1000),
        })
    return klines


def random_returns(n: int = 500, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(
        rng.normal(0, 0.01, n),
        index=pd.date_range("2022-01-01", periods=n, freq="15min", tz="UTC"),
    )


def trending_returns(n: int = 500, mean: float = 0.002, seed: int = 1) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(
        rng.normal(mean, 0.01, n),
        index=pd.date_range("2022-01-01", periods=n, freq="15min", tz="UTC"),
    )


@pytest.fixture
def spec_factory():
    return make_spec


@pytest.fixture
def klines_factory():
    return make_klines
