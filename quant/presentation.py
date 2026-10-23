"""API-side display totals. JSON schemas stay unchanged; no UI arithmetic."""
import math
from quant.backtest import as_dict

def portfolio_summary(portfolio):
    p=as_dict(portfolio)
    if p["total_usd"] <= 0:
        raise ValueError("Positive portfolio total required")
    result=dict(holdings_count=len(p["holdings"]),
        shares_weight=sum(h["weight"] for h in p["holdings"] if not h["is_bond"]),
        bonds_weight=sum(h["weight"] for h in p["holdings"] if h["is_bond"]),
        cash_weight=p["cash_usd"]/p["total_usd"])
    if p.get("gbpusd") is not None and p["gbpusd"] > 0:
        result["total_gbp"] = p["total_usd"] / p["gbpusd"]
    if not all(math.isfinite(v) for v in result.values()):
        raise ValueError("Non-finite presentation totals")
    return result

def selection_summary(selection):
    data = as_dict(selection)
    return dict(analysed_count=data.get("analysed_count", len(data["selected"])))
