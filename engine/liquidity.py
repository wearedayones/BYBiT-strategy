"""
Liquidity level detection and sweep identification.

Definitions used throughout:
  Swing high  — a bar whose high is the highest in [i-lookback, i+lookback].
  Swing low   — a bar whose low is the lowest in [i-lookback, i+lookback].
  Equal level — two or more swing highs (or lows) within `tolerance` of each other;
                their price cluster is a potential stop-cluster / liquidity pool.
  Sweep       — price wicks through a liquidity level intrabar but the candle closes
                back on the originating side; interpreted as a stop-hunt reversal.
  Order block — the last opposing candle before a strong impulsive move; price often
                returns to it as a demand/supply zone.
"""
from __future__ import annotations

import dataclasses
from typing import Literal

import numpy as np
import pandas as pd


# ── Data structures ───────────────────────────────────────────────────────────

@dataclasses.dataclass
class SwingPoint:
    bar_idx: int
    timestamp: pd.Timestamp
    price: float
    kind: Literal["high", "low"]


@dataclasses.dataclass
class LiquidityLevel:
    price: float
    kind: Literal["high", "low"]
    touches: int           # how many swing points cluster at this level
    bar_indices: list[int]


@dataclasses.dataclass
class Sweep:
    bar_idx: int
    timestamp: pd.Timestamp
    kind: Literal["sweep_high", "sweep_low"]
    swept_level: float     # the liquidity level that was pierced
    wick_extreme: float    # the intrabar wick tip (high or low of the sweep candle)
    close: float
    wick_ratio: float      # wick length / body length (higher = cleaner rejection)
    entry_price: float     # suggested entry (close of sweep candle)
    stop_price: float      # beyond the wick extreme
    confidence: float      # 0–1 composite score


@dataclasses.dataclass
class OrderBlock:
    bar_idx: int
    timestamp: pd.Timestamp
    kind: Literal["bullish", "bearish"]  # bullish OB = last down candle before up impulse
    high: float
    low: float
    mid: float


# ── Swing-point detection ─────────────────────────────────────────────────────

def find_swing_highs(df: pd.DataFrame, lookback: int = 5) -> list[SwingPoint]:
    """A bar is a swing high if its high is strictly the highest in [i-lookback, i+lookback]."""
    highs = df["high"].values
    n = len(highs)
    points: list[SwingPoint] = []
    for i in range(lookback, n - lookback):
        window = highs[i - lookback: i + lookback + 1]
        if highs[i] >= np.max(window):
            points.append(SwingPoint(
                bar_idx=i,
                timestamp=df.index[i],
                price=float(highs[i]),
                kind="high",
            ))
    return points


def find_swing_lows(df: pd.DataFrame, lookback: int = 5) -> list[SwingPoint]:
    """A bar is a swing low if its low is strictly the lowest in [i-lookback, i+lookback]."""
    lows = df["low"].values
    n = len(lows)
    points: list[SwingPoint] = []
    for i in range(lookback, n - lookback):
        window = lows[i - lookback: i + lookback + 1]
        if lows[i] <= np.min(window):
            points.append(SwingPoint(
                bar_idx=i,
                timestamp=df.index[i],
                price=float(lows[i]),
                kind="low",
            ))
    return points


# ── Liquidity level clustering ────────────────────────────────────────────────

def cluster_levels(
    swing_points: list[SwingPoint],
    tolerance: float = 0.001,
) -> list[LiquidityLevel]:
    """
    Cluster swing points whose prices are within `tolerance` (fraction) of each other.
    Only clusters with >= 2 touches are returned — single touches are not liquidity.
    Returns levels sorted by price descending.
    """
    if not swing_points:
        return []

    kind = swing_points[0].kind
    prices = np.array([p.price for p in swing_points])
    sorted_idx = np.argsort(prices)
    sorted_prices = prices[sorted_idx]
    sorted_points = [swing_points[i] for i in sorted_idx]

    levels: list[LiquidityLevel] = []
    used = [False] * len(sorted_points)

    for i in range(len(sorted_points)):
        if used[i]:
            continue
        cluster_prices = [sorted_prices[i]]
        cluster_bars = [sorted_points[i].bar_idx]
        used[i] = True
        ref = sorted_prices[i]
        for j in range(i + 1, len(sorted_points)):
            if used[j]:
                continue
            if abs(sorted_prices[j] - ref) / ref <= tolerance:
                cluster_prices.append(sorted_prices[j])
                cluster_bars.append(sorted_points[j].bar_idx)
                used[j] = True
        if len(cluster_prices) >= 2:
            levels.append(LiquidityLevel(
                price=float(np.mean(cluster_prices)),
                kind=kind,
                touches=len(cluster_prices),
                bar_indices=cluster_bars,
            ))

    levels.sort(key=lambda x: x.price, reverse=True)
    return levels


# ── Sweep detection ───────────────────────────────────────────────────────────

def _wick_ratio(row: pd.Series, direction: Literal["high", "low"]) -> float:
    """Wick-to-body ratio. Higher values = cleaner rejection candle."""
    body = abs(float(row["close"]) - float(row["open"]))
    if body < 1e-10:
        return 0.0
    if direction == "high":
        wick = float(row["high"]) - max(float(row["open"]), float(row["close"]))
    else:
        wick = min(float(row["open"]), float(row["close"])) - float(row["low"])
    return max(wick / body, 0.0)


