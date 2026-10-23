"""Chair: full / reduced / reject for ethically clean companies. Never sees a number it could allocate."""
import json

from ..llm import DemoModeCacheMiss, achat_json
from ..schemas import ChairOutput, ChairResult, FinResult, RiskResult, Weights
from ..verify import verify_chair

SYSTEM = """You are the Chair of a charity's investment committee. This company has already passed the ethics
screen; ethics is not your decision. Weigh financial health and risk using these weights: {weights}.
Return ONLY JSON:
{{"ticker": str, "decision": "full|reduced|reject",
 "reasons": [{{"text": str, "source_ids": [str]}}]}}
- full: sound on both. reduced: acceptable but one notable weakness. reject: serious weakness.
- Cite source_ids or metric keys from the specialists' verified reasons only.
- 2 or 3 reasons, each one sentence for a volunteer trustee."""
DEFAULT_REASON = "Chair unavailable, defaulted to reduced cap"


def _weights_text(w: Weights) -> str:
    return f"financial health {w.financial:.0%}, risk {w.risk:.0%} ({'stated in the policy' if w.origin == 'stated' else 'assumed 50/50 pending trustee confirmation'})"


def _spec(score, reasons, note: str, cite) -> dict:
    return {"score": score if score is not None else "data missing", "note": note,
            "verified_reasons": [{"text": r.text, "cite": cite(r)} for r in reasons]}


def allowed_ids(fin: FinResult, risk: RiskResult) -> set[str]:
    ids = {r.metric for r in fin.reasons if r.metric and r.metric != "missing"}
    ids |= {r.metric for r in risk.reasons if r.metric} | {r.source_id for r in risk.reasons if r.source_id}
    return ids


async def run(ticker: str, name: str, fin: FinResult, risk: RiskResult, weights: Weights) -> ChairResult:
    user = json.dumps({"company": f"{name} ({ticker})",
                       "financial_health": _spec(fin.score, fin.reasons, fin.note, lambda r: [r.metric]),
                       "risk": _spec(risk.score, risk.reasons, risk.note,
                                     lambda r: [i for i in (r.metric, r.source_id) if i])}, indent=1)
    system = SYSTEM.format(weights=_weights_text(weights))
    for _ in range(2):      # "if the Chair call fails twice, default to reduced"
        try:
            out = await achat_json("chair", system, user, ChairOutput, ticker=ticker)
            return verify_chair(out, allowed_ids(fin, risk))
        except DemoModeCacheMiss:
            raise           # a missing cache in demo mode is a setup error, not a Chair failure
        except Exception:
            continue
    return ChairResult(ticker=ticker, decision="reduced", defaulted=True,
                       reasons=[{"text": DEFAULT_REASON, "source_ids": []}])
