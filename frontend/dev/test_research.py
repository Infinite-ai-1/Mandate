import copy
import unittest
from frontend.research_summary import research_summary

def report(verdict="PASS",verified=True,decision="APPROVE"):
    return dict(melchior=dict(verdicts=[dict(verdict=verdict,verified=verified,reason="Ethics evidence")]),
        balthasar=dict(score=70,summary="Financial evidence"),casper=dict(score=70,summary="Risk evidence"),
        decision=dict(decision=decision,reason="Chair explanation"))

class ResearchTests(unittest.TestCase):
    def test_three_votes_strong_buy_two_votes_buy(self):
        all_yes=research_summary(report(),dict(balthasar="INVEST",casper="INVEST"))
        self.assertEqual(all_yes["recommendation"],"STRONG_BUY")
        self.assertEqual(all_yes["invest_votes"],3)
        self.assertEqual(all_yes["ethics_score"],100)
        two_yes=research_summary(report(),dict(balthasar="INVEST",casper="DO_NOT_INVEST"))
        self.assertEqual(two_yes["recommendation"],"BUY")

    def test_ethics_veto_beats_majority(self):
        summary=research_summary(report("FAIL",decision="REJECT"),dict(balthasar="INVEST",casper="INVEST"))
        self.assertEqual(summary["consensus"],"BUY")
        self.assertEqual(summary["recommendation"],"REJECT")
        self.assertTrue(summary["ethics_blocked"])
        self.assertEqual(summary["ethics_score"],0)

    def test_majority_rejection_and_flag_review(self):
        summary=research_summary(report(),dict(balthasar="DO_NOT_INVEST",casper="DO_NOT_INVEST"))
        self.assertEqual(summary["recommendation"],"REJECT")
        flagged=research_summary(report("FLAG",decision="TRUSTEE_REVIEW"),dict(balthasar="INVEST",casper="INVEST"))
        self.assertEqual(flagged["recommendation"],"REVIEW")

    def test_scores_do_not_invent_votes(self):
        summary=research_summary(report())
        self.assertIsNone(summary["recommendation"])
        self.assertIsNone(summary["votes"]["balthasar"])
        self.assertIsNone(summary["invest_votes"])

    def test_ethics_metric_is_measured_verified_pass_coverage(self):
        evidence=report()
        evidence["melchior"]["verdicts"].append(dict(verdict="PASS",verified=False,reason="Unverified"))
        summary=research_summary(evidence,dict(balthasar="INVEST",casper="INVEST"))
        self.assertEqual(summary["ethics_score"],50)
        self.assertEqual(summary["recommendation"],"REVIEW")

if __name__=="__main__":unittest.main()
