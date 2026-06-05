"""Tests for engine/validation.py."""
from __future__ import annotations

import math

import numpy as np
import pytest

from engine.validation import (
    _apply_embargo,
    check_regime_stability,
    check_robustness,
    compute_dsr,
    compute_pbo,
    run_cpcv,
)
from tests.conftest import random_returns, trending_returns


# ── _apply_embargo ────────────────────────────────────────────────────────────

def test_embargo_removes_adjacent_bars():
    purged = _apply_embargo(np.arange(0, 100), np.array([50, 51, 52]), embargo=3, total_bars=100)
    for bar in range(47, 56):
        assert bar not in purged


def test_embargo_preserves_distant_bars():
    purged = _apply_embargo(np.arange(0, 100), np.array([50]), embargo=3, total_bars=100)
    assert 0 in purged
    assert 99 in purged


def test_embargo_boundary_zero():
    train = np.arange(0, 50)
    purged = _apply_embargo(train, np.array([25, 26]), embargo=0, total_bars=50)
    # test bars are not in train anyway; with embargo=0 nothing else is removed
    assert len(purged) == len(train) - 2


# ── run_cpcv ──────────────────────────────────────────────────────────────────

def test_cpcv_combination_count():
    result = run_cpcv(
        returns=random_returns(300),
        backtest_fn=lambda r: float(r.mean() / r.std()) if r.std() > 0 else 0.0,
        n_groups=6,
        k_test=2,
        embargo_bars=2,
    )
    assert result.n_combinations == 15
    assert len(result.oos_sharpes) <= 15


def test_cpcv_high_sharpe_strategy():
    result = run_cpcv(
        returns=trending_returns(600, mean=0.003),
        backtest_fn=lambda r: float(r.mean() / r.std() * math.sqrt(252 * 4)) if r.std() > 0 else 0.0,
        n_groups=6,
        k_test=2,
    )
    assert result.mean_oos_sharpe > 0


def test_cpcv_random_strategy_near_zero():
    result = run_cpcv(
        returns=random_returns(600, seed=42),
        backtest_fn=lambda r: float(r.mean() / r.std()) if r.std() > 0 else 0.0,
        n_groups=6,
        k_test=2,
    )
    assert abs(result.mean_oos_sharpe) < 1.0


# ── compute_dsr ───────────────────────────────────────────────────────────────

def test_dsr_bounds():
    result = compute_dsr(random_returns(500).values, n_trials=10)
    assert 0.0 <= result.dsr <= 1.0


def test_dsr_increases_with_sr():
    rng = np.random.default_rng(0)
    low = compute_dsr(rng.normal(0.0001, 0.01, 500), n_trials=5)
    high = compute_dsr(rng.normal(0.003, 0.01, 500), n_trials=5)
    assert high.dsr > low.dsr


def test_dsr_decreases_with_more_trials():
    returns = np.random.default_rng(7).normal(0.001, 0.01, 500)
    few = compute_dsr(returns, n_trials=5)
    many = compute_dsr(returns, n_trials=100)
    assert few.dsr >= many.dsr


def test_dsr_trivial_input():
    result = compute_dsr(np.array([0.01, 0.01]), n_trials=1)
    assert result.dsr == 0.0


# ── compute_pbo ───────────────────────────────────────────────────────────────

def test_pbo_bounds():
    matrix = np.random.default_rng(0).normal(0, 0.01, (400, 5))
    result = compute_pbo(matrix, n_sub_periods=8)
    assert 0.0 <= result.pbo <= 1.0


def test_pbo_random_near_half():
    # A single matrix gives a noisy PBO (the C(8,4) combos share sub-periods),
    # so average across many independent random matrices for a stable estimate.
    pbos = [
        compute_pbo(np.random.default_rng(seed).normal(0, 0.01, (800, 10)), n_sub_periods=8).pbo
        for seed in range(30)
    ]
    mean_pbo = float(np.mean(pbos))
    # For truly random strategies the IS winner is OOS-random, so PBO ~ 0.5
    # (slightly elevated by finite-sample selection effects — the safe direction).
    assert 0.4 < mean_pbo < 0.75


def test_pbo_requires_multiple_variants():
    matrix = np.random.default_rng(0).normal(0, 0.01, (400, 1))
    with pytest.raises(ValueError, match="at least 2"):
        compute_pbo(matrix)


def test_pbo_lambda_values_count():
    matrix = np.random.default_rng(0).normal(0, 0.01, (400, 4))
    result = compute_pbo(matrix, n_sub_periods=8)
    # C(8, 4) = 70 combinations
    assert len(result.lambda_values) == 70


# ── Regime & robustness ───────────────────────────────────────────────────────

def test_regime_stable_strategy_passes():
    ok, _ = check_regime_stability(trending_returns(600, mean=0.002), min_regime_sharpe=0.0)
    assert ok


def test_robustness_check_pass():
    ok, _ = check_robustness(base_sharpe=1.2, stressed_sharpe=0.8, min_ratio=0.5)
    assert ok


def test_robustness_check_fail():
    ok, reason = check_robustness(base_sharpe=1.2, stressed_sharpe=0.3, min_ratio=0.5)
    assert not ok
    assert "FAIL" in reason


def test_robustness_negative_base():
    ok, _ = check_robustness(base_sharpe=-0.5, stressed_sharpe=0.1)
    assert not ok


# ── Property-based tests (hypothesis) ─────────────────────────────────────────

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    @given(
        n=st.integers(min_value=20, max_value=500),
        mean=st.floats(min_value=-0.01, max_value=0.01),
        trials=st.integers(min_value=1, max_value=200),
        seed=st.integers(min_value=0, max_value=9999),
    )
    @settings(max_examples=50, deadline=5000)
    def test_dsr_always_bounded(n, mean, trials, seed):
        r = np.random.default_rng(seed).normal(mean, 0.01, n)
        result = compute_dsr(r, n_trials=trials)
        assert 0.0 <= result.dsr <= 1.0

    @given(
        T=st.integers(min_value=64, max_value=400),
        N=st.integers(min_value=2, max_value=8),
        seed=st.integers(min_value=0, max_value=9999),
    )
    @settings(max_examples=30, deadline=10000)
    def test_pbo_always_bounded(T, N, seed):
        matrix = np.random.default_rng(seed).normal(0, 0.01, (T, N))
        result = compute_pbo(matrix, n_sub_periods=min(8, T // 8))
        assert 0.0 <= result.pbo <= 1.0

except ImportError:
    pass
