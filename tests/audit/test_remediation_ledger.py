"""
Unit & Integration Test Suite for Stateful Remediation Ledger & Closed-Loop Auditing Cycle.

Verifies:
1. Deterministic hashing via compute_finding_hash.
2. Database lifecycle transitions (OPEN -> RE_EVALUATING -> RESOLVED).
3. Verification attempt counters and consecutive failure tracking.
4. Progressive aging multipliers (1.0x for <3d, 1.5x for >=3d, 2.0x for >=7d).
5. Generation and disk persistence of audits/REMEDIATION_ACTION_PLAN.md.
6. Closed-loop execution cycle (Verify First -> Explore Next -> Publish Score & Report).
"""

import os
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

os.environ["TESTING"] = "1"
os.environ["ENVIRONMENT"] = "testing"

from core.db.connection import init_db, get_db_connection, is_postgres_connection
from core.db.remediation import (
    compute_finding_hash,
    record_or_update_finding,
    get_open_remediation_findings,
    mark_finding_re_evaluating,
    mark_finding_resolved,
    get_all_remediation_findings,
    get_remediation_summary_stats,
    _clean_remediation_row,
)
from core.audit.invariants import (
    verify_invariant,
    scan_database_schema_bounds,
)
from core.audit.remediation_plan import (
    generate_remediation_action_plan,
    write_remediation_action_plan,
    ACTION_PLAN_PATH,
)
from core.audit.project_auditor import execute_closed_loop_remediation_cycle


