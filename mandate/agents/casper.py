"""Casper: risk. Interprets stats computed in code plus legal/regulatory evidence."""
import asyncio
import json

from ..evidence import format_chunks, retrieve_text
from ..llm import achat_json
from ..schemas import CasperOutput, RiskResult
from ..verify import verify_risk

SYSTEM = """You are Casper, the risk specialist on a charity's investment committee.
You are given risk statistics computed by code and a few risk-related evidence chunks.
Interpret them. Do not compute new numbers.
Return ONLY JSON:
{"ticker": str, "score": int (0-10, 10 = lowest risk),
 "reasons": [{"text": str, "metric": str|null, "value": number|null, "source_id": str|null}]}
Each reason cites either one stat key and its exact value, or one source_id. Give 2 to 4 reasons."""
QUERY = "legal, regulatory and litigation risk"


async def run(ticker: str, stats: dict) -> RiskResult:
    chunks = await asyncio.to_thread(retrieve_text, ticker, QUERY, None, 4)
    user = f"Risk statistics:\n{json.dumps(stats, indent=1)}\n\nEvidence:\n{format_chunks(chunks)}"
    out = await achat_json("casper", SYSTEM, user, CasperOutput, ticker=ticker)
    return verify_risk(out, stats)
