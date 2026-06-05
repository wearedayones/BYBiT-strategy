"""
Statistical validation: CPCV, Deflated Sharpe Ratio, PBO, regime/robustness.

All four pillars must pass before gate.py will promote a strategy.
This module deliberately does NOT import engine/backtest.py.

References:
  Bailey & Lopez de Prado (2014) "The Deflated Sharpe Ratio"
  Lopez de Prado & Bailey (2014) "The Probability of Backtest Overfitting"
  Lopez de Prado (2018) "Advances in Financial Machine Learning" Ch.12
"""
from __future__ import annotations

import dataclasses
import itertools
import math
from typing import Callable

import numpy as np
import pandas as pd
from scipy import stats


# ── Data structures ───────────────────────────────────────────────────────────

@dataclasses.dataclass
class CPCVResult:
    oos_sharpes: list[float]
    mean_oos_sharpe: float
    std_oos_sharpe: float
    n_combinations: int


@dataclasses.dataclass
class DSRResult:
    dsr: float
    sr_observed: float
    sr_benchmark: float
    n_trials: int


@dataclasses.dataclass
class PBOResult:
    pbo: float
    n_combinations: int
    lambda_values: list[float]


@dataclasses.dataclass
class ValidationResult:
    cpcv: CPCVResult
    dsr: DSRResult
    pbo: PBOResult
    regime_ok: bool
    robustness_ok: bool
    passed: bool
    failure_reasons: list[str]


# ── Shared Sharpe helper ──────────────────────────────────────────────────────

def _sharpe(returns: np.ndarray, ann_factor: float = 252.0) -> float:
    if len(returns) < 2 or np.std(returns) == 0:
        return 0.0
    return float(np.mean(returns) / np.std(returns, ddof=1) * math.sqrt(ann_factor))


# ── Pillar 1: CPCV ───────────────────────────────────────────────────────────

def _apply_embargo(
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    embargo: int,
    total_bars: int,
) -> np.ndarray:
    """Remove bars within `embargo` distance of any test bar from the train set."""
    test_set = set(test_indices.tolist())
    embargo_zone: set[int] = set()
    for t in test_set:
        for offset in range(-embargo, embargo + 1):
            nb = t + offset
            if 0 <= nb < total_bars:
                embargo_zone.add(nb)
    return np.array([i for i in train_indices if i not in embargo_zone])


def run_cpcv(
    returns: pd.Series,
    backtest_fn: Callable[[pd.Series], float],
    n_groups: int = 6,
    k_test: int = 2,
    embargo_bars: int = 5,
    ann_factor: float = 252.0,
) -> CPCVResult:
    """
    Combinatorial Purged Cross-Validation (Lopez de Prado 2018).

    Splits T bars into n_groups groups. For every C(n_groups, k_test) combination
    of groups used as the test set, trains on the complement (with embargo applied
    at boundaries) and calls backtest_fn on the test returns to get OOS Sharpe.

    backtest_fn(test_returns: pd.Series) -> float
      The caller injects this to decouple signal generation from validation math.
    """
    T = len(returns)
    arr = returns.values.astype(float)

    group_size = T // n_groups
    groups = [
        np.arange(g * group_size, (g + 1) * group_size if g < n_groups - 1 else T)
        for g in range(n_groups)
    ]

    oos_sharpes: list[float] = []
    all_combos = list(itertools.combinations(range(n_groups), k_test))

    for test_gidx in all_combos:
        test_bars = np.concatenate([groups[g] for g in test_gidx])
        train_gidx = [g for g in range(n_groups) if g not in test_gidx]
        train_bars = np.concatenate([groups[g] for g in train_gidx])

        purged = _apply_embargo(train_bars, test_bars, embargo_bars, T)
        if len(purged) < 30 or len(test_bars) < 10:
            continue

        oos_sr = backtest_fn(pd.Series(arr[test_bars], index=returns.index[test_bars]))
        oos_sharpes.append(oos_sr)

    return CPCVResult(
        oos_sharpes=oos_sharpes,
        mean_oos_sharpe=float(np.mean(oos_sharpes)) if oos_sharpes else 0.0,
        std_oos_sharpe=float(np.std(oos_sharpes)) if oos_sharpes else 0.0,
        n_combinations=len(all_combos),
    )


# ── Pillar 2: Deflated Sharpe Ratio ──────────────────────────────────────────

