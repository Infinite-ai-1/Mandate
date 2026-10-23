"""Trustee memo: plain-English one-pager built only from the portfolio JSON."""
import json

from ..llm import chat_json
from ..schemas import MemoOutput

SYSTEM = """Write a one-page memo for the volunteer trustees of {charity}. They are not finance experts.
Use ONLY numbers that appear in this JSON. Cite the policy as [Clause X] and evidence as [source_id].
Order: the recommendation in one sentence; three reasons; what we rejected and why (top 5);
items needing trustee review; assumptions we made; the main risks; what would change our mind.
Under 450 words. Plain English. No hype.
Return ONLY JSON: {{"memo": "<the memo as markdown>"}}"""


def write_memo(charity: str, portfolio: dict) -> str:
    out = chat_json("memo", SYSTEM.format(charity=charity), json.dumps(portfolio, indent=1), MemoOutput, max_tokens=2000)
    return out.memo
