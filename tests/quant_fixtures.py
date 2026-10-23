"""Deterministic mathematical test inputs; never used by the application."""
from schemas import Portfolio
CHARITIES = [
    ("cancer_research_wales", "Cancer Research Wales", "Cancer research"),
    ("british_thoracic_society", "British Thoracic Society", "Lung health"),
    ("british_red_cross", "British Red Cross", "Humanitarian assistance"),
    ("nuffield_oxford_hospitals_fund", "Nuffield Oxford Hospitals Fund", "Hospital support"),
]

def fixture_inputs(charity_id, name):
    import numpy as np
    import pandas as pd
    dates = pd.bdate_range("2023-01-02", periods=800)
    frames = []
    for i, ticker in enumerate(["SPY", "AGG", "BND", "TEST", "CAPPED", "VETO", "REVIEW"]):
        changes = 0.0001 + (0.002 if ticker in ("AGG", "BND") else 0.009) * np.sin(np.arange(800)*0.3 + i)
        close = (90+i*3) * np.cumprod(1+changes)
        div = np.zeros(800)
        div[60::63] = 1.0 if ticker in ("AGG", "BND") else 0.4
        frames.append(pd.DataFrame(dict(date=dates, ticker=ticker, close=close, dividends=div)))
    prices = pd.concat(frames, ignore_index=True)
    rules = dict(charity_id=charity_id, name=name, purpose="Synthetic contract demonstration",
        rules=[dict(id="R1", clause="2", text="Synthetic tobacco exclusion", test="No tobacco", threshold="zero",
                    keywords=["tobacco"], origin="policy", approved=True)],
        constraints=dict(max_weight=0.10, min_bonds=0.30, min_yield=0.03, max_drawdown=-0.15),
        constraint_origin=dict(max_weight="assumed", min_bonds="assumed", min_yield="assumed", max_drawdown="assumed"),
        weights=dict(financial=0.4, risk=0.6), weights_reason="Synthetic conservative weighting", questions=["Confirm assumed investment limits."],
        screening_hints=dict(exclude_sic=["2111"], prefer_sic=[]))
    decisions = [dict(ticker=t, decision=d, cap=c, decided_by="code_veto" if d=="REJECT" else "chair",
                      reason="Synthetic decision for offline tests", source_ids=[f"S-{t}-TEST"], weighted_score=None)
                 for t, d, c in [("TEST", "APPROVE", .10), ("CAPPED", "APPROVE_CAPPED", .03),
                                  ("VETO", "REJECT", 0), ("REVIEW", "TRUSTEE_REVIEW", 0)]]
    return prices, rules, decisions
