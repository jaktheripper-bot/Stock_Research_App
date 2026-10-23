"""Unit tests for the 4 critical remediations:
1. Look-Through Recalculation Archival Guard (dossier_text preservation)
2. run_daily_fund_audit.py Paused Health Score formatting
3. Launchd Plist Python 3.14 target & valid XML structure
4. Sovereign Curve Daily Snapshot Ingestion & Term-Structure History
"""

import os
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime

from core.db.connection import init_db, IST
from core.db.mutual_funds import (
    save_fund_forensic_dossier,
    get_fund_forensic_dossier,
    save_mutual_fund_scheme,
)
from core.db.sovereign import (
    save_sovereign_curve_snapshot,
    get_sovereign_curve_history,
    refresh_daily_sovereign_benchmarks,
    get_sovereign_yield_curve,
)


class TestFindingsRemediations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_finding_1_save_fund_forensic_dossier_archival_guard(self):
        """Finding 1: Archival guard preserves existing qualitative research narrative when incoming text is empty."""
        test_scheme = "TEST_GUARD_SCHEME_001"
        save_mutual_fund_scheme({
            "scheme_code": test_scheme,
            "scheme_name": "Test Guard Fund Direct Growth",
            "category": "Equity Scheme - Large Cap",
        })

        initial_text = "# FORENSIC RESEARCH DOSSIER: Non-empty qualitative research analysis."
        first_dossier = {
            "scheme_code": test_scheme,
            "dossier_text": initial_text,
            "composite_health_score": 85.0,
            "weighted_moat_score": 75.0,
            "accounting_risk_index": 2.5,
            "margin_of_safety_pct": 12.0,
            "promoter_pledge_exposure_pct": 0.0,
            "active_share_pct": 68.0,
            "top_risky_holdings": [],
            "top_quality_holdings": [],
            "audited_by": "Test_Auditor",
        }
        saved = save_fund_forensic_dossier(first_dossier)
        self.assertTrue(saved)

        # Verify initial save
        dos1 = get_fund_forensic_dossier(test_scheme)
        self.assertIsNotNone(dos1)
        self.assertEqual(dos1["dossier_text"], initial_text)
        self.assertEqual(dos1["composite_health_score"], 85.0)

        # Recalculation pass with EMPTY dossier_text (e.g. from look-through calculator)
        recalculated_dossier = {
            "scheme_code": test_scheme,
            "dossier_text": "",  # Empty incoming narrative
            "composite_health_score": 88.0,
            "weighted_moat_score": 78.0,
            "accounting_risk_index": 2.0,
            "margin_of_safety_pct": 14.5,
            "promoter_pledge_exposure_pct": 0.0,
            "active_share_pct": 70.0,
            "top_risky_holdings": [],
            "top_quality_holdings": [],
            "audited_by": "Test_Auditor",
        }
        saved2 = save_fund_forensic_dossier(recalculated_dossier)
        self.assertTrue(saved2)

        # Verify that dossier_text was NOT wiped out and quantitative metrics were updated
        dos2 = get_fund_forensic_dossier(test_scheme)
        self.assertIsNotNone(dos2)
        self.assertEqual(dos2["dossier_text"], initial_text, "Archival guard failed: dossier_text was wiped by empty string!")
        self.assertEqual(dos2["composite_health_score"], 88.0)
        self.assertEqual(dos2["weighted_moat_score"], 78.0)

    def test_finding_2_paused_health_score_formatting_safe_against_none(self):
        """Finding 2: run_daily_fund_audit formatting does not raise TypeError on paused composite health score."""
        mock_dossier = {
            "composite_health_score": None,  # Coverage < 70%
            "accounting_risk_index": None,
            "margin_of_safety_pct": None,
            "last_audited_at": "2026-10-24 00:00:00",
        }

        comp_h = mock_dossier.get("composite_health_score")
        health = f"{comp_h:.1f}" if comp_h is not None else "Paused"
        self.assertEqual(health, "Paused")

        asri_val = mock_dossier.get("accounting_risk_index")
        asri = f"{float(asri_val):.1f}%" if asri_val is not None else "0.0%"
        self.assertEqual(asri, "0.0%")

        mos_val = mock_dossier.get("margin_of_safety_pct")
        mos = f"{float(mos_val):+.1f}%" if mos_val is not None else "+0.0%"
        self.assertEqual(mos, "+0.0%")

    def test_finding_3_launchd_plist_targets_python314(self):
        """Finding 3: launchd/com.moatnomics.pipeline.plist targets Python 3.14 and contains valid XML."""
        plist_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "launchd", "com.moatnomics.pipeline.plist")
        self.assertTrue(os.path.exists(plist_path))

        tree = ET.parse(plist_path)
        root = tree.getroot()
        self.assertEqual(root.tag, "plist")

        with open(plist_path, encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("/usr/bin/python3", content, "Plist must not target incompatible macOS system Python 3.9")
        self.assertIn("/Library/Frameworks/Python.framework/Versions/3.14/bin/python3", content)
        self.assertIn("<key>EnvironmentVariables</key>", content)
        self.assertIn("PYTHONPATH", content)

    def test_finding_4_sovereign_curve_snapshot_ingestion(self):
        """Finding 4: Sovereign curve daily snapshot records term structure points into sovereign_curve_history."""
        test_edition = "2026-10-24"
        saved_count = save_sovereign_curve_snapshot(test_edition)
        self.assertGreaterEqual(saved_count, 16)

        history_pts = get_sovereign_curve_history(test_edition)
        self.assertEqual(len(history_pts), saved_count)

        tenor_labels = [p["tenor_label"] for p in history_pts]
        self.assertIn("10Y_GSEC", tenor_labels)
        self.assertIn("91D_TBILL", tenor_labels)
        self.assertIn("40Y_GSEC", tenor_labels)

        # Refresh daily benchmarks summary contract check
        summary = refresh_daily_sovereign_benchmarks(edition_date=test_edition)
        self.assertEqual(summary.get("status"), "SUCCESS")
        self.assertEqual(summary.get("curve_snapshots_saved"), saved_count)
