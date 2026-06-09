"""Tests for engine/bracket.py and engine/events.py."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from engine.bracket import (
    BracketLevels,
    compute_bracket_levels,
    find_consolidation,
    size_bracket_trade,
)
from engine.events import (
    is_in_pre_event_window,
    minutes_to_next_funding,
    next_event,
    upcoming_events,
)
from tests.conftest import make_ohlcv, make_ranging_ohlcv


# ── Consolidation detection ───────────────────────────────────────────────────

def test_tight_range_is_valid():
    df = make_ranging_ohlcv(n=40, range_pct=0.003, seed=7)
    # Use a generous ATR threshold — the synthetic range is real but loose
    result = find_consolidation(df, bars=20, atr_ratio_threshold=3.0, min_range_pct=0.001)
    assert result.is_valid


def test_trending_range_is_invalid():
    df = make_ohlcv(n=60, trend=0.002, volatility=0.005)
    result = find_consolidation(df, bars=20, atr_ratio_threshold=0.5, min_range_pct=0.001)
    assert not result.is_valid
    assert "ATR ratio" in result.reason or "range" in result.reason


def test_micro_range_is_invalid():
    df = make_ranging_ohlcv(n=40, range_pct=0.0001)
    result = find_consolidation(df, bars=20, min_range_pct=0.002)
    assert not result.is_valid
    assert "min" in result.reason


def test_insufficient_bars_is_invalid():
    df = make_ohlcv(n=10)
    result = find_consolidation(df, bars=20)
    assert not result.is_valid
    assert "insufficient" in result.reason


def test_consolidation_range_high_gt_low():
    df = make_ranging_ohlcv(40)
    result = find_consolidation(df, bars=20, atr_ratio_threshold=2.0)
    assert result.range_high > result.range_low


# ── Bracket level computation ─────────────────────────────────────────────────

def _valid_consol(mid=40000.0, range_pct=0.004):
    from engine.bracket import Consolidation
    h = mid * range_pct
    return Consolidation(
        is_valid=True, range_high=mid + h / 2, range_low=mid - h / 2,
        range_height=h, range_pct=range_pct, atr=h * 1.5, atr_ratio=0.8,
        bars_checked=20, reason="valid",
    )


def _valid_consol_large(mid=40000.0, range_pct=0.02):
    """Wider range so that risk_pct sizing dominates over max_position_pct."""
    from engine.bracket import Consolidation
    h = mid * range_pct
    return Consolidation(
        is_valid=True, range_high=mid + h / 2, range_low=mid - h / 2,
        range_height=h, range_pct=range_pct, atr=h * 1.5, atr_ratio=0.8,
        bars_checked=20, reason="valid",
    )


def test_buy_entry_above_range():
    levels = compute_bracket_levels(_valid_consol())
    consol = _valid_consol()
    assert levels.buy_entry > consol.range_high


def test_sell_entry_below_range():
    levels = compute_bracket_levels(_valid_consol())
    consol = _valid_consol()
    assert levels.sell_entry < consol.range_low


def test_buy_stop_below_range():
    levels = compute_bracket_levels(_valid_consol())
    consol = _valid_consol()
    assert levels.buy_stop < consol.range_low


def test_sell_stop_above_range():
    levels = compute_bracket_levels(_valid_consol())
    consol = _valid_consol()
    assert levels.sell_stop > consol.range_high


def test_targets_are_measured_moves():
    levels = compute_bracket_levels(_valid_consol())
    h = levels.range_height
    assert abs(levels.buy_target1 - (levels.buy_entry + h)) < 1.0
    assert abs(levels.buy_target2 - (levels.buy_entry + 2 * h)) < 1.0
    assert abs(levels.sell_target1 - (levels.sell_entry - h)) < 1.0
    assert abs(levels.sell_target2 - (levels.sell_entry - 2 * h)) < 1.0


def test_rr_positive_for_valid_consol():
    levels = compute_bracket_levels(_valid_consol())
    assert levels.long_rr1 > 0
    assert levels.long_rr2 > levels.long_rr1
    assert levels.short_rr1 > 0
    assert levels.short_rr2 > levels.short_rr1


# ── Position sizing ───────────────────────────────────────────────────────────

def test_sizing_respects_risk_pct():
    # Use a large consolidation so the risk_pct leg dominates over max_position_pct cap
    levels = compute_bracket_levels(_valid_consol_large())
    nav = 10_000.0
    trade = size_bracket_trade("long", levels, nav, risk_pct=0.01, max_position_pct=0.50)
    # Risk amount should be approximately 1% of NAV
    assert abs(trade.risk_amount - nav * 0.01) / (nav * 0.01) < 0.05


def test_sizing_respects_max_position_pct():
    levels = compute_bracket_levels(_valid_consol())
    nav = 10_000.0
    trade = size_bracket_trade("long", levels, nav, risk_pct=0.5, max_position_pct=0.05)
    max_notional = nav * 0.05 * 1.0  # leverage=1
    assert trade.position_size * trade.entry_price <= max_notional + 0.01


def test_sizing_direction_short():
    levels = compute_bracket_levels(_valid_consol())
    trade = size_bracket_trade("short", levels, 10_000.0)
    assert trade.direction == "short"
    assert trade.entry_price == levels.sell_entry
    assert trade.stop_price == levels.sell_stop


def test_sizing_direction_long():
    levels = compute_bracket_levels(_valid_consol())
    trade = size_bracket_trade("long", levels, 10_000.0)
    assert trade.direction == "long"
    assert trade.entry_price == levels.buy_entry
    assert trade.stop_price == levels.buy_stop


# ── Event schedule ────────────────────────────────────────────────────────────

def test_upcoming_events_sorted():
    events = upcoming_events()
    times = [e.utc_time for e in events]
    assert times == sorted(times)


def test_upcoming_events_all_in_future():
    now = datetime.now(tz=timezone.utc)
    events = upcoming_events(now=now)
    for e in events:
        assert e.minutes_away > 0


def test_next_event_is_first_upcoming():
    ne = next_event()
    all_ev = upcoming_events()
    if all_ev:
        assert ne is not None
        assert ne.utc_time == all_ev[0].utc_time


def test_minutes_to_next_funding_positive():
    assert minutes_to_next_funding() > 0


def test_minutes_to_next_funding_within_8h():
    assert minutes_to_next_funding() <= 8 * 60


def test_pre_event_window_detection():
    # Construct a now that is 30 minutes before 08:00 UTC
    now = datetime(2025, 1, 15, 7, 30, 0, tzinfo=timezone.utc)
    in_window, event = is_in_pre_event_window(now=now, window_minutes=45, min_minutes_away=5)
    assert in_window
    assert event is not None
    assert 5 <= event.minutes_away <= 45


def test_outside_event_window():
    # 3 hours before any event
    now = datetime(2025, 1, 15, 5, 0, 0, tzinfo=timezone.utc)
    in_window, event = is_in_pre_event_window(now=now, window_minutes=45)
    assert not in_window
    assert event is None


# ── engine/risk.py ─────────────────────────────────────────────────────────────

def test_risk_halt_check(tmp_path):
    from engine.risk import check_halt
    # No .halt file
    ok = check_halt(tmp_path)
    assert ok.approved

    # Create .halt
    (tmp_path / ".halt").write_text("halted")
    blocked = check_halt(tmp_path)
    assert not blocked.approved
    assert "HALT" in blocked.reason


def test_risk_daily_loss_check(tmp_path):
    from engine.risk import DailyState, _save_daily_state, _STATE_PATH, check_daily_loss
    import engine.risk as risk_module

    original_path = risk_module._STATE_PATH
    risk_module._STATE_PATH = tmp_path / "state" / "daily_pnl.json"
    try:
        from datetime import datetime, timezone
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        state = DailyState(date_utc=today, pnl=-210.0, nav_start=10_000.0, trade_count=3)
        risk_module._save_daily_state(state)
        result = risk_module.check_daily_loss(10_000.0, daily_loss_limit_pct=0.02)
        assert not result.approved
        assert "Daily loss" in result.reason
    finally:
        risk_module._STATE_PATH = original_path


def test_risk_position_count():
    from engine.risk import check_position_count
    assert check_position_count(2, max_concurrent=4).approved
    assert not check_position_count(4, max_concurrent=4).approved


def test_risk_stop_distance():
    from engine.risk import check_stop_distance
    assert check_stop_distance(100.0, 98.5, max_stop_pct=0.02).approved
    assert not check_stop_distance(100.0, 97.0, max_stop_pct=0.02).approved


def test_risk_reward_risk():
    from engine.risk import check_reward_risk
    assert check_reward_risk(2.0, min_rr=1.5).approved
    assert not check_reward_risk(1.2, min_rr=1.5).approved
