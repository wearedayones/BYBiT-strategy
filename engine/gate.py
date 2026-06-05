"""
Promotion gate.

Loads acceptance.yaml, runs champion-vs-challenger logic, and tracks decay for
promoted strategies. Emits a GateResult with a clear action code.

A strategy reaches strategies/promoted/ only by passing this gate. The gate's
math runs in pure Python — never through the LLM or an external tool.
"""
from __future__ import annotations

import dataclasses
import json
from enum import Enum
from pathlib import Path

import yaml

from engine.validation import ValidationResult


class GateAction(str, Enum):
    PROMOTE = "promote"
    REJECT = "reject"
    REPLACE_CHAMPION = "replace_champion"
    KEEP_CHAMPION = "keep_champion"
    RETIRE_INCUMBENT = "retire_incumbent"


@dataclasses.dataclass
class GateResult:
    action: GateAction
    reason: str
    strategy_name: str
    oos_sharpe: float
    incumbent_sharpe: float | None = None


def load_acceptance(config_path: Path | None = None) -> dict:
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config" / "acceptance.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def run_gate(
    strategy_name: str,
    symbol: str,
    family: str,
    oos_sharpe: float,
    max_drawdown: float,
    n_trades_oos: int,
    validation: ValidationResult,
    promoted_dir: Path | None = None,
    config_path: Path | None = None,
) -> GateResult:
    acceptance = load_acceptance(config_path)
    if promoted_dir is None:
        promoted_dir = Path(__file__).parent.parent / "strategies" / "promoted"

    if not validation.passed:
        return GateResult(
            action=GateAction.REJECT,
            reason="; ".join(validation.failure_reasons),
            strategy_name=strategy_name,
            oos_sharpe=oos_sharpe,
        )

    if max_drawdown > acceptance["max_drawdown"]:
        return GateResult(
            action=GateAction.REJECT,
            reason=f"Max drawdown {max_drawdown:.1%} exceeds limit {acceptance['max_drawdown']:.1%}",
            strategy_name=strategy_name,
            oos_sharpe=oos_sharpe,
        )

    if n_trades_oos < acceptance["min_trades_oos"]:
        return GateResult(
            action=GateAction.REJECT,
            reason=f"Only {n_trades_oos} OOS trades; minimum is {acceptance['min_trades_oos']}",
            strategy_name=strategy_name,
            oos_sharpe=oos_sharpe,
        )

    incumbent = _find_incumbent(symbol, family, promoted_dir)
    if incumbent is not None:
        incumbent_sharpe = float(incumbent.get("oos_sharpe", 0.0))
        margin = acceptance.get("champion_margin", 0.05)
        if oos_sharpe > incumbent_sharpe + margin:
            return GateResult(
                action=GateAction.REPLACE_CHAMPION,
                reason=f"New OOS Sharpe {oos_sharpe:.2f} beats incumbent {incumbent_sharpe:.2f} by >{margin}",
                strategy_name=strategy_name,
                oos_sharpe=oos_sharpe,
                incumbent_sharpe=incumbent_sharpe,
            )
        return GateResult(
            action=GateAction.KEEP_CHAMPION,
            reason=f"New OOS Sharpe {oos_sharpe:.2f} does not beat incumbent {incumbent_sharpe:.2f} + margin {margin}",
            strategy_name=strategy_name,
            oos_sharpe=oos_sharpe,
            incumbent_sharpe=incumbent_sharpe,
        )

    return GateResult(
        action=GateAction.PROMOTE,
        reason=f"All gate checks passed; no incumbent for {symbol}/{family}",
        strategy_name=strategy_name,
        oos_sharpe=oos_sharpe,
    )


def check_decay(
    strategy_name: str,
    live_sharpe_90d: float,
    backtest_sharpe: float,
    config_path: Path | None = None,
) -> GateResult:
    """Compare rolling 90-day live Sharpe against backtest Sharpe; retire on decay."""
    acceptance = load_acceptance(config_path)
    threshold = acceptance.get("decay_threshold", 0.5)
    if live_sharpe_90d < backtest_sharpe * threshold:
        return GateResult(
            action=GateAction.RETIRE_INCUMBENT,
            reason=f"Live 90d Sharpe {live_sharpe_90d:.2f} < {threshold:.0%} of backtest {backtest_sharpe:.2f}",
            strategy_name=strategy_name,
            oos_sharpe=live_sharpe_90d,
            incumbent_sharpe=backtest_sharpe,
        )
    return GateResult(
        action=GateAction.KEEP_CHAMPION,
        reason=f"No decay: live {live_sharpe_90d:.2f} >= {threshold:.0%} * backtest {backtest_sharpe:.2f}",
        strategy_name=strategy_name,
        oos_sharpe=live_sharpe_90d,
        incumbent_sharpe=backtest_sharpe,
    )


def _find_incumbent(symbol: str, family: str, promoted_dir: Path) -> dict | None:
    """Return the best (highest oos_sharpe) promoted strategy matching symbol+family."""
    if not promoted_dir.exists():
        return None
    best: dict | None = None
    for fp in promoted_dir.glob("*.json"):
        try:
            meta = json.loads(fp.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if meta.get("symbol") == symbol and meta.get("family") == family:
            if best is None or meta.get("oos_sharpe", 0) > best.get("oos_sharpe", 0):
                best = meta
    return best
