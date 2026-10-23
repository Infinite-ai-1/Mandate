"""Persistent SIMULATED pots and policy compilation for the offline fixture."""
import copy
import json
import math
from pathlib import Path
import re
import threading
import time
import uuid
from quant.backtest import replay
from quant.presentation import portfolio_summary
from frontend.research_summary import research_summary

DEFAULT_POLICY="SYNTHETIC TEST POLICY. This is not the charity's actual policy.\nNo tobacco. All other limits in this fixture are assumed for testing."

class DemoWorkspace:
    def __init__(self,store,directory=None):
        self.store=store
        self.directory=Path(directory) if directory else None
        self.original=copy.deepcopy(store.decisions)
        self.states={}
        self.updating=set()
        for cid in store.rules:
            state=dict(charity_id=cid,policy_text=DEFAULT_POLICY,policy_revision=1,positions={},receipts={})
            path=self._path(cid)
            if path and path.exists():
                saved=json.loads(path.read_text(encoding="utf-8"))
                if saved.get("charity_id")!=cid or not isinstance(saved.get("positions"),dict):raise ValueError("Invalid saved demo pot")
                state=saved
            self.states[cid]=state
            if state["policy_revision"]>1:
                self._compile(cid,state["policy_text"],state["policy_revision"])
                store.portfolios[cid]=store._compute(cid)

    def _path(self,cid):return self.directory/f"workspace-{cid}.json" if self.directory else None

    def _save(self,cid):
        path=self._path(cid)
        if path:
            path.parent.mkdir(parents=True,exist_ok=True)
            temp=path.with_suffix(".tmp")
            temp.write_text(json.dumps(self.states[cid],indent=2,allow_nan=False)+"\n",encoding="utf-8")
            temp.replace(path)

    def account(self,cid):
        with self.store.lock:
            state=self.states[cid]
            p=copy.deepcopy(self.store.portfolios[cid])
            holdings=list(copy.deepcopy(state["positions"]).values())
            spent=round(sum(h["usd"] for h in holdings),2)
            p.update(holdings=holdings,cash_usd=round(p["total_usd"]-spent,2))
            p["risk"],p["checks"]=replay(holdings,p["cash_usd"],p["total_usd"],self.store.rules[cid],self.store.prices[cid])
            p["memo"]="Simulated trustee allocations. Past performance, not a forecast. Historical risk is replayed using these holdings, with no costs or taxes."
            decisions={d["ticker"]:d for d in self.store.decisions[cid]}
            review=[dict(ticker=h["ticker"],reason=decisions[h["ticker"]]["reason"]) for h in holdings if decisions[h["ticker"]]["decision"] not in ("APPROVE","APPROVE_CAPPED")]
            chart=[dict(ticker=h["ticker"],usd=h["usd"],weight=h["weight"]) for h in holdings]
            if p["cash_usd"]>0:chart.append(dict(ticker="Cash",usd=p["cash_usd"],weight=p["cash_usd"]/p["total_usd"]))
            return dict(charity_id=cid,simulated=True,policy_revision=state["policy_revision"],portfolio=p,
                invested_usd=spent,presentation=portfolio_summary(p),chart=chart,to_verify=review)

    def _votes(self,ticker):
        return dict(balthasar="DO_NOT_INVEST",casper="DO_NOT_INVEST") if ticker in ("DECLINE","REVIEW") else dict(balthasar="INVEST",casper="DO_NOT_INVEST" if ticker=="CAPPED" else "INVEST")

    def quote(self,cid,ticker):
        with self.store.lock:
            state=self.states[cid]
            report=self.store.company(cid,ticker)
            if report is None:raise KeyError(ticker)
            summary=research_summary(report,self._votes(ticker))
            p=self.account(cid)["portfolio"]
            d=report["decision"]
            own=state["positions"].get(ticker)
            existing=own["usd"] if own else 0
            series=self.store.prices[cid].loc[lambda f:f.ticker==ticker].sort_values("date")
            price=float(series.close.iloc[-1]) if not series.empty else None
            allowed=d["decision"] in ("APPROVE","APPROVE_CAPPED") and summary["recommendation"] in ("BUY","STRONG_BUY") and cid not in self.updating and price is not None
            maximum=max(0.0,min(p["cash_usd"],round(d["cap"]*p["total_usd"]-existing,2))) if allowed else 0.0
            proposed=next((h["usd"] for h in self.store.portfolios[cid]["holdings"] if h["ticker"]==ticker),0.0)
            remaining_target=max(0.0,proposed-existing)
            suggested=round(math.floor(min(maximum,remaining_target)/price)*price,2) if allowed else 0.0
            findings=[v["verified"] for v in report["melchior"]["verdicts"]]
            findings += [r["verified"] for agent in ("balthasar","casper") for r in report[agent]["reasons"]]
            confidence=100*sum(v is True for v in findings)/len(findings) if findings else None
            can_buy=allowed and maximum>=price
            return dict(ticker=ticker,policy_revision=state["policy_revision"],available_usd=p["cash_usd"],maximum_usd=maximum,
                suggested_usd=suggested,price=price,buy_allowed=can_buy,confidence_score=confidence,
                confidence_definition="Percentage of this research assessment's claims with verified evidence. Not a probability of profit.",
                reason="Suggested whole-share allocation from the minimum-volatility portfolio, limited by the position cap and money remaining in the pot.",
                blocked_reason=None if can_buy else "This stock is rejected, needs review, has no usable price, is awaiting policy reassessment, or has insufficient capacity in the pot.")

    def buy(self,cid,body):
        with self.store.lock:
            state=self.states[cid]
            ticker=body.get("ticker")
            request_id=body.get("request_id")
            if not isinstance(request_id,str) or not request_id or len(request_id)>128:raise ValueError("A request_id is required")
            if request_id in state["receipts"]:
                receipt=state["receipts"][request_id]
                if receipt["ticker"]!=ticker or receipt["requested_usd"]!=body.get("amount_usd"):raise PermissionError("This request_id was already used for a different allocation")
                return dict(receipt=receipt,account=self.account(cid))
            if body.get("policy_revision")!=state["policy_revision"]:raise PermissionError("Policy changed. Research this stock again before allocating money.")
            amount=body.get("amount_usd")
            if isinstance(amount,bool) or not isinstance(amount,(int,float)) or not math.isfinite(amount) or amount<=0:raise ValueError("Enter a positive investment amount")
            if round(amount,2)!=amount:raise ValueError("Use no more than two decimal places")
            quote=self.quote(cid,ticker)
            if not quote["buy_allowed"]:raise PermissionError(quote["blocked_reason"])
            if amount>quote["available_usd"] or amount>quote["maximum_usd"]:raise ValueError("Amount exceeds the available pot or this stock's position cap")
            shares=math.floor(amount/quote["price"])
            if shares<1:raise ValueError("The amount must cover at least one whole share")
            usd=round(shares*quote["price"],2)
            report=self.store.company(cid,ticker)
            previous=copy.deepcopy(state)
            current=copy.deepcopy(state["positions"].get(ticker,dict(ticker=ticker,name=ticker,is_bond=False,usd=0.0,shares=0,price=quote["price"],weight=0.0,cap=report["decision"]["cap"],reason=report["decision"]["reason"],source_ids=report["decision"]["source_ids"])))
            current.update(usd=round(current["usd"]+usd,2),shares=current["shares"]+shares)
            current["weight"]=current["usd"]/self.store.portfolios[cid]["total_usd"]
            state["positions"][ticker]=current
            receipt=dict(request_id=request_id,ticker=ticker,requested_usd=amount,spent_usd=usd,shares=shares,simulated=True)
            state["receipts"][request_id]=receipt
            try:self._save(cid)
            except OSError:
                self.states[cid]=previous
                raise
            return dict(receipt=receipt,account=self.account(cid))

    def _compile(self,cid,text,revision):
        # Deliberately bounded fixture compiler. The live provider must call the
        # real policy compiler, verifier and agents; this demo makes no LLM calls.
        sid=f"Q-{cid}-policy-{revision}"
        self.store.register(source_id=sid,ticker="",kind="computed",origin="quant",title="Trustee supplied sample policy",date=self.store.portfolios[cid]["as_of"],url=f"/api/charities/{cid}/policy",section=f"Policy revision {revision}")
        baseline=copy.deepcopy(self.original[cid])
        rules=[r for r in self.store.rules[cid]["rules"] if not r["id"].startswith("POLICY-")]
        for d in baseline:
            ticker=d["ticker"]
            excluded=re.search(r"(?:exclude|avoid|do\s+not\s+invest\s+in|no)\s+"+re.escape(ticker)+r"\b",text,re.I)
            current=next(old for old in self.store.decisions[cid] if old["ticker"]==ticker)
            if current["reason"].startswith("Synthetic live-rule"):
                d.update(current)
            if excluded:
                d.update(decision="REJECT",cap=0.0,decided_by="code_veto",reason=f"Policy revision {revision} explicitly excludes {ticker}.",source_ids=[sid])
                rules.append(dict(id=f"POLICY-{revision}-{ticker}",clause="Trustee update",text=f"Exclude {ticker}",test="Explicit ticker exclusion",threshold="zero",keywords=[ticker],origin="policy",approved=True))
        self.store.decisions[cid]=baseline
        self.store.rules[cid]["rules"]=rules

    def update_policy(self,cid,body):
        with self.store.lock:
            state=self.states[cid]
            text=body.get("text")
            if not isinstance(text,str) or not text.strip() or len(text)>50000:raise ValueError("Enter policy text, up to 50,000 characters")
            if body.get("policy_revision")!=state["policy_revision"]:raise PermissionError("Policy has changed. Reload it before saving.")
            if cid in self.updating:raise PermissionError("A policy reassessment is already running")
            job_id=uuid.uuid4().hex
            job=dict(status="queued",progress=["Sample policy update queued."],result=None,error=None)
            self.store.jobs[job_id]=job
            self.updating.add(cid)
        def work():
            job["status"]="running"
            try:
                for message in ("Reading the revised sample policy.","Rechecking ethics exclusions and research decisions.","Rebuilding the proposed allocation; purchased holdings stay visible for trustee review."):
                    job["progress"].append(message);time.sleep(.35)
                with self.store.lock:
                    previous=copy.deepcopy((self.states[cid],self.store.rules[cid],self.store.decisions[cid],self.store.portfolios[cid]))
                    try:
                        revision=state["policy_revision"]+1
                        self._compile(cid,text.strip(),revision)
                        state.update(policy_text=text.strip(),policy_revision=revision)
                        self.store.portfolios[cid]=self.store._compute(cid)
                        self._save(cid)
                    except Exception:
                        self.states[cid],self.store.rules[cid],self.store.decisions[cid],self.store.portfolios[cid]=previous
                        raise
                    job.update(status="done",result=self.store.portfolios[cid])
                    job["progress"].append("Policy saved. Updated sample decisions are ready.")
            except Exception as error:job.update(status="error",error=str(error))
            finally:self.updating.discard(cid)
        threading.Thread(target=work,daemon=True).start()
        return dict(job_id=job_id)
