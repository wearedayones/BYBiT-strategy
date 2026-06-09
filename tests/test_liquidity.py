"""Tests for engine/liquidity.py."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.liquidity import (
    Sweep,
    cluster_levels,
    detect_sweeps,
    find_order_blocks,
    find_swing_highs,
    find_swing_lows,
    scan,
)
from tests.conftest import make_ohlcv


# ── Swing detection ───────────────────────────────────────────────────────────

def test_swing_highs_are_local_maxima():
    df = make_ohlcv(100, seed=1)
    highs = find_swing_highs(df, lookback=5)
    for sp in highs:
        window = df["high"].values[sp.bar_idx - 5: sp.bar_idx + 6]
        assert sp.price >= window.max() - 1e-9


def test_swing_lows_are_local_minima():
    df = make_ohlcv(100, seed=2)
    lows = find_swing_lows(df, lookback=5)
    for sp in lows:
        window = df["low"].values[sp.bar_idx - 5: sp.bar_idx + 6]
        assert sp.price <= window.min() + 1e-9


def test_swing_highs_and_lows_kinds():
    df = make_ohlcv(80)
    for sp in find_swing_highs(df):
        assert sp.kind == "high"
    for sp in find_swing_lows(df):
        assert sp.kind == "low"


def test_swing_empty_on_monotone_series():
    # Strictly increasing series has no swing highs (each bar has a higher bar to its right)
    idx = pd.date_range("2024-01-01", periods=50, freq="15min", tz="UTC")
    prices = np.linspace(100, 150, 50)
    df = pd.DataFrame({
        "open": prices, "high": prices * 1.001, "low": prices * 0.999,
        "close": prices, "volume": 100.0,
    }, index=idx)
    assert find_swing_highs(df, lookback=3) == []


def test_swing_lookback_controls_sensitivity():
    df = make_ohlcv(200)
    h_tight = find_swing_highs(df, lookback=2)
    h_loose = find_swing_highs(df, lookback=10)
    assert len(h_tight) >= len(h_loose)


# ── Level clustering ──────────────────────────────────────────────────────────

def test_cluster_levels_groups_close_prices():
    df = make_ohlcv(200)
    highs = find_swing_highs(df, lookback=5)
    levels = cluster_levels(highs, tolerance=0.001)
    for level in levels:
        assert level.touches >= 2


def test_cluster_levels_empty_input():
    assert cluster_levels([]) == []


def test_cluster_level_kind():
    df = make_ohlcv(200)
    high_levels = cluster_levels(find_swing_highs(df))
    low_levels = cluster_levels(find_swing_lows(df))
    for lv in high_levels:
        assert lv.kind == "high"
    for lv in low_levels:
        assert lv.kind == "low"


def test_cluster_prices_within_tolerance():
    df = make_ohlcv(200)
    levels = cluster_levels(find_swing_highs(df), tolerance=0.002)
    for lv in levels:
        # All bar_indices map to highs within 0.2% of the level price
        for i in lv.bar_indices:
            assert abs(df["high"].iloc[i] - lv.price) / lv.price <= 0.003


# ── Sweep detection ───────────────────────────────────────────────────────────

def _make_sweep_df(kind: str) -> pd.DataFrame:
    """Synthetic OHLCV with a single clean sweep candle injected."""
    idx = pd.date_range("2024-01-01", periods=30, freq="15min", tz="UTC")
    base = 40000.0
    data = {
        "open": [base] * 30, "high": [base * 1.001] * 30,
        "low": [base * 0.999] * 30, "close": [base] * 30,
        "volume": [500.0] * 30,
    }
    df = pd.DataFrame(data, index=idx)
    if kind == "sweep_high":
        # Candle 25 wicks above 40100 (the level) but closes below
        df.loc[df.index[25], "high"] = base * 1.005   # wick above level
        df.loc[df.index[25], "open"] = base * 0.999
        df.loc[df.index[25], "close"] = base * 0.998  # close below level
    elif kind == "sweep_low":
        df.loc[df.index[25], "low"] = base * 0.995
        df.loc[df.index[25], "open"] = base * 1.001
        df.loc[df.index[25], "close"] = base * 1.002
    return df


def test_detect_sweep_high():
    from engine.liquidity import LiquidityLevel, SwingPoint
    level = LiquidityLevel(price=40000.0, kind="high", touches=2, bar_indices=[5, 10])
    df = _make_sweep_df("sweep_high")
    sweeps = detect_sweeps(df, [level], sweep_buffer=0.0002, min_wick_ratio=0.5)
    assert len(sweeps) >= 1
    assert sweeps[0].kind == "sweep_high"
    assert sweeps[0].wick_extreme > level.price


def test_detect_sweep_low():
    from engine.liquidity import LiquidityLevel
    level = LiquidityLevel(price=40000.0, kind="low", touches=2, bar_indices=[5, 10])
    df = _make_sweep_df("sweep_low")
    sweeps = detect_sweeps(df, [level], sweep_buffer=0.0002, min_wick_ratio=0.5)
    assert len(sweeps) >= 1
    assert sweeps[0].kind == "sweep_low"
    assert sweeps[0].wick_extreme < level.price


def test_sweep_stop_is_beyond_wick():
    from engine.liquidity import LiquidityLevel
    level = LiquidityLevel(price=40000.0, kind="high", touches=2, bar_indices=[5, 10])
    df = _make_sweep_df("sweep_high")
    sweeps = detect_sweeps(df, [level], sweep_buffer=0.0002, min_wick_ratio=0.5)
    for s in sweeps:
        assert s.stop_price > s.wick_extreme  # stop above wick for sweep_high


def test_sweep_confidence_bounded():
    from engine.liquidity import LiquidityLevel
    level = LiquidityLevel(price=40000.0, kind="high", touches=3, bar_indices=[5, 10, 15])
    df = _make_sweep_df("sweep_high")
    sweeps = detect_sweeps(df, [level], sweep_buffer=0.0002, min_wick_ratio=0.5)
    for s in sweeps:
        assert 0.0 <= s.confidence <= 1.0


def test_no_sweep_without_close_rejection():
    """A candle that wicks through but also closes above the level is NOT a sweep."""
    from engine.liquidity import LiquidityLevel
    level = LiquidityLevel(price=40000.0, kind="high", touches=2, bar_indices=[5, 10])
    idx = pd.date_range("2024-01-01", periods=30, freq="15min", tz="UTC")
    base = 40000.0
    data = {"open": [base] * 30, "high": [base * 1.001] * 30,
            "low": [base * 0.999] * 30, "close": [base] * 30, "volume": [500.0] * 30}
    df = pd.DataFrame(data, index=idx)
    # Closes ABOVE the level — no sweep
    df.loc[df.index[25], "high"] = base * 1.005
    df.loc[df.index[25], "close"] = base * 1.003
    sweeps = detect_sweeps(df, [level], sweep_buffer=0.0002, min_wick_ratio=0.5)
    assert len(sweeps) == 0


# ── Order block detection ─────────────────────────────────────────────────────

def test_order_blocks_have_valid_structure():
    df = make_ohlcv(100, seed=5)
    obs = find_order_blocks(df, impulse_threshold=0.001)
    for ob in obs:
        assert ob.kind in ("bullish", "bearish")
        assert ob.low <= ob.mid <= ob.high


def test_order_blocks_mid_is_midpoint():
    df = make_ohlcv(100)
    for ob in find_order_blocks(df, impulse_threshold=0.001):
        assert abs(ob.mid - (ob.high + ob.low) / 2) < 1e-6


# ── Full scan ─────────────────────────────────────────────────────────────────

def test_scan_returns_result():
    df = make_ohlcv(150)
    result = scan(df)
    assert result.swing_highs is not None
    assert result.swing_lows is not None
    assert isinstance(result.sweeps, list)
    assert isinstance(result.order_blocks, list)


def test_scan_latest_sweep_is_last():
    df = make_ohlcv(150)
    result = scan(df)
    if result.sweeps:
        assert result.latest_sweep == result.sweeps[-1]
    else:
        assert result.latest_sweep is None