def detect_sweeps(
    df: pd.DataFrame,
    levels: list[LiquidityLevel],
    sweep_buffer: float = 0.0002,
    min_wick_ratio: float = 1.5,
    stop_buffer: float = 0.0005,
) -> list[Sweep]:
    """
    For each liquidity level, scan the dataframe for candles that:
      — Pierce the level intrabar by at least `sweep_buffer` (the wick tip clears the level)
      — Close back on the originating side (the sweep is rejected)
      — Have a wick-to-body ratio >= `min_wick_ratio`

    A "sweep_high" is a bearish reversal signal: longs were stopped, now sell.
    A "sweep_low" is a bullish reversal signal: shorts were stopped, now buy.
    """
    sweeps: list[Sweep] = []

    for level in levels:
        lp = level.price
        last_bar_in_level = max(level.bar_indices) if level.bar_indices else 0

        for i in range(last_bar_in_level + 1, len(df)):
            row = df.iloc[i]
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])

            if level.kind == "high":
                # Sweep of highs: wick above level, close back below
                if high > lp * (1 + sweep_buffer) and close < lp:
                    wr = _wick_ratio(row, "high")
                    if wr < min_wick_ratio:
                        continue
                    # Confidence: touches × wick_ratio (normalised 0–1, capped at 1)
                    confidence = min(level.touches * 0.15 + wr * 0.1, 1.0)
                    sweeps.append(Sweep(
                        bar_idx=i,
                        timestamp=df.index[i],
                        kind="sweep_high",
                        swept_level=lp,
                        wick_extreme=high,
                        close=close,
                        wick_ratio=wr,
                        entry_price=close,
                        stop_price=high * (1 + stop_buffer),
                        confidence=confidence,
                    ))

            elif level.kind == "low":
                # Sweep of lows: wick below level, close back above
                if low < lp * (1 - sweep_buffer) and close > lp:
                    wr = _wick_ratio(row, "low")
                    if wr < min_wick_ratio:
                        continue
                    confidence = min(level.touches * 0.15 + wr * 0.1, 1.0)
                    sweeps.append(Sweep(
                        bar_idx=i,
                        timestamp=df.index[i],
                        kind="sweep_low",
                        swept_level=lp,
                        wick_extreme=low,
                        close=close,
                        wick_ratio=wr,
                        entry_price=close,
                        stop_price=low * (1 - stop_buffer),
                        confidence=confidence,
                    ))

    return sweeps


# ── Order block detection ─────────────────────────────────────────────────────

def find_order_blocks(
    df: pd.DataFrame,
    impulse_threshold: float = 0.003,
    lookback: int = 50,
) -> list[OrderBlock]:
    """
    Scan for order blocks: the last candle in the opposing direction immediately
    before a strong impulsive move.

    A bullish OB = the last bearish (red) candle before a strong up-impulse.
    A bearish OB = the last bullish (green) candle before a strong down-impulse.

    impulse_threshold: the impulse candle must move >= this fraction of price.
    """
    blocks: list[OrderBlock] = []
    closes = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    n = min(lookback, len(df))
    start = max(1, len(df) - n)

    for i in range(start, len(df)):
        move = (closes[i] - opens[i]) / opens[i]

        if move >= impulse_threshold:
            # Strong bullish candle — look back for last bearish candle
            for j in range(i - 1, max(0, i - 5), -1):
                if closes[j] < opens[j]:   # bearish
                    blocks.append(OrderBlock(
                        bar_idx=j,
                        timestamp=df.index[j],
                        kind="bullish",
                        high=float(highs[j]),
                        low=float(lows[j]),
                        mid=float((highs[j] + lows[j]) / 2),
                    ))
                    break

        elif move <= -impulse_threshold:
            # Strong bearish candle — look back for last bullish candle
            for j in range(i - 1, max(0, i - 5), -1):
                if closes[j] > opens[j]:   # bullish
                    blocks.append(OrderBlock(
                        bar_idx=j,
                        timestamp=df.index[j],
                        kind="bearish",
                        high=float(highs[j]),
                        low=float(lows[j]),
                        mid=float((highs[j] + lows[j]) / 2),
                    ))
                    break

    return blocks


# ── Public convenience: run the full liquidity scan ───────────────────────────

@dataclasses.dataclass
class LiquidityScanResult:
    swing_highs: list[SwingPoint]
    swing_lows: list[SwingPoint]
    high_levels: list[LiquidityLevel]
    low_levels: list[LiquidityLevel]
    sweeps: list[Sweep]
    order_blocks: list[OrderBlock]
    latest_sweep: Sweep | None


def scan(
    df: pd.DataFrame,
    lookback: int = 5,
    tolerance: float = 0.001,
    sweep_buffer: float = 0.0002,
    min_wick_ratio: float = 1.5,
) -> LiquidityScanResult:
    """Full liquidity scan. Returns latest sweep if present."""
    sh = find_swing_highs(df, lookback)
    sl = find_swing_lows(df, lookback)
    high_levels = cluster_levels(sh, tolerance)
    low_levels = cluster_levels(sl, tolerance)
    sweeps = detect_sweeps(df, high_levels + low_levels, sweep_buffer, min_wick_ratio)
    obs = find_order_blocks(df)
    latest = sweeps[-1] if sweeps else None
    return LiquidityScanResult(sh, sl, high_levels, low_levels, sweeps, obs, latest)
