import tempfile
import time
import unittest
from unittest.mock import patch
from frontend.dev.stub_api import create_app
from quant.contract_fixtures import CHARITIES

class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=create_app();cls.client=cls.app.test_client()

    def setUp(self):
        self.cid=CHARITIES[0][0]
        ws=self.app.config["MANDATE_WORKSPACE_PROVIDER"]
        for cid in ws.states:
            ws.states[cid]["positions"]={};ws.states[cid]["receipts"]={}

    def buy(self,**overrides):
        body=dict(ticker="TEST",amount_usd=5000,policy_revision=self.client.get(f"/api/charities/{self.cid}/account").json["policy_revision"],request_id="test-buy")
        body.update(overrides)
        return self.client.post(f"/api/charities/{self.cid}/investments",json=body)

    def test_buy_reconciles_cash_chart_and_stats_without_network(self):
        with patch("socket.socket.connect",side_effect=AssertionError("No network")):
            initial=self.client.get(f"/api/charities/{self.cid}/account").json
            self.assertEqual(initial["portfolio"]["cash_usd"],100000)
            response=self.buy()
        self.assertEqual(response.status_code,200,response.json)
        data=response.json;account=data["account"]
        self.assertEqual(account["portfolio"]["holdings"][0]["ticker"],"TEST")
        self.assertAlmostEqual(account["invested_usd"]+account["portfolio"]["cash_usd"],100000)
        self.assertAlmostEqual(sum(item["weight"] for item in account["chart"]),1)
        self.assertGreater(account["portfolio"]["risk"]["volatility"],0)
        self.assertTrue(data["receipt"]["simulated"])
        again=self.buy()
        self.assertEqual(again.json["account"]["invested_usd"],account["invested_usd"])

    def test_rejections_caps_invalid_amounts_and_stale_policy(self):
        for amount in (-1,0,True,1000000,5000.001):
            self.assertEqual(self.buy(amount_usd=amount).status_code,400)
        self.assertEqual(self.buy(ticker="VETO").status_code,409)
        self.assertEqual(self.buy(ticker="REVIEW").status_code,409)
        self.assertEqual(self.buy(policy_revision=-1).status_code,409)
        self.assertEqual(self.buy().status_code,200)
        self.assertEqual(self.buy(amount_usd=6000).status_code,409)
        self.assertEqual(self.buy(amount_usd=6000,request_id="over-cap").status_code,400)

    def test_charity_isolation(self):
        self.buy()
        other=self.client.get(f"/api/charities/{CHARITIES[1][0]}/account").json
        self.assertEqual(other["portfolio"]["cash_usd"],100000)

    def test_policy_reassesses_and_flags_existing_position(self):
        self.buy()
        revision=self.client.get(f"/api/charities/{self.cid}/account").json["policy_revision"]
        text="No tobacco. Exclude TEST."
        job_id=self.client.post(f"/api/charities/{self.cid}/policy",json=dict(text=text,policy_revision=revision)).json["job_id"]
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            job=self.client.get(f"/api/jobs/{job_id}").json
            if job["status"] in ("done","error"):break
            time.sleep(.1)
        self.assertEqual(job["status"],"done",job.get("error"))
        report=self.client.get(f"/api/charities/{self.cid}/companies/TEST").json
        self.assertEqual(report["decision"]["decision"],"REJECT")
        self.assertEqual(report["melchior"]["verdicts"][0]["quote"],text)
        account=self.client.get(f"/api/charities/{self.cid}/account").json
        self.assertEqual(account["to_verify"][0]["ticker"],"TEST")
        self.assertEqual(len(account["portfolio"]["holdings"]),1)
        self.assertFalse(self.client.get(f"/api/charities/{self.cid}/companies/TEST/investment-quote").json["buy_allowed"])
        # Restore the initial fixture for subsequent tests.
        ws=self.app.config["MANDATE_WORKSPACE_PROVIDER"]
        ws._compile(self.cid,"No tobacco",revision+2)
        ws.states[self.cid].update(policy_text="No tobacco",policy_revision=revision+2)
        self.app.config["FIXTURE_STORE"].portfolios[self.cid]=self.app.config["FIXTURE_STORE"]._compute(self.cid)

    def test_persistence_survives_server_restart(self):
        from frontend.dev.workspace import DemoWorkspace
        store=self.app.config["FIXTURE_STORE"]
        with tempfile.TemporaryDirectory() as directory:
            workspace=DemoWorkspace(store,directory)
            workspace.buy(self.cid,dict(ticker="TEST",amount_usd=1000,policy_revision=1,request_id="persist"))
            restored=DemoWorkspace(store,directory)
            self.assertEqual(restored.account(self.cid)["portfolio"]["holdings"][0]["ticker"],"TEST")

if __name__=="__main__":unittest.main()
