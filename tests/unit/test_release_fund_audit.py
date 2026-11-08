"""Release regression coverage for published disclosures, SLA caps, and paid fund settlement."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
import tempfile
from threading import Event
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from core.analysis.fund_overlap_auditor import calculate_deep_dive_credit_cost
from core.analysis.fund_research_evidence import PILLAR_LABELS, qualify_fund_research
from core.db import fund_audit_jobs as billing
from core.db.connection import IST, get_db_connection, get_placeholder, init_db
from core.db.mutual_funds import (
    get_current_fund_disclosure,
    get_fund_forensic_dossier,
    publish_mutual_fund_disclosure,
)
from core.db.users import (
    get_or_create_user,
    get_user_credits_balance,
    is_ticker_unlocked_for_user,
)


class TestFundRelease(TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._tmp_dir.name, "test_fund_release.db")
        self._env_patch = patch.dict(
            os.environ,
            {
                "TESTING": "1",
                "TEST_DB_PATH": self._db_path,
            },
        )
        self._env_patch.start()
        import core.db.connection as db_conn

        db_conn._DB_INITIALIZED = False
        db_conn._INITIALIZED_DBS.clear()
        init_db(force=True)
        self.owner = f"release-{uuid4().hex}"
        self.code = f"RELEASE_{uuid4().hex[:12].upper()}"
        get_or_create_user(self.owner, f"{self.owner}@example.invalid")
        self.scheme = {
            "scheme_code": self.code,
            "scheme_name": self.code,
            "fund_house": "Test AMC",
            "category": "Equity",
            "broad_category": "Equity",
            "last_portfolio_date": "2025-11-30",
            "metadata": {
                "holdings_source": "sebi_monthly_disclosure",
                "holdings_source_url": "https://example.invalid/disclosure.xlsx",
            },
        }
        self.holdings = [
            {
                "holding_type": "EQUITY",
                "identifier": "RELIANCE",
                "weight_pct": 100,
                "portfolio_date": self.scheme["last_portfolio_date"],
            }
        ]
        self.snapshot_id = publish_mutual_fund_disclosure(self.scheme, self.holdings)

    def tearDown(self):
        self._env_patch.stop()
        import core.db.connection as db_conn

        db_conn._DB_INITIALIZED = False
        db_conn._INITIALIZED_DBS.clear()
        self._tmp_dir.cleanup()

    def _submit(self, request_id, tickers=("RELIANCE",)):
        revision = billing.quote_revision(self.owner, self.snapshot_id, True, 1, tickers)
        return billing.enqueue_fund_audit(
            self.owner, request_id, self.scheme, self.snapshot_id, True, tickers, revision
        )

    def test_duplicate_submit_lost_worker_and_owner_isolation(self):
        request_id = uuid4().hex
        with patch.object(billing, "time", return_value=1_800_000_000):
            billing.record_worker_heartbeat()
            with ThreadPoolExecutor(max_workers=2) as workers:
                jobs = list(workers.map(lambda _: self._submit(request_id), range(2)))
            self.assertEqual(jobs[0]["job_id"], jobs[1]["job_id"])
            job_id = jobs[0]["job_id"]
            self.assertEqual(get_user_credits_balance(self.owner), 0)
            self.assertIsNone(billing.get_fund_audit_status_for_owner(job_id, "someone-else"))
            with self.assertRaises(billing.FundAuditConflict):
                billing.unlock_published_fund_dossier(self.owner, self.code)
            claimed = billing.claim_fund_audit()
            self.assertEqual(claimed["job_id"], job_id)

        with patch.object(billing, "time", return_value=1_800_000_000 + billing.WORKER_LEASE + 1):
            with ThreadPoolExecutor(max_workers=2) as workers:
                settled = list(workers.map(lambda _: billing.reconcile_expired_fund_audits(), range(2)))
            self.assertEqual(sorted(settled), [0, 1])
            billing.fail_fund_audit(claimed, "Late worker")
            self.assertEqual(billing.reconcile_expired_fund_audits(), 0)
        status = billing.get_fund_audit_status_for_owner(job_id, self.owner)
        self.assertEqual(status["status"], "FAILED")
        self.assertEqual(status["audit_settlement"]["credits_refunded"], 2)
        self.assertEqual(get_user_credits_balance(self.owner), 2)
        self.assertFalse(is_ticker_unlocked_for_user(self.owner, f"FUND:{self.code}"))

    def test_busy_worker_keeps_admitting_audits_without_extending_its_claim(self):
        from scripts import run_paid_fund_audit_worker as worker

        now = 1_800_000_000
        stale_at = now + billing.WORKER_HEARTBEAT_MAX_AGE + 1
        busy = Event()
        release = Event()
        refreshed = Event()

        def block_synthesis(_job):
            busy.set()
            if not release.wait(5):
                raise TimeoutError("Test did not release the busy worker")

        def record_heartbeat(job):
            tick = now
            billing.record_worker_heartbeat(job)
            if tick >= stale_at:
                refreshed.set()

        with patch.object(billing, "time", side_effect=lambda: now):
            billing.record_worker_heartbeat()
            first = self._submit(uuid4().hex)
            claim = billing.claim_fund_audit()
            deadline = billing.get_fund_audit_status_for_owner(first["job_id"], self.owner)["deadline_unix"]

            with (
                patch.object(worker, "run_claim", side_effect=block_synthesis),
                patch.object(worker, "record_worker_heartbeat", side_effect=record_heartbeat),
                patch.object(worker, "WORKER_HEARTBEAT_MAX_AGE", 0.03),
                ThreadPoolExecutor(max_workers=1) as pool,
            ):
                work = pool.submit(worker.run_claim_with_heartbeat, claim)
                try:
                    self.assertTrue(busy.wait(5))
                    now = stale_at
                    self.assertTrue(refreshed.wait(5))
                    other_owner = f"release-{uuid4().hex}"
                    get_or_create_user(other_owner, f"{other_owner}@example.invalid")
                    tickers = ("RELIANCE",)
                    revision = billing.quote_revision(other_owner, self.snapshot_id, True, 1, tickers)
                    second = billing.enqueue_fund_audit(
                        other_owner, uuid4().hex, self.scheme, self.snapshot_id, True, tickers, revision
                    )
                    self.assertEqual(second["status"], "QUEUED")
                    status = billing.get_fund_audit_status_for_owner(first["job_id"], self.owner)
                    self.assertEqual(status["deadline_unix"], deadline)

                    now = deadline + 1
                    billing.record_worker_heartbeat(claim)
                    self.assertEqual(billing.reconcile_expired_fund_audits(), 1)
                    status = billing.get_fund_audit_status_for_owner(first["job_id"], self.owner)
                    self.assertEqual(status["audit_settlement"]["credits_refunded"], 2)
                    with self.assertRaises(billing.FundAuditUnavailable):
                        self._submit(uuid4().hex)
                finally:
                    release.set()
                work.result(timeout=5)
            now = second["deadline"]
            self.assertEqual(billing.reconcile_expired_fund_audits(), 1)

    def test_completion_persists_receipt_and_refunds_undelivered_line(self):
        billing.record_worker_heartbeat()
        job = self._submit(uuid4().hex)
        claimed = billing.claim_fund_audit()
        self.assertEqual(claimed["job_id"], job["job_id"])
        receipt = {"snapshot_id": self.snapshot_id, "method_version": "test", "metrics": {}}
        record = {
            "scheme_code": self.code,
            "dossier_text": "A dated fund dossier.",
            "evidence_receipt": receipt,
        }
        self.assertTrue(billing.complete_fund_audit(claimed, record))
        self.assertFalse(billing.complete_fund_audit(claimed, record))
        status = billing.get_fund_audit_status_for_owner(job["job_id"], self.owner, include_dossier=True)
        self.assertEqual(status["status"], "COMPLETED")
        self.assertEqual(status["audit_settlement"]["credits_refunded"], 1)
        self.assertEqual(status["dossier"]["evidence_receipt"], receipt)
        self.assertEqual(get_fund_forensic_dossier(self.code)["evidence_receipt"], receipt)
        self.assertEqual(billing.unlock_published_fund_dossier(self.owner, self.code), 1)

    def test_dossier_failure_leaves_job_unsettled_for_refund(self):
        billing.record_worker_heartbeat()
        job = self._submit(uuid4().hex)
        claimed = billing.claim_fund_audit()
        self.assertEqual(claimed["job_id"], job["job_id"])
        dossier = {
            "scheme_code": self.code,
            "dossier_text": "Current research",
            "evidence_receipt": {"snapshot_id": self.snapshot_id},
        }
        with patch("core.db.mutual_funds.save_fund_forensic_dossier", return_value=False):
            with self.assertRaises(billing.FundAuditConflict):
                billing.complete_fund_audit(claimed, dossier)
        billing.fail_fund_audit(claimed, "Could not save")
        status = billing.get_fund_audit_status_for_owner(job["job_id"], self.owner)
        self.assertEqual(status["status"], "FAILED")
        self.assertEqual(status["audit_settlement"]["credits_refunded"], 2)

    def test_date_and_holdings_are_rolled_back_together(self):
        newer = {**self.scheme, "last_portfolio_date": "2025-12-31"}
        holdings = [{**self.holdings[0], "portfolio_date": "2025-12-31"}]
        with patch("core.db.mutual_funds.save_mutual_fund_holdings", return_value=False):
            with self.assertRaises(RuntimeError):
                publish_mutual_fund_disclosure(newer, holdings)
        self.assertEqual(get_current_fund_disclosure(self.code)["snapshot_id"], self.snapshot_id)
        newer_id = publish_mutual_fund_disclosure(newer, holdings)
        with self.assertRaises(ValueError):
            publish_mutual_fund_disclosure(self.scheme, self.holdings)
        self.assertEqual(get_current_fund_disclosure(self.code)["snapshot_id"], newer_id)

    def test_research_needs_current_identity_matrix_and_primary_link(self):
        matrix = "\n".join(
            f"- {key.replace('_', ' ')}: {sorted(values)[0]}" for key, values in PILLAR_LABELS.items()
        )
        now = datetime.now(IST)
        report = {
            "ticker": "RELIANCE",
            "timestamp": now.isoformat(),
            "report_text": "### Health Matrix\n" + matrix + "\n### Rationale\n" + "Evidence " * 60,
            "citations": [{"uri": "https://www.nseindia.com/filing.pdf"}],
        }
        self.assertIsNotNone(qualify_fund_research(report, "RELIANCE", analyzed_at=now))
        self.assertIsNone(qualify_fund_research(report, "INFY", analyzed_at=now))
        self.assertIsNone(qualify_fund_research({**report, "citations": []}, "RELIANCE", analyzed_at=now))

    def test_snapshot_change_refunds_unfulfilled_items(self):
        billing.record_worker_heartbeat()
        job = self._submit(uuid4().hex)
        claimed = billing.claim_fund_audit()
        self.assertEqual(claimed["job_id"], job["job_id"])
        next_scheme = {**self.scheme, "last_portfolio_date": "2025-12-31"}
        next_holdings = [{**self.holdings[0], "portfolio_date": "2025-12-31"}]
        publish_mutual_fund_disclosure(next_scheme, next_holdings)
        record = {
            "scheme_code": self.code,
            "dossier_text": "Superseded dossier",
            "evidence_receipt": {"snapshot_id": self.snapshot_id},
        }
        self.assertFalse(billing.complete_fund_audit(claimed, record))
        status = billing.get_fund_audit_status_for_owner(job["job_id"], self.owner)
        self.assertEqual(status["status"], "FAILED")
        self.assertEqual(status["audit_settlement"]["credits_refunded"], 2)

    def test_http_retry_replays_request_and_status_requires_owner(self):
        from fastapi.testclient import TestClient
        from web.main import app

        client = TestClient(app)
        request_key = uuid4().hex
        headers = {"Idempotency-Key": request_key}
        with patch.dict("os.environ", {"ENABLE_DURABLE_FUND_AUDITS": "1"}), patch(
            "web.main._get_current_web_user", return_value={"id": self.owner}
        ), patch("web.routers.markets._validate_request_origin", return_value=True):
            quote = client.get(f"/api/funds/deep-dive-quote/{self.code}")
            self.assertEqual(quote.status_code, 200, quote.text)
            payload = {
                "scheme_code": self.code,
                "allow_deep_dive": True,
                "quote_revision": quote.json()["quote_revision"],
            }
            with patch.object(billing, "time", return_value=2_100_000_000):
                rejected = client.post("/api/funds/on-demand-audit", json=payload, headers=headers)
                self.assertEqual(rejected.status_code, 503, rejected.text)
                self.assertEqual(get_user_credits_balance(self.owner), 2)
            billing.record_worker_heartbeat()
            first = client.post("/api/funds/on-demand-audit", json=payload, headers=headers)
            self.assertEqual(first.status_code, 200, first.text)
            with patch.dict("os.environ", {"ENABLE_DURABLE_FUND_AUDITS": "0"}):
                second = client.post("/api/funds/on-demand-audit", json=payload, headers=headers)
                self.assertEqual(first.json(), second.json())
                self.assertEqual(client.post(f"/api/funds/unlock/{self.code}").status_code, 503)
            job_id = first.json()["task_id"]
            self.assertEqual(client.get(f"/api/funds/audit-status/{job_id}").status_code, 200)
            my_audits = client.get(f"/api/funds/my-audits?scheme_code={self.code}")
            self.assertEqual(my_audits.status_code, 200)
            self.assertEqual([j["task_id"] for j in my_audits.json()["items"]], [job_id])
            claimed = billing.claim_fund_audit()
            self.assertEqual(claimed["job_id"], job_id)
            billing.fail_fund_audit(claimed, "Release test cleanup")
        with patch("web.main._get_current_web_user", return_value={"id": "someone-else"}):
            self.assertEqual(client.get(f"/api/funds/audit-status/{job_id}").status_code, 404)
            other_audits = client.get(f"/api/funds/my-audits?scheme_code={self.code}")
            self.assertEqual(other_audits.status_code, 200)
            self.assertEqual(other_audits.json()["items"], [])

    def test_stale_worker_heartbeat_rejects_submission_without_a_debit(self):
        request_id = uuid4().hex
        with patch.object(billing, "time", return_value=2_000_000_000):
            billing.record_worker_heartbeat()
        with patch.object(billing, "time", return_value=2_000_000_000 + billing.WORKER_HEARTBEAT_MAX_AGE):
            with self.assertRaises(billing.FundAuditUnavailable):
                self._submit(request_id)
        revision = billing.quote_revision(self.owner, self.snapshot_id, True, 1, ["RELIANCE"])
        self.assertIsNone(
            billing.get_existing_fund_audit_request(self.owner, request_id, self.code, True, revision)
        )
        self.assertEqual(get_user_credits_balance(self.owner), 2)

    def test_owner_status_refunds_unclaimed_expired_job_during_worker_outage(self):
        with patch.object(billing, "time", return_value=2_000_000_000):
            billing.record_worker_heartbeat()
            job = self._submit(uuid4().hex)
        self.assertEqual(get_user_credits_balance(self.owner), 0)
        with patch.object(billing, "time", return_value=2_000_000_000 + billing.QUEUE_TIMEOUT):
            self.assertIsNone(billing.get_fund_audit_status_for_owner(job["job_id"], "someone-else"))
            self.assertEqual(get_user_credits_balance(self.owner), 0)
            status = billing.get_fund_audit_status_for_owner(job["job_id"], self.owner)
            self.assertEqual(status["status"], "FAILED")
            self.assertEqual(status["audit_settlement"]["credits_refunded"], 2)
            self.assertEqual(billing.reconcile_expired_fund_audits(), 0)
        self.assertEqual(get_user_credits_balance(self.owner), 2)

    def test_render_cannot_accept_work_on_local_sqlite(self):
        if os.environ.get("FORCE_LOCAL_SQLITE") != "1":
            self.skipTest("This check requires the isolated SQLite test binding.")
        with patch.dict("os.environ", {"RENDER_SERVICE_ID": "test-web"}):
            with self.assertRaises(billing.FundAuditUnavailable):
                billing.record_worker_heartbeat()

    def test_sla_cap_and_foreign_or_raw_isin_exclusion(self):
        from fastapi.testclient import TestClient
        from web.main import app

        oversized_code = f"OVERSIZE_{uuid4().hex[:10].upper()}"
        oversized_scheme = {
            **self.scheme,
            "scheme_code": oversized_code,
            "scheme_name": oversized_code,
        }
        uncached_domestic = [f"ZZZDOM{i}{uuid4().hex[:4].upper()}" for i in range(6)]
        holdings = [
            {
                "holding_type": "EQUITY",
                "identifier": sym,
                "weight_pct": 12.0,
                "portfolio_date": "2025-11-30",
            }
            for sym in uncached_domestic
        ] + [
            {
                "holding_type": "FOREIGN_EQUITY",
                "identifier": "GOOGL",
                "weight_pct": 18.0,
                "portfolio_date": "2025-11-30",
            },
            {
                "holding_type": "EQUITY",
                "identifier": "INE999Z01099",
                "weight_pct": 10.0,
                "portfolio_date": "2025-11-30",
            },
        ]
        snap_id = publish_mutual_fund_disclosure(oversized_scheme, holdings)
        quote = calculate_deep_dive_credit_cost(oversized_code, holdings_override=holdings)
        self.assertEqual(quote["uncached_count"], 6)
        self.assertFalse(quote["deep_dive_available"])
        self.assertEqual(quote["excluded_foreign_count"], 1)
        self.assertEqual(quote["excluded_unresolved_isin_count"], 1)

        billing.record_worker_heartbeat()
        client = TestClient(app)
        with patch.dict("os.environ", {"ENABLE_DURABLE_FUND_AUDITS": "1"}), patch(
            "web.main._get_current_web_user", return_value={"id": self.owner}
        ), patch("web.routers.markets._validate_request_origin", return_value=True):
            q_resp = client.get(f"/api/funds/deep-dive-quote/{oversized_code}?allow_deep_dive=true")
            self.assertEqual(q_resp.status_code, 200, q_resp.text)
            self.assertFalse(q_resp.json()["deep_dive_available"])
            rejected = client.post(
                "/api/funds/on-demand-audit",
                json={
                    "scheme_code": oversized_code,
                    "allow_deep_dive": True,
                    "quote_revision": q_resp.json()["quote_revision"],
                },
                headers={"Idempotency-Key": uuid4().hex},
            )
            self.assertEqual(rejected.status_code, 422, rejected.text)
            self.assertEqual(get_user_credits_balance(self.owner), 2)

        # Forged foreign ticker in enqueue_fund_audit is also rejected fail-closed
        forged_rev = billing.quote_revision(self.owner, snap_id, True, 1, ["GOOGL"])
        with self.assertRaises(billing.FundAuditUnprocessable):
            billing.enqueue_fund_audit(
                self.owner, uuid4().hex, oversized_scheme, snap_id, True, ["GOOGL"], forged_rev
            )

    def test_settlement_operations_recorded_on_reserve_and_refund(self):
        billing.record_worker_heartbeat()
        job = self._submit(uuid4().hex)
        claimed = billing.claim_fund_audit()
        billing.fail_fund_audit(claimed, "Simulated synthesis outage")

        conn = get_db_connection()
        p = get_placeholder()
        cur = conn.cursor()
        try:
            cur.execute(
                f"""SELECT operation_type, credits_delta, line_key
                    FROM credit_settlement_operations
                    WHERE job_id = {p}
                    ORDER BY created_at,
                             CASE WHEN operation_type = 'AUDIT_RESERVE' THEN 0 ELSE 1 END,
                             COALESCE(line_key, '')""",
                (job["job_id"],),
            )
            ops = cur.fetchall()
        finally:
            cur.close()
            conn.close()

        self.assertEqual(ops[0][0], "AUDIT_RESERVE")
        self.assertEqual(float(ops[0][1]), -2.0)
        refund_ops = [r for r in ops if r[0] == "AUDIT_REFUND"]
        self.assertEqual(len(refund_ops), 2)
        self.assertTrue(all(float(r[1]) == 1.0 for r in refund_ops))
