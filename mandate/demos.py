"""Explicit scripted research scenarios, isolated from live ticker identities."""
import json
from pathlib import Path

SCENARIOS = {"DEMO-" + s["ticker"]: s for s in json.loads(Path(__file__).with_name("demo_scenarios.json").read_text(encoding="utf-8"))}
PRICES = {"DEMO-XYL": 100.0, "DEMO-MSFT": 200.0, "DEMO-PM": 50.0, "DEMO-MMM": 125.0}


def report(ticker):
    s = SCENARIOS[ticker]
    verdict = "FAIL" if s["decision"] == "REJECT" else "FLAG" if s["decision"] == "TRUSTEE_REVIEW" else "PASS"
    votes = {"balthasar": "INVEST", "casper": "REVIEW" if s["decision"] in ("APPROVE_CAPPED", "TRUSTEE_REVIEW") else "INVEST"}
    sid = ticker + "-ASSUMPTION"
    def score(agent, index):
        return dict(ticker=ticker, agent=agent, model="Scripted demo", score=None,
                    reasons=[dict(claim=s["notes"][index], source_ids=[sid], verified=None)], summary=s["notes"][index])
    return dict(simulated=True, devils_advocate=s["challenges"], explicit_votes=votes,
                melchior=dict(ticker=ticker, agent="melchior", model="Scripted demo", verdicts=[dict(rule_id="DEMO-R1", verdict=verdict,
                  confidence=0, quote=s["notes"][0], source_id=sid, reason=s["notes"][0], verified=verdict != "FLAG")]),
                balthasar=score("balthasar", 1), casper=score("casper", 2),
                decision=dict(ticker=ticker, name="★ " + s["name"] + " · DEMO", decision=s["decision"], cap=s["cap"]/100,
                  decided_by="code_veto" if verdict != "PASS" else "chair", reason=s["reason"] + " " + s["notes"][3], source_ids=[sid], weighted_score=None))
