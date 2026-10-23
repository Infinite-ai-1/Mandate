"""Melchior: ethics. One call per company covering every rule, evidence retrieved per rule."""
import asyncio

from ..evidence import format_chunks, retrieve
from ..llm import achat_json
from ..schemas import MelchiorOutput, MelchiorResult, Rule
from ..verify import verify_verdicts

SYSTEM = """You are Melchior, the ethics specialist on a charity's investment committee.
Check ONE company against EACH rule using ONLY the evidence given.
Return ONLY JSON:
{"ticker": str,
 "verdicts": [{"rule_id": str, "verdict": "PASS|FAIL|FLAG", "confidence": float,
               "quote": str|null, "source_id": str|null, "reason": str}]}
Rules:
- FAIL requires a quote copied word for word from one evidence chunk, plus its source_id.
- If the evidence is ambiguous or insufficient to decide, answer FLAG and explain what is missing.
- PASS requires a relevant verbatim quote and source_id supporting compliance with the rule.
- Missing evidence is FLAG, never PASS.
- reason: one plain sentence a volunteer trustee would understand.
- Do not use outside knowledge."""


def build_user(ticker: str, name: str, summary: str, rules: list[Rule], evidence: dict) -> str:
    parts = [f"Company: {name} ({ticker})", f"Business summary: {summary or 'not available'}", ""]
    for r in rules:
        parts.append(f"[{r.id}] {r.text}" + (f" (threshold: {r.threshold})" if r.threshold else ""))
        parts.append(format_chunks(evidence[r.id]))
        parts.append("")
    return "\n".join(parts)


async def run(ticker: str, name: str, summary: str, rules: list[Rule], agent: str = "melchior",
              allow_live: bool = False) -> MelchiorResult:
    """Verified verdicts, one per rule. agent="fast" is used by the live-rule path."""
    evidence = await asyncio.to_thread(lambda: {r.id: retrieve(ticker, r) for r in rules})
    out = await achat_json(agent, SYSTEM, build_user(ticker, name, summary, rules, evidence), MelchiorOutput,
                           ticker=ticker, max_tokens=4000, allow_live=allow_live)
    return verify_verdicts(ticker, [r.id for r in rules], out)
