"""
Risk management engine.

All hard limits live here as pure Python functions.
The agent and the MCP call these; they never recompute limits themselves.
Daily P&L state is persisted to state/daily_pnl.json so it survives restarts.
"""
from __future__ import annotations

import dataclasses
import json
import os
from datetime import datetime, timezone
from pathlib import Path


_STATE_PATH = Path(__file__).parent.parent / "state" / "daily_pnl.json"


# ── Data structures ───────────────────────────────────────────────────────────

@dataclasses.dataclass
class RiskCheck:
    approved: bool
    reason: str


@dataclasses.dataclass
class DailyState:
    date_utc: str           # YYYY-MM-DD
    pnl: float              # cumulative realised + unrealised PnL for the day
    nav_start: float        # NAV at start of day (for % calculation)
    trade_count: int


# ── Daily state persistence ───────────────────────────────────────────────────

def _today_utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def load_daily_state(nav_current: float) -> DailyState:
    """Load today's state, resetting if the stored date is not today."""
    today = _today_utc()
    if _STATE_PATH.exists():
        try:
            d = json.loads(_STATE_PATH.read_text())
            if d.get("date_utc") == today:
                return DailyState(**d)
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
    # New day or corrupt file — reset
    state = DailyState(date_utc=today, pnl=0.0, nav_start=nav_current, trade_count=0)
    _save_daily_state(state)
    return state


def _save_daily_state(state: DailyState) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(dataclasses.asdict(state), indent=2))


def record_trade_pnl(pnl_delta: float, nav_current: float) -> DailyState:
    """Update daily PnL after a trade closes. Returns the updated state."""
    state = load_daily_state(nav_current)
    state.pnl += pnl_delta
    state.trade_count += 1
    _save_daily_state(state)
    return state


# ── Hard limit checks ─────────────────────────────────────────────────────────

def check_halt(repo_root: Path | None = None) -> RiskCheck:
    """First check: is the HALT flag set?"""
    root = repo_root or Path(__file__).parent.parent
    if (root / ".halt").exists():
        return RiskCheck(False, "HALT flag is set — all activity suspended")
    return RiskCheck(True, "no halt")


def check_daily_loss(
    nav_current: float,
    daily_loss_limit_pct: float = 0.02,
) -> RiskCheck:
    """Reject new trades if today's P&L has hit the daily loss limit."""
    state = load_daily_state(nav_current)
    if state.nav_start <= 0:
        return RiskCheck(True, "nav_start=0, skipping daily loss check")
    pnl_pct = state.pnl / state.nav_start
    if pnl_pct <= -daily_loss_limit_pct:
        return RiskCheck(
            False,
            f"Daily loss {pnl_pct:.2%} reached limit {-daily_loss_limit_pct:.2%}",
        )
    return RiskCheck(True, f"Daily PnL {pnl_pct:+.2%} within limit")


def check_position_count(
    open_positions: int,
    max_concurrent: int = 4,
) -> RiskCheck:
    """Reject new trades if already at max concurrent positions."""
    if open_positions >= max_concurrent:
        return RiskCheck(
            False,
            f"Max concurrent positions ({max_concurrent}) reached ({open_positions} open)",
        )
    return RiskCheck(True, f"{open_positions}/{max_concurrent} positions open")


def check_position_size(
    entry_price: float,
    qty: float,
    account_nav: float,
    max_position_pct: float = 0.05,
    leverage: float = 3.0,
) -> RiskCheck:
    """Reject if the notional exceeds max_position_pct of NAV (with leverage)."""
    notional = entry_price * qty
    max_notional = account_nav * max_position_pct * leverage
    if notional > max_notional:
        return RiskCheck(
            False,
            f"Notional {notional:.2f} exceeds limit {max_notional:.2f} "
            f"({max_position_pct:.0%} NAV × {leverage}x)",
        )
    return RiskCheck(True, f"Position size {notional:.2f} within limit {max_notional:.2f}")


def check_stop_distance(
    entry_price: float,
    stop_price: float,
    max_stop_pct: float = 0.015,
) -> RiskCheck:
    """Reject if stop is further from entry than max_stop_pct."""
    dist = abs(entry_price - stop_price) / entry_price
    if dist > max_stop_pct:
        return RiskCheck(
            False,
            f"Stop distance {dist:.3%} exceeds max {max_stop_pct:.3%}",
        )
    return RiskCheck(True, f"Stop distance {dist:.3%} within limit")


def check_reward_risk(rr: float, min_rr: float = 1.5) -> RiskCheck:
    """Reject trades with reward:risk below the minimum."""
    if rr < min_rr:
        return RiskCheck(False, f"R:R {rr:.2f} below minimum {min_rr:.2f}")
    return RiskCheck(True, f"R:R {rr:.2f} passes minimum {min_rr:.2f}")


def run_all_checks(
    entry_price: float,
    stop_price: float,
    qty: float,
    rr: float,
    account_nav: float,
    open_positions: int,
    limits: dict,
) -> RiskCheck:
    """
    Run every hard limit check in sequence. Returns the first failure, or approval.
    `limits` is the parsed config/risk.yaml dict.
    """
    checks = [
        check_halt(),
        check_daily_loss(account_nav, limits.get("daily_loss_limit_pct", 0.02)),
        check_position_count(open_positions, limits.get("max_concurrent_positions", 4)),
        check_position_size(
            entry_price, qty, account_nav,
            limits.get("max_position_pct", 0.05),
            limits.get("max_leverage", 3),
        ),
        check_stop_distance(entry_price, stop_price, limits.get("max_stop_pct", 0.015)),
        check_reward_risk(rr, limits.get("min_rr", 1.5)),
    ]
    for c in checks:
        if not c.approved:
            return c
    return RiskCheck(True, "all checks passed")
