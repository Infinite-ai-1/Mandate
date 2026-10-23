"""Phase 5 check, offline: live rule + the Streamlit page rendered headlessly with Streamlit's AppTest.

Real: cached filings/prices/fundamentals, verification, veto, optimiser, view helpers, app.py.
Mocked: model replies. Run: python scripts/test_phase5.py
"""
import asyncio
import hashlib
import json
import os
import sys
import tempfile
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mandate import config as C  # noqa: E402
from mandate import evidence, llm, view  # noqa: E402
from mandate.live_rule import add_rule  # noqa: E402
from mandate.pipeline import run_charity  # noqa: E402

tmp = Path(tempfile.mkdtemp())
C.LLM_CACHE_DIR, C.LLM_LOG, evidence.EMB_DIR, C.RESULTS_DIR = tmp / "llm", tmp / "log.jsonl", tmp / "emb", tmp / "results"
C.MODELS.update(chair="sol", melchior="sol", balthasar="mai", casper="terra", memo="sol", fast="t56", backup="")
C.DEMO_MODE, C.LIVE_RULE_TIMEOUT_S = False, 1.0
TICKERS = ["MO", "MMM", "XYL", "BP"]
(tmp / "policies").mkdir()
(tmp / "policies" / "cancer_research_wales.md").write_text(
    "Stub policy for the offline test.\nClause 2: The charity shall not invest in tobacco producers.\n", encoding="utf-8")


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
chunks = {t: evidence.build_chunks(t) for t in TICKERS}
keys = {t: [k for k, v in fund[t].items() if isinstance(v, (int, float)) and k != "marketCap"][:2] for t in TICKERS}


def quote_for(t: str, word: str):
    c = next(c for c in chunks[t] if word in c.text.lower())
    return c.text[c.text.lower().find(word):][:90], c.source_id


def reply(agent, ticker):
    live = agent == "fast"
    if agent in ("chair", "fast") and ticker is None:      # compiler (policy, or the one live sentence)
        if live:
            return {"charity": "Live", "rules": [{"id": "R1", "clause_ref": "live", "type": "hard_exclusion", "text": "No water utilities",
                                                  "keywords": ["water"], "source_quote": "no water utilities"}]}
        return {"charity": "Test Charity", "purpose_summary": "Cancer research.", "rules": [
            {"id": "R1", "clause_ref": "2", "type": "hard_exclusion", "text": "No tobacco producers", "keywords": ["tobacco"],
             "source_quote": "The charity shall not invest in tobacco producers"}],
            "proposed_mission_conflicts": [{"id": "M1", "text": "No sugary drinks", "keywords": ["sugar"], "reasoning": "x"}]}
    if agent == "melchior":
        if ticker == "MO":
            q, sid = quote_for("MO", "tobacco")
            return {"ticker": ticker, "verdicts": [{"rule_id": "R1", "verdict": "FAIL", "quote": q, "source_id": sid, "reason": "Sells tobacco."},
                                                   {"rule_id": "M1", "verdict": "PASS", "reason": "ok"}]}
        return {"ticker": ticker, "verdicts": [{"rule_id": r, "verdict": "PASS", "reason": "ok"} for r in ("R1", "M1")]}
    if live:    # fast Melchior on rule L1
        if ticker == "XYL":
            q, sid = quote_for("XYL", "water")
            return {"ticker": ticker, "verdicts": [{"rule_id": "L1", "verdict": "FAIL", "quote": q, "source_id": sid, "reason": "Runs water utilities."}]}
        return {"ticker": ticker, "verdicts": [{"rule_id": "L1", "verdict": "PASS", "reason": "ok"}]}
    if agent == "balthasar":
        return {"ticker": ticker, "score": 8, "reasons": [{"text": "Healthy.", "metric": k, "value": fund[ticker][k]} for k in keys[ticker]]}
    if agent == "casper":
        return {"ticker": ticker, "score": 7, "reasons": [{"text": "Volatility is moderate.", "metric": "annual_vol", "value": risk[ticker]["annual_vol"]},
                                                          {"text": "Legal note.", "source_id": chunks[ticker][0].source_id}]}
    if agent == "chair":
        return {"ticker": ticker, "decision": "full", "reasons": [{"text": "Sound on both.", "source_ids": [keys[ticker][0]]}]}
    if agent == "memo":
        return {"memo": "## Recommendation\nWe recommend a **bond-heavy** portfolio. " + "word " * 30}
    raise KeyError(agent)


