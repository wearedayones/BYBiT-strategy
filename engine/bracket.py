"""
Event-driven bracket order construction.

A bracket is a pair of stop orders placed above and below a pre-event consolidation:
  — Buy-stop  just above the range high → triggers if price breaks up
  — Sell-stop just below the range low  → triggers if price breaks down

When one side fills, the other becomes a contingent stop-loss.
The strategy targets a measured move equal to the range height (1R), with a
second target at 2× range height (2R). Risk = range boundary to stop beyond range.
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd


# ── Data structures ───────────────────────────────────────────────────────────

@dataclasses.dataclass
class Consolidation:
    is_valid: bool
    range_high: float
    range_low: float
    range_height: float
    range_pct: float        # (high - low) / low
    atr: float
    atr_ratio: float        # range_height / atr; tight if <= threshold
    bars_checked: int
    reason: str             # why valid/invalid


@dataclasses.dataclass
class BracketLevels:
    buy_entry: float        # stop-buy entry (above range)
    sell_entry: float       # stop-sell entry (below range)
    buy_stop: float         # stop-loss if long (below range)
    sell_stop: float        # stop-loss if short (above range)
    buy_target1: float      # long target 1 (1R)
    buy_target2: float      # long target 2 (2R)
    sell_target1: float     # short target 1 (1R)
    sell_target2: float     # short target 2 (2R)
    range_height: float
    long_rr1: float         # reward:risk for long target 1
    long_rr2: float
    short_rr1: float
    short_rr2: float


@dataclasses.dataclass
class BracketTrade:
    direction: str          # "long" or "short"
    entry_price: float
    stop_price: float
    target1_price: float
    target2_price: float
    position_size: float    # units
    risk_amount: float      # $ at risk
    rr1: float
    rr2: float


# ── ATR helper ────────────────────────────────────────────────────────────────

def _atr(df: pd.DataFrame) -> float:
    """Average True Range over the provided DataFrame."""
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return float(tr.mean())


# ── Consolidation detection ───────────────────────────────────────────────────

def find_consolidation(
    df: pd.DataFrame,
    bars: int = 20,
    atr_ratio_threshold: float = 1.2,
    min_range_pct: float = 0.002,
) -> Consolidation:
    """
    Inspect the last `bars` candles for a tight pre-event range.

    Valid consolidation criteria:
      1. range height ≤ atr_ratio_threshold × ATR (tight relative to recent volatility)
      2. range height ≥ min_range_pct × mid-price (not a micro-range / data artefact)

    Returns a Consolidation with is_valid=False and a reason string if not met.
    """
    if len(df) < bars + 5:
        return Consolidation(
            is_valid=False, range_high=0, range_low=0, range_height=0,
            range_pct=0, atr=0, atr_ratio=0, bars_checked=len(df),
            reason="insufficient bars",
        )

    recent = df.iloc[-bars:]
    rh = float(recent["high"].max())
    rl = float(recent["low"].min())
    height = rh - rl
    mid = (rh + rl) / 2
    range_pct = height / rl if rl > 0 else 0.0

    atr_val = _atr(df.iloc[-(bars + 5):])
    atr_ratio = height / atr_val if atr_val > 0 else float("inf")

    if range_pct < min_range_pct:
        return Consolidation(
            is_valid=False, range_high=rh, range_low=rl, range_height=height,
            range_pct=range_pct, atr=atr_val, atr_ratio=atr_ratio,
            bars_checked=bars, reason=f"range {range_pct:.4f} < min {min_range_pct}",
        )

    if atr_ratio > atr_ratio_threshold:
        return Consolidation(
            is_valid=False, range_high=rh, range_low=rl, range_height=height,
            range_pct=range_pct, atr=atr_val, atr_ratio=atr_ratio,
            bars_checked=bars, reason=f"ATR ratio {atr_ratio:.2f} > threshold {atr_ratio_threshold}",
        )

    return Consolidation(
        is_valid=True, range_high=rh, range_low=rl, range_height=height,
        range_pct=range_pct, atr=atr_val, atr_ratio=atr_ratio,
        bars_checked=bars, reason="valid",
    )


# ── Bracket level computation ─────────────────────────────────────────────────

def compute_bracket_levels(
    consol: Consolidation,
    entry_buffer_pct: float = 0.001,
    stop_buffer_pct: float = 0.001,
) -> BracketLevels:
    """
    Given a valid consolidation, compute the full bracket.

    Entry: one buffer-tick beyond the range edge (stop-order placement).
    Stop:  one buffer-tick beyond the OPPOSITE range edge (worst case: the range
           breaks the other way after filling; this limits the loss to ~range_height).
    Target1: range height projected from entry (measured move, 1R).
    Target2: 2 × range height from entry.
    """
    rh = consol.range_high
    rl = consol.range_low
    h = consol.range_height

    buy_entry = rh * (1 + entry_buffer_pct)
    sell_entry = rl * (1 - entry_buffer_pct)
    buy_stop = rl * (1 - stop_buffer_pct)
    sell_stop = rh * (1 + stop_buffer_pct)

    buy_risk = buy_entry - buy_stop
    sell_risk = sell_stop - sell_entry

    buy_t1 = buy_entry + h
    buy_t2 = buy_entry + 2 * h
    sell_t1 = sell_entry - h
    sell_t2 = sell_entry - 2 * h

    return BracketLevels(
        buy_entry=buy_entry, sell_entry=sell_entry,
        buy_stop=buy_stop, sell_stop=sell_stop,
        buy_target1=buy_t1, buy_target2=buy_t2,
        sell_target1=sell_t1, sell_target2=sell_t2,
        range_height=h,
        long_rr1=h / buy_risk if buy_risk > 0 else 0,
        long_rr2=2 * h / buy_risk if buy_risk > 0 else 0,
        short_rr1=h / sell_risk if sell_risk > 0 else 0,
        short_rr2=2 * h / sell_risk if sell_risk > 0 else 0,
    )


# ── Position sizing ───────────────────────────────────────────────────────────

def size_bracket_trade(
    direction: str,
    levels: BracketLevels,
    account_nav: float,
    risk_pct: float = 0.01,
    max_position_pct: float = 0.05,
    leverage: float = 1.0,
) -> BracketTrade:
    """
    Size a bracket leg using fixed fractional risk.

    risk_pct:  fraction of NAV to risk on this trade
    max_position_pct: hard cap on position size as fraction of NAV
    leverage: account leverage multiplier

    Position size = (NAV × risk_pct) / (entry - stop) per unit.
    """
    if direction == "long":
        entry = levels.buy_entry
        stop = levels.buy_stop
        t1 = levels.buy_target1
        t2 = levels.buy_target2
        rr1 = levels.long_rr1
        rr2 = levels.long_rr2
    else:
        entry = levels.sell_entry
        stop = levels.sell_stop
        t1 = levels.sell_target1
        t2 = levels.sell_target2
        rr1 = levels.short_rr1
        rr2 = levels.short_rr2

    risk_amount = account_nav * risk_pct
    stop_distance = abs(entry - stop)
    if stop_distance <= 0:
        qty = 0.0
    else:
        qty = risk_amount / stop_distance

    # Cap by max_position_pct
    max_qty = (account_nav * max_position_pct * leverage) / entry
    qty = min(qty, max_qty)

    return BracketTrade(
        direction=direction,
        entry_price=entry,
        stop_price=stop,
        target1_price=t1,
        target2_price=t2,
        position_size=qty,
        risk_amount=qty * stop_distance,
        rr1=rr1,
        rr2=rr2,
    )
