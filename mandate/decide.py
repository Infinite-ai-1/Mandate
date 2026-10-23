"""Decision logic in plain code: ethics veto, FLAG handling, caps. The LLMs only supply verified inputs."""
import asyncio
from typing import Optional

from . import config as C
from .agents import balthasar, casper, chair, melchior
from .schemas import CompanyDecision, MelchiorResult, Rule, Verdict, Weights


def classify_ethics(verdicts: list[Verdict]) -> str:
    """REJECTED_ETHICS if any verified FAIL, else TRUSTEE_REVIEW if any FLAG, else CLEAN."""
    if any(v.verdict == "FAIL" and v.verified for v in verdicts):
        return "REJECTED_ETHICS"
    if any(v.verdict != "PASS" for v in verdicts):      # FLAG, or an unverified FAIL that slipped through
        return "TRUSTEE_REVIEW"
    return "CLEAN"


def first_veto(verdicts: list[Verdict]) -> Optional[Verdict]:
    return next((v for v in verdicts if v.verdict == "FAIL" and v.verified), None)


def decide_ethics(ticker: str, mel: MelchiorResult) -> Optional[CompanyDecision]:
    """The veto. Returns a final decision for rejected/flagged companies, None for clean ones (Chair decides)."""
    status = classify_ethics(mel.verdicts)
    if status == "REJECTED_ETHICS":
        v = first_veto(mel.verdicts)
        return CompanyDecision(ticker=ticker, status=status, cap=0.0, veto=v, melchior=mel,
                               reason=f"Breaks rule {v.rule_id}: {v.reason}")
    if status == "TRUSTEE_REVIEW":
        v = next(v for v in mel.verdicts if v.verdict != "PASS")
        return CompanyDecision(ticker=ticker, status=status, cap=0.0, melchior=mel,
                               reason=f"Needs trustee review on rule {v.rule_id}: {v.reason}")
    return None


def decide_chair(ticker: str, mel: MelchiorResult, fin, risk, ch) -> CompanyDecision:
    cap = C.CAP_BY_DECISION[ch.decision]
    return CompanyDecision(ticker=ticker, status="APPROVED" if cap > 0 else "REJECTED_CHAIR", cap=cap,
                           melchior=mel, balthasar=fin, casper=risk, chair=ch,
                           reason=ch.reasons[0].text if ch.reasons else "")


async def evaluate_company(ticker: str, name: str, rules: list[Rule], weights: Weights,
                           fundamentals: dict, stats: dict) -> CompanyDecision:
    """Melchior -> verify -> veto/flag, otherwise Balthasar + Casper in parallel -> Chair -> cap."""
    mel = await melchior.run(ticker, name, fundamentals.get("longBusinessSummary") or "", rules)
    final = decide_ethics(ticker, mel)
    if final:
        return final        # never reaches the Chair
    fin, risk = await asyncio.gather(balthasar.run(ticker, fundamentals), casper.run(ticker, stats))
    ch = await chair.run(ticker, name, fin, risk, weights)
    return decide_chair(ticker, mel, fin, risk, ch)


def bond_decision(ticker: str) -> CompanyDecision:
    """Bond ETFs skip the ethics screen and every agent."""
    return CompanyDecision(ticker=ticker, status="APPROVED", cap=C.BOND_MAX_WEIGHT, reason="Bond ETF, no ethics screen.")
