"""Balthasar: financial health, scored from fundamentals only."""
import json

from ..llm import achat_json
from ..schemas import BalthasarOutput, FinResult
from ..verify import verify_fin

SYSTEM = """You are Balthasar, the financial health specialist on a charity's investment committee.
Judge the company's financial health from the metrics given. Use no outside knowledge.
Return ONLY JSON:
{"ticker": str, "score": int (0-10, 10 = strongest),
 "reasons": [{"text": str, "metric": str, "value": number}]}
Every reason must cite exactly one metric key from the data and its value as given.
Give 2 to 4 reasons. If key metrics are missing, say so in a reason with metric "missing" and value 0,
and keep the score near 5."""


def metrics_only(fundamentals: dict) -> dict:
    return {k: v for k, v in fundamentals.items() if k != "longBusinessSummary"}


async def run(ticker: str, fundamentals: dict) -> FinResult:
    data = metrics_only(fundamentals)
    out = await achat_json("balthasar", SYSTEM, json.dumps(data, indent=1), BalthasarOutput, ticker=ticker)
    return verify_fin(out, data)
