"""Pydantic models for every JSON shape in CLAUDE.md. Agents return these, code never trusts raw dicts."""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ---- Evidence ----
class Chunk(Base):
    source_id: str          # MMM-10K-c0042 / MMM-20F-c0042 / MMM-NEWS-007
    ticker: str
    kind: Literal["filing", "news"]
    section: str = ""
    url: str = ""
    date: str = ""
    text: str


# ---- Compiler (Chair) ----
RuleType = Literal["hard_exclusion", "mission_conflict", "preference"]


class Rule(Base):
    id: str                 # R1.. from the policy, M1.. approved mission conflicts, L1.. live rules
    clause_ref: str = ""
    type: RuleType
    text: str
    threshold: Optional[str] = None
    keywords: list[str] = []
    source_quote: str = ""


class ProposedConflict(Base):
    id: str
    text: str
    keywords: list[str] = []
    reasoning: str = ""
    approved: bool = True   # set by code, pre-approved for the demo


class VagueWording(Base):
    quote: str
    issue: str
    assumption_used: str


class StatedWeights(Base):
    financial: float
    risk: float


class StatedLimits(Base):
    min_bonds: Optional[float] = None
    min_yield: Optional[float] = None
    worst_year_limit: Optional[float] = None
    max_single_holding: Optional[float] = None


class CompilerOutput(Base):
    charity: str
    purpose_summary: str = ""
    rules: list[Rule] = []
    proposed_mission_conflicts: list[ProposedConflict] = []
    vague_wording: list[VagueWording] = []
    stated_weights: Optional[StatedWeights] = None
    stated_limits: StatedLimits = StatedLimits()


Origin = Literal["stated", "assumed"]


class Limit(Base):
    """A limit after merging policy and defaults (done in code, not by the LLM)."""
    value: float
    origin: Origin


class Weights(Base):
    financial: float = 0.5
    risk: float = 0.5
    origin: Origin = "assumed"


class Limits(Base):
    min_bonds: Limit
    min_yield: Limit
    worst_year_limit: Limit
    max_single_holding: Optional[Limit] = None


# ---- Melchior (ethics) ----
class Verdict(Base):
    rule_id: str
    verdict: Literal["PASS", "FAIL", "FLAG"]
    confidence: float = 0.0
    quote: Optional[str] = None
    source_id: Optional[str] = None
    reason: str = ""


class MelchiorOutput(Base):
    ticker: str
    verdicts: list[Verdict]


# ---- Balthasar (financial health) ----
class FinReason(Base):
    text: str
    metric: str
    value: float


class BalthasarOutput(Base):
    ticker: str
    score: int = Field(ge=0, le=10)
    reasons: list[FinReason]


# ---- Casper (risk) ----
class RiskReason(Base):
    text: str
    metric: Optional[str] = None
    value: Optional[float] = None
    source_id: Optional[str] = None


class CasperOutput(Base):
    ticker: str
    score: int = Field(ge=0, le=10)
    reasons: list[RiskReason]


# ---- Chair (final decision) ----
class ChairReason(Base):
    text: str
    source_ids: list[str] = []


class ChairOutput(Base):
    ticker: str
    decision: Literal["full", "reduced", "reject"]
    reasons: list[ChairReason]
