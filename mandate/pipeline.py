"""Runs every stage for one charity and writes results/run.json. Every LLM and network call is cached on disk."""
import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from . import config as C
from . import universe
from .agents import devils_advocate, memo
from .agents.compiler import compile_policy
from .decide import bond_decision, evaluate_company
from .llm import DemoModeCacheMiss
from .optimise import optimise
from .schemas import CompanyDecision, ResolvedPolicy
from .sources import market

DEFAULT_CHARITY = "cancer_research_wales"
DISCLAIMER = "Educational hackathon project. Not financial advice. Not affiliated with any charity named."


async def _screen_all(equities: list[str], policy: ResolvedPolicy, fund: dict, stats: dict,
                      progress: Callable[[str], None]) -> list[CompanyDecision]:
    """All equities in parallel (llm.py caps in-flight calls at 8). A failure sends the company to trustee review."""
    async def one(t: str) -> CompanyDecision:
        try:
            d = await evaluate_company(t, t, policy.rules, policy.weights, fund.get(t, {}), stats.get(t, {}))
        except DemoModeCacheMiss:
            raise
        except Exception as e:      # never approve a company we could not evaluate
            d = CompanyDecision(ticker=t, status="TRUSTEE_REVIEW", cap=0.0,
                                reason=f"Could not be evaluated ({type(e).__name__}: {str(e)[:80]}).")
        progress(f"    {t:6s} {d.status}")
        return d
    return list(await asyncio.gather(*(one(t) for t in equities)))


def _llm_stats(offset: int, wall: float) -> dict:
    """Totals for the 'About this run' panel, from the rows this run appended to the LLM log."""
    rows = []
    if C.LLM_LOG.exists():
        with C.LLM_LOG.open("rb") as f:
            f.seek(offset)
            rows = [json.loads(line) for line in f.read().decode("utf-8").splitlines() if line.strip()]
    by_agent = defaultdict(lambda: {"calls": 0, "cache_hits": 0, "prompt_tokens": 0, "completion_tokens": 0, "seconds": 0.0})
    for r in rows:
        a = by_agent[r["agent"]]
        a["cache_hits" if r["cache_hit"] else "calls"] += 1
        a["prompt_tokens"] += r["prompt_tokens"]
        a["completion_tokens"] += r["completion_tokens"]
        a["seconds"] = round(a["seconds"] + r["seconds"], 2)
    return {"wall_seconds": round(wall, 2), "llm_calls": sum(a["calls"] for a in by_agent.values()),
            "cache_hits": sum(a["cache_hits"] for a in by_agent.values()),
            "tokens": sum(a["prompt_tokens"] + a["completion_tokens"] for a in by_agent.values()),
            "by_agent": dict(by_agent), "models": {k: v for k, v in C.MODELS.items() if v}}


def _memo_input(policy: ResolvedPolicy, decisions: list[CompanyDecision], opt) -> dict:
    """The only data the memo may use: everything in it comes from code or from verified citations."""
    def row(d: CompanyDecision) -> dict:
        v = d.veto
        return {"ticker": d.ticker, "status": d.status, "reason": d.reason,
                **({"rule_id": v.rule_id, "quote": v.quote, "source_id": v.source_id} if v else {})}
    held = {h.ticker: h for h in opt.holdings}
    return {
        "portfolio_status": "Suggested allocation only; no purchases have occurred",
        "charity": policy.charity, "purpose": policy.purpose_summary,
        "holdings": [{"ticker": h.ticker, "dollars": h.dollars, "shares": h.shares, "weight": round(h.weight, 4),
                      "is_bond": h.is_bond} for h in opt.holdings],
        "cash_usd": opt.cash_usd,
        "rejected": [row(d) for d in decisions if d.status in ("REJECTED_ETHICS", "REJECTED_CHAIR")][:10],
        "trustee_review": [row(d) for d in decisions if d.status == "TRUSTEE_REVIEW"],
        "approved_not_held": [d.ticker for d in decisions if d.status == "APPROVED" and d.ticker not in held],
        "rules": [{"id": r.id, "clause": r.clause_ref, "text": r.text} for r in policy.rules],
        "limits": {k: {"value": getattr(policy.limits, k).value, "assumed": getattr(policy.limits, k).origin == "assumed"}
                   for k in ("min_bonds", "min_yield", "worst_year_limit")},
        "weights": policy.weights.model_dump(),
        "risk_card": opt.backtest.model_dump() if opt.backtest else None,
        "constraints_relaxed": opt.relaxed, "optimiser_error": opt.error,
    }


