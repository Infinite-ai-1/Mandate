"""Offline integration tests. Doubles exist only in tests, never served to users."""
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mandate import config as C, evidence
from mandate.agents.compiler import merge_limits, resolve
from mandate.decide import classify_ethics, decide_chair, decide_ethics
from mandate.schemas import (ChairResult, CompilerOutput, FinResult, MelchiorOutput,
                             MelchiorResult, RiskResult, StatedLimits, Verdict)
from mandate.verify import verify_verdicts
from mandate.web import Workspace, create_app

CID = "british_thoracic_society"


class IntegrationTests(unittest.TestCase):
    def test_full_reset_clears_all_charities_and_invalidates_old_workers(self):
        from mandate.web import CHARITIES
        import threading
        for cid in CHARITIES:
            s = self.ws.state(cid)
            s.update(policy="Custom test policy", run={"test": True}, cash=123,
                     positions={"DEMO-XYL": {}}, receipts={"old": {}}, demo_assessments={"DEMO-XYL": 0})
            self.ws.save(cid, s)
        started, release = threading.Event(), threading.Event()
        def old_work(progress):
            old = self.ws.state(CID)
            started.set()
            release.wait(5)
            self.ws.save(CID, old)
        jid = self.ws.submit(CID, old_work)['job_id']
        self.assertTrue(started.wait(2))
        try:
            response = self.client.post('/api/reset', json={})
            self.assertEqual(response.json, {'reset': True})
        finally:
            release.set()
        self.ws.executor.submit(lambda: None).result(timeout=5)
        self.assertEqual(self.client.get('/api/jobs/'+jid).status_code, 404)
        for cid in CHARITIES:
            s = self.ws.state(cid)
            self.assertIsNone(s['policy'])
            self.assertIsNone(s['run'])
            self.assertEqual(s['cash'], C.BUDGET_USD)
            self.assertEqual(s['positions'], {})
            self.assertEqual(s['receipts'], {})
            self.assertNotIn('demo_assessments', s)
            self.assertEqual(s['revision'], 1)
            self.assertNotEqual(self.ws.policy(cid)['text'], 'Custom test policy')
        self.assertFalse(self.ws.busy)
        self.assertEqual(self.client.post('/api/reset', json={}, headers={'Origin':'https://untrusted.invalid'}).status_code, 403)

    def test_demo_jobs_use_standard_routes_and_allocation_rules(self):
        from mandate.demos import SCENARIOS
        for ticker, scenario in SCENARIOS.items():
            with self.subTest(ticker=ticker), patch("time.sleep", return_value=None):
                response = self.client.post(f"/api/companies/{ticker}/refresh", json={"charity_id": CID})
                self.assertEqual(response.status_code, 202)
                # Avoid the test wait helper's mocked sleep racing the worker.
                self.ws.executor.submit(lambda: None).result(timeout=5)
                job = self.client.get('/api/jobs/'+response.json['job_id']).json
                self.assertEqual(job['status'], 'done')
                self.assertTrue(any('[melchior:done]' in msg for msg in job['progress']))
                report = self.client.get(f'/api/charities/{CID}/companies/{ticker}')
                self.assertEqual(report.json['decision']['decision'], scenario['decision'])
                self.assertTrue(report.json['simulated'])
                self.assertIn('X-Mandate-Research', report.headers)
                quote = self.client.get(f'/api/charities/{CID}/companies/{ticker}/investment-quote').json
                allowed = scenario['decision'] in ('APPROVE', 'APPROVE_CAPPED')
                self.assertEqual(quote['buy_allowed'], allowed)
                body = dict(ticker=ticker, amount_usd=1000, request_id=ticker, policy_revision=0)
                buy = self.client.post(f'/api/charities/{CID}/investments', json=body)
                self.assertEqual(buy.status_code, 200 if allowed else 409)
                if allowed:
                    self.assertIn('DEMO', buy.json['account']['portfolio']['holdings'][-1]['name'])
                    self.assertEqual(self.client.post(f'/api/charities/{CID}/investments', json=body).json['receipt'], buy.json['receipt'])
                    oversized = self.client.post(f'/api/charities/{CID}/investments', json={**body,'amount_usd':quote['maximum_usd']+1,'request_id':ticker+'-over'})
                    self.assertEqual(oversized.status_code, 409)
        account = self.ws.account(CID)
        self.assertEqual(account['invested_usd'], 2000)
        self.assertEqual(len(account['portfolio']['holdings']), 2)
        self.assertEqual(sum(c['usd'] for c in account['chart']), C.BUDGET_USD)
        state = self.ws.state(CID)
        state['revision'] += 1
        self.ws.save(CID, state)
        self.assertFalse(self.ws.quote(CID, 'DEMO-XYL')['buy_allowed'])
        self.assertEqual(len(self.ws.account(CID)['to_verify']), 2)
        # No demo approval has been published for the actual issuer.
        self.assertEqual(self.client.get(f'/api/charities/{CID}/companies/XYL').status_code, 409)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(self.tmp.name)
        self.client = self.app.test_client()
        self.ws = self.app.config["MANDATE_WORKSPACE"]

    def tearDown(self):
        self.ws.executor.shutdown(wait=True)
        self.tmp.cleanup()

    def wait_job(self, jid):
        for _ in range(200):
            job = self.client.get(f"/api/jobs/{jid}").get_json()
            if job["status"] in ("done", "error"):
                return job
            time.sleep(.01)
        self.fail("Background job did not finish")

    def test_startup_with_real_policies_and_empty_paper_account(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        charities = self.client.get("/api/charities").get_json()
        self.assertEqual(len(charities), 4)
        for charity in charities:
            cid = charity["charity_id"]
            account = self.client.get(f"/api/charities/{cid}/account").get_json()
            self.assertTrue(account["simulated"])
            self.assertEqual(account["portfolio"]["holdings"], [])
            self.assertEqual(account["portfolio"]["cash_usd"], C.BUDGET_USD)
            self.assertIsNone(account["portfolio"]["gbpusd"])
            self.assertTrue(all(v is None for v in account["portfolio"]["risk"].values()))
            self.assertNotIn("total_gbp", account["presentation"])
            policy = self.client.get(f"/api/charities/{cid}/policy").get_json()
            self.assertGreater(len(policy["text"]), 100)
            self.assertEqual(self.client.get(f"/api/charities/{cid}/portfolio").status_code, 409)
            selection = self.client.get(f"/api/charities/{cid}/selection")
            self.assertEqual(json.loads(selection.headers["X-Mandate-Presentation"])["analysed_count"], 0)

    def test_unknown_routes_and_input_errors_are_json(self):
        for path in ("/api/not-a-route", "/api/jobs/unknown", "/api/charities/unknown/account", "/api/sources/unknown"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404, path)
            self.assertIn("error", response.get_json())
        self.assertEqual(self.client.post(f"/api/charities/{CID}/run", json=[]).status_code, 400)
        self.assertEqual(self.client.post(f"/api/charities/{CID}/run", json={}, headers={"Origin": "https://untrusted.invalid"}).status_code, 403)

    def test_policy_save_without_keys_is_persistent_and_finishes(self):
        with patch.object(self.ws, "requirements", return_value=["MODEL_BALTHASAR"]), patch.object(C, "DEMO_MODE", False):
            response = self.client.post(f"/api/charities/{CID}/policy", json={"text": "Trustee policy entered for this test", "policy_revision": 0})
            self.assertEqual(response.status_code, 202)
            job = self.wait_job(response.get_json()["job_id"])
            self.assertEqual(job["status"], "done")
            self.assertIsNone(job["result"])
            self.assertIn("Configure API", job["progress"][-1])
        saved = self.ws.state(CID)
        self.assertEqual(saved["revision"], 1)
        self.assertIsNone(saved["run"])
        other = Workspace(self.tmp.name)
        try:
            self.assertEqual(other.policy(CID)["text"], saved["policy"])
        finally:
            other.executor.shutdown()
        stale = self.client.post(f"/api/charities/{CID}/policy", json={"text": "Overwrite", "policy_revision": 0})
        self.assertEqual(stale.status_code, 409)

    def test_unconfigured_research_finishes_as_actionable_error(self):
        with patch.object(self.ws, "requirements", return_value=["MODEL_BALTHASAR"]), patch.object(C, "DEMO_MODE", False):
            response = self.client.post(f"/api/charities/{CID}/run", json={})
            job = self.wait_job(response.get_json()["job_id"])
        self.assertEqual(job["status"], "error")
        self.assertIn("MODEL_BALTHASAR", job["error"])
        self.assertNotIn(CID, self.ws.busy)

    def test_real_ingestion_evidence_resolves_through_flask(self):
        chunks, _ = evidence._load("PM")
        self.assertGreater(len(chunks), 0)
        chunk = next(c for c in chunks if c.source_id.startswith("S-PM-") and c.url)
        self.assertEqual(evidence.get_chunk(chunk.source_id).text, chunk.text)
        response = self.client.get(f"/api/sources/{chunk.source_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["ticker"], "PM")

    def test_paper_buy_idempotency_revision_and_cash_accounting(self):
        # Controlled quote verifies ledger arithmetic, not a market recommendation.
        quote = dict(buy_allowed=True, blocked_reason=None, maximum_usd=10000, price=123.45)
        report = dict(decision=dict(cap=.1, reason="Test-only verified decision", source_ids=[], decision="APPROVE"))
        body = dict(ticker="XYL", amount_usd=1000, request_id="test-id", policy_revision=0)
        with patch.object(self.ws, "quote", return_value=quote), patch.object(self.ws, "company", return_value=report):
            first = self.client.post(f"/api/charities/{CID}/investments", json=body)
            second = self.client.post(f"/api/charities/{CID}/investments", json=body)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.get_json(), second.get_json())
            self.assertEqual(first.get_json()["receipt"]["shares"], 8)
            account = first.get_json()["account"]
            self.assertAlmostEqual(account["portfolio"]["cash_usd"]+account["invested_usd"], C.BUDGET_USD)
            conflict = self.client.post(f"/api/charities/{CID}/investments", json={**body, "amount_usd": 2000})
            self.assertEqual(conflict.status_code, 409)
            stale = self.client.post(f"/api/charities/{CID}/investments", json={**body, "request_id": "new", "policy_revision": 1})
            self.assertEqual(stale.status_code, 409)
            overspend = self.client.post(f"/api/charities/{CID}/investments", json={**body, "request_id": "new", "amount_usd": 11000})
            self.assertEqual(overspend.status_code, 409)

    def test_unassessed_stock_cannot_be_bought(self):
        quote = self.client.get(f"/api/charities/{CID}/companies/XYL/investment-quote").get_json()
        self.assertFalse(quote["buy_allowed"])
        response = self.client.post(f"/api/charities/{CID}/investments", json=dict(ticker="XYL", amount_usd=1000, request_id="a", policy_revision=0))
        self.assertEqual(response.status_code, 409)

    def test_policy_fingerprint_invalidates_external_file_changes(self):
        state = self.ws.state(CID)
        state["run"] = {"policy_hash": "outdated"}
        self.ws.save(CID, state)
        self.assertEqual(self.client.get(f"/api/charities/{CID}/portfolio").status_code, 409)

    def test_flask_serves_built_react_assets(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="root"', response.data)
        response.close()
        with self.client.get("/research") as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/assets/missing.js").status_code, 404)


class VerificationTests(unittest.TestCase):
    def test_keyless_mode_replays_saved_result_without_pipeline(self):
        from mandate.web import Workspace
        ws = Workspace(Path("unused-test-state"))
        try:
            with patch.object(C, 'DEMO_MODE', True), patch.object(ws, 'run', return_value={}), patch.object(ws, 'portfolio', return_value={'cached': True}), patch('mandate.pipeline.run_charity', side_effect=AssertionError('No live pipeline')):
                progress=[]
                self.assertEqual(ws.assess(CID, progress.append, 'XYL'), {'cached': True})
                self.assertIn('no network', progress[0])
        finally:
            ws.executor.shutdown()

    def test_embedding_calls_cannot_escape_cache_only_mode(self):
        from mandate.llm import embed, aembed, DemoModeCacheMiss
        with patch.object(C, 'DEMO_MODE', True):
            with self.assertRaises(DemoModeCacheMiss): embed(['uncached'])
            # The offline guard must fail before reaching any asynchronous I/O.
            with self.assertRaises(DemoModeCacheMiss): aembed(['uncached']).send(None)

    def test_devils_advocate_uses_actual_run_conditions(self):
        from mandate.challenges import build_challenges
        run = dict(decisions=[dict(ticker="XYL", status="TRUSTEE_REVIEW")],
                   policy=dict(limits=dict(min_bonds=dict(value=.3, origin="assumed"))),
                   optimiser=dict(ok=True, holdings=[dict(ticker="BND", is_bond=True, weight=.25)],
                                  relaxed=["Income target dropped"], backtest=dict(vs_6040=-.125)))
        text = " ".join(build_challenges(run))
        for expected in ("XYL", "underlying issuers", "min bonds", "Income target dropped", "12.5 percentage points", "BND at 25.0%"):
            self.assertIn(expected, text)
        clean = dict(decisions=[], policy=dict(limits={}), optimiser=dict(ok=True, holdings=[], backtest=dict(vs_6040=.1)))
        self.assertNotIn("trails", " ".join(build_challenges(clean)))
        self.assertNotIn("unresolved", " ".join(build_challenges(clean)))

    def test_parallel_unsupported_parameter_responses_each_retry(self):
        import httpx
        import openai
        from mandate.llm import _bad_param, _dropped
        response = httpx.Response(400, request=httpx.Request("POST", "https://example.invalid"))
        error = openai.BadRequestError("Unsupported value: temperature", response=response, body={})
        _dropped.pop("test-model", None)
        self.assertTrue(_bad_param(error, "test-model"))
        self.assertTrue(_bad_param(error, "test-model"))

    def test_no_checks_or_uncited_pass_requires_review(self):
        self.assertEqual(classify_ethics([]), "TRUSTEE_REVIEW")
        self.assertEqual(classify_ethics([Verdict(rule_id="R1", verdict="PASS", verified=False)]), "TRUSTEE_REVIEW")
        result = verify_verdicts("PM", ["R1"], MelchiorOutput(ticker="PM", verdicts=[Verdict(rule_id="R1", verdict="PASS")]))
        self.assertEqual(result.verdicts[0].verdict, "FLAG")
        self.assertEqual(decide_ethics("PM", result).status, "TRUSTEE_REVIEW")

    def test_real_quote_is_verified_and_veto_cannot_be_overridden(self):
        chunk = evidence._load("PM")[0][0]
        verdict = Verdict(rule_id="R1", verdict="FAIL", quote=chunk.text[:200], source_id=chunk.source_id)
        mel = verify_verdicts("PM", ["R1"], MelchiorOutput(ticker="PM", verdicts=[verdict]))
        self.assertTrue(mel.verdicts[0].verified)
        decision = decide_chair("PM", mel, FinResult(ticker="PM", score=10), RiskResult(ticker="PM", score=10), ChairResult(ticker="PM", decision="full"))
        self.assertEqual(decision.status, "REJECTED_ETHICS")
        self.assertEqual(decision.cap, 0)

    def test_chair_failure_never_approves(self):
        mel = MelchiorResult(ticker="XYL", verdicts=[Verdict(rule_id="R1", verdict="PASS", verified=True)])
        result = decide_chair("XYL", mel, FinResult(ticker="XYL", score=10), RiskResult(ticker="XYL", score=10),
                              ChairResult(ticker="XYL", decision="reduced", defaulted=True))
        self.assertEqual(result.status, "TRUSTEE_REVIEW")

    def test_proposed_restrictions_are_not_automatically_approved(self):
        out = CompilerOutput(charity="Test", proposed_mission_conflicts=[dict(id="M1", text="Proposal", reasoning="Test")])
        policy = resolve(out, "")
        self.assertEqual(policy.rules, [])
        self.assertFalse(policy.proposed_mission_conflicts[0].approved)

    def test_demo_mode_blocks_even_allow_live_escape(self):
        from mandate.llm import _lookup, DemoModeCacheMiss
        with patch.object(C, "DEMO_MODE", True), patch("mandate.llm._cache_get", return_value=None), patch("mandate.llm._check_model", return_value="test"):
            with self.assertRaises(DemoModeCacheMiss):
                _lookup("chair", "test", "test", CompilerOutput, None, True)


if __name__ == "__main__":
    unittest.main()