def compute_dsr(
    returns: np.ndarray,
    n_trials: int,
    ann_factor: float = 252.0,
) -> DSRResult:
    """
    Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014).

    Corrects the observed SR for:
      (a) Multiple testing: n_trials strategies were evaluated to find this one
      (b) Non-normality: skewness gamma3 and excess kurtosis gamma4
      (c) Finite sample: T observations

    Returns DSR in [0, 1]. Values > 0.65 indicate the edge is likely real.

    Implementation note: SR_benchmark is in period (not annualised) SR units.
    The deflation formula operates on the period SR to avoid unit mismatch.
    Fallback: for n_trials < 10, use simpler Φ⁻¹(1 - 1/n) benchmark.
    """
    T = len(returns)
    if T < 10 or n_trials < 1:
        return DSRResult(dsr=0.0, sr_observed=0.0, sr_benchmark=0.0, n_trials=n_trials)

    r = np.asarray(returns, dtype=float)

    # Period SR (not annualised) for the deflation formula
    if np.std(r, ddof=1) == 0:
        return DSRResult(dsr=0.0, sr_observed=0.0, sr_benchmark=0.0, n_trials=n_trials)
    sr_obs_period = float(np.mean(r) / np.std(r, ddof=1))
    sr_obs_ann = sr_obs_period * math.sqrt(ann_factor)

    # Moments (clamp to physically plausible range for crypto fat tails)
    gamma3 = float(np.clip(stats.skew(r), -3.0, 3.0))
    gamma4 = float(np.clip(stats.kurtosis(r), -2.0, 20.0))

    # SR benchmark: expected max SR under the null (all n_trials have zero true SR)
    n = float(max(n_trials, 1))
    if n_trials >= 10:
        euler_gamma = 0.5772156649
        z1 = stats.norm.ppf(1.0 - 1.0 / n)
        z2 = stats.norm.ppf(1.0 - 1.0 / (n * math.e))
        z_benchmark = (1 - euler_gamma) * z1 + euler_gamma * z2
    else:
        z_benchmark = stats.norm.ppf(1.0 - 1.0 / n)
    sr_benchmark = z_benchmark * math.sqrt(1.0 / T)

    # Deflation formula denominator
    denom_sq = 1.0 - gamma3 * sr_obs_period + (gamma4 / 4.0) * sr_obs_period ** 2
    denom_sq = max(denom_sq, 1e-8)

    dsr_z = (sr_obs_period - sr_benchmark) * math.sqrt(T - 1) / math.sqrt(denom_sq)
    dsr_val = float(np.clip(stats.norm.cdf(dsr_z), 0.0, 1.0))

    return DSRResult(
        dsr=dsr_val,
        sr_observed=sr_obs_ann,
        sr_benchmark=sr_benchmark * math.sqrt(ann_factor),
        n_trials=n_trials,
    )


# ── Pillar 3: PBO ─────────────────────────────────────────────────────────────

