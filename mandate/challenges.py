"""Deterministic challenges grounded in the actual run, without new model claims."""


def build_challenges(run: dict) -> list[str]:
    opt = run.get("optimiser", {})
    decisions = run.get("decisions", [])
    policy = run.get("policy", {})
    challenges = []
    reviews = [d["ticker"] for d in decisions if d["status"] == "TRUSTEE_REVIEW"]
    if reviews:
        challenges.append(f"{len(reviews)} companies remain unresolved ({', '.join(reviews[:6])}{', …' if len(reviews) > 6 else ''}). What specific evidence would resolve each flag? Missing evidence is not proof of a breach.")
    holdings = opt.get("holdings", [])
    if any(h["is_bond"] for h in holdings):
        challenges.append("Bond ETFs bypassed the company ethics screen. Check their underlying issuers against the adopted exclusions before accepting the suggested allocation.")
    assumed = [key.replace("_", " ") for key, limit in policy.get("limits", {}).items() if limit and limit.get("origin") == "assumed"]
    if assumed:
        challenges.append("Trustees have not confirmed these assumed limits: " + ", ".join(assumed) + ". Would the recommendation change under their actual spending needs and risk tolerance?")
    if opt.get("relaxed"):
        challenges.append("The optimiser relaxed constraints: " + "; ".join(opt["relaxed"]) + " Confirm each compromise is acceptable before adopting the portfolio.")
    bt = opt.get("backtest") or {}
    if bt.get("vs_6040", 0) < 0:
        challenges.append(f"The historical scenario trails the 60/40 benchmark by {abs(bt['vs_6040']) * 100:.1f} percentage points. Are the policy alignment and risk characteristics worth that historical trade-off?")
    if holdings:
        largest = max(holdings, key=lambda h: h["weight"])
        challenges.append(f"The largest suggested position is {largest['ticker']} at {largest['weight']:.1%}. Check issuer, sector and fund overlap rather than relying on the position cap alone.")
    if not opt.get("ok"):
        challenges.append("The optimiser did not produce a feasible portfolio. Resolve the reported data or constraint problem before treating any allocation as investable.")
    if not bt:
        challenges.append("No usable historical backtest is available. Do not infer that the yield or loss limits have passed.")
    return challenges or ["Approval depends on the evidence available for this run. What adverse evidence or changed spending requirement would reverse the decision?"]
