"""Production HTTP boundary: real evidence, persisted paper accounts, serialized jobs.

The application is a local, single-process trustee workspace. No brokerage orders
are sent. Unknown measurements are null, never synthetic fallback values.
"""
import copy
import hashlib
import json
import math
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from . import config as C
from .demos import SCENARIOS, PRICES, report as demo_report

CHARITIES = {
    "cancer_research_wales": "Cancer Research Wales",
    "british_thoracic_society": "British Thoracic Society",
    "british_red_cross": "British Red Cross",
    "nuffield_oxford_hospitals_fund": "Nuffield Oxford Hospitals Fund",
}


def read_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(tmp, path)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ServiceError(Exception):
    def __init__(self, message, status=400):
        self.status = status
        super().__init__(message)


class Workspace:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.RLock()
        # Ingestion's on-disk registry and LLM logs require serialized runs.
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mandate")
        self.jobs = {}
        self.busy = set()

    def check(self, cid):
        if cid not in CHARITIES:
            raise ServiceError("Unknown charity", 404)

    def state(self, cid):
        self.check(cid)
        return read_json(self.root / f"{cid}.json", {
            "revision": 0, "policy": None, "run": None, "cash": C.BUDGET_USD,
            "positions": {}, "receipts": {},
        })

    def save(self, cid, state):
        write_json(self.root / f"{cid}.json", state)

    def policy(self, cid):
        state = self.state(cid)
        text = state["policy"]
        if text is None:
            for suffix in (".txt", ".md"):
                path = C.POLICIES_DIR / f"{cid}{suffix}"
                if path.exists():
                    text = path.read_text(encoding="utf-8")
                    break
        return {"text": text or "", "policy_revision": state["revision"]}

    def run(self, cid):
        state = self.state(cid)
        run = state["run"]
        if not run or run.get("policy_hash") != hashlib.sha256(self.policy(cid)["text"].encode()).hexdigest():
            raise ServiceError("No current assessment. Save the charity policy, configure API credentials, then re-run the mandate.", 409)
        return run

    def requirements(self):
        required = {"AZURE_OPENAI_ENDPOINT": C.ENDPOINT, "AZURE_OPENAI_API_KEY": C.API_KEY,
                    "MODEL_CHAIR / DEPLOY_SOL": C.MODELS["chair"],
                    "MODEL_MELCHIOR / DEPLOY_SOL": C.MODELS["melchior"],
                    "MODEL_BALTHASAR / DEPLOY_MAI": C.MODELS["balthasar"],
                    "MODEL_CASPER / DEPLOY_TERRA_6": C.MODELS["casper"]}
        if C.provider_for(C.MODELS["casper"]) == "anthropic":
            required["ANTHROPIC_API_KEY"] = C.ANTHROPIC_API_KEY
        return [key for key, value in required.items() if not value]

    def decision(self, d):
        kind = {"REJECTED_ETHICS": "REJECT", "REJECTED_CHAIR": "REJECT",
                "TRUSTEE_REVIEW": "TRUSTEE_REVIEW", "APPROVED": "APPROVE"}[d["status"]]
        if kind == "APPROVE" and (d.get("chair") or {}).get("decision") == "reduced":
            kind = "APPROVE_CAPPED"
        ids = []
        if d.get("veto") and d["veto"].get("source_id"):
            ids.append(d["veto"]["source_id"])
        for reason in (d.get("chair") or {}).get("reasons", []):
            ids.extend(self.source_id(d["ticker"], sid) for sid in reason["source_ids"])
        return dict(ticker=d["ticker"], decision=kind, cap=d["cap"],
                    decided_by="code_veto" if d["status"] in ("REJECTED_ETHICS", "TRUSTEE_REVIEW") else "chair",
                    reason=d["reason"], source_ids=list(dict.fromkeys(ids)), weighted_score=None)

    @staticmethod
    def source_id(ticker, sid):
        from .sources.market import FUND_KEYS
        if sid in FUND_KEYS or sid in ("annual_vol", "max_drawdown", "worst_12m_return", "beta_vs_spy"):
            return f"metric:{ticker}:{sid}"
        return sid

    def company(self, cid, ticker):
        if ticker in SCENARIOS:
            state = self.state(cid)
            if state.get("demo_assessments", {}).get(ticker) != state["revision"]:
                raise ServiceError("Run this starred demo before allocating, and rerun after policy changes.", 409)
            return demo_report(ticker)
        run = self.run(cid)
        d = next((d for d in run["decisions"] if d["ticker"] == ticker), None)
        if not d:
            raise ServiceError("Company has not been assessed for this charity", 404)
        def specialist(agent):
            value = d.get(agent) or {}
            reasons = []
            for verified, key in ((True, "reasons"), (False, "unverified")):
                for r in value.get(key, []):
                    ids = [self.source_id(ticker, sid) for sid in (r.get("metric"), r.get("source_id")) if sid and sid != "missing"]
                    reasons.append(dict(claim=r["text"], source_ids=ids, verified=verified))
            # The displayed number is calculated verification coverage, not an LLM rating.
            score = 100 * sum(r["verified"] for r in reasons) / len(reasons) if reasons else None
            return dict(ticker=ticker, agent=agent, model=run.get("stats", {}).get("models", {}).get(agent, ""),
                        score=score, reasons=reasons, summary=value.get("note") or " ".join(r["claim"] for r in reasons if r["verified"]))
        verdicts = [dict(v, quote=v.get("quote") or "", source_id=v.get("source_id") or "",
                         confidence=1.0 if v.get("verified") else 0.0)
                    for v in (d.get("melchior") or {}).get("verdicts", [])]
        return dict(melchior=dict(ticker=ticker, agent="melchior", model=run.get("stats", {}).get("models", {}).get("melchior", ""), verdicts=verdicts),
                    balthasar=specialist("balthasar"), casper=specialist("casper"), decision=self.decision(d))

    def rules(self, cid):
        run = self.run(cid)
        policy = run["policy"]
        limits = policy["limits"]
        mapping = {"max_weight": "max_single_holding", "min_bonds": "min_bonds", "min_yield": "min_yield", "max_drawdown": "worst_year_limit"}
        constraints = {k: (limits.get(v) or {"value": .10})["value"] for k, v in mapping.items()}
        origins = {k: "policy" if (limits.get(v) or {}).get("origin") == "stated" else "assumed" for k, v in mapping.items()}
        rules = [dict(id=r["id"], clause=r.get("clause_ref", ""), text=r["text"], test=r["type"],
                      threshold=r.get("threshold") or "", keywords=r["keywords"],
                      origin="judge" if r["id"].startswith("L") else "policy", approved=True) for r in policy["rules"]]
        rules += [dict(id=p["id"], clause="Charity purpose", text=p["text"], test="mission_conflict", threshold="",
                       keywords=p["keywords"], origin="proposed", approved=False) for p in policy.get("proposed_mission_conflicts", []) if not p["approved"]]
        return dict(charity_id=cid, name=CHARITIES[cid], purpose=policy["purpose_summary"], rules=rules,
                    constraints=constraints, constraint_origin=origins, weights={k: policy["weights"][k] for k in ("financial", "risk")},
                    weights_reason=f"Weights are {policy['weights']['origin']}.",
                    questions=[v["issue"] for v in policy.get("vague_wording", [])] + run.get("warnings", []),
                    screening_hints=dict(exclude_sic=[], prefer_sic=[]))

    def selection(self, cid):
        from .universe import EQUITIES
        tickers = EQUITIES
        try:
            analysed = sum(d["ticker"] in EQUITIES for d in self.run(cid)["decisions"])
        except ServiceError:
            analysed = 0
        return dict(charity_id=cid, universe_size=len(tickers), after_prefilter=len(tickers), analysed_count=analysed, excluded_by_sic=[],
                    selected=[dict(ticker=t, why="Configured research universe; assessment required") for t in tickers])

    def empty_portfolio(self, cid):
        return dict(charity_id=cid, total_usd=C.BUDGET_USD, gbpusd=None, as_of="", holdings=[], cash_usd=C.BUDGET_USD,
                    risk={"worst_12m": None, "yield": None, "volatility": None, "vs_6040_return": None},
                    checks=dict(max_drawdown_ok=None, yield_ok=None, bonds_ok=None), relaxed=[], rejected=[], trustee_review=[],
                    memo="", devils_advocate=[], run_stats=dict(seconds=0, llm_calls=0, tokens=0, by_agent={}))

    def portfolio(self, cid):
        from .challenges import build_challenges
        run = self.run(cid)
        opt = run["optimiser"]
        p = self.empty_portfolio(cid)
        decisions = {d["ticker"]: self.decision(d) for d in run["decisions"]}
        p.update(as_of=run["generated_at"], gbpusd=run.get("gbpusd"),
                 cash_usd=opt["cash_usd"] if opt["ok"] else C.BUDGET_USD,
                 holdings=[dict(ticker=h["ticker"], name=h["ticker"], is_bond=h["is_bond"], usd=h["dollars"],
                                shares=h["shares"], price=h["price"], weight=h["weight"], cap=h["cap"],
                                reason=decisions[h["ticker"]]["reason"], source_ids=decisions[h["ticker"]]["source_ids"]) for h in opt["holdings"]],
                 rejected=[d for d in decisions.values() if d["decision"] == "REJECT"],
                 trustee_review=[d for d in decisions.values() if d["decision"] == "TRUSTEE_REVIEW"],
                 relaxed=opt["relaxed"] + ([opt["error"]] if opt.get("error") else []), memo="" if run.get("memo_stale") else run["memo"],
                 devils_advocate=build_challenges(run), run_stats=dict(seconds=run["stats"]["wall_seconds"],
                    llm_calls=run["stats"]["llm_calls"], tokens=run["stats"]["tokens"], by_agent=run["stats"]["by_agent"]))
        bt = opt.get("backtest") or {}
        p["risk"] = dict(worst_12m=bt.get("worst_12m_return"), volatility=bt.get("annual_vol"), vs_6040_return=bt.get("vs_6040"))
        p["risk"]["yield"] = bt.get("trailing_yield")
        p["checks"] = dict(max_drawdown_ok=bt.get("worst_12m_ok"), yield_ok=bt.get("yield_ok"), bonds_ok=opt.get("checks", {}).get("bonds_ok"))
        return p

    def account(self, cid):
        from quant.presentation import portfolio_summary
        with self.lock:
            s = self.state(cid)
            p = self.empty_portfolio(cid)
            p["risk"] = {"worst_12m": None, "yield": None, "volatility": None, "vs_6040_return": None}
            p["holdings"] = list(s["positions"].values())
            p["cash_usd"] = s["cash"]
            # Paper ledger at recorded purchase cost; no fabricated live mark or performance.
            p["as_of"] = s.get("updated_at", "")
            try:
                assessed = self.portfolio(cid)
                p["rejected"] = assessed["rejected"]
                p["trustee_review"] = assessed["trustee_review"]
            except ServiceError:
                pass
            review = []
            for h in p["holdings"]:
                try:
                    decision = self.company(cid, h["ticker"])["decision"]
                    reason = decision["reason"] if decision["decision"] not in ("APPROVE", "APPROVE_CAPPED") or h["weight"] > decision["cap"] else None
                except ServiceError:
                    reason = "Policy changed or no current assessment. Reassess before buying more."
                if reason:
                    review.append(dict(ticker=h["ticker"], reason=reason))
            chart = [dict(ticker=h["ticker"], usd=h["usd"], weight=h["weight"]) for h in p["holdings"]]
            chart.append(dict(ticker="Cash", usd=s["cash"], weight=s["cash"] / C.BUDGET_USD))
            return dict(charity_id=cid, simulated=True, policy_revision=s["revision"], portfolio=p,
                        invested_usd=round(C.BUDGET_USD-s["cash"], 2), presentation=portfolio_summary(p), chart=chart, to_verify=review)

    def quote(self, cid, ticker):
        from .sources import market
        with self.lock:
            s = self.state(cid)
            maximum, suggested, price, blocked, reason = 0, 0, None, None, ""
            try:
                d = self.company(cid, ticker)["decision"]
                reason = d["reason"]
                if d["decision"] not in ("APPROVE", "APPROVE_CAPPED"):
                    raise ServiceError("Current assessment does not permit an allocation.")
                if ticker in SCENARIOS:
                    price, age = PRICES[ticker], 0
                else:
                    prices = market.load_prices()
                    series = prices[ticker].dropna()
                    price = float(series.iloc[-1])
                    age = (datetime.now(timezone.utc).date() - series.index[-1].date()).days
                if age > 7 or not math.isfinite(price) or price <= 0:
                    raise ServiceError("Market price is stale or unavailable. Refresh research before allocating.")
                held = s["positions"].get(ticker, {}).get("usd", 0)
                maximum = max(0, min(s["cash"], C.BUDGET_USD * d["cap"] - held))
                target = C.BUDGET_USD * d["cap"] if ticker in SCENARIOS else next((h["usd"] for h in self.portfolio(cid)["holdings"] if h["ticker"] == ticker), 0)
                suggested = min(maximum, max(0, target-held))
            except (ServiceError, KeyError, IndexError, FileNotFoundError) as e:
                blocked = str(e)
            if cid in self.busy:
                blocked = "Assessment is running. Wait for it to finish."
            if not blocked and (price is None or maximum < price):
                blocked = "Insufficient cash or position capacity for a whole share."
            return dict(ticker=ticker, policy_revision=s["revision"], available_usd=s["cash"], maximum_usd=maximum,
                        suggested_usd=suggested, price=price, buy_allowed=blocked is None, confidence_score=None,
                        confidence_definition="No probability of investment success is calculated.", reason=reason, blocked_reason=blocked)

    def buy(self, cid, body):
        with self.lock:
            s = self.state(cid)
            rid, ticker = body.get("request_id"), body.get("ticker")
            amount = body.get("amount_usd")
            if not isinstance(rid, str) or not 1 <= len(rid) <= 128 or not isinstance(ticker, str):
                raise ServiceError("A request_id and ticker are required.")
            if isinstance(amount, bool) or not isinstance(amount, (float, int)) or not math.isfinite(amount) or amount <= 0:
                raise ServiceError("Amount must be a positive finite number.")
            if rid in s["receipts"]:
                receipt = s["receipts"][rid]
                if receipt["ticker"] != ticker or receipt["requested_usd"] != amount:
                    raise ServiceError("Request ID was already used for a different allocation.", 409)
                return dict(receipt=receipt, account=self.account(cid))
            if body.get("policy_revision") != s["revision"]:
                raise ServiceError("Policy changed. Reload the quote.", 409)
            q = self.quote(cid, ticker)
            if not q["buy_allowed"]:
                raise ServiceError(q["blocked_reason"], 409)
            if amount > q["maximum_usd"]:
                raise ServiceError("Amount exceeds available cash or the position cap.", 409)
            shares = math.floor(amount/q["price"])
            if shares < 1:
                raise ServiceError("Amount is below the price of one whole share.")
            spent = round(shares*q["price"], 2)
            h = s["positions"].get(ticker, dict(ticker=ticker, name=ticker, is_bond=False, shares=0, usd=0))
            h.update(shares=h["shares"]+shares, usd=round(h["usd"]+spent, 2))
            d = self.company(cid, ticker)["decision"]
            h.update(price=h["usd"]/h["shares"], weight=h["usd"]/C.BUDGET_USD, cap=d["cap"], reason=d["reason"], source_ids=d["source_ids"])
            if ticker in SCENARIOS:
                h["name"] = "★ " + SCENARIOS[ticker]["name"] + " · DEMO (simulated price)"
            from .universe import BONDS
            h["is_bond"] = ticker in BONDS
            s["positions"][ticker] = h
            s["cash"] = round(s["cash"]-spent, 2)
            receipt = dict(request_id=rid, ticker=ticker, requested_usd=amount, spent_usd=spent, shares=shares, simulated=True)
            s["receipts"][rid] = receipt
            s["updated_at"] = now()
            self.save(cid, s)
            return dict(receipt=receipt, account=self.account(cid))

    def submit(self, cid, action):
        with self.lock:
            self.check(cid)
            if cid in self.busy:
                raise ServiceError("An assessment is already running for this charity.", 409)
            jid = uuid.uuid4().hex
            job = dict(status="queued", progress=[], result=None, error=None)
            self.jobs[jid] = job
            self.busy.add(cid)
        def work():
            with self.lock:
                job["status"] = "running"
            def progress(message):
                with self.lock:
                    job["progress"].append(message)
            try:
                result = action(progress)
                with self.lock:
                    job.update(status="done", result=result)
            except Exception as e:
                with self.lock:
                    # Provider errors can contain request URLs or credentials; expose only safe errors.
                    message = str(e) if isinstance(e, ServiceError) else f"{type(e).__name__}: assessment failed. Check configuration and available evidence."
                    job.update(status="error", error=message)
            finally:
                with self.lock:
                    self.busy.discard(cid)
        self.executor.submit(work)
        return dict(job_id=jid)

    def assess(self, cid, progress, refresh=None):
        if C.DEMO_MODE:
            try:
                self.run(cid)
            except ServiceError:
                raise ServiceError("No completed cached assessment matches this policy. Restore the keyless demo bundle or run this policy online first.", 409)
            progress("DEMO_MODE: replaying the completed saved assessment; no network or model calls. Evidence and prices retain their original dates.")
            if refresh:
                progress(f"{refresh}: showing the saved assessment; offline mode cannot fetch fresh evidence.")
            return self.portfolio(cid)
        from . import evidence, pipeline, universe
        from .sources import market, edgar, news
        text = self.policy(cid)["text"]
        if not text.strip():
            raise ServiceError("Save a charity policy before running analysis.")
        missing = self.requirements()
        if missing and not C.DEMO_MODE:
            raise ServiceError("Configure " + ", ".join(missing) + " in .env, then restart the server.")
        tickers = universe.EQUITIES
        progress("Loading observed market data and source evidence")
        px = market.fetch_prices(universe.price_tickers(), force=bool(refresh))
        if px.empty:
            raise ServiceError("No observed market history is available.")
        market.fetch_fundamentals([refresh] if refresh else tickers, force=bool(refresh))
        market.fetch_yields(universe.price_tickers(), px, force=bool(refresh))
        market.compute_risk_stats(px)
        for ticker in ([refresh] if refresh else tickers):
            if not evidence._load(ticker)[0] or refresh:
                if not C.DEMO_MODE:
                    for label, fetch in (("filings", lambda: edgar.fetch_filing(ticker, universe.form_for(ticker), force=bool(refresh)) if C.EDGAR_USER_AGENT else None),
                                         ("news", lambda: news.fetch_news(ticker, force=bool(refresh)))):
                        try:
                            fetch()
                        except Exception:
                            progress(f"{ticker}: {label} unavailable; only retained evidence can be evaluated.")
                evidence.save_chunks(ticker)
        evidence._load.cache_clear()
        # Use the real compiler/verification/optimiser pipeline without inventing a policy file.
        run = pipeline.run_charity(cid, policy_text=text, progress=progress, out_path=self.root / f"{cid}-run.json")
        run["policy_hash"] = hashlib.sha256(text.encode()).hexdigest()
        from ingest.fx import fetch_gbpusd
        run["gbpusd"] = fetch_gbpusd()
        with self.lock:
            s = self.state(cid)
            s["run"] = run
            self.save(cid, s)
        return self.portfolio(cid)

    def update_policy(self, cid, body):
        text = body.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 100000:
            raise ServiceError("Policy text must contain 1–100,000 characters.")
        with self.lock:
            s = self.state(cid)
            if cid in self.busy or body.get("policy_revision") != s["revision"]:
                raise ServiceError("Policy changed or an assessment is running. Reload before saving.", 409)
            s.update(policy=text.strip(), revision=s["revision"]+1, run=None)
            self.save(cid, s)
            def action(progress):
                progress("Policy saved. Previous assessments invalidated; existing paper holdings retained for review.")
                if self.requirements() and not C.DEMO_MODE:
                    progress("Configure API credentials and deployment names, restart, then re-run the mandate to assess this policy.")
                    return None
                return self.assess(cid, progress)
            return self.submit(cid, action)


