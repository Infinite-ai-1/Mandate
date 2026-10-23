"""SYNTHETIC ONLY offline contract server, never a fallback for the real API.

Run at repo root: python -m frontend.dev.stub_api. Does not load .env or fetch data.
All routes follow AGENTS.md. The response header labels this fixture explicitly.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import threading
import time
import types
import uuid
from unittest.mock import patch

from flask import Flask, jsonify, request
from quant.contract_fixtures import CHARITIES, Portfolio, fixture_inputs
from quant.optimiser import optimise
from frontend.flask_static import register_frontend

class Store:
    def __init__(self, cache_dir=None):
        self.rules, self.prices, self.decisions, self.portfolios, self.sources, self.jobs = {}, {}, {}, {}, {}, {}
        self.lock = threading.RLock()
        self.cache_dir = Path(cache_dir) if cache_dir else None
        with patch.dict("sys.modules", {"schemas": types.SimpleNamespace(Portfolio=Portfolio)}):
            for cid, name, _ in CHARITIES:
                prices, rules, decisions = fixture_inputs(cid, name)
                rules["rules"].append(dict(id="R2", clause="Purpose", text="Synthetic mission alignment review", test="Trustee approval required", threshold="review", keywords=[], origin="proposed", approved=False))
                self.prices[cid], self.rules[cid], self.decisions[cid] = prices, rules, decisions
                self.portfolios[cid] = self._compute(cid)
        for ticker in ("TEST", "CAPPED", "VETO", "REVIEW", "SPY", "AGG", "BND"):
            self.sources[f"S-{ticker}-TEST"] = dict(source_id=f"S-{ticker}-TEST", ticker=ticker, kind="filing", origin="edgar_10k",
                title=f"SYNTHETIC {ticker} filing for interface tests", date="2026-01-23", section="Synthetic test evidence",
                url=f"/api/fixture-evidence/{ticker}")

    def register(self, **source):
        self.sources[source["source_id"]] = source

    def _compute(self, cid):
        # Demonstration only: inject documented contract model if real model is absent.
        with patch.dict("sys.modules", {"schemas": types.SimpleNamespace(Portfolio=Portfolio)}):
            result = optimise(self.decisions[cid], self.rules[cid], self.prices[cid], gbpusd=1.30, register_source=self.register).model_dump(mode="json")
        result["memo"] += "\n\nSYNTHETIC fixture: demonstrates the contract only. Confirm all proposed and assumed limits before any real use."
        result["devils_advocate"] = ["Synthetic prices cannot support an investment decision.", "The historical replay excludes costs and taxes.", "Assumed rules need trustee approval."]
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{cid}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    def company(self, cid, ticker):
        decision = next((d for d in self.decisions[cid] if d["ticker"]==ticker), None)
        if decision is None:
            return None
        verdict = "FAIL" if decision["decision"]=="REJECT" else "FLAG" if decision["decision"]=="TRUSTEE_REVIEW" else "PASS"
        source = f"S-{ticker}-TEST"
        def score(agent, model):
            return dict(ticker=ticker, agent=agent, model=model, score=70, reasons=[dict(claim="Synthetic evidence for an offline interface test.", source_ids=[source], verified=True)], summary="Fixture score, not an investment assessment.")
        return dict(melchior=dict(ticker=ticker, agent="melchior", model="GPT 6.1 Sol (fixture)", verdicts=[dict(rule_id="R1", verdict=verdict, confidence=.9,
            quote="Synthetic test quote: this company sells tobacco." if verdict=="FAIL" else "Synthetic test quote: further evidence is available.",
            source_id=source, reason=decision["reason"], verified=True)]), balthasar=score("balthasar", "MAI Thinking 1 (fixture)"),
            casper=score("casper", "Claude Sonnet 5.5 (fixture)"), decision=decision)

    def job(self, cid, rule_text=None, ticker=None):
        job_id = uuid.uuid4().hex
        self.jobs[job_id] = dict(status="queued", progress=["Synthetic job queued; no external services are called."], result=None, error=None)
        def work():
            job=self.jobs[job_id]
            try:
                job["status"]="running"
                for message in ["Reading cached synthetic evidence.", "Checking rule and ethics decisions.", "Solving minimum-volatility allocation."]:
                    job["progress"].append(message);time.sleep(.45)
                with self.lock:
                    targets=[cid] if cid else [c[0] for c in CHARITIES]
                    for target in targets:
                        if rule_text:
                            self.rules[target]["rules"].append(dict(id=f"J-{job_id}",clause="Judge",text=rule_text,test="Synthetic live-rule demonstration",threshold="review",keywords=[],origin="judge",approved=True))
                            # Explicitly simulated policy effect, never an actual agent conclusion.
                            for d in self.decisions[target]:
                                if d["ticker"]=="TEST":
                                    d.update(decision="REJECT",cap=0,reason="Synthetic live-rule demonstration: TEST removed for this interface test.")
                        self.portfolios[target]=self._compute(target)
                    job["result"]=self.portfolios[targets[0]]
                job["progress"].append("Synthetic portfolio ready.")
                job["status"]="done"
            except Exception as error:
                job["status"]="error";job["error"]=str(error)
        threading.Thread(target=work,daemon=True).start()
        return job_id

def create_app(cache_dir=None, serve_static=True):
    app=Flask(__name__);store=Store(cache_dir);app.config["FIXTURE_STORE"]=store
    @app.after_request
    def label(response):
        response.headers["X-Mandate-Data"]="synthetic"
        response.headers["Access-Control-Allow-Origin"]="*"
        return response
    @app.get("/api/health")
    def health():return jsonify(status="ok", mode="synthetic")
    @app.get("/api/charities")
    def charities():return jsonify([dict(charity_id=cid,name=name,purpose=purpose+" · SYNTHETIC fixture") for cid,name,purpose in CHARITIES])
    @app.get("/api/charities/<cid>/<resource>")
    def resource(cid,resource):
        if cid not in store.rules:return jsonify(error="Unknown charity"),404
        if resource=="policy":return jsonify(text="SYNTHETIC TEST POLICY. This is not the charity's actual policy.\nNo tobacco. All other limits in this fixture are assumed for testing.")
        if resource=="rules":return jsonify(store.rules[cid])
        if resource=="portfolio":return jsonify(store.portfolios[cid])
        if resource=="selection":return jsonify(charity_id=cid,universe_size=550,after_prefilter=400,excluded_by_sic=[dict(ticker="VETO",sic="2111",rule_id="R1")],selected=[dict(ticker=d["ticker"],why="diversification") for d in store.decisions[cid]])
        return jsonify(error="Unknown resource"),404
    @app.get("/api/charities/<cid>/companies/<ticker>")
    def company(cid,ticker):
        result=store.company(cid,ticker) if cid in store.rules else None
        return jsonify(result) if result else (jsonify(error="Company report unavailable"),404)
    @app.get("/api/sources/<sid>")
    def source(sid):return jsonify(store.sources[sid]) if sid in store.sources else (jsonify(error="Unknown source"),404)
    @app.get("/api/fixture-evidence/<ticker>")
    def evidence(ticker):return jsonify(title="SYNTHETIC evidence",text="Synthetic test quote: this company sells tobacco. Synthetic test quote: further evidence is available.")
    @app.get("/api/compare/<ticker>")
    def compare(ticker):return jsonify([dict(charity_id=cid,decision=report["decision"]) for cid,_,_ in CHARITIES if (report:=store.company(cid,ticker))])
    @app.post("/api/charities/<cid>/rules")
    def rule(cid):
        if cid not in store.rules:return jsonify(error="Unknown charity"),404
        body=request.get_json(silent=True) or {}
        if not isinstance(body.get("rule_text"),str) or not body["rule_text"].strip():return jsonify(error="rule_text is required"),400
        return jsonify(job_id=store.job(cid,rule_text=body["rule_text"]))
    @app.post("/api/charities/<cid>/run")
    def run(cid):return jsonify(job_id=store.job(cid)) if cid in store.rules else (jsonify(error="Unknown charity"),404)
    @app.post("/api/companies/<ticker>/refresh")
    def refresh(ticker):return jsonify(job_id=store.job(None,ticker=ticker))
    @app.get("/api/jobs/<job_id>")
    def job(job_id):return jsonify(store.jobs[job_id]) if job_id in store.jobs else (jsonify(error="Unknown job"),404)
    @app.errorhandler(404)
    def missing(_):return jsonify(error="Unknown endpoint"),404
    if serve_static:register_frontend(app)
    return app

if __name__ == "__main__":
    create_app(Path(__file__).parent/".cache").run(host="127.0.0.1",port=5000,debug=False)