class TestStatefulRemediationLedger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        # Clear remediation ledger for testing isolation
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM audit_remediation_ledger;")
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def test_compute_finding_hash_deterministic(self):
        """Invariant: Identical (category, invariant_name, target) produces identical SHA256."""
        h1 = compute_finding_hash("BACKEND_STABILITY", "INV_UNBOUNDED_CACHE", "core/db/test.py:10")
        h2 = compute_finding_hash("BACKEND_STABILITY", "INV_UNBOUNDED_CACHE", "core/db/test.py:10")
        h3 = compute_finding_hash("DATABASE_PARITY", "INV_SQL_DIALECT_COMPAT", "core/db/test.py:10")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)
        self.assertEqual(len(h1), 32)

    def test_record_and_update_finding_lifecycle(self):
        """Lifecycle: New finding inserted as OPEN, subsequent updates increment attempts and failures."""
        finding = {
            "category": "BACKEND_STABILITY",
            "invariant_name": "INV_UNBOUNDED_CACHE",
            "target_file_or_route": "core/test_cache.py:42",
            "title": "Unbounded Test Cache",
            "description": "Cache lacks maxsize eviction bounds.",
            "severity": "HIGH",
            "remediation_notes": "Add OrderedDict LRU cap.",
            "metadata": {"test_key": "val"}
        }

        # 1. First Detection -> OPEN, attempts=1, failures=1
        rec1 = record_or_update_finding(finding)
        self.assertTrue(rec1)
        self.assertEqual(rec1["status"], "OPEN")
        self.assertEqual(rec1["verification_attempts"], 1)
        self.assertEqual(rec1["consecutive_failures"], 1)
        self.assertEqual(rec1["base_deduction"], 8.0)
        self.assertEqual(rec1["aging_multiplier"], 1.0)
        self.assertEqual(rec1["effective_penalty"], 8.0)

        # 2. Second Execution (Failed pass) -> attempts=2, failures=2
        rec2 = record_or_update_finding(finding)
        self.assertEqual(rec2["verification_attempts"], 2)
        self.assertEqual(rec2["consecutive_failures"], 2)

        # 3. Transition to RE_EVALUATING
        h = rec1["finding_hash"]
        success_eval = mark_finding_re_evaluating(h)
        self.assertTrue(success_eval)
        open_items = get_open_remediation_findings()
        re_eval_item = next((i for i in open_items if i["finding_hash"] == h), None)
        self.assertIsNotNone(re_eval_item)
        self.assertEqual(re_eval_item["status"], "RE_EVALUATING")

        # 4. Transition to RESOLVED
        success_res = mark_finding_resolved(h, notes="Fixed cache with OrderedDict maxsize 500.")
        self.assertTrue(success_res)

        # Should no longer be in open items
        open_after = get_open_remediation_findings()
        self.assertFalse(any(i["finding_hash"] == h for i in open_after))

        # Should be in all findings as RESOLVED with consecutive_failures reset to 0
        all_items = get_all_remediation_findings()
        resolved_item = next((i for i in all_items if i["finding_hash"] == h), None)
        self.assertIsNotNone(resolved_item)
        self.assertEqual(resolved_item["status"], "RESOLVED")
        self.assertEqual(resolved_item["consecutive_failures"], 0)
        self.assertIsNotNone(resolved_item["resolved_at"])

    def test_progressive_aging_multipliers(self):
        """Invariant: <3d = 1.0x, >=3d = 1.5x, >=7d = 2.0x."""
        conn = get_db_connection()
        cur = conn.cursor()
        use_pg = is_postgres_connection(conn)
        try:
            # Insert item simulated from 4 days ago in IST
            from core.db.connection import IST
            now_ist = datetime.now(IST)
            four_days_ago = (now_ist - timedelta(days=4, hours=2)).strftime("%Y-%m-%d %H:%M:%S+05:30")
            h_4d = compute_finding_hash("BACKEND_STABILITY", "INV_TEST", "aging_4d")

            if use_pg:
                cur.execute("""
                    INSERT INTO audit_remediation_ledger (
                        finding_hash, category, invariant_name, title, description,
                        target_file_or_route, severity, status, verification_attempts,
                        consecutive_failures, first_detected_at, last_verified_at
                    ) VALUES (%s, 'BACKEND_STABILITY', 'INV_TEST', 'Aging 4d', 'Desc', 'target', 'HIGH', 'OPEN', 4, 4, %s, now());
                """, (h_4d, four_days_ago))
            else:
                cur.execute("""
                    INSERT INTO audit_remediation_ledger (
                        finding_hash, category, invariant_name, title, description,
                        target_file_or_route, severity, status, verification_attempts,
                        consecutive_failures, first_detected_at, last_verified_at
                    ) VALUES (?, 'BACKEND_STABILITY', 'INV_TEST', 'Aging 4d', 'Desc', 'target', 'HIGH', 'OPEN', 4, 4, ?, (datetime('now', '+5 hours', '+30 minutes') || '+05:30'));
                """, (h_4d, four_days_ago))

            # Insert item simulated from 8 days ago in IST
            eight_days_ago = (now_ist - timedelta(days=8, hours=1)).strftime("%Y-%m-%d %H:%M:%S+05:30")
            h_8d = compute_finding_hash("SECURITY_VULNERABILITY", "INV_SEC", "aging_8d")
            if use_pg:
                cur.execute("""
                    INSERT INTO audit_remediation_ledger (
                        finding_hash, category, invariant_name, title, description,
                        target_file_or_route, severity, status, verification_attempts,
                        consecutive_failures, first_detected_at, last_verified_at
                    ) VALUES (%s, 'SECURITY_VULNERABILITY', 'INV_SEC', 'Aging 8d', 'Desc', 'target', 'CRITICAL', 'OPEN', 8, 8, %s, now());
                """, (h_8d, eight_days_ago))
            else:
                cur.execute("""
                    INSERT INTO audit_remediation_ledger (
                        finding_hash, category, invariant_name, title, description,
                        target_file_or_route, severity, status, verification_attempts,
                        consecutive_failures, first_detected_at, last_verified_at
                    ) VALUES (?, 'SECURITY_VULNERABILITY', 'INV_SEC', 'Aging 8d', 'Desc', 'target', 'CRITICAL', 'OPEN', 8, 8, ?, (datetime('now', '+5 hours', '+30 minutes') || '+05:30'));
                """, (h_8d, eight_days_ago))

            conn.commit()
        finally:
            cur.close()
            conn.close()

        open_findings = get_open_remediation_findings()
        f_4d = next(f for f in open_findings if f["finding_hash"] == h_4d)
        f_8d = next(f for f in open_findings if f["finding_hash"] == h_8d)

        # Verify 4-day aging: 1.5x multiplier on HIGH (8.0 pts) -> 12.0 pts
        self.assertGreaterEqual(f_4d["age_in_days"], 4.0)
        self.assertEqual(f_4d["aging_multiplier"], 1.5)
        self.assertEqual(f_4d["effective_penalty"], 12.0)

        # Verify 8-day aging: 2.0x multiplier on CRITICAL (15.0 pts) -> 30.0 pts
        self.assertGreaterEqual(f_8d["age_in_days"], 8.0)
        self.assertEqual(f_8d["aging_multiplier"], 2.0)
        self.assertEqual(f_8d["effective_penalty"], 30.0)

        # Summary stats check
        stats = get_remediation_summary_stats()
        self.assertEqual(stats["total_open"], 2)
        self.assertEqual(stats["critical_open"], 1)
        self.assertEqual(stats["high_open"], 1)
        self.assertEqual(stats["aging_over_3d"], 2)
        self.assertEqual(stats["aging_over_7d"], 1)
        self.assertEqual(stats["total_penalty"], 42.0)

    def test_remediation_action_plan_generation(self):
        """Verifies audits/REMEDIATION_ACTION_PLAN.md generation with all mandatory sections."""
        open_findings = [
            {
                "finding_hash": "a1b2c3d4e5f67890",
                "category": "BACKEND_STABILITY",
                "invariant_name": "INV_UNBOUNDED_CACHE",
                "title": "Unbounded module-level cache in core/test.py",
                "description": "Cache lacks maxsize eviction.",
                "target_file_or_route": "core/test.py:15",
                "severity": "HIGH",
                "age_in_days": 3.5,
                "verification_attempts": 3,
                "consecutive_failures": 3,
                "base_deduction": 8.0,
                "aging_multiplier": 1.5,
                "effective_penalty": 12.0,
                "remediation_notes": "Wrap with OrderedDict LRU eviction."
            }
        ]
        summary_stats = {
            "total_open": 1,
            "critical_open": 0,
            "high_open": 1,
            "medium_open": 0,
            "low_open": 0,
            "aging_over_3d": 1,
            "aging_over_7d": 0,
            "resolved_total": 5,
            "total_penalty": 12.0
        }
        resolved = [
            {
                "finding_hash": "f0e1d2c3b4a5",
                "invariant_name": "INV_SQL_DIALECT_COMPAT",
                "target_file_or_route": "core/db/digest.py:45",
                "notes": "Dialect branched via is_postgres_connection."
            }
        ]

        plan_md = generate_remediation_action_plan(
            audit_id="AUD-TEST-001",
            composite_score=88.0,
            open_findings=open_findings,
            summary_stats=summary_stats,
            resolved_in_cycle=resolved
        )

        self.assertIn("# System Remediation Action Plan", plan_md)
        self.assertIn("Executive Triage Scorecard", plan_md)
        self.assertIn("Aging Technical Debt & Compounding Penalty Alerts", plan_md)
        self.assertIn("Prioritized Active Remediation Queue", plan_md)
        self.assertIn("Closed-Loop Verification Log & Recent Resolutions", plan_md)
        self.assertIn("INV_UNBOUNDED_CACHE", plan_md)
        self.assertIn("core/test.py:15", plan_md)
        self.assertIn("INV_SQL_DIALECT_COMPAT", plan_md)

        # Write to disk and check file exists
        out_path = write_remediation_action_plan(
            audit_id="AUD-TEST-001",
            composite_score=88.0,
            open_findings=open_findings,
            summary_stats=summary_stats,
            resolved_in_cycle=resolved
        )
        self.assertTrue(out_path.exists())
        self.assertTrue(len(out_path.read_text(encoding="utf-8")) > 500)

    def test_closed_loop_remediation_cycle_execution(self):
        """Verifies Step 1 (Verify First) and Step 2 (Explore Next) execution cycle."""
        # Seed an item that is ALREADY FIXED (so Verify First marks it RESOLVED)
        h_fixed = compute_finding_hash("DATABASE_PARITY", "INV_DB_SCHEMA_BOUNDS", "sovereign_macro_rates:period_label:test")
        record_or_update_finding({
            "category": "DATABASE_PARITY",
            "invariant_name": "INV_DB_SCHEMA_BOUNDS",
            "target_file_or_route": "core/db/sovereign.py",
            "title": "Period label length",
            "description": "Exceeds bounds",
            "severity": "HIGH",
            "finding_hash": h_fixed
        })

        active_open, stats, resolved_in_cycle = execute_closed_loop_remediation_cycle()

        # Step 1 should have verified the schema bounds (which pass) and resolved the finding!
        self.assertTrue(any(r["finding_hash"] == h_fixed for r in resolved_in_cycle))
        self.assertFalse(any(o["finding_hash"] == h_fixed for o in active_open))


if __name__ == "__main__":
    unittest.main()
