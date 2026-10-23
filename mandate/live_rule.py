"""Live rule: a judge types one rule, only that rule is re-screened, the portfolio is rebuilt."""
import asyncio
import copy
import hashlib
import json
import time
from typing import Optional

from . import config as C
from . import universe
from .agents import melchior
from .agents.compiler import SYSTEM
from .decide import decide_ethics
from .llm import chat_json
from .optimise import optimise
from .schemas import CompanyDecision, CompilerOutput, Limits, MelchiorResult, Rule, Verdict
from .sources import market
from .verify import quote_in

TIMEOUT_REASON = "Not checked in time, so it goes to the trustees rather than into the portfolio."


def normalise(text: str) -> str:
    """Cache key form of a rule: lowercase, single spaces, no trailing full stop."""
    return " ".join(text.lower().split()).strip(" .")


def make_rule(text: str, live_id: str) -> Rule:
    """The compiler prompt on this one sentence (fast model). If that fails, use the sentence itself."""
    sentence = normalise(text)
    try:
        out = chat_json("fast", SYSTEM, sentence, CompilerOutput, max_tokens=1500, allow_live=True)
        good = [r for r in out.rules if quote_in(r.source_quote, sentence)]
    except Exception:
        good = []
    r = good[0] if good else None
    return Rule(id=live_id, clause_ref="live rule", type=r.type if r else "hard_exclusion",
                text=r.text if r else text.strip(), threshold=r.threshold if r else None,
                keywords=r.keywords if r else [], source_quote=text.strip())


async def _screen(rule: Rule, tickers: list[str], fund: dict) -> dict[str, Verdict]:
    """Melchior (fast model) on the one rule for every approved equity. Stragglers become FLAG at the timeout."""
    tasks = {asyncio.create_task(melchior.run(t, t, fund.get(t, {}).get("longBusinessSummary") or "", [rule],
                                              agent="fast", allow_live=True)): t for t in tickers}
    done, pending = await asyncio.wait(tasks, timeout=C.LIVE_RULE_TIMEOUT_S) if tasks else (set(), set())
    for p in pending:
        p.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    flag = lambda why: Verdict(rule_id=rule.id, verdict="FLAG", verified=False, reason=why)  # noqa: E731
    out = {tasks[p]: flag(TIMEOUT_REASON) for p in pending}
    for task in done:
        try:
            out[tasks[task]] = task.result().verdicts[0]
        except Exception as e:
            out[tasks[task]] = flag(f"Could not be checked ({type(e).__name__}), so it goes to the trustees.")
    return out


def add_rule(run: dict, text: str, save: bool = True) -> dict:
    """Return a copy of `run` with the rule added, newly failing companies removed and the portfolio rebuilt."""
    t0 = time.time()
    n = sum(1 for r in run["policy"]["rules"] if str(r["id"]).startswith("L")) + 1
    rule = make_rule(text, f"L{n}")
    decisions = [CompanyDecision.model_validate(d) for d in run["decisions"]]
    approved = [d.ticker for d in decisions if d.status == "APPROVED" and d.ticker not in universe.BONDS]
    verdicts = asyncio.run(_screen(rule, approved, market._load_json(market.FUNDAMENTALS)))

    removed = []
    for i, d in enumerate(decisions):
        v = verdicts.get(d.ticker)
        if v is None:
            continue
        mel = MelchiorResult(ticker=d.ticker, verdicts=(d.melchior.verdicts if d.melchior else []) + [v])
        final = decide_ethics(d.ticker, mel)
        if final is None:           # passed the new rule: keep the Chair's decision and cap
            decisions[i] = d.model_copy(update={"melchior": mel})
            continue
        decisions[i] = final.model_copy(update={"balthasar": d.balthasar, "casper": d.casper, "chair": d.chair})
        removed.append({"ticker": d.ticker, "status": final.status, "reason": v.reason, "quote": v.quote,
                        "source_id": v.source_id, "timed_out": v.reason == TIMEOUT_REASON})

    caps = {d.ticker: d.cap for d in decisions if d.status == "APPROVED" and d.ticker not in universe.BONDS}
    opt = optimise(caps, universe.BONDS, market.load_prices(), market._load_json(market.YIELDS),
                   Limits.model_validate(run["policy"]["limits"]))
    new = copy.deepcopy(run)
    new["policy"]["rules"].append(rule.model_dump(mode="json"))
    new["decisions"] = [d.model_dump(mode="json") for d in decisions]
    new["optimiser"] = opt.model_dump(mode="json")
    new["memo_stale"] = True
    new["what_changed"] = {"rule": rule.model_dump(mode="json"), "removed": removed,
                           "old_holdings": run["optimiser"]["holdings"], "new_holdings": new["optimiser"]["holdings"],
                           "old_error": run["optimiser"].get("error"), "new_error": opt.error,
                           "seconds": round(time.time() - t0, 1)}
    if save:
        C.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        slug = hashlib.sha256(normalise(text).encode()).hexdigest()[:8]
        (C.RESULTS_DIR / f"live_{slug}.json").write_text(json.dumps(new, indent=1), encoding="utf-8")
    return new