def create_app(state_dir=None, serve_frontend=True):
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 128 * 1024
    ws = Workspace(state_dir or C.RESULTS_DIR / "workspace")
    app.config["MANDATE_WORKSPACE"] = ws

    @app.errorhandler(ServiceError)
    def service_error(e):
        return jsonify(error=str(e)), e.status

    @app.errorhandler(HTTPException)
    def http_error(e):
        return jsonify(error=e.description), e.code

    @app.errorhandler(Exception)
    def internal_error(e):
        app.logger.error("Request failed: %s", type(e).__name__)
        return jsonify(error="Request failed. Check the server configuration and available data."), 500

    @app.before_request
    def local_write():
        # Local unauthenticated workspace: reject browser writes from other origins.
        if request.method == "POST":
            from urllib.parse import urlparse
            origin = request.headers.get("Origin")
            if origin and urlparse(origin).netloc not in (request.host, "127.0.0.1:5173", "localhost:5173"):
                raise ServiceError("Cross-origin writes are not allowed.", 403)
            if not request.is_json or not isinstance(request.get_json(silent=True), dict):
                raise ServiceError("A JSON object is required.")

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", stack="React + Flask", demo_mode=C.DEMO_MODE,
                       missing_configuration=ws.requirements(), paper_trading=True)

    @app.get("/api/charities")
    def charities():
        return jsonify([dict(charity_id=cid, name=name, purpose="Policy document required" if not ws.policy(cid)["text"] else "Policy saved for assessment") for cid, name in CHARITIES.items()])

    @app.get("/api/charities/<cid>/policy")
    def policy(cid): return jsonify(ws.policy(cid))

    @app.post("/api/charities/<cid>/policy")
    def update_policy(cid): return jsonify(ws.update_policy(cid, request.get_json())), 202

    @app.get("/api/charities/<cid>/rules")
    def rules(cid): return jsonify(ws.rules(cid))

    @app.get("/api/charities/<cid>/selection")
    def selection(cid):
        ws.check(cid)
        return jsonify(ws.selection(cid))

    @app.get("/api/charities/<cid>/portfolio")
    def portfolio(cid): return jsonify(ws.portfolio(cid))

    @app.get("/api/charities/<cid>/account")
    def account(cid): return jsonify(ws.account(cid))

    @app.get("/api/charities/<cid>/companies/<ticker>")
    def company(cid, ticker): return jsonify(ws.company(cid, ticker))

    @app.get("/api/charities/<cid>/companies/<ticker>/investment-quote")
    def quote(cid, ticker): return jsonify(ws.quote(cid, ticker))

    @app.post("/api/charities/<cid>/investments")
    def buy(cid): return jsonify(ws.buy(cid, request.get_json()))

    @app.post("/api/charities/<cid>/run")
    def run(cid): return jsonify(ws.submit(cid, lambda progress: ws.assess(cid, progress))), 202

    @app.post("/api/charities/<cid>/rules")
    def add_rule(cid):
        text = request.get_json().get("rule_text")
        if not isinstance(text, str) or not text.strip() or len(text) > 5000:
            raise ServiceError("Rule text must contain 1–5,000 characters.")
        policy = ws.policy(cid)
        return jsonify(ws.update_policy(cid, dict(text=policy["text"]+"\n\nTrustee-added rule:\n"+text, policy_revision=policy["policy_revision"]))), 202

    @app.post("/api/companies/<ticker>/refresh")
    def refresh(ticker):
        from .universe import EQUITIES
        if ticker not in EQUITIES and ticker not in SCENARIOS:
            raise ServiceError("Ticker is not in the configured research universe.", 404)
        cid = request.get_json().get("charity_id")
        if not cid:
            raise ServiceError("charity_id is required for research.")
        if ticker in SCENARIOS:
            def simulate(progress):
                import time
                progress("SIMULATED DEMO: scripted assumptions and illustrative prices; no live model or market calls.")
                for agent, note in zip(("melchior", "balthasar", "casper", "chair"), SCENARIOS[ticker]["notes"]):
                    progress(f"[{agent}] Reviewing scenario assumptions")
                    time.sleep(.7)
                    progress(f"[{agent}:done] {note}")
                with ws.lock:
                    state = ws.state(cid)
                    state.setdefault("demo_assessments", {})[ticker] = state["revision"]
                    ws.save(cid, state)
                return None
            return jsonify(ws.submit(cid, simulate)), 202
        return jsonify(ws.submit(cid, lambda progress: ws.assess(cid, progress, ticker))), 202

    @app.get("/api/jobs/<jid>")
    def job(jid):
        with ws.lock:
            if jid not in ws.jobs:
                raise ServiceError("Unknown job (jobs do not survive a server restart). Reload the saved account or run again.", 404)
            return jsonify(copy.deepcopy(ws.jobs[jid]))

    @app.get("/api/compare/<ticker>")
    def compare(ticker):
        rows = []
        for cid in CHARITIES:
            try:
                rows.append(dict(charity_id=cid, decision=ws.company(cid, ticker)["decision"]))
            except ServiceError:
                pass
        return jsonify(rows)

    @app.get("/api/sources/<sid>")
    def source(sid):
        ticker = sid.removesuffix("-ASSUMPTION")
        if ticker in SCENARIOS and sid.endswith("-ASSUMPTION"):
            return jsonify(source_id=sid, ticker=ticker, kind="demo", origin="scripted_demo", title="Simulated scenario assumptions; not factual company evidence",
                           date="", url="", section=" ".join(SCENARIOS[ticker]["notes"]))
        import sources
        from . import evidence
        if sid.startswith("metric:"):
            from .sources import market
            parts = sid.split(":")
            if len(parts) != 3:
                raise ServiceError("Unknown source", 404)
            _, ticker, metric = parts
            for path, origin in ((market.FUNDAMENTALS, "yfinance"), (market.RISK_STATS, "quant")):
                value = market._load_json(path).get(ticker, {}).get(metric)
                if value is not None:
                    return jsonify(source_id=sid, ticker=ticker, kind="computed" if origin == "quant" else "market", origin=origin,
                                   title=f"{metric}: {value}", date=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat(),
                                   url=f"https://finance.yahoo.com/quote/{ticker}/", section="Cached market metric")
        found = sources.get(sid)
        if found:
            return jsonify({k: v if v is not None else "" for k, v in found.items()})
        chunk = evidence.get_chunk(sid)
        if not chunk:
            raise ServiceError("Unknown source", 404)
        return jsonify(source_id=sid, ticker=chunk.ticker, kind=chunk.kind, origin="edgar" if chunk.kind == "filing" else "finnhub",
                       title=chunk.section or sid, date=chunk.date, url=chunk.url, section=chunk.section)

    from frontend.flask_static import register_frontend
    register_frontend(app, assets=serve_frontend)
    return app