def run_charity(charity_id: str = DEFAULT_CHARITY, equities: Optional[list[str]] = None,
                policies_dir: Path = C.POLICIES_DIR, out_path: Optional[Path] = None,
                progress: Callable[[str], None] = print, policy_text: Optional[str] = None) -> dict:
    t0 = time.time()
    log_offset = C.LLM_LOG.stat().st_size if C.LLM_LOG.exists() else 0
    out_path = out_path or C.RESULTS_DIR / "run.json"
    equities = equities or universe.EQUITIES
    warnings: list[str] = []

    progress("[1/7] Compiling the policy into rules")
    policy_file = policies_dir / f"{charity_id}.md"
    if policy_text is None and not policy_file.exists():
        policy_file = policies_dir / f"{charity_id}.txt"
    if policy_text is None and not policy_file.exists():
        raise FileNotFoundError(f"No policy file at {policy_file}")
    if policy_text is None:
        policy_text = policy_file.read_text(encoding="utf-8")
    policy = compile_policy(policy_text)
    progress(f"      {len(policy.rules)} rules, {len(policy.unverified_rules)} unverified, "
             f"limits assumed: {[k for k in ('min_bonds', 'min_yield', 'worst_year_limit') if getattr(policy.limits, k).origin == 'assumed']}")

    progress("[2/7] Loading cached market data and evidence")
    prices = market.load_prices()
    fund, stats, yields = (market._load_json(p) for p in (market.FUNDAMENTALS, market.RISK_STATS, market.YIELDS))
    missing = [t for t in equities if t not in fund or t not in stats]
    if missing:
        warnings.append(f"No market data cached for {', '.join(missing)}; run scripts/fetch_data.py.")

    progress(f"[3-5/7] Melchior, veto, Balthasar, Casper, Chair for {len(equities)} equities")
    decisions = asyncio.run(_screen_all(equities, policy, fund, stats, progress))
    decisions += [bond_decision(b) for b in universe.BONDS]

    progress("[6/7] Optimising the portfolio")
    caps = {d.ticker: d.cap for d in decisions if d.status == "APPROVED" and d.ticker in equities}
    opt = optimise(caps, universe.BONDS, prices, yields, policy.limits)
    if not opt.ok:
        warnings.append(f"Optimiser: {opt.error}")

    progress("[7/7] Writing the trustee memo")
    memo_input = _memo_input(policy, decisions, opt)
    memo_text = ""
    try:
        memo_text = memo.write_memo(policy.charity, memo_input)
    except DemoModeCacheMiss:
        raise
    except Exception as e:
        warnings.append(f"Memo not generated ({type(e).__name__}: {str(e)[:100]}).")

    devils_advocate_points: list[str] = []
    try:
        devils_advocate_points = devils_advocate.write_devils_advocate(policy.charity, memo_input)
    except DemoModeCacheMiss:
        raise
    except Exception as e:
        warnings.append(f"Devil's advocate not generated ({type(e).__name__}: {str(e)[:100]}).")

    result = {
        "charity_id": charity_id, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "demo_mode": C.DEMO_MODE, "disclaimer": DISCLAIMER, "budget_usd": C.BUDGET_USD,
        "policy": policy.model_dump(mode="json"),
        "decisions": [d.model_dump(mode="json") for d in decisions],
        "optimiser": opt.model_dump(mode="json"),
        "memo": memo_text, "devils_advocate": devils_advocate_points, "warnings": warnings,
        "stats": _llm_stats(log_offset, time.time() - t0),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result