def compute_pbo(
    returns_matrix: np.ndarray,
    n_sub_periods: int = 16,
    ann_factor: float = 252.0,
) -> PBOResult:
    """
    Probability of Backtest Overfitting (Lopez de Prado & Bailey 2014).

    Input: returns_matrix of shape (T, N) — T bars, N strategy variants.
    N >= 2 required (with N=1 PBO is undefined; caller must pass param variants).

    For each C(S, S//2) split of S sub-periods into IS/OOS halves:
      - Rank all N variants by IS Sharpe; identify the IS winner
      - Find the IS winner's OOS rank (ascending: rank 1 = worst, rank N = best)
      - Relative rank omega = rank / (N + 1); λ = log(omega / (1 - omega))
        λ < 0  <=>  omega < 0.5  <=>  IS winner is below the OOS median (overfit)
    PBO = fraction of combinations where λ < 0.
    """
    T, N = returns_matrix.shape
    if N < 2:
        raise ValueError("PBO requires at least 2 strategy variants (N >= 2)")

    # Halve sub-periods if not enough data
    S = min(n_sub_periods, T // 8)
    S = max(S, 4)
    S_half = S // 2
    bar_size = T // S

    sub_periods = [
        returns_matrix[g * bar_size: (g + 1) * bar_size, :]
        for g in range(S)
    ]

    all_combos = list(itertools.combinations(range(S), S_half))
    lambda_values: list[float] = []

    for is_idx in all_combos:
        oos_idx = [g for g in range(S) if g not in is_idx]

        is_ret = np.vstack([sub_periods[g] for g in is_idx])
        oos_ret = np.vstack([sub_periods[g] for g in oos_idx])

        is_sharpes = np.array([_sharpe(is_ret[:, n], ann_factor) for n in range(N)])
        oos_sharpes = np.array([_sharpe(oos_ret[:, n], ann_factor) for n in range(N)])

        best_idx = int(np.argmax(is_sharpes))

        # Ascending OOS rank of the IS winner (1 = worst, N = best); ties → average rank
        oos_rank = float(stats.rankdata(oos_sharpes)[best_idx])
        omega = oos_rank / (N + 1)
        omega = min(max(omega, 1e-8), 1 - 1e-8)

        lam = math.log(omega / (1 - omega))
        lambda_values.append(lam)

    pbo = float(np.clip(np.mean([1.0 if lam < 0 else 0.0 for lam in lambda_values]), 0.0, 1.0))

    return PBOResult(
        pbo=pbo,
        n_combinations=len(all_combos),
        lambda_values=lambda_values,
    )


# ── Pillar 4: Regime & Robustness ─────────────────────────────────────────────

def check_regime_stability(
    returns: pd.Series,
    min_regime_sharpe: float = 0.3,
    vol_window: int = 30,
) -> tuple[bool, str]:
    """Split into high/low vol regimes and check Sharpe doesn't collapse in either."""
    if len(returns) < vol_window * 3:
        return True, "insufficient data for regime check — skipped"

    rolling_vol = returns.rolling(vol_window).std()
    median_vol = float(rolling_vol.median())

    high_mask = rolling_vol >= median_vol
    low_mask = ~high_mask

    sr_high = _sharpe(returns[high_mask].values)
    sr_low = _sharpe(returns[low_mask].values)

    if sr_high < min_regime_sharpe:
        return False, f"High-vol regime Sharpe {sr_high:.2f} < {min_regime_sharpe}"
    if sr_low < min_regime_sharpe:
        return False, f"Low-vol regime Sharpe {sr_low:.2f} < {min_regime_sharpe}"

    return True, f"Regime ok: high-vol SR={sr_high:.2f}, low-vol SR={sr_low:.2f}"


def check_robustness(
    base_sharpe: float,
    stressed_sharpe: float,
    min_ratio: float = 0.5,
) -> tuple[bool, str]:
    """Stressed Sharpe (fees * cost_multiplier) must be >= base_sharpe * min_ratio."""
    if base_sharpe <= 0:
        return False, "Base Sharpe is non-positive; robustness check not applicable"
    ratio = stressed_sharpe / base_sharpe
    ok = ratio >= min_ratio
    label = "pass" if ok else "FAIL"
    return ok, f"Robustness: stressed/base = {ratio:.2f} ({label})"


# ── Public entry point ────────────────────────────────────────────────────────

def validate_strategy(
    equity_curve: pd.Series,
    returns_matrix: np.ndarray,
    n_trials: int,
    base_sharpe: float,
    stressed_sharpe: float,
    acceptance: dict,
    ann_factor: float = 252.0,
) -> ValidationResult:
    """
    Run all four validation pillars and return a structured result.

    equity_curve    : pd.Series from BacktestResult.equity_curve
    returns_matrix  : np.ndarray (T, N) where N >= 2 (parameter variants)
    n_trials        : total strategies evaluated so far (from candidates.jsonl trial_number)
    base_sharpe     : from BacktestResult.summary['sharpe']
    stressed_sharpe : from a second backtest run with cost_params * acceptance['cost_multiplier']
    acceptance      : dict parsed from config/acceptance.yaml
    """
    returns = equity_curve.pct_change().dropna()
    arr = returns.values.astype(float)

    cpcv = run_cpcv(
        returns=returns,
        backtest_fn=lambda r: _sharpe(r.values, ann_factor),
        n_groups=6,
        k_test=2,
        embargo_bars=5,
        ann_factor=ann_factor,
    )

    dsr = compute_dsr(arr, n_trials=n_trials, ann_factor=ann_factor)

    pbo = compute_pbo(returns_matrix, n_sub_periods=16, ann_factor=ann_factor)

    regime_ok, regime_reason = check_regime_stability(returns)

    cost_min_ratio = 1.0 / acceptance.get("cost_multiplier", 1.5)
    robustness_ok, robustness_reason = check_robustness(
        base_sharpe, stressed_sharpe, min_ratio=cost_min_ratio
    )

    failures: list[str] = []
    if cpcv.mean_oos_sharpe < acceptance.get("min_oos_sharpe", 0.8):
        failures.append(
            f"CPCV mean OOS Sharpe {cpcv.mean_oos_sharpe:.2f} < {acceptance['min_oos_sharpe']}"
        )
    if dsr.dsr < acceptance.get("min_dsr", 0.65):
        failures.append(f"DSR {dsr.dsr:.3f} < {acceptance['min_dsr']}")
    if pbo.pbo > acceptance.get("pbo_ceiling", 0.45):
        failures.append(f"PBO {pbo.pbo:.3f} > ceiling {acceptance['pbo_ceiling']}")
    if not regime_ok:
        failures.append(regime_reason)
    if not robustness_ok:
        failures.append(robustness_reason)

    return ValidationResult(
        cpcv=cpcv,
        dsr=dsr,
        pbo=pbo,
        regime_ok=regime_ok,
        robustness_ok=robustness_ok,
        passed=len(failures) == 0,
        failure_reasons=failures,
    )
