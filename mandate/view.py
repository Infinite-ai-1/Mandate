"""Turns run.json into the rows and numbers the Streamlit page shows. No Streamlit imports, so it is testable."""
from . import config as C
from .evidence import get_chunk
from .sources import market

ORDER = {"REJECTED_ETHICS": 0, "REJECTED_CHAIR": 1, "TRUSTEE_REVIEW": 2, "APPROVED": 3}
OUTCOME = {"REJECTED_ETHICS": "Rejected (ethics)", "REJECTED_CHAIR": "Rejected (Chair)", "TRUSTEE_REVIEW": "Flagged for trustees"}
LIMIT_LABELS = {"min_bonds": "Minimum bonds", "min_yield": "Minimum portfolio yield",
                "worst_year_limit": "Worst 12-month return limit", "max_single_holding": "Largest single holding"}


def source_url(source_id: str | None) -> str:
    try:
        c = get_chunk(source_id) if source_id else None
    except Exception:
        c = None
    return c.url if c else ""


def headline(run: dict) -> dict | None:
    opt = run["optimiser"]
    if not opt["ok"]:
        return None
    budget = run.get("budget_usd", C.BUDGET_USD)
    bonds = sum(h["dollars"] for h in opt["holdings"] if h["is_bond"])
    shares = sum(h["dollars"] for h in opt["holdings"] if not h["is_bond"])
    return {"budget": budget, "n": len(opt["holdings"]), "shares_pct": shares / budget, "bonds_pct": bonds / budget,
            "cash": opt["cash_usd"]}


def melchior_badge(d: dict) -> str:
    vs = (d.get("melchior") or {}).get("verdicts") or []
    if not vs:
        return "no screen"
    if any(v["verdict"] == "FAIL" and v["verified"] for v in vs):
        return "🟥 FAIL"
    return "🟨 FLAG" if any(v["verdict"] != "PASS" for v in vs) else "🟩 PASS"


def board_rows(run: dict) -> list[dict]:
    """Max 6 columns: ticker, Melchior, Balthasar, Casper, Chair (with cap), status."""
    rows = []
    for d in sorted(run["decisions"], key=lambda d: (ORDER[d["status"]], d["ticker"])):
        ch, fin, rk = d.get("chair"), d.get("balthasar"), d.get("casper")
        score = lambda r: "-" if not r else ("n/a" if r["score"] is None else f"{r['score']}/10")  # noqa: E731
        rows.append({"Ticker": d["ticker"], "Melchior": melchior_badge(d), "Balthasar": score(fin), "Casper": score(rk),
                     "Chair (cap)": f"{ch['decision']} ({d['cap']:.0%})" if ch else (f"bond ({d['cap']:.0%})" if d["status"] == "APPROVED" else f"- ({d['cap']:.0%})"),
                     "Status": d["status"].replace("_", " ").title()})
    return rows


def rejection_rows(run: dict) -> list[dict]:
    rules = {r["id"]: r["text"] for r in run["policy"]["rules"]}
    rows = []
    for d in sorted(run["decisions"], key=lambda d: (ORDER[d["status"]], d["ticker"])):
        if d["status"] == "APPROVED":
            continue
        v, why, quote, sid = d.get("veto"), d["reason"], "", ""
        if v:
            why, quote, sid = f"{v['rule_id']} {rules.get(v['rule_id'], '')}: {v['reason']}", v["quote"] or "", v["source_id"] or ""
        elif d["status"] == "REJECTED_CHAIR" and d.get("chair"):
            ids = [i for r in d["chair"]["reasons"] for i in r["source_ids"]]
            sid = next((i for i in ids if source_url(i)), "")
        rows.append({"Ticker": d["ticker"], "Outcome": OUTCOME[d["status"]], "Why": why, "Quote": quote,
                     "Source": source_url(sid) or sid})
    return rows


def holdings_rows(run: dict) -> list[dict]:
    dec = {d["ticker"]: d for d in run["decisions"]}
    rows = []
    for h in run["optimiser"]["holdings"]:
        d = dec.get(h["ticker"], {})
        ch = d.get("chair")
        ids = sorted({i for r in (ch["reasons"] if ch else []) for i in r["source_ids"]})
        rows.append({"Ticker": h["ticker"], "Dollars": h["dollars"], "Shares": h["shares"], "Cap": h["cap"],
                     "Chair": ch["decision"] if ch else "bond ETF",
                     "Reason": (d.get("reason") or "Bond ETF, no ethics screen.") + (f" [{', '.join(ids)}]" if ids else "")})
    return rows


def sector_of(ticker: str, is_bond: bool, fundamentals: dict) -> str:
    return "Bond ETF" if is_bond else (fundamentals.get(ticker, {}).get("sector") or "Other")


def review_items(run: dict) -> list[str]:
    items = [f"**{d['ticker']}** flagged: {d['reason']}" for d in run["decisions"] if d["status"] == "TRUSTEE_REVIEW"]
    items += [f"**{d['ticker']}**: {d['reason']} (Chair defaulted)" for d in run["decisions"]
              if d.get("chair") and d["chair"]["defaulted"]]
    items += [f"Constraint relaxed: {x}" for x in run["optimiser"]["relaxed"]]
    if run["optimiser"].get("error"):
        items.append(f"Optimiser could not build a portfolio: {run['optimiser']['error']}")
    lim = run["policy"]["limits"]
    items += [f"Assumed limit: {LIMIT_LABELS[k]} = {v['value']:.1%}. The policy does not state it; trustees to confirm."
              for k, v in lim.items() if v and v["origin"] == "assumed"]
    w = run["policy"]["weights"]
    if w["origin"] == "assumed":
        items.append(f"Assumed weighting: financial health {w['financial']:.0%}, risk {w['risk']:.0%}. Trustees to confirm.")
    items += [f"Policy quote could not be matched, rule not used: {r['id']} {r['text']}" for r in run["policy"]["unverified_rules"]]
    items += [f"Note: {w}" for w in run["warnings"]]
    return items


def risk_cards(run: dict) -> list[dict]:
    bt = run["optimiser"].get("backtest")
    if not bt:
        return []
    w = bt["worst_12m_return"]
    return [
        {"label": "Worst 12-month return", "value": "n/a" if w is None else f"{w:+.1%}", "note": f"limit {bt['worst_12m_limit']:+.0%}", "ok": bt["worst_12m_ok"]},
        {"label": "Portfolio yield", "value": f"{bt['trailing_yield']:.2%}", "note": f"target {bt['min_yield']:.1%}", "ok": bt["yield_ok"]},
        {"label": "Total return vs 60/40", "value": f"{bt['total_return']:+.1%}", "note": f"60/40 SPY/BND {bt['benchmark_6040_return']:+.1%} ({bt['vs_6040']:+.1%})", "ok": bt["vs_6040"] >= 0},
        {"label": "Max drawdown", "value": f"{bt['max_drawdown']:.1%}", "note": f"volatility {bt['annual_vol']:.1%}", "ok": None},
    ]


def fund_cache() -> dict:
    return market._load_json(market.FUNDAMENTALS)
