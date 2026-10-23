"""Phase 2 acceptance check, offline. Real cached filings/fundamentals for MO, MMM, XYL; model replies are mocked.

Run: python scripts/test_phase2.py
"""
import asyncio
import hashlib
import json
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mandate import config as C  # noqa: E402
from mandate import decide, evidence, llm  # noqa: E402
from mandate.agents import chair, compiler, melchior, memo  # noqa: E402
from mandate.schemas import Rule  # noqa: E402

tmp = Path(tempfile.mkdtemp())
C.LLM_CACHE_DIR, C.LLM_LOG, evidence.EMB_DIR = tmp / "llm", tmp / "log.jsonl", tmp / "emb"
C.MODELS.update(chair="sol", melchior="sol", balthasar="mai", casper="terra", memo="sol", fast="t56", backup="")
C.DEMO_MODE = False


def fake_embed(texts):      # hashing bag-of-words: enough to exercise retrieval without the network
    out = []
    for t in texts:
        v = np.zeros(256)
        for w in t.lower().split():
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 256] += 1
        out.append(v.tolist())
    return out


evidence.embed = fake_embed
fund = json.loads((C.CACHE_DIR / "fundamentals.json").read_text(encoding="utf-8"))
risk = json.loads((C.CACHE_DIR / "risk_stats.json").read_text(encoding="utf-8"))
RULES = [Rule(id="R1", type="hard_exclusion", text="No tobacco producers", keywords=["tobacco", "cigarette"]),
         Rule(id="R2", type="hard_exclusion", text="No weapons manufacturers", keywords=["weapons", "munitions"])]
for t in ("MO", "MMM", "XYL"):
    evidence.build_index(t)

calls, SCRIPT = [], {}


async def fake_acomplete(agent, system, user, max_tokens, ticker):
    calls.append((agent, ticker))
    reply = SCRIPT[(agent, ticker)]
    if isinstance(reply, Exception):
        raise reply
    return json.dumps(reply)


llm._acomplete = fake_acomplete
llm._complete = lambda agent, system, user, max_tokens, ticker: json.dumps(SCRIPT[(agent, ticker)])


def real_quote(ticker: str, word: str) -> tuple[str, str]:
    """A genuine 90-character passage from a cached chunk that mentions `word`."""
    for c in evidence.retrieve(ticker, RULES[0]):
        i = c.text.lower().find(word)
        if i >= 0:
            return c.text[i:i + 90], c.source_id
    raise SystemExit(f"no chunk mentions {word!r} for {ticker}")


def verdicts(r1: dict, r2_pass: bool = True) -> dict:
    return {"ticker": "", "verdicts": [{"rule_id": "R1", "confidence": 0.9, **r1},
                                        {"rule_id": "R2", "verdict": "PASS", "confidence": 0.9, "reason": "No weapons business."}]}


def check(label: str, ok: bool) -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        check.failed += 1


check.failed = 0


