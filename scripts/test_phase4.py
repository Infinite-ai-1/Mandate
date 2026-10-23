"""Phase 4 acceptance check, offline: the whole pipeline on MO, MMM, XYL with mocked model replies.

Real: cached filings, fundamentals, prices, risk stats, verification, veto, optimiser, run.json, caching.
Mocked: what the Azure models say (no .env needed). Run: python scripts/test_phase4.py
"""
import hashlib
import json
import sys
import tempfile
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mandate import config as C  # noqa: E402
from mandate import evidence, llm  # noqa: E402
from mandate.pipeline import run_charity  # noqa: E402

tmp = Path(tempfile.mkdtemp())
C.LLM_CACHE_DIR, C.LLM_LOG, evidence.EMB_DIR = tmp / "llm", tmp / "log.jsonl", tmp / "emb"
C.MODELS.update(chair="sol", melchior="sol", balthasar="mai", casper="terra", memo="sol", fast="t56", backup="")
C.DEMO_MODE = False
TICKERS = ["MO", "MMM", "XYL"]
POLICY = ("Test Charity policy (stub for the offline test, not a real charity policy)\n"
          "Clause 2: The charity shall not invest in tobacco producers.\n")
(tmp / "policies").mkdir()
(tmp / "policies" / "cancer_research_wales.md").write_text(POLICY, encoding="utf-8")


def fake_embed(texts):
    out = []
    for t in texts:
        v = np.zeros(256)
        for w in t.lower().split():
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 256] += 1
        out.append(v.tolist())
    return out


evidence.embed = fake_embed
for t in TICKERS:
    evidence.build_index(t)
fund = json.loads((C.CACHE_DIR / "fundamentals.json").read_text(encoding="utf-8"))
risk = json.loads((C.CACHE_DIR / "risk_stats.json").read_text(encoding="utf-8"))
mo_chunk = next(c for c in evidence.build_chunks("MO") if "tobacco" in c.text.lower())
quote = mo_chunk.text[mo_chunk.text.lower().find("tobacco"):][:90]
fkeys = [k for k, v in fund["XYL"].items() if isinstance(v, (int, float)) and k != "marketCap"][:2]
xyl_chunk = evidence.build_chunks("XYL")[0].source_id
calls = []


def reply(agent: str, ticker, user: str) -> dict:
    if agent == "chair" and ticker is None:     # policy compiler
        return {"charity": "Test Charity", "purpose_summary": "Cancer research.", "rules": [
            {"id": "R1", "clause_ref": "2", "type": "hard_exclusion", "text": "No tobacco producers", "keywords": ["tobacco"],
             "source_quote": "The charity shall not invest in tobacco producers"}],
            "proposed_mission_conflicts": [{"id": "M1", "text": "No sugary drinks", "keywords": ["sugar"], "reasoning": "x"}],
            "vague_wording": [], "stated_weights": None, "stated_limits": {}}
    if agent == "melchior":
        v = {"MO": [{"rule_id": "R1", "verdict": "FAIL", "quote": quote, "source_id": mo_chunk.source_id, "reason": "Sells tobacco."},
                    {"rule_id": "M1", "verdict": "PASS", "reason": "ok"}],
             "MMM": [{"rule_id": "R1", "verdict": "PASS", "reason": "ok"},
                     {"rule_id": "M1", "verdict": "FLAG", "reason": "Evidence on sugar products is missing."}],
             "XYL": [{"rule_id": "R1", "verdict": "PASS", "reason": "ok"}, {"rule_id": "M1", "verdict": "PASS", "reason": "ok"}]}[ticker]
        return {"ticker": ticker, "verdicts": v}
    if agent == "balthasar":
        return {"ticker": ticker, "score": 8, "reasons": [{"text": "Healthy.", "metric": k, "value": fund[ticker][k]} for k in fkeys]}
    if agent == "casper":
        return {"ticker": ticker, "score": 7, "reasons": [
            {"text": "Volatility is moderate.", "metric": "annual_vol", "value": risk[ticker]["annual_vol"], "source_id": None},
            {"text": "Legal note.", "metric": None, "value": None, "source_id": xyl_chunk}]}
    if agent == "chair":
        return {"ticker": ticker, "decision": "full", "reasons": [{"text": "Sound on both.", "source_ids": [fkeys[0]]}]}
    if agent == "memo":
        return {"memo": "# Memo\nWe recommend a bond-heavy portfolio. " + "word " * 40}
    raise KeyError(agent)


