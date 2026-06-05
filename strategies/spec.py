from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


_BOILERPLATE = frozenset([
    "lorem ipsum", "buy low sell high", "this is a strategy",
    "insert thesis here", "tbd", "to be determined",
])
_LOREM_RE = re.compile(r"\blorem\b", re.IGNORECASE)


class RiskParams(BaseModel):
    stop_loss_pct: float = Field(..., gt=0, lt=1)
    take_profit_pct: float = Field(..., gt=0, lt=5)
    max_position_pct: float = Field(..., gt=0, le=0.10)
    leverage: float = Field(..., ge=1, le=5)


class StrategySpec(BaseModel):
    thesis: str = Field(..., min_length=20)
    name: str = Field(..., min_length=3, max_length=64)
    family: Literal["trend", "mean_reversion", "carry", "stat_arb", "volatility"]
    symbol: str = Field(..., pattern=r"^[A-Z]{3,10}USDT$")
    timeframe: str = Field(..., description="Bybit timeframe: '1','5','15','60','240','D'")
    parameters: dict[str, Any] = Field(default_factory=dict)
    entry_logic: str = Field(..., min_length=10)
    exit_logic: str = Field(..., min_length=10)
    risk: RiskParams

    @field_validator("thesis")
    @classmethod
    def thesis_must_not_be_boilerplate(cls, v: str) -> str:
        lower = v.lower().strip()
        if _LOREM_RE.search(lower):
            raise ValueError("Thesis contains lorem ipsum placeholder text")
        for phrase in _BOILERPLATE:
            if phrase in lower:
                raise ValueError(f"Thesis contains boilerplate phrase: '{phrase}'")
        if len(v.split()) < 10:
            raise ValueError(f"Thesis too short ({len(v.split())} words); explain the edge in at least 10 words")
        return v

    @model_validator(mode="after")
    def risk_within_hard_limits(self) -> StrategySpec:
        # Hard limits mirrored from config/settings.yaml — cannot be loosened via YAML edit
        if self.risk.leverage > 5:
            raise ValueError("leverage exceeds global hard limit of 5x")
        if self.risk.max_position_pct > 0.10:
            raise ValueError("max_position_pct exceeds global hard limit of 10%")
        return self
