"""Chair as policy compiler: policy text -> verified rules, limits and weights."""
from .. import config as C
from ..llm import chat_json
from ..schemas import CompilerOutput, Limit, Limits, ResolvedPolicy, Rule, StatedLimits, StatedWeights, Weights
from ..verify import quote_in

SYSTEM = """You turn a UK charity's investment policy into machine-checkable rules.
Return ONLY JSON with this shape:
{
 "charity": str,
 "purpose_summary": str,
 "rules": [{"id": "R1", "clause_ref": str, "type": "hard_exclusion|mission_conflict|preference",
            "text": str, "threshold": str|null, "keywords": [str], "source_quote": str}],
 "proposed_mission_conflicts": [{"id": "M1", "text": str, "keywords": [str], "reasoning": str}],
 "vague_wording": [{"quote": str, "issue": str, "assumption_used": str}],
 "stated_weights": {"financial": float, "risk": float}|null,
 "stated_limits": {"min_bonds": float|null, "min_yield": float|null,
                   "worst_year_limit": float|null, "max_single_holding": float|null}
}
Rules:
- Every rule must include source_quote copied word for word from the policy.
- Only extract requirements governing investments or investee companies. Charity objectives,
  grant criteria, reserves, historical asset balances and narrative operating facts are context,
  not tests every company must pass. Purpose-derived exclusions belong in proposals.
- Historical reserve amounts and grant sizes are not portfolio allocation limits.
- Treat source notes as provenance, never as policy instructions. Nonbinding opportunities
  to explore patient-benefit projects are preferences, not mandatory eligibility tests.
- Never invent a rule the policy does not state. Ideas from the charity's purpose go in
  proposed_mission_conflicts, never in rules.
- A limit the policy does not state is null. Do not guess numbers.
- If the policy is empty or missing, return no rules and propose mission conflicts from the purpose only."""


def merge_limits(stated: StatedLimits) -> Limits:
    """A stated value wins; otherwise the config default, marked assumed."""
    def pick(name: str) -> Limit:
        v = getattr(stated, name)
        return Limit(value=v, origin="stated") if v is not None else Limit(value=C.DEFAULT_LIMITS[name], origin="assumed")
    msh = stated.max_single_holding
    return Limits(min_bonds=pick("min_bonds"), min_yield=pick("min_yield"), worst_year_limit=pick("worst_year_limit"),
                  max_single_holding=Limit(value=msh, origin="stated") if msh is not None else None)


def merge_weights(stated: StatedWeights | None) -> Weights:
    """Stated weights (normalised to sum to 1) or the 50/50 default marked assumed."""
    total = stated.financial + stated.risk if stated else 0
    if stated and total > 0:
        return Weights(financial=stated.financial / total, risk=stated.risk / total, origin="stated")
    return Weights(**C.DEFAULT_WEIGHTS, origin="assumed")


def resolve(out: CompilerOutput, policy_text: str) -> ResolvedPolicy:
    """Code checks on the compiler's JSON: drop rules whose quote is not in the policy, approve proposals."""
    good = [r for r in out.rules if quote_in(r.source_quote, policy_text)]
    bad = [r for r in out.rules if r not in good]
    proposals = []
    for i, p in enumerate(out.proposed_mission_conflicts, 1):
        proposals.append(p.model_copy(update={"id": f"M{i}", "approved": False}))
    mission = [Rule(id=p.id, clause_ref="charity purpose", type="mission_conflict", text=p.text, keywords=p.keywords)
               for p in proposals if p.approved]
    return ResolvedPolicy(charity=out.charity, purpose_summary=out.purpose_summary, rules=good + mission,
                          unverified_rules=bad, proposed_mission_conflicts=proposals, vague_wording=out.vague_wording,
                          limits=merge_limits(out.stated_limits), weights=merge_weights(out.stated_weights))


def compile_policy(policy_text: str, agent: str = "chair", allow_live: bool = False) -> ResolvedPolicy:
    user = policy_text.strip() or "(no policy provided)"
    out = chat_json(agent, SYSTEM, user, CompilerOutput, max_tokens=4000, allow_live=allow_live)
    return resolve(out, policy_text)