async def fake_acomplete(agent, system, user, max_tokens, ticker):
    calls.append((agent, ticker))
    llm._log(agent, ticker, "mock", 100, 50, 0.01, False)
    return json.dumps(reply(agent, ticker, user))


def fake_complete(agent, system, user, max_tokens, ticker):
    calls.append((agent, ticker))
    llm._log(agent, ticker, "mock", 100, 50, 0.01, False)
    return json.dumps(reply(agent, ticker, user))


llm._acomplete, llm._complete = fake_acomplete, fake_complete
failed = 0


def check(label: str, ok: bool) -> None:
    global failed
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    failed += not ok


out = tmp / "run.json"
kw = dict(equities=TICKERS, policies_dir=tmp / "policies", out_path=out, progress=lambda s: None)
print("Run 1 (cold cache)")
t = time.time()
r1 = run_charity("cancer_research_wales", **kw)
d1 = time.time() - t
n1 = len(calls)
st = {d["ticker"]: d for d in r1["decisions"]}
print(f"  {d1:.1f}s, {n1} model calls; statuses: {{t: st[t]['status'] for t in TICKERS}}".replace("{t: st[t]['status'] for t in TICKERS}", str({t: st[t]['status'] for t in TICKERS})))
check("run.json written and parses", json.loads(out.read_text(encoding="utf-8"))["charity_id"] == "cancer_research_wales")
check("MO rejected on the ethics veto with a verified quote", st["MO"]["status"] == "REJECTED_ETHICS" and st["MO"]["veto"]["verified"])
check("MMM sent to trustee review (FLAG)", st["MMM"]["status"] == "TRUSTEE_REVIEW" and st["MMM"]["cap"] == 0)
check("XYL approved at the full cap", st["XYL"]["status"] == "APPROVED" and st["XYL"]["cap"] == 0.10)
check("MO and MMM never reached Balthasar/Casper/Chair", not [c for c in calls if c[1] in ("MO", "MMM") and c[0] != "melchior"])
opt = r1["optimiser"]
check("optimiser ok, whole shares, under $100,000", opt["ok"] and opt["invested_usd"] < 100_000
      and all(isinstance(h["shares"], int) for h in opt["holdings"]))
check("only approved equities and bond ETFs held", {h["ticker"] for h in opt["holdings"]} <= {"XYL", "SHY", "IEF", "BND", "TIP"})
check("memo, limits (assumed), stats present", bool(r1["memo"]) and r1["policy"]["limits"]["min_bonds"]["origin"] == "assumed"
      and r1["stats"]["llm_calls"] == n1 and r1["stats"]["tokens"] > 0)
check("disclaimer in output", "Not financial advice" in r1["disclaimer"])

print("Run 2 (everything cached)")
t = time.time()
r2 = run_charity("cancer_research_wales", **kw)
d2 = time.time() - t
print(f"  {d2:.1f}s, {len(calls) - n1} new model calls, {r2['stats']['cache_hits']} cache hits")
check("no new model calls", len(calls) == n1 and r2["stats"]["llm_calls"] == 0)
check("finished in under 10 seconds", d2 < 10)
check("identical decisions and holdings", [d["status"] for d in r2["decisions"]] == [d["status"] for d in r1["decisions"]]
      and r2["optimiser"]["holdings"] == r1["optimiser"]["holdings"])

print("DEMO_MODE=1 with an empty LLM cache raises a clear error")
C.DEMO_MODE, C.LLM_CACHE_DIR = True, tmp / "empty"
try:
    run_charity("cancer_research_wales", **kw)
    check("DemoModeCacheMiss raised", False)
except llm.DemoModeCacheMiss as e:
    check(f"DemoModeCacheMiss raised ({str(e)[:50]}...)", True)

print(f"\n{'ALL CHECKS PASSED' if not failed else str(failed) + ' CHECK(S) FAILED'}")
sys.exit(1 if failed else 0)
