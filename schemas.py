"""Shared API/quant contracts. Internal agent models live in mandate.schemas."""
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

class Decision(Strict):
    ticker: str
    decision: Literal["APPROVE", "APPROVE_CAPPED", "REJECT", "TRUSTEE_REVIEW"]
    cap: float
    decided_by: Literal["code_veto", "prefilter", "chair"]
    reason: str
    source_ids: list[str]
    weighted_score: float | None

class Holding(Strict):
    ticker: str
    name: str
    is_bond: bool
    usd: float
    shares: int
    price: float
    weight: float
    cap: float
    reason: str
    source_ids: list[str]

class Risk(Strict):
    worst_12m: float
    yield_: float = Field(alias="yield")
    volatility: float
    vs_6040_return: float

class Checks(Strict):
    max_drawdown_ok: bool
    yield_ok: bool
    bonds_ok: bool

class RunStats(Strict):
    seconds: float
    llm_calls: int
    tokens: int
    by_agent: dict

class Portfolio(Strict):
    charity_id: str
    total_usd: float
    gbpusd: float
    as_of: str
    holdings: list[Holding]
    cash_usd: float
    risk: Risk
    checks: Checks
    relaxed: list[str]
    rejected: list[Decision]
    trustee_review: list[Decision]
    memo: str
    devils_advocate: list[str]
    run_stats: RunStats

    def model_dump(self, **kwargs):
        kwargs.setdefault("by_alias", True)
        return super().model_dump(**kwargs)


class Metric(Strict):
    name: str
    value: float
    unit: str
    as_of: str
    source_id: str