async def fake_acomplete(agent, system, user, max_tokens, ticker):
    if agent == "fast" and ticker == "BP":
        await asyncio.sleep(30)         # never finishes: must hit the live-rule timeout
    llm._log(agent, ticker, "mock", 100, 50, 0.01, False)
    return json.dumps(reply(agent, ticker))


llm._acomplete = fake_acomplete
llm._complete = lambda agent, system, user, max_tokens, ticker: (llm._log(agent, ticker, "mock", 100, 50, 0.01, False),
                                                                  json.dumps(reply(agent, ticker)))[1]
failed = 0


def check(label: str, ok: bool) -> None:
    global failed
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    failed += not ok


run = run_charity("cancer_research_wales", TICKERS, tmp / "policies", tmp / "run.json", progress=lambda s: None)
base_hold = {h["ticker"] for h in run["optimiser"]["holdings"]}
print(f"Base run: {sorted(base_hold)}")

print("1. Live rule 'No water utilities.'")
t = time.time()
new = add_rule(run, "No water utilities.")
dt = time.time() - t
wc = new["what_changed"]
st = {d["ticker"]: d for d in new["decisions"]}
print(f"   {dt:.1f}s; removed: {[(r['ticker'], r['status']) for r in wc['removed']]}")
check("rule added as L1", new["policy"]["rules"][-1]["id"] == "L1")
check("XYL fails the live rule with a verified quote and is removed", st["XYL"]["status"] == "REJECTED_ETHICS" and st["XYL"]["veto"]["verified"])
check("BP timed out -> FLAG, dropped (not hung)", st["BP"]["status"] == "TRUSTEE_REVIEW" and any(r["timed_out"] for r in wc["removed"]) and dt < 10)
check("MMM passed: decision and cap reused", st["MMM"]["status"] == "APPROVED" and st["MMM"]["cap"] == 0.10 and st["MMM"]["chair"]["decision"] == "full")
check("removed tickers no longer held, MMM still in play", {"XYL", "BP"}.isdisjoint({h["ticker"] for h in new["optimiser"]["holdings"]}))
check("original run untouched", {h["ticker"] for h in run["optimiser"]["holdings"]} == base_hold and "what_changed" not in run)
check("saved to results/live_*.json", len(list(C.RESULTS_DIR.glob("live_*.json"))) == 1)
t = time.time()
add_rule(run, "no water utilities", save=False)
print(f"   same rule again (cached, except the timed-out company): {time.time() - t:.1f}s")

print("2. view helpers")
hl = view.headline(new)
check("headline percentages + cash add to the budget", abs(hl["shares_pct"] + hl["bonds_pct"] + hl["cash"] / hl["budget"] - 1) < 1e-9)
check("board has 6 columns max", all(len(r) <= 6 for r in view.board_rows(new)))
check("rejections list ethics vetoes first", view.rejection_rows(new)[0]["Outcome"] == "Rejected (ethics)")

print("3. Streamlit page (AppTest)")
from streamlit.testing.v1 import AppTest  # noqa: E402

for label, data in (("base run", run), ("after live rule", new)):
    f = tmp / f"view_{label.split()[0]}.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    os.environ["MANDATE_RUN_JSON"] = str(f)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
    heads = [h.value for h in at.header]
    check(f"{label}: renders with no exception", not at.exception)
    check(f"{label}: headline shown", any(h.startswith("Invest $100,000 across") for h in heads))
    check(f"{label}: five sections + {len(at.expander)} expanders + dataframes", len(at.subheader) >= 6 and len(at.dataframe) >= 3)
    check(f"{label}: footer disclaimer visible", any("Not financial advice" in c.value for c in at.caption))
    print(f"      {heads[0][:110]}")

os.environ["MANDATE_RUN_JSON"] = str(tmp / "run.json")
at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
at.sidebar.text_input[0].set_value("No water utilities.").run()
at.sidebar.button[0].click().run(timeout=60)
check("typing a rule and clicking rebuild shows the What changed panel", not at.exception
      and any("What changed" in s.value for s in at.subheader))

if os.getenv("PHASE5_KEEP"):     # keep the mock run so the app can be launched on it by hand
    Path(os.environ["PHASE5_KEEP"]).write_text((tmp / "run.json").read_text(encoding="utf-8"), encoding="utf-8")

print(f"\n{'ALL CHECKS PASSED' if not failed else str(failed) + ' CHECK(S) FAILED'}")
sys.exit(1 if failed else 0)
