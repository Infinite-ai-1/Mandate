"""Server-calculated research presentation; never infer votes from score thresholds."""
VOTES = {"INVEST", "DO_NOT_INVEST", "REVIEW"}

def research_summary(report, explicit_votes=None):
    explicit_votes = explicit_votes or {}
    verdicts = report["melchior"]["verdicts"]
    blocked = any(v["verdict"] == "FAIL" and v["verified"] is True for v in verdicts)
    unresolved = not verdicts or any(v["verdict"] == "FLAG" or v["verified"] is not True for v in verdicts)
    ethics_vote = "DO_NOT_INVEST" if blocked else "REVIEW" if unresolved else "INVEST"
    votes = {"melchior": ethics_vote}
    for agent in ("balthasar", "casper"):
        value = explicit_votes.get(agent)
        votes[agent] = value if value in VOTES else None
    complete = all(v is not None for v in votes.values())
    yes = sum(v == "INVEST" for v in votes.values()) if complete else None
    no = sum(v == "DO_NOT_INVEST" for v in votes.values()) if complete else None
    consensus = ("STRONG_BUY" if yes == 3 else "BUY" if yes == 2 else "REJECT" if no is not None and no >= 2 else "REVIEW") if complete else None
    decision = report["decision"]
    recommendation = "REJECT" if blocked or decision["decision"] == "REJECT" else "REVIEW" if unresolved or decision["decision"] == "TRUSTEE_REVIEW" else consensus
    return dict(votes=votes, invest_votes=yes, consensus=consensus, recommendation=recommendation,
        ethics_blocked=blocked,
        ethics_score=(100 * sum(v["verdict"] == "PASS" and v["verified"] is True for v in verdicts) / len(verdicts)) if verdicts else None,
        ethics_definition=("Simulated coverage of scripted rule assumptions, not verification of real company evidence." if report.get("simulated") else "Percentage of rule checks that passed with verified evidence. This is evidence coverage, not a probability that a company is ethical."),
        rationale=dict(ethics=" ".join(v["reason"] for v in verdicts), financial=report["balthasar"]["summary"], risk=report["casper"]["summary"]),
        chair_reason=decision["reason"])
