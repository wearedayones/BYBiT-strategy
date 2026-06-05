"""Unit and integration tests for engine/backtest.py."""
from __future__ import annotations

import pandas as pd
import pytest

from engine.backtest import (
    CostParams,
    _compute_summary,
    compute_signals,
    ohlcv_to_dataframe,
    run_backtest,
)
from tests.conftest import make_klines, make_spec


# ── CostParams ────────────────────────────────────────────────────────────────

def test_cost_params_taker_fees():
    cp = CostParams(taker_fee=0.00055, slippage_bps=5.0, use_market_orders=True)
    expected = 0.00055 + 5.0 * 1e-4
    assert abs(cp.entry_cost - expected) < 1e-9
    assert abs(cp.exit_cost - expected) < 1e-9


def test_cost_params_maker_fees():
    cp = CostParams(maker_fee=0.0002, slippage_bps=0.0, use_market_orders=False)
    assert abs(cp.entry_cost - 0.0002) < 1e-9


# ── ohlcv_to_dataframe ────────────────────────────────────────────────────────

def test_ohlcv_dataframe_columns():
    df = ohlcv_to_dataframe(make_klines(10))
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert str(df.index.tz) == "UTC"


def test_ohlcv_dataframe_sorted():
    df = ohlcv_to_dataframe(make_klines(10)[::-1])
    assert df.index.is_monotonic_increasing


# ── compute_signals ───────────────────────────────────────────────────────────

def test_trend_signal_range():
    df = ohlcv_to_dataframe(make_klines(200))
    spec = make_spec(family="trend", parameters={"fast_period": 5, "slow_period": 15})
    signals = compute_signals(df, spec)
    assert set(signals.unique()).issubset({-1, 0, 1})
    assert (signals.iloc[20:] != 0).any()


def test_mean_reversion_signal_range():
    df = ohlcv_to_dataframe(make_klines(200))
    spec = make_spec(family="mean_reversion", parameters={"bb_period": 20, "bb_std": 2.0})
    signals = compute_signals(df, spec)
    assert set(signals.unique()).issubset({-1, 0, 1})


# ── run_backtest ──────────────────────────────────────────────────────────────

def test_backtest_determinism():
    klines = make_klines(300)
    spec = make_spec()
    r1 = run_backtest(klines, spec)
    r2 = run_backtest(klines, spec)
    pd.testing.assert_series_equal(r1.equity_curve, r2.equity_curve)


def test_backtest_equity_length():
    result = run_backtest(make_klines(200), make_spec())
    assert len(result.equity_curve) == 200


def test_backtest_equity_positive():
    result = run_backtest(make_klines(300, trend=0.0001), make_spec())
    assert result.equity_curve.min() > 0


def test_backtest_summary_keys():
    result = run_backtest(make_klines(200), make_spec())
    for key in ["sharpe", "max_drawdown", "n_trades", "win_rate", "total_return"]:
        assert key in result.summary


def test_backtest_fees_reduce_return():
    klines = make_klines(300)
    spec = make_spec()
    low = run_backtest(klines, spec, cost_params=CostParams(taker_fee=0.0001, slippage_bps=1.0))
    high = run_backtest(klines, spec, cost_params=CostParams(taker_fee=0.001, slippage_bps=20.0))
    assert low.summary["total_return"] >= high.summary["total_return"]


def test_zero_trades_no_crash():
    spec = make_spec(parameters={"fast_period": 100, "slow_period": 200})
    result = run_backtest(make_klines(50), spec)
    assert result.summary["n_trades"] == 0


# ── Summary edge cases ────────────────────────────────────────────────────────

def test_sharpe_zero_variance():
    flat = pd.Series(
        [10000.0] * 100,
        index=pd.date_range("2023-01-01", periods=100, freq="15min", tz="UTC"),
    )
    summary = _compute_summary(flat, [], 10000.0)
    assert summary["sharpe"] == 0.0
