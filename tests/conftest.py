"""Shared test fixtures."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def make_ohlcv(
    n: int = 200,
    base_price: float = 40000.0,
    trend: float = 0.0,
    volatility: float = 0.003,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ts_start = 1_700_000_000_000
    interval_ms = 15 * 60 * 1000
    price = base_price
    rows = []
    for i in range(n):
        price = max(price * (1 + trend + rng.normal(0, volatility)), 1.0)
        hi = price * (1 + abs(rng.normal(0, 0.001)))
        lo = price * (1 - abs(rng.normal(0, 0.001)))
        rows.append({
            "ts": ts_start + i * interval_ms,
            "open": price * (1 - 0.0005),
            "high": hi,
            "low": lo,
            "close": price,
            "volume": rng.uniform(100, 1000),
        })
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts")[["open", "high", "low", "close", "volume"]].astype(float)


def make_ranging_ohlcv(
    n: int = 60,
    mid_price: float = 40000.0,
    range_pct: float = 0.005,
    seed: int = 7,
) -> pd.DataFrame:
    """Tight sideways range — good for bracket consolidation tests."""
    rng = np.random.default_rng(seed)
    ts_start = 1_700_000_000_000
    interval_ms = 15 * 60 * 1000
    half = mid_price * range_pct / 2
    rows = []
    for i in range(n):
        c = mid_price + rng.uniform(-half * 0.8, half * 0.8)
        rows.append({
            "ts": ts_start + i * interval_ms,
            "open": c + rng.uniform(-half * 0.1, half * 0.1),
            "high": c + abs(rng.normal(0, half * 0.1)),
            "low": c - abs(rng.normal(0, half * 0.1)),
            "close": c,
            "volume": rng.uniform(50, 200),
        })
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts")[["open", "high", "low", "close", "volume"]].astype(float)


@pytest.fixture
def ohlcv():
    return make_ohlcv()


@pytest.fixture
def ranging_ohlcv():
    return make_ranging_ohlcv()
