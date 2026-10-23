"""Devil's advocate: the strongest real objections to this specific portfolio, for the trustees to weigh.

Not a list of things that went wrong while running the pipeline (that's `warnings`, surfaced separately
in Rules.questions and the job progress log). This is substantive pushback on the recommendation itself --
the kind of challenge a critical trustee would raise before signing off -- grounded only in this
portfolio's own JSON, same discipline as the memo.
"""
import json

from ..llm import chat_json
from ..schemas import DevilsAdvocateOutput

SYSTEM = """You are the devil's advocate on {charity}'s investment committee. Your one job is to argue
AGAINST the recommended portfolio below, as persuasively and specifically as a critical trustee would.
Use ONLY what appears in this JSON -- holdings, rejected/trustee-review companies, rules, limits, risk
figures. Never invent a number or claim.
Each argument must name a specific holding, rule, limit, or risk figure from the JSON and explain
concretely why a thoughtful trustee might object to it -- concentration in one holding or sector,
a rejected company that arguably shouldn't have been excluded (or vice versa), an assumed limit or
weight standing in for one the policy never stated, a risk figure that looks weaker than it should,
evidence that was unverified, or a rule that was only proposed and never approved. Generic caution
("markets can be volatile", "past performance is not indicative") is not acceptable; every argument
must be specific to THIS portfolio.
Give exactly 3 arguments, each 1-3 sentences, plain English, no hedging softeners ("might", "could
perhaps") -- state the objection directly.
Return ONLY JSON: {{"arguments": ["<argument 1>", "<argument 2>", "<argument 3>"]}}"""


def write_devils_advocate(charity: str, portfolio: dict) -> list[str]:
    out = chat_json("memo", SYSTEM.format(charity=charity), json.dumps(portfolio, indent=1),
                     DevilsAdvocateOutput, max_tokens=1200)
    return out.arguments