async def main() -> None:
    print("1. MO: verified FAIL -> ethics veto, never reaches the Chair")
    q, sid = real_quote("MO", "tobacco")
    SCRIPT[("melchior", "MO")] = verdicts({"verdict": "FAIL", "quote": q, "source_id": sid, "reason": "Sells tobacco products."})
    mo = await decide.evaluate_company("MO", "Altria", RULES, compiler.merge_weights(None), fund["MO"], risk["MO"])
    print(f"     quote: {q[:70]!r}  source: {sid}")
    check("status REJECTED_ETHICS, cap 0", mo.status == "REJECTED_ETHICS" and mo.cap == 0.0)
    check("veto verdict is verified", mo.veto is not None and mo.veto.verified is True)
    check("no balthasar/casper/chair call for MO", not [c for c in calls if c[1] == "MO" and c[0] != "melchior"])

    print("2. MMM: FAIL with a fabricated quote -> downgraded to FLAG -> trustee review")
    _, real_id = real_quote("MMM", "")
    SCRIPT[("melchior", "MMM")] = verdicts({"verdict": "FAIL", "quote": "This sentence does not appear anywhere in the filing.",
                                            "source_id": real_id, "reason": "Invented."})
    mmm = await decide.evaluate_company("MMM", "3M", RULES, compiler.merge_weights(None), fund["MMM"], risk["MMM"])
    r1 = mmm.melchior.verdicts[0]
    print(f"     R1 -> {r1.verdict}, downgraded={r1.downgraded}: {r1.reason[:60]}")
    check("FAIL downgraded to FLAG", r1.verdict == "FLAG" and r1.downgraded and r1.verified is False)
    check("status TRUSTEE_REVIEW, cap 0, no Chair", mmm.status == "TRUSTEE_REVIEW" and mmm.cap == 0.0
          and not [c for c in calls if c[1] == "MMM" and c[0] != "melchior"])
    SCRIPT[("melchior", "MMM")] = verdicts({"verdict": "FAIL", "quote": q, "source_id": "MMM-10K-c9999", "reason": "Fake id."})
    mel = await melchior.run("MMM", "3M (second prompt)", "", RULES)     # new prompt text, so no cache hit
    check("FAIL citing a source_id that does not exist is downgraded", mel.verdicts[0].verdict == "FLAG")
    SCRIPT[("melchior", "MMM")] = {"ticker": "MMM", "verdicts": [{"rule_id": "R1", "verdict": "PASS", "reason": "ok"}]}
    mel = await melchior.run("MMM", "3M (third prompt)", "", RULES)
    check("a rule with no verdict becomes FLAG", [v.verdict for v in mel.verdicts] == ["PASS", "FLAG"])

    print("3. XYL: clean -> Balthasar + Casper -> Chair -> cap")
    SCRIPT[("melchior", "XYL")] = verdicts({"verdict": "PASS", "quote": None, "source_id": None, "reason": "Nothing found."})
    keys = [k for k, v in fund["XYL"].items() if isinstance(v, (int, float)) and k != "marketCap"][:2]
    SCRIPT[("balthasar", "XYL")] = {"ticker": "XYL", "score": 8, "reasons": [
        {"text": "Good margin.", "metric": keys[0], "value": fund["XYL"][keys[0]]},
        {"text": "Wrong value.", "metric": keys[1], "value": fund["XYL"][keys[1]] * 3 + 5}]}
    _, chunk_id = real_quote("XYL", "")
    vol = risk["XYL"]["annual_vol"]
    SCRIPT[("casper", "XYL")] = {"ticker": "XYL", "score": 7, "reasons": [
        {"text": "Moderate volatility.", "metric": "annual_vol", "value": vol, "source_id": None},
        {"text": "Legal note.", "metric": None, "value": None, "source_id": chunk_id},
        {"text": "Wrong stat.", "metric": "annual_vol", "value": vol * 1.5, "source_id": None}]}
    SCRIPT[("chair", "XYL")] = {"ticker": "XYL", "decision": "full", "reasons": [
        {"text": "Strong financials.", "source_ids": [keys[0]]},
        {"text": "Made-up citation.", "source_ids": ["XYL-10K-c9999"]}]}
    xyl = await decide.evaluate_company("XYL", "Xylem", RULES, compiler.merge_weights(None), fund["XYL"], risk["XYL"])
    check("Balthasar: wrong-value reason dropped to unverified", len(xyl.balthasar.reasons) == 1 and len(xyl.balthasar.unverified) == 1)
    check("Casper: wrong stat unverified, real chunk id verified", len(xyl.casper.reasons) == 2 and len(xyl.casper.unverified) == 1)
    check("Chair: fake citation unverified", len(xyl.chair.reasons) == 1 and len(xyl.chair.unverified) == 1)
    check("decision full -> cap 0.10 -> APPROVED", xyl.chair.decision == "full" and xyl.cap == 0.10 and xyl.status == "APPROVED")
    for d, cap in (("reduced", 0.05), ("reject", 0.0)):
        check(f"{d} -> cap {cap}", C.CAP_BY_DECISION[d] == cap)

    print("4. Chair failure twice -> defaults to reduced")
    SCRIPT[("chair", "XYL")] = RuntimeError("boom")
    n = len([c for c in calls if c == ("chair", "XYL")])
    res = await chair.run("XYL", "Xylem (uncached prompt)", xyl.balthasar, xyl.casper, compiler.merge_weights(None))
    check("defaulted reduced + flagged", res.decision == "reduced" and res.defaulted and "defaulted" in res.reasons[0].text)
    check("two attempts made", len([c for c in calls if c == ("chair", "XYL")]) - n == 2)

    print("5. Compiler: quote check, limits, weights")
    policy = "Cancer Research Wales\nClause 2: The charity shall not invest in tobacco producers.\nWe aim for at least 40% in bonds."
    SCRIPT_C = {"charity": "Cancer Research Wales", "purpose_summary": "Cancer research.", "rules": [
        {"id": "R1", "clause_ref": "2", "type": "hard_exclusion", "text": "No tobacco", "keywords": ["tobacco"],
         "source_quote": "the charity shall not   invest in TOBACCO producers"},
        {"id": "R2", "clause_ref": "9", "type": "hard_exclusion", "text": "No arms", "keywords": ["arms"],
         "source_quote": "The charity shall not invest in arms."}],
        "proposed_mission_conflicts": [{"id": "X", "text": "No sugary drinks", "keywords": ["sugar"], "reasoning": "Cancer risk."}],
        "vague_wording": [], "stated_weights": None, "stated_limits": {"min_bonds": 0.4}}
    SCRIPT[("chair", None)] = SCRIPT_C
    pol = compiler.compile_policy(policy)
    check("rule with real quote kept (case/whitespace-normalised)", [r.id for r in pol.rules] == ["R1", "M1"])
    check("rule with invented quote dropped to unverified", [r.id for r in pol.unverified_rules] == ["R2"])
    check("stated min_bonds wins, others assumed", pol.limits.min_bonds.origin == "stated" and pol.limits.min_yield.origin == "assumed"
          and pol.limits.min_yield.value == 0.025)
    check("weights default 50/50 assumed", (pol.weights.financial, pol.weights.risk, pol.weights.origin) == (0.5, 0.5, "assumed"))
    w = compiler.merge_weights(compiler.StatedWeights(financial=2, risk=6))
    check("stated weights normalised", (w.financial, w.risk, w.origin) == (0.25, 0.75, "stated"))

    print("6. Memo")
    SCRIPT[("memo", None)] = {"memo": "# Memo\nWe recommend a cautious portfolio."}
    check("memo returns text", memo.write_memo("Cancer Research Wales", {"holdings": []}).startswith("# Memo"))


asyncio.run(main())
print(f"\n{'ALL CHECKS PASSED' if not check.failed else str(check.failed) + ' CHECK(S) FAILED'}")
sys.exit(1 if check.failed else 0)
