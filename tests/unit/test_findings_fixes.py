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

from core.db.connection import get_db_connection, init_db, is_postgres_connection, IST
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

    @classmethod
    def tearDownClass(cls):
        conn = get_db_connection()
        p = "%s" if is_postgres_connection(conn) else "?"
        cur = conn.cursor()
        try:
            cur.execute(f"DELETE FROM fund_forensic_dossiers WHERE scheme_code = {p}", ("TEST_GUARD_SCHEME_001",))
            cur.execute(f"DELETE FROM mutual_fund_schemes WHERE scheme_code = {p}", ("TEST_GUARD_SCHEME_001",))
            conn.commit()
        finally:
            cur.close()
            conn.close()

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
        """Finding 3: Scheduled pipeline runner (macOS launchd, GitHub Actions workflow, or standalone runner)."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        plist_path = os.path.join(base_dir, "launchd", "com.moatnomics.pipeline.plist")
        gha_workflow = os.path.join(base_dir, ".github", "workflows", "scheduled_pipeline.yml")
        runner_script = os.path.join(base_dir, "scripts", "run_scheduled_pipeline.py")

        if os.path.exists(plist_path):
            tree = ET.parse(plist_path)
            root = tree.getroot()
            self.assertEqual(root.tag, "plist")

            with open(plist_path, encoding="utf-8") as f:
                content = f.read()
            self.assertNotIn("/usr/bin/python3", content, "Plist must not target incompatible macOS system Python 3.9")
            self.assertIn("/Library/Frameworks/Python.framework/Versions/3.14/bin/python3", content)
            self.assertIn("<key>EnvironmentVariables</key>", content)
            self.assertIn("PYTHONPATH", content)
        elif os.path.exists(gha_workflow):
            # Laptop launchd decommissioned in favor of autonomous cloud GitHub Actions runner
            with open(gha_workflow, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("Autonomous Multi-Asset Scheduled Pipeline", content)
            self.assertIn("scripts/run_scheduled_pipeline.py", content)
            self.assertIn("SUPABASE_DB_URL", content)
        else:
            # Container / Cloud environment where .github is gitignored and launchd is absent
            self.assertTrue(os.path.exists(runner_script), "Scheduled pipeline runner script must exist at scripts/run_scheduled_pipeline.py")
            with open(runner_script, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("run_morning_pipeline", content)
            self.assertIn("run_nightly_pipeline", content)
            self.assertIn("DAILY_LEASE_TTL_SECONDS", content)


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

    def test_ind_as_108_segment_and_order_book_extractor(self):
        """Ind AS 108 extractor enforces [VERIFIED FACT] period attribution, Pillar 01/02 scoping, word-boundary safety, and entity-match guards."""
        from core.analysis.segment_extractor import extract_ind_as_108_segments

        # 1. Short/empty input fails closed to PENDING_FILING
        short_res = extract_ind_as_108_segments("LT", "Too short")
        self.assertEqual(short_res["status"], "PENDING_FILING")
        self.assertEqual(short_res["segments"], [])
        self.assertIsNone(short_res["order_book_cr"])

        # 2. Multi-segment BSE Reg 33 / Pillar 01-02 disclosure + Lakh Cr order book + word-boundary safety ("Microelectronics" has "roe" substring)
        valid_report = (
            "# BHARAT ELECTRONICS (NSE: BEL)\n"
            "## Pillar 01: Business Model & Revenue Visibility\n"
            "[VERIFIED FACT — BEL Q4 FY26 BSE Reg 33 Segmental Filing] Operating revenue across statutory divisions:\n"
            "- **Defence Radar & Avionics**: ₹14,200 Cr (58.5%)\n"
            "- **Microelectronics & Electro-Optics**: ₹6,800 Cr (28.0%)\n"
            "- **Homeland & Smart City Systems**: ₹3,280 Cr (13.5%)\n"
            "Executable order book stood at ₹0.76 Lakh Cr at the close of Q4 FY26.\n"
            "#### What Would Change This View (Revision Triggers)\n"
            "- **Evidence That Forces a Revision:** Order book contracting below ₹25,000 Cr.\n"
            "## Pillar 03: Promoter Quality & Shareholding\n"
            "- **Government of India**: 51.1%\n"
            "- **Institutional Public**: 48.9%\n"
        ) + (" " * 120)

        res = extract_ind_as_108_segments("BEL", valid_report)
        self.assertEqual(res["status"], "DISCLOSED")
        self.assertEqual(res["filing_period"], "Q4 FY26 Statutory Filing")
        self.assertEqual(len(res["segments"]), 3)
        self.assertEqual(res["segments"][1]["segment_name"], "Microelectronics & Electro-Optics")
        self.assertEqual(res["segments"][0]["epistemic_tier"], "VERIFIED_FACT")
        self.assertAlmostEqual(res["order_book_cr"], 76000.0)

        # 3. Cross-company product tree leak fails closed to ENTITY_MISMATCH
        leaked = extract_ind_as_108_segments("INFY", valid_report, company_name="Infosys Limited")
        self.assertEqual(leaked["status"], "ENTITY_MISMATCH")
        self.assertEqual(leaked["segments"], [])
        self.assertIsNone(leaked["order_book_cr"])

        # 4. Partial / single-segment percentages & Market Share tables fail closed
        market_share_only = (
            "## Pillar 02: Competitive Positioning\n"
            "| Segment | Market Share | Competitors |\n"
            "| --- | --- | --- |\n"
            "| Utility Vehicles | 25.3% | Creta, Harrier |\n"
            "| Farm Tractors | 43.6% | TAFE, Sonalika |\n"
            "| Electric 3W | 40.0% | Bajaj |\n"
            "#### What Would Change This View (Revision Triggers)\n"
            "- Order backlog falling below INR 8,000 Cr in two consecutive quarters.\n"
        ) + ("Steady domestic execution across utility platforms. " * 8)

        ms_res = extract_ind_as_108_segments("M&M", market_share_only)
        self.assertEqual(ms_res["status"], "SINGLE_SEGMENT_OR_UNDISCLOSED")
        self.assertEqual(ms_res["segments"], [])
        self.assertIsNone(ms_res["order_book_cr"])

    def test_sequential_thesis_drift_accountability_engine(self):
        """Sequential thesis drift surfaces factual 7-pillar posture migrations, skips duplicate snapshots, and guards unadjusted price discontinuities."""
        from unittest.mock import patch
        from core.analysis.guidance_delivery_audit import compute_sequential_thesis_drift

        # 1. Single snapshot returns BASELINE_ONLY
        single_snap = [{
            "report_text": "### Health Matrix\n- Macro: Stable\n- Moat: Wide\n- Valuation: Fair\n",
            "formatted_date": "01 Oct 2026",
            "baseline_price": 1200.0,
            "revision_trigger": "Archived Baseline",
        }]
        with patch("core.analysis.guidance_delivery_audit.get_report_revisions", return_value=single_snap):
            base_res = compute_sequential_thesis_drift("tcs")
            self.assertEqual(base_res["ticker"], "TCS")
            self.assertEqual(base_res["status"], "BASELINE_ONLY")
            self.assertEqual(base_res["revision_count"], 1)
            self.assertEqual(base_res["pillar_migrations"], [])
            self.assertIsNone(base_res["price_drift_pct"])

        # 2. Multi-snapshot drift resolves distinct prior snapshot across duplicate saves & parses active revision triggers
        latest_md = (
            "### Health Matrix\n- Macro: Headwinds\n- Moat: Wide\n- Governance: Clean\n- Valuation: Fair\n\n"
            "## Pillar 1: Macro\n#### What Would Change This View (Revision Triggers)\n"
            "- **Evidence That Forces a Revision:** Constant-currency revenue growth dropping below 2% YoY for two quarters.\n"
        )
        prior_md = "### Health Matrix\n- Macro: Stable\n- Moat: Wide\n- Governance: Clean\n- Valuation: Undervalued\n"
        mock_revs = [
            {
                "report_text": latest_md,
                "formatted_date": "29 Oct 2026",
                "baseline_price": "₹1,320.00",
                "revision_trigger": "Q2 FY27 Statutory Filing",
            },
            {
                "report_text": latest_md,  # duplicate price-refresh save
                "formatted_date": "28 Oct 2026",
                "baseline_price": "₹1,310.00",
                "revision_trigger": "Price Refresh",
            },
            {
                "report_text": prior_md,
                "formatted_date": "15 Jul 2026",
                "baseline_price": "₹1,200.00",
                "revision_trigger": "Q1 FY27 Statutory Filing",
            },
        ]
        with patch("core.analysis.guidance_delivery_audit.get_report_revisions", return_value=mock_revs):
            drift_res = compute_sequential_thesis_drift("INFY")
            self.assertEqual(drift_res["status"], "DRIFT_COMPUTED")
            self.assertEqual(drift_res["revision_count"], 3)
            self.assertEqual(drift_res["prior_snapshot_date"], "15 Jul 2026")
            self.assertEqual(drift_res["latest_snapshot_date"], "29 Oct 2026")
            self.assertAlmostEqual(drift_res["price_drift_pct"], 10.0)
            migrated_pillars = {m["pillar"]: (m["prior_posture"], m["current_posture"]) for m in drift_res["pillar_migrations"]}
            self.assertEqual(migrated_pillars["Macro"], ("Stable", "Headwinds"))
            self.assertEqual(migrated_pillars["Valuation"], ("Undervalued", "Fair"))
            self.assertIn(1, drift_res["active_revision_triggers"])

        # 3. Remediation / >5x corporate discontinuity withholds misleading price_drift_pct
        discontinuity_revs = [
            {"report_text": latest_md, "formatted_date": "29 Oct 2026", "baseline_price": 3502.0, "revision_trigger": "NSE Canonical Token Remediation"},
            {"report_text": prior_md, "formatted_date": "01 Oct 2026", "baseline_price": 80.34, "revision_trigger": "Material Update"},
        ]
        with patch("core.analysis.guidance_delivery_audit.get_report_revisions", return_value=discontinuity_revs):
            disc_res = compute_sequential_thesis_drift("BSE")
            self.assertEqual(disc_res["status"], "DRIFT_COMPUTED")
            self.assertIsNone(disc_res["price_drift_pct"])

    def test_watermarked_financial_model_exporter(self):
        """Watermarked CSV and multi-tab XLSX exporters include UTF-8 BOM, SEBI disclaimer, DCF matrix, IMPLIED_GROWTH_ONLY guard, and formula sanitization."""
        import io
        import zipfile
        from core.analysis.equity_dossier import compile_equity_dossier
        from core.reporting.xlsx_exporter import (
            build_equity_model_csv_bundle,
            build_equity_model_xlsx_workbook,
        )

        fund = {
            "current_price": 1450.0,
            "pe_ratio": 22.5,
            "roce": 38.0,
            "roe": 31.0,
            "debt_to_equity": 0.05,
            "operating_margin": 24.0,
            "sector": "Information Technology",
        }
        intel = compile_equity_dossier("INFY", fund)
        csv_bytes = build_equity_model_csv_bundle("INFY", fund, intel, account_ref="=INJECT_TEST")
        self.assertTrue(csv_bytes.startswith(b"\xef\xbb\xbf"))
        csv_text = csv_bytes.decode("utf-8-sig")
        self.assertIn("MOATNOMICS QUANTITATIVE RESEARCH MODEL,INFY", csv_text)
        self.assertIn("'=INJECT_TEST", csv_text)
        self.assertIn("SECTION 2: WACC vs. STAGE-1 GROWTH DCF SENSITIVITY MATRIX", csv_text)
        self.assertIn("40% DCF / 35% Median PE / 25% EPV", csv_text)

        # Extreme-multiple IMPLIED_GROWTH_ONLY suppresses unnormalized EPS in DCF sensitivity cells
        vedl_fund = {"current_price": 450.0, "pe_ratio": 2.22, "sector": "Metals & Mining"}
        vedl_intel = compile_equity_dossier("VEDL", vedl_fund)
        vedl_csv = build_equity_model_csv_bundle("VEDL", vedl_fund, vedl_intel, account_ref="ACCT_99").decode("utf-8-sig")
        self.assertIn("Implied-Growth Regime", vedl_csv)
        self.assertIn("11.0%,N/A,N/A,N/A,N/A,N/A", vedl_csv)

        # Multi-tab OOXML (.xlsx) archive structure check
        xlsx_bytes = build_equity_model_xlsx_workbook("INFY", fund, intel, account_ref="ACCT_PRO_01")
        with zipfile.ZipFile(io.BytesIO(xlsx_bytes), "r") as zf:
            names = set(zf.namelist())
            self.assertIn("xl/workbook.xml", names)
            self.assertIn("xl/worksheets/sheet1.xml", names)
            self.assertIn("xl/worksheets/sheet2.xml", names)
            self.assertIn("xl/worksheets/sheet3.xml", names)
            self.assertIn("ACCT_PRO_01", zf.read("xl/worksheets/sheet1.xml").decode("utf-8"))

    def test_live_security_tax_bridge_across_hni_surcharge_tiers(self):
        """Live security tax bridge evaluates real NCD ISINs, Sec 115UA REITs/InvITs, and Sec 47(viic) SGBs across HNI surcharge slabs."""
        from core.analysis.live_security_tax_bridge import (
            HNI_EFFECTIVE_SLABS,
            compare_live_tracked_yield_instruments,
        )

        self.assertEqual(HNI_EFFECTIVE_SLABS["UHNI_ABOVE_2CR"], 39.00)
        base_rows = compare_live_tracked_yield_instruments(slab_key="SLAB_30_BASE", cpi_inflation_pct=5.0, limit_per_class=3)
        uhni_rows = compare_live_tracked_yield_instruments(slab_key="UHNI_ABOVE_2CR", cpi_inflation_pct=5.0, limit_per_class=3)

        self.assertGreaterEqual(len(base_rows), 6)
        classes = {r["asset_class"] for r in base_rows}
        self.assertIn("CORPORATE_DEBT", classes)
        self.assertIn("REIT_INVIT", classes)
        self.assertIn("SGB", classes)

        # Sorted descending by net_real_return_pct
        reals = [r["net_real_return_pct"] for r in base_rows]
        self.assertEqual(reals, sorted(reals, reverse=True))

        # Higher UHNI 39% surcharge slab must strictly increase tax drag vs 31.20% base slab on taxable NCDs
        base_ncd = next(r for r in base_rows if r["asset_class"] == "CORPORATE_DEBT")
        uhni_ncd = next(r for r in uhni_rows if r["identifier"] == base_ncd["identifier"])
        self.assertGreater(uhni_ncd["tax_drag_pct"], base_ncd["tax_drag_pct"])
        self.assertLess(uhni_ncd["net_real_return_pct"], base_ncd["net_real_return_pct"])

    def test_structural_safety_radar_archetypes_persistence(self):
        """Structural RBI/SEBI safety-radar archetypes persist counterparty_risk, bankruptcy_reality, and audit_matrix."""
        from scripts.expand_safety_radar_registry import NEW_STRUCTURAL_ARCHETYPES, run as expand_safety_radar
        from core.analysis.retail_safety_radar import audit_alternative_yield_radar

        expand_safety_radar(apply=True)
        radar = audit_alternative_yield_radar()
        by_id = {p["product_id"]: p for p in radar["all_products"]}
        for item in NEW_STRUCTURAL_ARCHETYPES:
            self.assertIn(item["product_id"], by_id)
            saved = by_id[item["product_id"]]
            self.assertTrue(saved["precedent_losses_summary"], f"Empty summary for {item['product_id']}")
            self.assertIn("Bankruptcy reality:", saved["precedent_losses_summary"])
            self.assertTrue(saved["rbi_warning_circular"])
            self.assertIsInstance(saved["audit_matrix"], dict)
