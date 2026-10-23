import re
import json
import time
import unittest
from unittest.mock import patch
from frontend.dev.stub_api import create_app
from quant.contract_fixtures import CHARITIES, Portfolio

class ContractApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=create_app()
        cls.client=cls.app.test_client()

    def test_four_charities_and_sources_offline(self):
        with patch("socket.socket.connect",side_effect=AssertionError("Network forbidden in fixture test")):
            self.assertEqual(len(self.client.get("/api/charities").json),4)
            for cid,_,_ in CHARITIES:
                response=self.client.get(f"/api/charities/{cid}/portfolio")
                self.assertEqual(response.headers["X-Mandate-Data"],"synthetic")
                summary=json.loads(response.headers["X-Mandate-Presentation"])
                self.assertEqual(summary["holdings_count"],len(response.json["holdings"]))
                self.assertAlmostEqual(summary["total_gbp"],100000/1.3)
                self.assertAlmostEqual(summary["shares_weight"]+summary["bonds_weight"]+summary["cash_weight"],1)
                p=Portfolio.model_validate(response.json)
                for h in p.holdings:
                    for source in h.source_ids:
                        self.assertEqual(self.client.get(f"/api/sources/{source}").status_code,200)

    def wait_job(self, job_id):
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            job=self.client.get(f"/api/jobs/{job_id}").json
            if job["status"] in ("done","error"):return job
            time.sleep(.1)
        self.fail("Fixture job timed out")

    def test_rule_progress_and_holdings_update(self):
        cid=CHARITIES[1][0]
        with patch("socket.socket.connect",side_effect=AssertionError("No network")):
            response=self.client.post(f"/api/charities/{cid}/rules",json={"rule_text":"Judge test"})
            job=self.wait_job(response.json["job_id"])
        self.assertEqual(job["status"],"done",job.get("error"))
        self.assertGreater(len(job["progress"]),1)
        self.assertNotIn("TEST",[h["ticker"] for h in job["result"]["holdings"]])
        self.assertEqual(self.client.get(f"/api/charities/{cid}/rules").json["rules"][-1]["origin"],"judge")

    def test_refresh_and_compare(self):
        with patch("socket.socket.connect",side_effect=AssertionError("No network")):
            response=self.client.post("/api/companies/TEST/refresh")
            job=self.wait_job(response.json["job_id"])
            self.assertEqual(job["status"],"done",job.get("error"))
            self.assertEqual(len(self.client.get("/api/compare/TEST").json),4)

    def test_flask_build_and_api_errors(self):
        response=self.client.get("/")
        self.assertEqual(response.status_code,200)
        asset=re.search(r'src="([^"]+\.js)"',response.text).group(1)
        response.close()
        asset_response=self.client.get(asset)
        self.assertEqual(asset_response.status_code,200)
        asset_response.close()
        self.assertEqual(self.client.get("/assets/not-found.js").status_code,404)
        response=self.client.get("/api/not-real")
        self.assertEqual(response.status_code,404)
        self.assertEqual(response.json,{"error":"Unknown API endpoint"})
        self.assertEqual(self.client.post(f"/api/charities/{CHARITIES[0][0]}/rules",json={}).status_code,400)

if __name__=="__main__":unittest.main()
