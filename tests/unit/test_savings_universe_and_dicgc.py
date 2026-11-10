"""Unit & domain-invariant verification suite for the 8th Asset Class:
Fixed Savings, Term Deposits, Statutory Small Savings & Retirement Universe (`/savings`).

Verifies:
- Schema v049 & v050 (`savings_instruments`, `savings_rate_observations`, `tax_rule_registry`)
- Rate provenance immutability (`effective_from` preserved when `base_rate_pct` unchanged)
- Dynamic benchmark cascade (`SAV-NSC` -> `SAV-FRSB-2020` +35 bps)
- Automated inbox bulletin ingestion & staleness badge computation
- Finance Act 2025 dual-regime (`NEW_115BAC` vs `OLD_REGIME`) tax waterfall, Sec 87A ₹12L rebate,
  Sec 80TTA / 80TTB bank-vs-NBFC boundary, NSC Yr 1-4 reinvestment, EPF ₹2.5L split, NPS 60/40 exit,
  and Sec 194A TDS thresholds
- Exact DICGC Act Sec 16(1) ₹5,00,000 principal + accrued-interest solver & multi-charter deduplication
- FD <-> Listed Senior NCD <-> Equity contagion bridge (`ISSUER_DEBT_TICKER_ALIASES`, AT1/Tier-2 exclusion,
  BFSI metric hygiene, and <= 72/100 Corporate FD safety ceiling)
- Pure Sec 112A Arbitrage MF vs Arbitrage FoF guard & zero fabricated MF return fallbacks
- Cross-surface macro CPI & 10Y G-Sec anchor parity + Fisher real-return deflation
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core.db.connection as db_conn
import core.db.savings as savings_db
from core.analysis import net_real_tax_calculator, opportunity_terminal
from core.analysis.savings_engine import (
    CORPORATE_FD_SAFETY_CAP,
    DICGC_STATUTORY_LIMIT_INR,
    compute_dicgc_safe_ladder,
    compute_dicgc_safe_principal,
    compute_fisher_real_yield_pct,
    evaluate_fd_issuer_contagion_bridge,
    evaluate_savings_post_tax,
    get_cash_park_sleeve,
    get_enriched_savings_directory,
    get_savings_instrument_dossier,
    is_pure_sec_112a_arbitrage_fund,
    resolve_effective_tax_parameters,
)
from core.cortex.setu import SetuMatrixEngine
from core.db.connection import get_db_connection, init_db
from core.db.debt import save_debt_security
from core.db.savings import (
    SAVINGS_CATEGORIES,
    compute_staleness_badge,
    get_active_savings_instruments,
    get_active_tax_rule_version,
    get_savings_instrument_by_id,
    get_savings_rate_history,
    seed_baseline_savings_universe,
    upsert_savings_instrument,
    verify_and_sync_automated_savings_rates,
)
from core.db.sovereign import get_live_macro_anchors, refresh_daily_sovereign_benchmarks


class TestSavingsUniverseAndDicgc(unittest.TestCase):
    """Isolated SQLite sandbox test suite covering all savings, tax, DICGC, and contagion contracts."""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp_dir.name, "test_savings_v049.db")
        self._env_patcher = patch.dict(
            os.environ,
            {
                "TESTING": "1",
                "FORCE_LOCAL_SQLITE": "1",
                "SUPABASE_DB_URL": "",
                "TEST_DB_PATH": self.db_path,
            },
        )
        self._env_patcher.start()
        db_conn._DB_INITIALIZED = False
        db_conn._INITIALIZED_DBS.clear()
        init_db(force=True)
        self.seed_res = seed_baseline_savings_universe()

    def tearDown(self) -> None:
        db_conn._DB_INITIALIZED = False
        db_conn._INITIALIZED_DBS.clear()
        self._env_patcher.stop()
        self._tmp_dir.cleanup()

    def test_v049_baseline_seed_and_seven_categories(self) -> None:
        self.assertEqual(self.seed_res["status"], "SUCCESS")
        self.assertGreaterEqual(self.seed_res["total_processed"], 30)

        active = get_active_savings_instruments()
        self.assertGreaterEqual(len(active), 30)
        present_cats = {row["category"] for row in active}
        for expected_cat in SAVINGS_CATEGORIES:
            self.assertIn(expected_cat, present_cats, f"Missing category {expected_cat}")

        tax_ver = get_active_tax_rule_version()
        self.assertEqual(tax_ver["rule_version"], "FY2025_26_FA2025")
        self.assertEqual(tax_ver["rules"]["default_regime"], "NEW_115BAC")

    def test_upsert_preserves_effective_from_and_cascades_nsc_to_frsb(self) -> None:
        ppf_before = get_savings_instrument_by_id("SAV-PPF")
        self.assertIsNotNone(ppf_before)
        orig_eff = ppf_before["effective_from"]

        # Attempt re-upsert with identical rate (7.10%) and identical terms on an active date (<= today)
        attempt = dict(ppf_before)
        attempt["effective_from"] = "2026-11-05"
        res_same = upsert_savings_instrument(attempt)
        self.assertEqual(res_same["status"], "METADATA_SYNCED")
        self.assertFalse(res_same["rate_changed"])
        self.assertEqual(res_same["effective_from"], orig_eff)

        ppf_after = get_savings_instrument_by_id("SAV-PPF")
        self.assertEqual(ppf_after["effective_from"], orig_eff)
        self.assertEqual(len(get_savings_rate_history("SAV-PPF")), 1)

        # Now update SAV-NSC from 7.70% -> 7.90% on an active date (2026-11-01) and verify SAV-FRSB-2020 (+35 bps) cascades to 8.25%
        nsc = get_savings_instrument_by_id("SAV-NSC")
        self.assertAlmostEqual(nsc["base_rate_pct"], 7.70, places=2)
        nsc_update = dict(nsc)
        nsc_update["base_rate_pct"] = 7.90
        nsc_update["effective_from"] = "2026-11-01"
        res_nsc = upsert_savings_instrument(nsc_update)
        self.assertEqual(res_nsc["status"], "RATE_UPDATED")
        self.assertTrue(res_nsc["rate_changed"])

        nsc_hist = get_savings_rate_history("SAV-NSC")
        self.assertGreaterEqual(len(nsc_hist), 2)
        self.assertAlmostEqual(nsc_hist[0]["base_rate_pct"], 7.90, places=2)
        self.assertIsNone(nsc_hist[0]["effective_to"])
        self.assertEqual(nsc_hist[1]["effective_to"], "2026-11-01")

        frsb = get_savings_instrument_by_id("SAV-FRSB-2020")
        self.assertAlmostEqual(frsb["base_rate_pct"], 8.25, places=2)
        self.assertEqual(frsb["effective_from"], "2026-11-01")

    def test_automated_inbox_sync_and_staleness_badges(self) -> None:
        tmp_inbox = Path(self._tmp_dir.name) / "inbox"
        tmp_inbox.mkdir(parents=True, exist_ok=True)
        bulletin_path = tmp_inbox / "sbi_rate_revision.json"
        bulletin_path.write_text(
            json.dumps(
                {
                    "instruments": [
                        {
                            "instrument_id": "FD-SBI-444D",
                            "base_rate_pct": 7.40,
                            "effective_from": "2026-11-05",
                            "source_authority": "State Bank of India Retail Term Deposit Tariff",
                            "source_url": "https://sbi.co.in/web/interest-rates/deposit-rates/retail-domestic-term-deposits",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        with patch.object(savings_db, "SAVINGS_INBOX_DIR", tmp_inbox):
            sync_res = verify_and_sync_automated_savings_rates(
                edition_date="2026-11-09",
                allow_network=False,
            )
        self.assertEqual(sync_res["status"], "SUCCESS")
        self.assertEqual(sync_res["inbox_files_processed"], 1)
        self.assertEqual(sync_res["inbox_rate_updates"], 1)
        self.assertFalse(bulletin_path.exists())
        self.assertTrue((tmp_inbox / "processed" / "2026-11-09_sbi_rate_revision.json").exists())

        sbi = get_savings_instrument_by_id("FD-SBI-444D")
        self.assertAlmostEqual(sbi["base_rate_pct"], 7.40, places=2)
        self.assertEqual(sbi["effective_from"], "2026-11-05")

        # Staleness badges: fresh vs >45d review due vs overdue next_review_date
        fresh_badge = compute_staleness_badge(sbi, reference_date="2026-11-15")
        self.assertEqual(fresh_badge["status"], "FRESH")

        due_badge = compute_staleness_badge(sbi, reference_date="2027-01-10")
        self.assertEqual(due_badge["status"], "REVIEW_DUE")
        self.assertTrue(due_badge["review_overdue"])

        stale_badge = compute_staleness_badge(sbi, reference_date="2027-04-20")
        self.assertEqual(stale_badge["status"], "STALE_TARIFF")

        ppf = get_savings_instrument_by_id("SAV-PPF")
        overdue_stat = compute_staleness_badge(ppf, reference_date="2027-01-15")
        self.assertEqual(overdue_stat["status"], "REVIEW_DUE")

    def test_finance_act_2025_dual_regime_tax_waterfall_and_tds(self) -> None:
        # 1. Surcharge caps: New Regime caps slab surcharge at 25% vs Old Regime 37%; CG 111A/112A capped at 15%
        p_new = resolve_effective_tax_parameters("NEW_115BAC", slab_rate_pct=30.0, surcharge_rate_pct=37.0)
        p_old = resolve_effective_tax_parameters("OLD_REGIME", slab_rate_pct=30.0, surcharge_rate_pct=37.0)
        self.assertEqual(p_new["surcharge_slab_pct"], 25.0)
        self.assertEqual(p_old["surcharge_slab_pct"], 37.0)
        self.assertEqual(p_new["surcharge_cg_111a_112a_pct"], 15.0)
        self.assertAlmostEqual(p_new["effective_slab_rate_pct"], 39.0, places=2)  # 30 * 1.25 * 1.04
        self.assertAlmostEqual(p_old["effective_slab_rate_pct"], 42.744, places=3)  # 30 * 1.37 * 1.04

        # 2. Sec 87A ₹12L income rebate under New Regime -> 0% effective slab
        p_rebate = resolve_effective_tax_parameters(
            "NEW_115BAC",
            slab_rate_pct=15.0,
            annual_taxable_income_inr=1200000.0,
        )
        self.assertTrue(p_rebate["sec_87a_rebate_applied"])
        self.assertEqual(p_rebate["effective_slab_rate_pct"], 0.0)

        # 3. PPF & SSY are EEE exempt across both regimes
        ppf = get_savings_instrument_by_id("SAV-PPF")
        ev_ppf = evaluate_savings_post_tax(ppf, tax_regime="NEW_115BAC", slab_rate_pct=30.0)
        self.assertEqual(ev_ppf["effective_tax_rate_pct"], 0.0)
        self.assertEqual(ev_ppf["post_tax_yield_pct"], ev_ppf["gross_apy_pct"])

        # 4. EPF ₹2.5L Sec 10(12) Proviso split
        epf = get_savings_instrument_by_id("SAV-EPF-VPF")
        ev_epf_below = evaluate_savings_post_tax(
            epf, tax_regime="NEW_115BAC", slab_rate_pct=30.0, annual_contribution_inr=200000.0
        )
        ev_epf_above = evaluate_savings_post_tax(
            epf, tax_regime="NEW_115BAC", slab_rate_pct=30.0, annual_contribution_inr=500000.0
        )
        self.assertEqual(ev_epf_below["effective_tax_rate_pct"], 0.0)
        self.assertGreater(ev_epf_above["effective_tax_rate_pct"], 10.0)
        self.assertLess(ev_epf_above["post_tax_yield_pct"], ev_epf_below["post_tax_yield_pct"])

        # 5. NSC: Old Regime shields Years 1-4 via Sec 80C reinvestment, taxing only Year 5
        nsc = get_savings_instrument_by_id("SAV-NSC")
        ev_nsc_new = evaluate_savings_post_tax(nsc, tax_regime="NEW_115BAC", slab_rate_pct=30.0)
        ev_nsc_old = evaluate_savings_post_tax(nsc, tax_regime="OLD_REGIME", slab_rate_pct=30.0)
        self.assertGreater(ev_nsc_old["post_tax_yield_pct"], ev_nsc_new["post_tax_yield_pct"] + 1.5)

        # 6. Sec 80TTB ₹50k Senior Shield: applies to Bank FD in Old Regime, NOT in New Regime, NEVER on NBFC Corporate FD
        sbi_fd = get_savings_instrument_by_id("FD-SBI-444D")
        bajaj_fd = get_savings_instrument_by_id("FD-BAJAJ-42M")
        ev_sbi_sr_old = evaluate_savings_post_tax(
            sbi_fd, tax_regime="OLD_REGIME", slab_rate_pct=30.0, is_senior=True, principal_inr=500000.0
        )
        ev_sbi_sr_new = evaluate_savings_post_tax(
            sbi_fd, tax_regime="NEW_115BAC", slab_rate_pct=30.0, is_senior=True, principal_inr=500000.0
        )
        ev_bajaj_sr_old = evaluate_savings_post_tax(
            bajaj_fd, tax_regime="OLD_REGIME", slab_rate_pct=30.0, is_senior=True, principal_inr=500000.0
        )
        self.assertEqual(ev_sbi_sr_old["effective_tax_rate_pct"], 0.0)  # ₹39k interest <= ₹50k 80TTB shield
        self.assertGreater(ev_sbi_sr_new["effective_tax_rate_pct"], 30.0)
        self.assertGreater(ev_bajaj_sr_old["effective_tax_rate_pct"], 30.0)  # Corporate FD gets ZERO 80TTB

        # 7. Sec 80TTA ₹10k Savings Account Shield (Old Regime non-senior HYSA only, not FD)
        hysa = get_savings_instrument_by_id("HYSA-IDFCFIRST")
        ev_hysa_old = evaluate_savings_post_tax(
            hysa, tax_regime="OLD_REGIME", slab_rate_pct=30.0, is_senior=False, principal_inr=100000.0
        )
        self.assertEqual(ev_hysa_old["effective_tax_rate_pct"], 0.0)

        # 8. Sec 194A TDS thresholds: ₹10k NBFC triggers on ₹5L principal, while ₹1L Senior Bank FD threshold does not
        self.assertFalse(ev_sbi_sr_new["tds_triggered_on_principal"])
        self.assertEqual(ev_sbi_sr_new["tds_threshold_inr"], 100000.0)
        self.assertTrue(ev_bajaj_sr_old["tds_triggered_on_principal"])
        self.assertLessEqual(ev_bajaj_sr_old["tds_threshold_inr"], 10000.0)

        # 9. NPS Tier-I 60/40 normal exit & 20/80 premature exit note
        nps = get_savings_instrument_by_id("SAV-NPS-TIER1")
        ev_nps = evaluate_savings_post_tax(nps, tax_regime="NEW_115BAC", slab_rate_pct=30.0)
        self.assertIn("premature exit before age 60 requires 80% annuity", ev_nps["tax_statute_note"])
        self.assertLess(ev_nps["effective_tax_rate_pct"], 15.0)  # 40% * 31.2% = 12.48%

    def test_dicgc_safe_principal_and_multi_charter_ladder_invariants(self) -> None:
        # Cumulative 36M @ 8.25% quarterly compounding: P * (1 + 0.0825/4)^12 <= 500,000
        cum = compute_dicgc_safe_principal(
            annual_rate_pct=8.25,
            tenure_months=36,
            compounding_freq="QUARTERLY",
            payout_mode="CUMULATIVE",
        )
        self.assertLess(cum["safe_principal_inr"], 400000.0)
        self.assertLessEqual(cum["maturity_or_peak_value_inr"], DICGC_STATUTORY_LIMIT_INR)
        self.assertEqual(cum["uninsured_exposure_inr"], 0.0)

        # Quarterly payout mode keeps accrued interest limited to 1 quarter, allowing ~₹4.89L principal
        qpay = compute_dicgc_safe_principal(
            annual_rate_pct=8.25,
            tenure_months=36,
            compounding_freq="QUARTERLY",
            payout_mode="QUARTERLY_PAYOUT",
        )
        self.assertGreater(qpay["safe_principal_inr"], 485000.0)
        self.assertLessEqual(qpay["peak_insured_balance_inr"], DICGC_STATUTORY_LIMIT_INR)
        self.assertEqual(qpay["uninsured_exposure_inr"], 0.0)

        # Multi-bank charter ladder on ₹25L and ₹1.20Cr:
        # - Strictly 1 tranche per RBI bank_charter_key (no double-counting FD + HYSA on same charter)
        # - Excess corpus routed to SOVEREIGN_OVERFLOW
        # - Zero uninsured credit exposure
        for corpus, senior_flag in ((2500000.0, False), (12000000.0, True)):
            ladder = compute_dicgc_safe_ladder(
                corpus_inr=corpus,
                tenure_months=36,
                payout_mode="CUMULATIVE",
                is_senior=senior_flag,
                include_sfb=True,
            )
            self.assertEqual(ladder["total_uninsured_credit_exposure_inr"], 0.0)
            allocated_sum = sum(t["principal_allocated_inr"] for t in ladder["tranches"])
            self.assertAlmostEqual(allocated_sum, corpus, places=1)

            bank_tranches = [
                t for t in ladder["tranches"] if t["tranche_type"] == "DICGC_INSURED_BANK_CHARTER"
            ]
            charter_keys = [t["bank_charter_key"] for t in bank_tranches]
            self.assertEqual(len(charter_keys), len(set(charter_keys)), "Duplicate bank charter allocated!")
            for bt in bank_tranches:
                self.assertLessEqual(bt["peak_balance_under_dicgc_inr"], DICGC_STATUTORY_LIMIT_INR)
                self.assertEqual(bt["uninsured_exposure_inr"], 0.0)

            if corpus > 6000000.0:
                self.assertGreater(ladder["sovereign_overflow_inr"], 0.0)
                sov_ids = {
                    t["instrument_id"]
                    for t in ladder["tranches"]
                    if t["tranche_type"] == "SOVEREIGN_OVERFLOW"
                }
                self.assertIn("GOI_GSEC_LADDER", sov_ids)

        # At 60M QUARTERLY_PAYOUT for a senior citizen, overflow allocates SAV-SCSS first
        ladder_60_sr = compute_dicgc_safe_ladder(
            corpus_inr=5000000.0,
            tenure_months=60,
            payout_mode="QUARTERLY_PAYOUT",
            is_senior=True,
            include_sfb=True,
        )
        sov_ids_60_sr = {
            t["instrument_id"]
            for t in ladder_60_sr["tranches"]
            if t["tranche_type"] == "SOVEREIGN_OVERFLOW"
        }
        self.assertIn("SAV-SCSS", sov_ids_60_sr)

        # At 60M CUMULATIVE, overflow allocates SAV-NSC; at 60M MONTHLY_PAYOUT, SAV-POMIS
        ladder_60_cum = compute_dicgc_safe_ladder(
            corpus_inr=5000000.0,
            tenure_months=60,
            payout_mode="CUMULATIVE",
            is_senior=False,
            include_sfb=True,
        )
        self.assertIn(
            "SAV-NSC",
            {t["instrument_id"] for t in ladder_60_cum["tranches"] if t["tranche_type"] == "SOVEREIGN_OVERFLOW"},
        )
        ladder_60_mon = compute_dicgc_safe_ladder(
            corpus_inr=5000000.0,
            tenure_months=60,
            payout_mode="MONTHLY_PAYOUT",
            is_senior=False,
            include_sfb=True,
        )
        self.assertIn(
            "SAV-POMIS",
            {t["instrument_id"] for t in ladder_60_mon["tranches"] if t["tranche_type"] == "SOVEREIGN_OVERFLOW"},
        )

    def test_fd_issuer_contagion_bridge_seniority_inversion_and_bfsi_hygiene(self) -> None:
        # Seed listed Corporate Debt rows:
        # 1. Shriram Finance Senior Secured NCD @ 9.45% YTM vs Shriram Unsecured FD (8.80% base / 9.16% APY -> -29 bps inversion)
        save_debt_security(
            {
                "isin": "INE721A07RN5",
                "ticker": "SHRIRAMFIN",
                "instrument_name": "Shriram Finance 9.35% Senior Secured NCD 2028",
                "issuer_name": "Shriram Finance Ltd",
                "seniority_tier": "SENIOR_SECURED",
                "credit_rating": "AA+",
                "coupon_rate_pct": 9.35,
                "ytm_pct": 9.45,
                "asset_cover_ratio": 1.15,
                "maturity_date": "2028-10-15",
            }
        )
        # 2. Bajaj Finance Senior Secured NCD stored under debt ticker alias BAJAJFIN (tests B5 alias bridge)
        save_debt_security(
            {
                "isin": "INE296A07SL2",
                "ticker": "BAJAJFIN",
                "instrument_name": "Bajaj Finance 7.95% Senior Secured NCD 2028",
                "issuer_name": "Bajaj Finance Ltd",
                "seniority_tier": "SENIOR_SECURED",
                "credit_rating": "AAA",
                "coupon_rate_pct": 7.95,
                "ytm_pct": 7.90,
                "asset_cover_ratio": 1.10,
                "maturity_date": "2028-08-20",
            }
        )
        # 3. HDFC Bank Subordinated Tier-2 & IndusInd Bank Perpetual AT1 (must be excluded from senior comparisons - L3)
        save_debt_security(
            {
                "isin": "INE040A08401",
                "ticker": "HDFCBANK",
                "instrument_name": "HDFC Bank 7.85% Tier-2 Subordinated Bond",
                "issuer_name": "HDFC Bank Ltd",
                "seniority_tier": "SUBORDINATED_TIER_2",
                "credit_rating": "AAA",
                "coupon_rate_pct": 7.85,
                "ytm_pct": 8.05,
                "maturity_date": "2032-05-10",
            }
        )
        save_debt_security(
            {
                "isin": "INE095A08082",
                "ticker": "SHRIRAMFIN",
                "instrument_name": "Shriram Perpetual AT1 Mock",
                "issuer_name": "Shriram Finance Ltd",
                "seniority_tier": "PERPETUAL_AT1",
                "credit_rating": "AA",
                "coupon_rate_pct": 9.90,
                "ytm_pct": 10.20,
                "maturity_date": "2099-12-31",
            }
        )

        # Seed BFSI cached_fundamentals row with noisy ROCE/Debt-to-Equity to verify B7 suppression
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO cached_fundamentals (
                ticker, company_name, sector, current_price, market_cap,
                pe_ratio, pb_ratio, roe, roce, debt_to_equity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            ("SHRIRAMFIN", "Shriram Finance Limited", "Financial Services", 645.0, 1210000000000.0, 14.8, 2.3, 16.4, 9.8, 4.4),
        )
        conn.commit()
        cur.close()
        conn.close()

        shriram_fd = get_savings_instrument_by_id("FD-SHRIRAM-50M")
        shriram_bridge = evaluate_fd_issuer_contagion_bridge(shriram_fd)
        self.assertEqual(shriram_bridge["contagion_flag"], "SENIORITY_YIELD_INVERSION")
        self.assertLess(shriram_bridge["unsecured_spread_vs_senior_ncd_bps"], 0.0)
        self.assertEqual(shriram_bridge["excluded_subordinated_or_at1_bonds"], 1)
        self.assertLessEqual(shriram_bridge["composite_safety_score"], CORPORATE_FD_SAFETY_CAP)
        self.assertIsNotNone(shriram_bridge["equity_health"])
        self.assertTrue(shriram_bridge["equity_health"]["is_bfsi_balance_sheet"])
        self.assertIsNone(shriram_bridge["equity_health"]["roce_pct"])
        self.assertIsNone(shriram_bridge["equity_health"]["debt_to_equity"])

        # Verify BAJFINANCE <-> BAJAJFIN alias bridge & <= 72/100 Corporate FD safety cap
        bajaj_fd = get_savings_instrument_by_id("FD-BAJAJ-42M")
        bajaj_bridge = evaluate_fd_issuer_contagion_bridge(bajaj_fd)
        self.assertIsNotNone(bajaj_bridge["best_senior_secured_ncd"])
        self.assertEqual(bajaj_bridge["best_senior_secured_ncd"]["isin"], "INE296A07SL2")
        self.assertLessEqual(bajaj_bridge["composite_safety_score"], CORPORATE_FD_SAFETY_CAP)

        # Verify HDFCBANK FD excludes Tier-2 subordinated bond from senior NCD comparables
        hdfc_fd = get_savings_instrument_by_id("FD-HDFC-35M")
        hdfc_bridge = evaluate_fd_issuer_contagion_bridge(hdfc_fd)
        self.assertEqual(len(hdfc_bridge["comparable_senior_ncds"]), 0)
        self.assertEqual(hdfc_bridge["excluded_subordinated_or_at1_bonds"], 1)
        self.assertGreaterEqual(hdfc_bridge["composite_safety_score"], 90)

        # Verify EVERY Corporate FD in the entire universe obeys composite_safety_score <= 72
        corp_dir = get_enriched_savings_directory(category="CORPORATE_FD")
        self.assertGreaterEqual(corp_dir["total_count"], 5)
        for row in corp_dir["instruments"]:
            self.assertLessEqual(row["contagion"]["composite_safety_score"], CORPORATE_FD_SAFETY_CAP)

    def test_pure_arbitrage_guard_and_no_fabricated_mf_returns(self) -> None:
        # Pure Sec 112A Arbitrage MF accepted; FoFs and Debt funds strictly rejected (L1)
        self.assertTrue(
            is_pure_sec_112a_arbitrage_fund(
                "HYBRID",
                "Hybrid Scheme - Arbitrage Fund",
                "Kotak Equity Arbitrage Fund - Direct Plan - Growth",
            )
        )
        self.assertFalse(
            is_pure_sec_112a_arbitrage_fund(
                "HYBRID",
                "FoF Domestic",
                "ICICI Prudential Income plus Arbitrage Active FoF - Direct Growth",
            )
        )
        self.assertFalse(
            is_pure_sec_112a_arbitrage_fund(
                "OTHER",
                "Fund of Funds",
                "Nippon India Arbitrage Fund of Funds",
            )
        )
        self.assertFalse(
            is_pure_sec_112a_arbitrage_fund(
                "DEBT",
                "Liquid Fund",
                "SBI Liquid Fund - Direct Growth",
            )
        )

        # Seed one pure Arbitrage MF, one Arbitrage FoF, and one Liquid Debt MF WITHOUT return observations
        conn = get_db_connection()
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT INTO mutual_fund_schemes (
                scheme_code, scheme_name, fund_house, broad_category, category,
                benchmark_index, nav, aum_crores, ter_direct_pct, metadata_json, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            [
                ("119771", "Kotak Equity Arbitrage Fund - Direct Growth", "Kotak", "HYBRID", "Arbitrage Fund", "Nifty 50 Arbitrage Index", 38.4, 54000.0, 0.43, "{}", "2026-11-01"),
                ("152001", "Sample Income plus Arbitrage Active FoF - Direct", "ICICI", "HYBRID", "FoF Domestic", "CRISIL Hybrid Index", 14.2, 1800.0, 0.28, "{}", "2026-11-01"),
                ("119800", "SBI Liquid Fund - Direct Growth", "SBI", "DEBT", "Liquid Fund", "CRISIL Liquid Debt Index", 3920.0, 72000.0, 0.18, "{}", "2026-11-01"),
            ],
        )
        cur.executemany(
            """
            INSERT INTO mutual_fund_holdings (
                scheme_code, holding_type, identifier, holding_name, weight_pct, sector_or_rating, portfolio_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            [
                ("119771", "EQUITY", "RELIANCE", "Reliance Industries Ltd (Hedged)", 6.5, "Energy", "2026-10-31"),
                ("152001", "MUTUAL_FUND", "ICICI-ARB", "Underlying Arbitrage & Debt Units", 98.0, "Hybrid FoF", "2026-10-31"),
                ("119800", "SOVEREIGN", "IN002026T91", "91D GOI Treasury Bill", 24.0, "SOV", "2026-10-31"),
            ],
        )
        conn.commit()
        cur.close()
        conn.close()

        sleeve = get_cash_park_sleeve(holding_months=13, slab_rate_pct=30.0)
        sleeve_ids = {item["id"] for item in sleeve["items"]}
        self.assertIn("119771", sleeve_ids)
        self.assertIn("119800", sleeve_ids)
        self.assertNotIn("152001", sleeve_ids)
        self.assertGreaterEqual(sleeve["excluded_arbitrage_fof_count"], 1)

        # Verify Opportunity Terminal NEVER fabricates 7.2% or 14.5% returns for unobserved MFs
        opp_rows = {r["id"]: r for r in opportunity_terminal.get_normalized_opportunity_universe()}
        self.assertIn("119771", opp_rows)
        self.assertIn("119800", opp_rows)
        self.assertIsNone(opp_rows["119771"]["gross_yield_pct"])
        self.assertIsNone(opp_rows["119800"]["gross_yield_pct"])
        self.assertEqual(opp_rows["119771"]["seniority_tier"], "SENIOR_SECURED")  # Arbitrage MF != residual EQUITY
        self.assertEqual(opp_rows["152001"]["seniority_tier"], "EQUITY")  # FoF rejected from pure 112A arbitrage

    def test_cross_surface_macro_anchors_and_sovereign_timestamp_immutability(self) -> None:
        # Refresh benchmarks offline twice and verify auction_date/updated_at are not overwritten when unchanged
        with (
            patch(
                "core.db.sovereign.fetch_live_rbi_ccil_yield_curve",
                return_value={"is_live": False, "live_benchmarks": [], "data_source": "RBI_AUCTION_CUTOFF"},
            ),
            patch("core.db.sovereign.fetch_live_rbi_mospi_macro_corridor", return_value={}),
        ):
            refresh_daily_sovereign_benchmarks()
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT cut_off_yield, auction_date, updated_at FROM sovereign_benchmarks WHERE tenor_label = '10Y_GSEC';")
            first_row = cur.fetchone()
            cur.execute("SELECT metric_value, updated_at FROM sovereign_macro_rates WHERE metric_key = 'cpi_inflation';")
            first_macro = cur.fetchone()
            cur.close()
            conn.close()

            refresh_daily_sovereign_benchmarks()
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT cut_off_yield, auction_date, updated_at FROM sovereign_benchmarks WHERE tenor_label = '10Y_GSEC';")
            second_row = cur.fetchone()
            cur.execute("SELECT metric_value, updated_at FROM sovereign_macro_rates WHERE metric_key = 'cpi_inflation';")
            second_macro = cur.fetchone()
            cur.close()
            conn.close()

        self.assertEqual(first_row[0], second_row[0])
        self.assertEqual(first_row[1], second_row[1])
        self.assertEqual(first_row[2], second_row[2])
        self.assertEqual(first_macro[0], second_macro[0])
        self.assertEqual(first_macro[1], second_macro[1])

        anchors = get_live_macro_anchors()
        self.assertAlmostEqual(net_real_tax_calculator.get_default_cpi_inflation(), anchors["cpi_inflation_pct"], places=2)
        self.assertAlmostEqual(SetuMatrixEngine._resolve_live_gsec_10y(), anchors["gsec_10y_pct"], places=2)

        # Verify Fisher deflation parity between Net Real Tax Calculator and Savings Engine
        calc = net_real_tax_calculator.calculate_net_real_return(
            nominal_annual_return_pct=7.50,
            tax_rate_pct=31.20,
            cpi_inflation_pct=anchors["cpi_inflation_pct"],
        )
        expected_fisher = compute_fisher_real_yield_pct(calc["post_tax_nominal_pct"], anchors["cpi_inflation_pct"])
        self.assertAlmostEqual(calc["net_real_return_pct"], expected_fisher, places=2)

        dossier = get_savings_instrument_dossier("SAV-PPF")
        self.assertIsNotNone(dossier)
        self.assertEqual(len(dossier["slab_matrix"]), 10)
        self.assertAlmostEqual(dossier["macro_anchors"]["cpi_inflation_pct"], anchors["cpi_inflation_pct"], places=2)

    def test_defect1_rate_updates_monotonic_and_never_reverted_by_sync_or_import(self) -> None:
        from scripts.import_savings_rates import run_apply

        nsc = dict(get_savings_instrument_by_id("SAV-NSC"))
        nsc["base_rate_pct"] = 7.90
        nsc["effective_from"] = "2026-11-01"
        res_upd = upsert_savings_instrument(nsc)
        self.assertEqual(res_upd["status"], "RATE_UPDATED")

        # 1. Re-seeding baseline universe (force_overwrite=False) must NOT revert 7.90% back to 7.70%
        seed_baseline_savings_universe(force_overwrite=False)
        self.assertAlmostEqual(get_savings_instrument_by_id("SAV-NSC")["base_rate_pct"], 7.90, places=2)
        self.assertAlmostEqual(get_savings_instrument_by_id("SAV-FRSB-2020")["base_rate_pct"], 8.25, places=2)

        # 2. Automated rate verification & sync must NOT revert 7.90% back to 7.70%
        verify_and_sync_automated_savings_rates(edition_date="2026-11-10", allow_network=False)
        self.assertAlmostEqual(get_savings_instrument_by_id("SAV-NSC")["base_rate_pct"], 7.90, places=2)
        self.assertAlmostEqual(get_savings_instrument_by_id("SAV-FRSB-2020")["base_rate_pct"], 8.25, places=2)

        # 3. CLI run_apply(--apply) on baseline JSON without --force must NOT revert 7.90%
        run_apply(savings_db.BASELINE_SAVINGS_JSON_PATH, force=False)
        self.assertAlmostEqual(get_savings_instrument_by_id("SAV-NSC")["base_rate_pct"], 7.90, places=2)
        self.assertAlmostEqual(get_savings_instrument_by_id("SAV-FRSB-2020")["base_rate_pct"], 8.25, places=2)

        # 4. Direct upsert with an older effective_from date is rejected from active tariff regression
        older = dict(get_savings_instrument_by_id("SAV-NSC"))
        older["base_rate_pct"] = 7.40
        older["effective_from"] = "2025-04-01"
        res_old = upsert_savings_instrument(older)
        self.assertEqual(res_old["status"], "SKIPPED_OLDER_EFFECTIVE_DATE")
        self.assertAlmostEqual(get_savings_instrument_by_id("SAV-NSC")["base_rate_pct"], 7.90, places=2)

    def test_defect2_empty_macro_db_never_fakes_mospi_or_rbi_labels(self) -> None:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM sovereign_macro_rates;")
        cur.execute("DELETE FROM sovereign_benchmarks;")
        conn.commit()
        cur.close()
        conn.close()

        anchors = get_live_macro_anchors()
        self.assertTrue(anchors["cpi_is_fallback"])
        self.assertTrue(anchors["gsec_10y_is_fallback"])
        self.assertTrue(anchors["repo_is_fallback"])
        self.assertIsNone(anchors["cpi_observed_pct"])
        self.assertIsNone(anchors["gsec_10y_observed_pct"])
        for src_key in ("cpi_source", "gsec_10y_source", "repo_source", "tbill_91d_source"):
            src_val = str(anchors.get(src_key) or "").upper()
            self.assertIn("ASSUMED_FALLBACK", src_val)
            self.assertNotIn("MOSPI", src_val)
            self.assertNotIn("RBI_AUCTION_CUTOFF", src_val)

        # Verify reading anchors did NOT stealth-seed empty tables
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sovereign_macro_rates;")
        self.assertEqual(cur.fetchone()[0], 0)
        cur.execute("SELECT COUNT(*) FROM sovereign_benchmarks;")
        self.assertEqual(cur.fetchone()[0], 0)
        cur.close()
        conn.close()

    def test_defect3_hni_tax_inputs_31_2_to_39_0_move_all_taxable_rows(self) -> None:
        from core.analysis.live_security_tax_bridge import compare_live_tracked_yield_instruments

        # New Regime: 32 of 34 rows change (all except EEE-exempt SAV-PPF & SAV-SSY)
        dir_312 = sorted(
            get_enriched_savings_directory(tax_regime="NEW_115BAC", slab_rate_pct=31.2)["instruments"],
            key=lambda x: x["instrument_id"],
        )
        dir_390 = sorted(
            get_enriched_savings_directory(tax_regime="NEW_115BAC", slab_rate_pct=39.0)["instruments"],
            key=lambda x: x["instrument_id"],
        )
        self.assertEqual(len(dir_312), 34)
        new_changed = [
            a["instrument_id"]
            for a, b in zip(dir_312, dir_390)
            if a["tax_eval"]["post_tax_yield_pct"] != b["tax_eval"]["post_tax_yield_pct"]
        ]
        self.assertEqual(len(new_changed), 32)

        # Old Regime: 33 of 34 rows change at default ₹5L principal (SAV-NPS-TIER1 has exact 40% upfront 80CCD saving vs 40% annuity tax symmetry at ₹5L, and moves at principal != ₹5L)
        old_312 = sorted(
            get_enriched_savings_directory(tax_regime="OLD_REGIME", slab_rate_pct=31.2)["instruments"],
            key=lambda x: x["instrument_id"],
        )
        old_390 = sorted(
            get_enriched_savings_directory(tax_regime="OLD_REGIME", slab_rate_pct=39.0)["instruments"],
            key=lambda x: x["instrument_id"],
        )
        old_changed = [
            a["instrument_id"]
            for a, b in zip(old_312, old_390)
            if a["tax_eval"]["post_tax_yield_pct"] != b["tax_eval"]["post_tax_yield_pct"]
        ]
        self.assertEqual(len(old_changed), 33)
        nps1 = get_savings_instrument_by_id("SAV-NPS-TIER1")
        ev_nps_10l_312 = evaluate_savings_post_tax(nps1, tax_regime="OLD_REGIME", slab_rate_pct=31.2, principal_inr=1000000.0)
        ev_nps_10l_390 = evaluate_savings_post_tax(nps1, tax_regime="OLD_REGIME", slab_rate_pct=39.0, principal_inr=1000000.0)
        self.assertNotEqual(ev_nps_10l_312["post_tax_yield_pct"], ev_nps_10l_390["post_tax_yield_pct"])

        # Live Security Tax Bridge parity: 32 of 34 SAVINGS_DEPOSIT rows move in New Regime
        br_312 = sorted(
            [r for r in compare_live_tracked_yield_instruments(slab_key=31.2, limit_per_class=50) if r["asset_class"] == "SAVINGS_DEPOSIT"],
            key=lambda x: x["identifier"],
        )
        br_390 = sorted(
            [r for r in compare_live_tracked_yield_instruments(slab_key=39.0, limit_per_class=50) if r["asset_class"] == "SAVINGS_DEPOSIT"],
            key=lambda x: x["identifier"],
        )
        br_changed = sum(1 for a, b in zip(br_312, br_390) if a["post_tax_nominal_pct"] != b["post_tax_nominal_pct"])
        self.assertEqual(br_changed, 32)

    def test_defect4_complete_pension_deduction_models_and_strict_dicgc_validation(self) -> None:
        # 1. Upfront Sec 80C deduction boosts Old Regime post-tax IRR on PPF & SCSS vs New Regime
        ppf = get_savings_instrument_by_id("SAV-PPF")
        scss = get_savings_instrument_by_id("SAV-SCSS")
        ev_ppf_new = evaluate_savings_post_tax(ppf, tax_regime="NEW_115BAC", slab_rate_pct=30.0)
        ev_ppf_old = evaluate_savings_post_tax(ppf, tax_regime="OLD_REGIME", slab_rate_pct=30.0)
        self.assertGreater(ev_ppf_old["post_tax_yield_pct"], ev_ppf_new["post_tax_yield_pct"] + 2.0)

        ev_scss_new = evaluate_savings_post_tax(scss, tax_regime="NEW_115BAC", slab_rate_pct=30.0, is_senior=True)
        ev_scss_old = evaluate_savings_post_tax(
            scss, tax_regime="OLD_REGIME", slab_rate_pct=30.0, is_senior=True, principal_inr=1500000.0
        )
        self.assertGreater(ev_scss_old["post_tax_yield_pct"], ev_scss_new["post_tax_yield_pct"] + 2.0)

        # 2. POSB Sec 10(15)(i) ₹3,500 single / ₹7,000 joint exemption works in BOTH regimes
        posb = {
            "instrument_id": "SAV-POSB",
            "scheme_name": "Post Office Savings Account (POSB)",
            "category": "SMALL_SAVINGS",
            "issuer_name": "India Post (Government of India)",
            "base_rate_pct": 4.0,
            "senior_citizen_bonus_bps": 0.0,
            "compounding_freq": "ANNUAL",
            "tenure_max_months": 12,
            "lock_in_months": 0,
            "tax_section_80c_eligible": 0,
            "interest_taxability": "SLAB_TAXABLE",
            "maturity_taxability": "EXEMPT",
            "tds_applicable": 0,
            "notes": {
                "is_savings_account": True,
                "sec_10_15_i_exempt_single_inr": 3500.0,
                "sec_10_15_i_exempt_joint_inr": 7000.0,
            },
        }
        ev_posb_single = evaluate_savings_post_tax(posb, tax_regime="NEW_115BAC", slab_rate_pct=30.0, principal_inr=80000.0)
        ev_posb_joint = evaluate_savings_post_tax(
            posb, tax_regime="NEW_115BAC", slab_rate_pct=30.0, principal_inr=160000.0, is_joint_account=True
        )
        self.assertEqual(ev_posb_single["effective_tax_rate_pct"], 0.0)  # ₹3,200 <= ₹3,500 exempt
        self.assertEqual(ev_posb_joint["effective_tax_rate_pct"], 0.0)  # ₹6,400 <= ₹7,000 joint exempt

        # 3. EPF ₹5.00L non-employer threshold & <5Y premature withdrawal taxability + Sec 192A TDS
        epf = get_savings_instrument_by_id("SAV-EPF-VPF")
        ev_epf_no_emp = evaluate_savings_post_tax(
            epf, tax_regime="NEW_115BAC", slab_rate_pct=30.0, annual_contribution_inr=450000.0, has_employer_epf=False
        )
        ev_epf_premature = evaluate_savings_post_tax(
            epf, tax_regime="NEW_115BAC", slab_rate_pct=30.0, annual_contribution_inr=200000.0, service_years=3
        )
        self.assertEqual(ev_epf_no_emp["effective_tax_rate_pct"], 0.0)
        self.assertGreater(ev_epf_premature["effective_tax_rate_pct"], 30.0)
        self.assertTrue(ev_epf_premature["tds_triggered_on_principal"])

        # 4. NPS Tier-I: Sec 80CCD(1B) + 80CCD(2), premature 20/80 exit, and <= ₹5L 100% exempt small corpus
        nps1 = get_savings_instrument_by_id("SAV-NPS-TIER1")
        ev_nps_norm = evaluate_savings_post_tax(nps1, tax_regime="NEW_115BAC", slab_rate_pct=30.0, principal_inr=500000.0)
        ev_nps_prem = evaluate_savings_post_tax(
            nps1, tax_regime="NEW_115BAC", slab_rate_pct=30.0, principal_inr=500000.0, premature_exit=True
        )
        ev_nps_emp = evaluate_savings_post_tax(
            nps1,
            tax_regime="NEW_115BAC",
            slab_rate_pct=30.0,
            principal_inr=200000.0,
            basic_salary_inr=1500000.0,
            employer_nps_contribution_inr=150000.0,
        )
        ev_nps_small = evaluate_savings_post_tax(nps1, tax_regime="NEW_115BAC", slab_rate_pct=30.0, principal_inr=50000.0)
        self.assertLess(ev_nps_prem["post_tax_yield_pct"], ev_nps_norm["post_tax_yield_pct"])
        self.assertGreater(ev_nps_emp["upfront_tax_saved_inr"], 40000.0)
        self.assertEqual(ev_nps_small["effective_tax_rate_pct"], 0.0)

        # 5. NPS Tier-II: NAV deferral + Central Govt 3Y Sec 80C
        nps2 = get_savings_instrument_by_id("SAV-NPS-TIER2")
        ev_nps2_reg = evaluate_savings_post_tax(nps2, tax_regime="OLD_REGIME", slab_rate_pct=30.0, is_govt_employee=False)
        ev_nps2_cg = evaluate_savings_post_tax(nps2, tax_regime="OLD_REGIME", slab_rate_pct=30.0, is_govt_employee=True)
        self.assertGreater(ev_nps2_cg["post_tax_yield_pct"], ev_nps2_reg["post_tax_yield_pct"] + 2.0)

        # 6. HYSA progressive balance-slab blending (<= ₹5L @ 3.00% vs > ₹5L @ 7.00%)
        hysa = get_savings_instrument_by_id("HYSA-IDFCFIRST")
        ev_hysa_3l = evaluate_savings_post_tax(hysa, tax_regime="NEW_115BAC", slab_rate_pct=0.0, principal_inr=300000.0)
        ev_hysa_10l = evaluate_savings_post_tax(hysa, tax_regime="NEW_115BAC", slab_rate_pct=0.0, principal_inr=1000000.0)
        ev_hysa_20l = evaluate_savings_post_tax(hysa, tax_regime="NEW_115BAC", slab_rate_pct=0.0, principal_inr=2000000.0)
        self.assertAlmostEqual(ev_hysa_3l["nominal_rate_pct"], 3.00, places=2)
        self.assertAlmostEqual(ev_hysa_10l["nominal_rate_pct"], 5.00, places=2)
        self.assertAlmostEqual(ev_hysa_20l["nominal_rate_pct"], 6.00, places=2)

        # 7. Strict DICGC ladder rejection of unsupported payout modes, tenors, corpus, and bank band gaps
        with self.assertRaises(ValueError):
            compute_dicgc_safe_ladder(corpus_inr=1000000.0, tenure_months=36, payout_mode="WEEKLY_PAYOUT")
        with self.assertRaises(ValueError):
            compute_dicgc_safe_ladder(corpus_inr=1000000.0, tenure_months=96, payout_mode="CUMULATIVE")
        with self.assertRaises(ValueError):
            compute_dicgc_safe_ladder(corpus_inr=500.0, tenure_months=36, payout_mode="CUMULATIVE")
        with self.assertRaises(ValueError):
            compute_dicgc_safe_ladder(corpus_inr=1000000.0, tenure_months=36, payout_mode="CUMULATIVE", include_sfb=False)

    def test_defect5_provenance_validation_staleness_and_dynamic_bouquet_rates(self) -> None:
        from core.analysis.research_bouquet import _load_live_savings_posture, _load_live_sovereign_posture

        # 1. Provenance validation rejects HTTP or third-party vendor URLs
        bad_http = dict(get_savings_instrument_by_id("SAV-PPF"))
        bad_http["source_url"] = "http://www.indiapost.gov.in"
        with self.assertRaises(ValueError):
            upsert_savings_instrument(bad_http)

        bad_vendor = dict(get_savings_instrument_by_id("SAV-PPF"))
        bad_vendor["source_url"] = "https://www.morningstar.in/funds"
        with self.assertRaises(ValueError):
            upsert_savings_instrument(bad_vendor)

        # 2. SMALL_SAVINGS & RETIREMENT_PENSION escalate to STALE_TARIFF when >45d overdue past next_review_date
        ppf = get_savings_instrument_by_id("SAV-PPF")
        stale_stat = compute_staleness_badge(ppf, reference_date="2027-03-01")
        self.assertEqual(stale_stat["status"], "STALE_TARIFF")

        epf = get_savings_instrument_by_id("SAV-EPF-VPF")
        stale_epf = compute_staleness_badge(epf, reference_date="2027-06-01")
        self.assertEqual(stale_epf["status"], "STALE_TARIFF")

        # 3. Morning Bouquet & Net Real Tax Calculator reflect updated SAV-PPF / SAV-SCSS rates dynamically
        refresh_daily_sovereign_benchmarks("2026-11-05")
        ppf_upd = dict(ppf)
        ppf_upd["base_rate_pct"] = 7.50
        ppf_upd["effective_from"] = "2026-11-01"
        ppf_upd["next_review_date"] = "2027-01-31"
        upsert_savings_instrument(ppf_upd)

        scss_upd = dict(get_savings_instrument_by_id("SAV-SCSS"))
        scss_upd["base_rate_pct"] = 8.40
        scss_upd["senior_citizen_bonus_bps"] = 0.0
        scss_upd["effective_from"] = "2026-11-01"
        scss_upd["next_review_date"] = "2027-01-31"
        upsert_savings_instrument(scss_upd)

        sov_posture = _load_live_sovereign_posture("2026-11-05")
        self.assertIn("PPF EEE 7.50%", sov_posture["tax_free_highlight"])
        self.assertIn("SCSS 8.40%", sov_posture["tax_free_highlight"])
        self.assertNotIn("7.10%", sov_posture["tax_free_highlight"])

        sav_posture = _load_live_savings_posture("2026-11-05")
        self.assertAlmostEqual(sav_posture["ppf_rate_pct"], 7.50, places=2)
        self.assertAlmostEqual(sav_posture["scss_rate_pct"], 8.40, places=2)

        tax_matrix = net_real_tax_calculator.compare_asset_classes_post_tax(marginal_tax_slab_pct=30.0)
        ppf_row = next(r for r in tax_matrix if r["category"] == "STATUTORY_SAVINGS")
        self.assertAlmostEqual(ppf_row["nominal_yield_pct"], 7.50, places=2)

    def test_pkg01_canonical_table_names_and_v050_legacy_upgrade(self) -> None:
        import sqlite3
        from core.db.savings import (
            drop_retired_v049_savings_tables,
            validate_legacy_savings_migration_preservation,
        )

        # 1. Fresh DB uses canonical savings_instruments, savings_rate_observations, tax_rule_registry, savings_override_audit_log
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {r[0] for r in cur.fetchall()}
        cur.close()
        conn.close()
        self.assertIn("savings_instruments", tables)
        self.assertIn("savings_rate_observations", tables)
        self.assertIn("tax_rule_registry", tables)
        self.assertIn("savings_override_audit_log", tables)
        self.assertNotIn("fixed_savings_instruments", tables)
        self.assertNotIn("savings_rate_history", tables)
        self.assertNotIn("regulatory_tax_rule_versions", tables)

        # 2. Simulate a database where BOTH legacy v049 tables AND canonical tables contain data (including conflicting rows!)
        legacy_db = os.path.join(self._tmp_dir.name, "legacy_v049_dual_populated.db")
        raw = sqlite3.connect(legacy_db)
        raw.executescript(
            """
            CREATE TABLE schema_migrations (version TEXT PRIMARY KEY);
            INSERT INTO schema_migrations (version) VALUES ('v049_fixed_savings_and_deposit_universe');
            CREATE TABLE fixed_savings_instruments (
                instrument_id TEXT PRIMARY KEY, scheme_name TEXT NOT NULL, category TEXT NOT NULL,
                issuer_name TEXT NOT NULL, issuer_ticker TEXT, issuer_type TEXT NOT NULL,
                sovereign_backed INTEGER NOT NULL DEFAULT 0, dicgc_insured INTEGER NOT NULL DEFAULT 0,
                dicgc_limit_inr REAL NOT NULL DEFAULT 0.0, credit_rating TEXT NOT NULL DEFAULT 'SOV',
                base_rate_pct REAL NOT NULL, senior_citizen_bonus_bps REAL NOT NULL DEFAULT 0.0,
                rate_type TEXT NOT NULL DEFAULT 'FIXED', floating_benchmark TEXT,
                floating_spread_bps REAL NOT NULL DEFAULT 0.0, compounding_freq TEXT NOT NULL DEFAULT 'ANNUAL',
                payout_options_json TEXT NOT NULL DEFAULT '["CUMULATIVE"]',
                tenure_min_months INTEGER NOT NULL DEFAULT 60, tenure_max_months INTEGER NOT NULL DEFAULT 60,
                lock_in_months INTEGER NOT NULL DEFAULT 60, premature_exit_rule TEXT DEFAULT 'LEGACY_EXIT_CLAUSE',
                min_investment_inr REAL NOT NULL DEFAULT 1000.0, max_investment_inr REAL,
                tax_section_80c_eligible INTEGER NOT NULL DEFAULT 1, interest_taxability TEXT NOT NULL DEFAULT 'NSC_REINVESTED_80C',
                maturity_taxability TEXT NOT NULL DEFAULT 'EXEMPT', tds_applicable INTEGER NOT NULL DEFAULT 0,
                tds_threshold_regular_inr REAL NOT NULL DEFAULT 0.0, tds_threshold_senior_inr REAL NOT NULL DEFAULT 0.0,
                effective_from TEXT NOT NULL, next_review_date TEXT, source_authority TEXT NOT NULL,
                source_url TEXT NOT NULL, notes_json TEXT NOT NULL DEFAULT '{"legacy_field":"preserved_100pct"}',
                is_active INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
            );
            INSERT INTO fixed_savings_instruments (
                instrument_id, scheme_name, category, issuer_name, issuer_type, base_rate_pct,
                effective_from, source_authority, source_url, updated_at
            ) VALUES (
                'SAV-NSC', 'National Savings Certificate', 'SMALL_SAVINGS', 'India Post', 'GOVT_POSTAL',
                7.75, '2026-10-01', 'Department of Economic Affairs (DEA), Ministry of Finance',
                'https://www.indiapost.gov.in', '2026-10-01T00:00:00+05:30'
            );
            INSERT INTO fixed_savings_instruments (
                instrument_id, scheme_name, category, issuer_name, issuer_type, base_rate_pct,
                effective_from, source_authority, source_url, updated_at
            ) VALUES (
                'SAV-KVP', 'Kisan Vikas Patra', 'SMALL_SAVINGS', 'India Post', 'GOVT_POSTAL',
                7.50, '2026-10-01', 'Department of Economic Affairs (DEA), Ministry of Finance',
                'https://www.indiapost.gov.in', '2026-10-01T00:00:00+05:30'
            );
            CREATE TABLE savings_instruments AS SELECT * FROM fixed_savings_instruments WHERE instrument_id = 'SAV-NSC';
            UPDATE savings_instruments
               SET base_rate_pct = 7.95,
                   effective_from = '2026-11-01',
                   premature_exit_rule = 'CANONICAL_EXIT_CLAUSE',
                   updated_at = '2026-11-01T09:00:00+05:30'
             WHERE instrument_id = 'SAV-NSC';
            CREATE TABLE savings_rate_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, instrument_id TEXT NOT NULL,
                base_rate_pct REAL NOT NULL, senior_citizen_bonus_bps REAL NOT NULL DEFAULT 0.0,
                effective_from TEXT NOT NULL, effective_to TEXT, source_authority TEXT NOT NULL,
                source_url TEXT NOT NULL, recorded_at TEXT NOT NULL
            );
            INSERT INTO savings_rate_history (
                instrument_id, base_rate_pct, senior_citizen_bonus_bps, effective_from,
                source_authority, source_url, recorded_at
            ) VALUES (
                'SAV-NSC', 7.75, 0.0, '2026-10-01',
                'Department of Economic Affairs (DEA), Ministry of Finance',
                'https://www.indiapost.gov.in', '2026-10-01T00:00:00+05:30'
            );
            CREATE TABLE regulatory_tax_rule_versions (
                rule_version TEXT PRIMARY KEY, finance_act_label TEXT NOT NULL,
                effective_from TEXT NOT NULL, effective_to TEXT, rules_json TEXT NOT NULL,
                source_authority TEXT NOT NULL, source_url TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            INSERT INTO regulatory_tax_rule_versions VALUES (
                'FY2025_26_FA2025', 'Finance Act 2025', '2025-04-01', NULL, '{"default_regime":"NEW_115BAC"}',
                'Central Board of Direct Taxes (CBDT), Ministry of Finance', 'https://incometaxindia.gov.in',
                '2026-10-01T00:00:00+05:30'
            );
            """
        )
        raw.commit()
        raw.close()

        with patch.dict(os.environ, {"TEST_DB_PATH": legacy_db}):
            db_conn._DB_INITIALIZED = False
            db_conn._INITIALIZED_DBS.clear()
            init_db(force=True)
            pres = validate_legacy_savings_migration_preservation()
            self.assertTrue(pres["valid"], f"Preservation check failed: {pres['errors']}")

            chk = sqlite3.connect(legacy_db)
            up_tables = {r[0] for r in chk.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
            migrated_nsc_rate = chk.execute(
                "SELECT base_rate_pct FROM savings_instruments WHERE instrument_id='SAV-NSC';"
            ).fetchone()[0]
            migrated_kvp_rate = chk.execute(
                "SELECT base_rate_pct FROM savings_instruments WHERE instrument_id='SAV-KVP';"
            ).fetchone()[0]
            nsc_obs_rows = chk.execute(
                "SELECT observation_id, effective_from, base_rate_pct, terms_snapshot_json, observation_status "
                "FROM savings_rate_observations WHERE instrument_id='SAV-NSC' ORDER BY effective_from DESC;"
            ).fetchall()
            migrated_tax = chk.execute("SELECT rule_version FROM tax_rule_registry;").fetchone()[0]
            # Verify retained legacy table was mirrored with reconciled active winner for rollback compatibility
            mirrored_legacy_nsc = chk.execute(
                "SELECT base_rate_pct, effective_from FROM fixed_savings_instruments WHERE instrument_id='SAV-NSC';"
            ).fetchone()
            chk.close()

            # Legacy tables are RETAINED until explicit post-soak confirmation
            self.assertIn("fixed_savings_instruments", up_tables)
            self.assertIn("savings_rate_history", up_tables)
            self.assertIn("regulatory_tax_rule_versions", up_tables)
            self.assertAlmostEqual(migrated_nsc_rate, 7.95, places=2)
            self.assertAlmostEqual(migrated_kvp_rate, 7.50, places=2)
            self.assertEqual(len(nsc_obs_rows), 2)
            # Verify BOTH 7.95% (canonical) and 7.75% (legacy, with LEGACY_EXIT_CLAUSE) are preserved in observations
            self.assertAlmostEqual(nsc_obs_rows[0][2], 7.95, places=2)
            self.assertAlmostEqual(nsc_obs_rows[1][2], 7.75, places=2)
            self.assertIn("LEGACY_EXIT_CLAUSE", nsc_obs_rows[1][3])
            self.assertIn("preserved_100pct", nsc_obs_rows[1][3])
            self.assertEqual(migrated_tax, "FY2025_26_FA2025")
            self.assertAlmostEqual(mirrored_legacy_nsc[0], 7.95, places=2)
            self.assertEqual(mirrored_legacy_nsc[1], "2026-11-01")

            # Post-soak cutover requires explicit confirm=True
            with self.assertRaises(ValueError):
                drop_retired_v049_savings_tables(confirm=False)
            cutover_res = drop_retired_v049_savings_tables(confirm=True)
            self.assertEqual(
                set(cutover_res["dropped_tables"]),
                {"fixed_savings_instruments", "savings_rate_history", "regulatory_tax_rule_versions"},
            )

    def test_pkg01_same_date_revisions_append_only_and_force_override(self) -> None:
        from core.db.savings import get_savings_override_audit_log, get_savings_rate_observations
        from scripts.import_savings_rates import run_apply

        nsc = dict(get_savings_instrument_by_id("SAV-NSC"))
        nsc_79 = {**nsc, "base_rate_pct": 7.90, "effective_from": "2026-11-01", "rate_circular_ref": "DEA-NOV-REV1"}
        r1 = upsert_savings_instrument(nsc_79)
        self.assertEqual(r1["status"], "RATE_UPDATED")
        self.assertEqual(r1["revision_seq"], 1)

        # Same-date correction 7.90% -> 8.00% appends revision_seq=2 and retains 7.90% as superseded
        nsc_80 = {**nsc, "base_rate_pct": 8.00, "effective_from": "2026-11-01", "rate_circular_ref": "DEA-NOV-REV2"}
        r2 = upsert_savings_instrument(nsc_80)
        self.assertEqual(r2["status"], "RATE_UPDATED")
        self.assertEqual(r2["revision_seq"], 2)

        nov_obs = [o for o in get_savings_rate_observations("SAV-NSC") if o["effective_from"] == "2026-11-01"]
        self.assertEqual(len(nov_obs), 2)
        self.assertEqual(nov_obs[0]["revision_seq"], 2)
        self.assertAlmostEqual(nov_obs[0]["base_rate_pct"], 8.00, places=2)
        self.assertEqual(nov_obs[0]["rate_circular_ref"], "DEA-NOV-REV2")
        self.assertIsNone(nov_obs[0]["superseded_at"])

        self.assertEqual(nov_obs[1]["revision_seq"], 1)
        self.assertAlmostEqual(nov_obs[1]["base_rate_pct"], 7.90, places=2)
        self.assertEqual(nov_obs[1]["rate_circular_ref"], "DEA-NOV-REV1")
        self.assertIsNotNone(nov_obs[1]["superseded_at"])
        self.assertEqual(nov_obs[1]["superseded_by_observation_id"], nov_obs[0]["observation_id"])

        # Older effective_from is skipped without force_overwrite=True
        older = {**nsc_80, "base_rate_pct": 7.60, "effective_from": "2026-10-15"}
        res_skip = upsert_savings_instrument(older)
        self.assertEqual(res_skip["status"], "SKIPPED_OLDER_EFFECTIVE_DATE")
        self.assertAlmostEqual(get_savings_instrument_by_id("SAV-NSC")["base_rate_pct"], 8.00, places=2)

        # Gap 5: force_overwrite=True without override_reason and override_operator is strictly rejected
        with self.assertRaises(ValueError):
            upsert_savings_instrument(older, force_overwrite=True)
        with self.assertRaises(ValueError):
            upsert_savings_instrument(older, force_overwrite=True, override_reason="short", override_operator="op")
        with self.assertRaises(ValueError):
            upsert_savings_instrument(older, force_overwrite=True, override_reason="Valid override reason", override_operator="")

        res_forced = upsert_savings_instrument(
            older,
            force_overwrite=True,
            override_reason="Statutory DEA retrospective gazette rollback",
            override_operator="cli:rahul_sharma",
        )
        self.assertEqual(res_forced["status"], "RATE_UPDATED")
        self.assertEqual(res_forced["override_epoch"], 1)
        self.assertIsNotNone(res_forced["override_id"])
        self.assertAlmostEqual(get_savings_instrument_by_id("SAV-NSC")["base_rate_pct"], 7.60, places=2)
        self.assertEqual(get_savings_instrument_by_id("SAV-NSC")["effective_from"], "2026-10-15")
        # Pegged dependent SAV-FRSB-2020 also rolled back to 7.95% (7.60% + 0.35%) and recorded in dependent_updates
        self.assertAlmostEqual(get_savings_instrument_by_id("SAV-FRSB-2020")["base_rate_pct"], 7.95, places=2)

        audit_rows = get_savings_override_audit_log("SAV-NSC")
        self.assertEqual(len(audit_rows), 1)
        self.assertEqual(audit_rows[0]["operator_id"], "cli:rahul_sharma")
        self.assertEqual(audit_rows[0]["override_reason"], "Statutory DEA retrospective gazette rollback")
        self.assertEqual(audit_rows[0]["prior_observation_id"], nov_obs[0]["observation_id"])
        self.assertEqual(audit_rows[0]["replacement_observation_id"], res_forced["observation_id"])
        self.assertEqual(len(audit_rows[0]["dependent_updates"]), 1)
        self.assertEqual(audit_rows[0]["dependent_updates"][0]["instrument_id"], "SAV-FRSB-2020")

        # Subsequent un-forced baseline sync does NOT revert the rolled-back 7.60% rate to 7.70% (2026-10-01 < 2026-10-15)
        seed_baseline_savings_universe(force_overwrite=False)
        self.assertAlmostEqual(get_savings_instrument_by_id("SAV-NSC")["base_rate_pct"], 7.60, places=2)

        # Baseline re-import with force=True + reason + operator resets to baseline 7.70% while retaining all observations
        upsert_savings_instrument({**nsc, "base_rate_pct": 8.10, "effective_from": "2026-11-05"})
        run_apply(
            savings_db.BASELINE_SAVINGS_JSON_PATH,
            force=True,
            override_reason="Full baseline reseed after quarterly audit",
            override_operator="cli:rahul_sharma",
        )
        self.assertAlmostEqual(get_savings_instrument_by_id("SAV-NSC")["base_rate_pct"], 7.70, places=2)
        self.assertGreaterEqual(len(get_savings_rate_observations("SAV-NSC")), 5)

    def test_pkg01_peg_cascade_and_reconcile_never_move_dates_backwards(self) -> None:
        from core.db.savings import _reconcile_pegged_instruments

        # Set SAV-NSC to 2026-11-01 @ 8.00% (cascades FRSB to 2026-11-01 @ 8.35%)
        nsc = dict(get_savings_instrument_by_id("SAV-NSC"))
        upsert_savings_instrument({**nsc, "base_rate_pct": 8.00, "effective_from": "2026-11-01"})
        frsb_mid = get_savings_instrument_by_id("SAV-FRSB-2020")
        self.assertAlmostEqual(frsb_mid["base_rate_pct"], 8.35, places=2)
        self.assertEqual(frsb_mid["effective_from"], "2026-11-01")

        # Advance SAV-FRSB-2020 explicitly to a newer date (2026-11-05 @ 8.80%)
        upsert_savings_instrument({**frsb_mid, "base_rate_pct": 8.80, "effective_from": "2026-11-05"})

        # Both _reconcile_pegged_instruments() and a same-date SAV-NSC update on 2026-11-01 MUST NOT regress FRSB
        conn = get_db_connection()
        reconciled = _reconcile_pegged_instruments(conn)
        conn.commit()
        conn.close()
        self.assertEqual(reconciled, 0)

        upsert_savings_instrument({**nsc, "base_rate_pct": 8.05, "effective_from": "2026-11-01"})
        frsb_after = get_savings_instrument_by_id("SAV-FRSB-2020")
        self.assertEqual(frsb_after["effective_from"], "2026-11-05")
        self.assertAlmostEqual(frsb_after["base_rate_pct"], 8.80, places=2)

    def test_pkg01_official_hostname_issuer_whitelist_and_180_420_staleness_policy(self) -> None:
        nsc = dict(get_savings_instrument_by_id("SAV-NSC"))
        hdfc = dict(get_savings_instrument_by_id("FD-HDFC-35M"))
        sbi = dict(get_savings_instrument_by_id("FD-SBI-444D"))

        rejected_payloads = [
            {**nsc, "source_url": "https://invented-source.example/rates", "source_authority": "Invented authority"},
            {**nsc, "source_url": "https://dea.gov.in.attacker.example/rates"},
            {**sbi, "source_url": "https://fake-sbi.co.in/rates"},
            {**hdfc, "source_url": "https://sbi.co.in/web/interest-rates"},
            {**sbi, "source_authority": "Invented authority"},
            {**nsc, "source_url": "https://user:pass@dea.gov.in/rates"},
            {**nsc, "source_url": "https://dea.gov.in:8443/rates"},
        ]
        for bad in rejected_payloads:
            with self.assertRaises(ValueError):
                upsert_savings_instrument(bad)
            self.assertEqual(compute_staleness_badge(bad)["status"], "UNVERIFIED_PROVENANCE")

        # Verify agreed 180d / 420d + active review-window staleness thresholds
        stat_no_window = {
            **nsc,
            "effective_from": "2026-01-01",
            "next_review_date": None,
            "notes": {"last_tariff_verified_on": "2026-01-01"},
        }
        self.assertEqual(compute_staleness_badge(stat_no_window, reference_date="2026-05-15")["status"], "REVIEW_DUE")  # 134d > 95d, <= 180d
        self.assertEqual(compute_staleness_badge(stat_no_window, reference_date="2026-07-10")["status"], "STALE_TARIFF")  # 190d > 180d

        epf = dict(get_savings_instrument_by_id("SAV-EPF-VPF"))
        epf_no_window = {
            **epf,
            "effective_from": "2025-04-01",
            "next_review_date": None,
            "notes": {"last_tariff_verified_on": "2025-04-01"},
        }
        self.assertEqual(compute_staleness_badge(epf_no_window, reference_date="2026-05-01")["status"], "REVIEW_DUE")  # 395d > 365d, <= 420d
        self.assertEqual(compute_staleness_badge(epf_no_window, reference_date="2026-06-05")["status"], "STALE_TARIFF")  # 430d > 420d

    def test_pkg01_cli_check_mode_performs_zero_database_writes(self) -> None:
        import hashlib
        import sqlite3
        from scripts.import_savings_rates import build_check_report

        missing_db = Path(self._tmp_dir.name) / "nonexistent_check.db"
        with patch.dict(os.environ, {"TEST_DB_PATH": str(missing_db)}):
            rep = build_check_report(savings_db.BASELINE_SAVINGS_JSON_PATH)
        self.assertFalse(missing_db.exists())
        self.assertTrue(rep["read_only"])
        self.assertEqual(rep["active_db_count"], 0)
        self.assertEqual(rep["incoming_count"], 34)

        empty_db = Path(self._tmp_dir.name) / "empty_uninitialized.db"
        c = sqlite3.connect(str(empty_db))
        c.execute("CREATE TABLE untouched_marker (id INTEGER PRIMARY KEY);")
        c.commit()
        c.close()
        digest_before = hashlib.sha256(empty_db.read_bytes()).hexdigest()
        with patch.dict(os.environ, {"TEST_DB_PATH": str(empty_db)}):
            rep2 = build_check_report(savings_db.BASELINE_SAVINGS_JSON_PATH)
        digest_after = hashlib.sha256(empty_db.read_bytes()).hexdigest()
        self.assertEqual(digest_before, digest_after)
        self.assertEqual(rep2["active_db_count"], 0)

    def test_pkg01_material_non_rate_terms_and_evidence_revisions(self) -> None:
        from core.db.savings import get_savings_rate_observations

        sbi = dict(get_savings_instrument_by_id("FD-SBI-444D"))
        orig_obs = get_savings_rate_observations("FD-SBI-444D")
        self.assertEqual(len(orig_obs), 1)
        orig_obs_id = orig_obs[0]["observation_id"]
        orig_url = orig_obs[0]["source_url"]

        # Amending circular ref, source_url, and payout_options with unchanged rate (7.25%) creates revision_seq=2
        amended = {
            **sbi,
            "rate_circular_ref": "SBI-AMEND-2026-Q3-CORRIGENDUM",
            "source_url": "https://bank.sbi/web/interest-rates/deposit-rates/retail-domestic-term-deposits",
            "payout_options": ["CUMULATIVE", "QUARTERLY_PAYOUT", "MONTHLY_PAYOUT"],
            "premature_exit_rule": "0.50% penalty up to ₹5L; 1.00% above ₹5L",
        }
        res_amend = upsert_savings_instrument(amended, reference_date="2026-11-10")
        self.assertEqual(res_amend["status"], "TERMS_OR_EVIDENCE_UPDATED")
        self.assertFalse(res_amend["rate_changed"])
        self.assertTrue(res_amend["terms_changed"])
        self.assertEqual(res_amend["revision_seq"], 2)
        self.assertNotEqual(res_amend["observation_id"], orig_obs_id)

        # Re-submitting identical amended terms is idempotent (METADATA_SYNCED, no 3rd observation)
        res_idem = upsert_savings_instrument(amended, reference_date="2026-11-10")
        self.assertEqual(res_idem["status"], "METADATA_SYNCED")

        obs_after = get_savings_rate_observations("FD-SBI-444D")
        self.assertEqual(len(obs_after), 2)
        self.assertEqual(obs_after[0]["revision_seq"], 2)
        self.assertEqual(obs_after[0]["change_reason"], "TERMS_OR_EVIDENCE_AMENDMENT")
        self.assertEqual(obs_after[0]["rate_circular_ref"], "SBI-AMEND-2026-Q3-CORRIGENDUM")
        self.assertIsNone(obs_after[0]["superseded_at"])
        # Original observation retains its original URL and terms snapshot untouched
        self.assertEqual(obs_after[1]["observation_id"], orig_obs_id)
        self.assertEqual(obs_after[1]["source_url"], orig_url)
        self.assertEqual(obs_after[1]["superseded_by_observation_id"], obs_after[0]["observation_id"])

        # Subsequent baseline sync does NOT overwrite the amended URL or payout_options
        seed_baseline_savings_universe(force_overwrite=False)
        sbi_now = get_savings_instrument_by_id("FD-SBI-444D")
        self.assertEqual(
            sbi_now["source_url"],
            "https://bank.sbi/web/interest-rates/deposit-rates/retail-domestic-term-deposits",
        )
        self.assertEqual(
            sbi_now["payout_options"],
            ["CUMULATIVE", "QUARTERLY_PAYOUT", "MONTHLY_PAYOUT"],
        )

    def test_pkg01_future_dated_rates_scheduled_and_activated(self) -> None:
        from core.db.savings import activate_due_future_savings_rates, get_savings_rate_observations

        nsc = dict(get_savings_instrument_by_id("SAV-NSC", reference_date="2026-11-10"))
        self.assertAlmostEqual(nsc["base_rate_pct"], 7.70, places=2)

        # Announce Q4 FY27 rate (7.95% w.e.f. 2027-01-01) while current date is 2026-11-10
        nsc_future = {
            **nsc,
            "base_rate_pct": 7.95,
            "effective_from": "2027-01-01",
            "rate_circular_ref": "DEA-Q4-FY27-ADVANCE",
        }
        res_sched = upsert_savings_instrument(nsc_future, reference_date="2026-11-10")
        self.assertEqual(res_sched["status"], "SCHEDULED_FUTURE_RATE")
        self.assertFalse(res_sched["rate_changed"])
        self.assertEqual(res_sched["scheduled_for"], "2027-01-01")

        # Current selection (2026-11-10) MUST remain 7.70% (SAV-FRSB-2020 remains 8.05%)
        cur_nsc = get_savings_instrument_by_id("SAV-NSC", reference_date="2026-11-10")
        cur_frsb = get_savings_instrument_by_id("SAV-FRSB-2020", reference_date="2026-11-10")
        self.assertAlmostEqual(cur_nsc["base_rate_pct"], 7.70, places=2)
        self.assertEqual(cur_nsc["effective_from"], "2026-10-01")
        self.assertIsNotNone(cur_nsc["scheduled_future_rate"])
        self.assertAlmostEqual(cur_nsc["scheduled_future_rate"]["base_rate_pct"], 7.95, places=2)
        self.assertAlmostEqual(cur_frsb["base_rate_pct"], 8.05, places=2)

        # Point-in-time future query (2027-01-05) selects 7.95% (+35 bps -> 8.30%) without mutating today's active row
        pit_nsc = get_savings_instrument_by_id("SAV-NSC", reference_date="2027-01-05")
        pit_frsb = get_savings_instrument_by_id("SAV-FRSB-2020", reference_date="2027-01-05")
        self.assertAlmostEqual(pit_nsc["base_rate_pct"], 7.95, places=2)
        self.assertAlmostEqual(pit_frsb["base_rate_pct"], 8.30, places=2)
        self.assertAlmostEqual(
            get_savings_instrument_by_id("SAV-NSC", reference_date="2026-11-10")["base_rate_pct"],
            7.70,
            places=2,
        )

        # Explicit activation on 2027-01-01 promotes SCHEDULED_FUTURE -> ACTIVE and cascades SAV-FRSB-2020
        act_res = activate_due_future_savings_rates(reference_date="2027-01-01")
        self.assertGreaterEqual(act_res["activated_count"], 1)
        self.assertIn("SAV-NSC", act_res["activated_ids"])

        obs_list = get_savings_rate_observations("SAV-NSC")
        jan_obs = next(o for o in obs_list if o["effective_from"] == "2027-01-01" and o["superseded_at"] is None)
        oct_obs = next(o for o in obs_list if o["effective_from"] == "2026-10-01" and o["superseded_at"] is None)
        self.assertEqual(jan_obs["observation_status"], "ACTIVE")
        self.assertEqual(oct_obs["effective_to"], "2027-01-01")
        self.assertEqual(oct_obs["observation_status"], "HISTORICAL")

    def test_pkg01_scoped_page_level_evidence_colocation(self) -> None:
        from core.db.savings import _PUBLIC_RATE_PROBES, extract_scoped_portal_rate_evidence

        ppf_probe = next(p for p in _PUBLIC_RATE_PROBES if p["instrument_id"] == "SAV-PPF")

        # 1. Cross-section page where banner has a w.e.f. date and PPF div has only a rate -> MUST reject!
        cross_section_html = """
        <div class="site-banner">Portal maintenance completed w.e.f. 2026-11-01</div>
        <div class="scheme-card">Public Provident Fund (PPF): 7.50% p.a. compounded annually.</div>
        """
        ev_cross = extract_scoped_portal_rate_evidence(cross_section_html, ppf_probe)
        self.assertFalse(ev_cross["valid"])
        self.assertEqual(ev_cross["reason"], "MISSING_OR_UNSCOPED_EFFECTIVE_DATE")
        self.assertAlmostEqual(ev_cross["parsed_rate"], 7.50, places=2)

        # 2. Combined unscoped block containing two rival schemes -> MUST reject!
        rival_block_html = """
        <div>Public Provident Fund: 7.50% p.a. and National Savings Certificate: 7.90% p.a. w.e.f. 01.11.2026</div>
        """
        ev_rival = extract_scoped_portal_rate_evidence(rival_block_html, ppf_probe)
        self.assertFalse(ev_rival["valid"])
        self.assertEqual(ev_rival["reason"], "RIVAL_SCHEME_IN_SAME_BLOCK")

        # 3. Block with two conflicting effective dates -> MUST reject!
        conflict_dates_html = """
        <div>Public Provident Fund (PPF): 7.50% p.a. w.e.f. 01.11.2026 (superseding w.e.f. 01.10.2026)</div>
        """
        ev_conf = extract_scoped_portal_rate_evidence(conflict_dates_html, ppf_probe)
        self.assertFalse(ev_conf["valid"])
        self.assertEqual(ev_conf["reason"], "CONFLICTING_EFFECTIVE_DATES_IN_BLOCK")

        # 4. Valid co-located notification row -> accepted with deterministic evidence_sha256
        valid_html = """
        <table>
          <caption>Small Savings Interest Rates w.e.f. 01.11.2026 (DEA Circular)</caption>
          <tbody>
            <tr><td>Public Provident Fund (PPF)</td><td>7.50% p.a.</td></tr>
            <tr><td>National Savings Certificate (NSC)</td><td>7.90% p.a.</td></tr>
          </tbody>
        </table>
        """
        ev_ok = extract_scoped_portal_rate_evidence(valid_html, ppf_probe)
        self.assertTrue(ev_ok["valid"])
        self.assertAlmostEqual(ev_ok["parsed_rate"], 7.50, places=2)
        self.assertEqual(ev_ok["effective_from"], "2026-11-01")
        self.assertEqual(len(ev_ok["evidence_sha256"]), 64)

    def test_pkg01_failure_recovery_rollback_and_replay_invariants(self) -> None:
        from core.db.savings import get_savings_rate_observations, reconcile_savings_schema_and_legacy_tables

        # (a) Interrupted migration / validation failure rolls back cleanly without dropping legacy tables
        conn = get_db_connection()
        cur = conn.cursor()
        with patch(
            "core.db.savings._verify_legacy_preservation_on_cursor",
            return_value={"valid": False, "errors": ["Simulated mid-migration preservation mismatch"]},
        ):
            with self.assertRaises(RuntimeError):
                reconcile_savings_schema_and_legacy_tables(cur, is_pg=False)
        conn.rollback()
        cur.close()
        conn.close()

        # (b) Simulated worker failure mid-inbox-batch rolls back partial writes and retains file in inbox/ for retry
        tmp_inbox = Path(self._tmp_dir.name) / "inbox_recovery"
        tmp_inbox.mkdir(parents=True, exist_ok=True)
        batch_file = tmp_inbox / "atomic_batch.json"
        # Item 1 is valid (FD-SBI-444D -> 7.45%), Item 2 has invalid vendor provenance (causes mid-batch failure)
        batch_file.write_text(
            json.dumps(
                {
                    "instruments": [
                        {
                            "instrument_id": "FD-SBI-444D",
                            "base_rate_pct": 7.45,
                            "effective_from": "2026-11-05",
                            "source_authority": "State Bank of India Retail Term Deposit Tariff",
                            "source_url": "https://sbi.co.in/web/interest-rates/deposit-rates/retail-domestic-term-deposits",
                        },
                        {
                            "instrument_id": "SAV-PPF",
                            "base_rate_pct": 7.50,
                            "effective_from": "2026-11-05",
                            "source_authority": "ValueResearch Aggregator",
                            "source_url": "https://www.valueresearchonline.com/rates",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        with patch.object(savings_db, "SAVINGS_INBOX_DIR", tmp_inbox):
            res_fail = verify_and_sync_automated_savings_rates(
                edition_date="2026-11-10", allow_network=False
            )
        self.assertEqual(res_fail["inbox_files_processed"], 0)
        self.assertEqual(res_fail["inbox_files_failed"], 1)
        self.assertTrue(batch_file.exists(), "Failed inbox file must stay in inbox/ for retry!")
        # Verify Item 1 was rolled back (FD-SBI-444D stayed at baseline 7.25%)
        self.assertAlmostEqual(get_savings_instrument_by_id("FD-SBI-444D")["base_rate_pct"], 7.25, places=2)

        # Fix Item 2 in the inbox file and retry -> succeeds and archives to processed/
        batch_file.write_text(
            json.dumps(
                {
                    "instruments": [
                        {
                            "instrument_id": "FD-SBI-444D",
                            "base_rate_pct": 7.45,
                            "effective_from": "2026-11-05",
                            "source_authority": "State Bank of India Retail Term Deposit Tariff",
                            "source_url": "https://sbi.co.in/web/interest-rates/deposit-rates/retail-domestic-term-deposits",
                        },
                        {
                            "instrument_id": "SAV-PPF",
                            "base_rate_pct": 7.35,
                            "effective_from": "2026-11-05",
                            "source_authority": "Department of Economic Affairs (DEA), Ministry of Finance",
                            "source_url": "https://dea.gov.in/small-savings-rates",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        with patch.object(savings_db, "SAVINGS_INBOX_DIR", tmp_inbox):
            res_retry = verify_and_sync_automated_savings_rates(
                edition_date="2026-11-10", allow_network=False
            )
        self.assertEqual(res_retry["inbox_files_processed"], 1)
        self.assertEqual(res_retry["inbox_files_failed"], 0)
        self.assertFalse(batch_file.exists())
        self.assertAlmostEqual(get_savings_instrument_by_id("FD-SBI-444D")["base_rate_pct"], 7.45, places=2)
        self.assertAlmostEqual(get_savings_instrument_by_id("SAV-PPF")["base_rate_pct"], 7.35, places=2)

        # (c) Transaction rollback when pegged cascade fails mid-upsert leaves benchmark & observations untouched
        nsc_before = get_savings_instrument_by_id("SAV-NSC")
        obs_cnt_before = len(get_savings_rate_observations("SAV-NSC"))
        with patch(
            "core.db.savings._cascade_pegged_dependents_on_cursor",
            side_effect=RuntimeError("Simulated mid-transaction peg cascade failure"),
        ):
            with self.assertRaises(RuntimeError):
                upsert_savings_instrument(
                    {**nsc_before, "base_rate_pct": 8.20, "effective_from": "2026-11-08"}
                )
        self.assertAlmostEqual(
            get_savings_instrument_by_id("SAV-NSC")["base_rate_pct"],
            nsc_before["base_rate_pct"],
            places=2,
        )
        self.assertEqual(len(get_savings_rate_observations("SAV-NSC")), obs_cnt_before)

        # (d) 3x duplicate replay idempotency
        valid_upd = {**nsc_before, "base_rate_pct": 7.85, "effective_from": "2026-11-08", "rate_circular_ref": "DEA-IDEM-1"}
        r_first = upsert_savings_instrument(valid_upd)
        obs_after_first = get_savings_rate_observations("SAV-NSC")
        for _ in range(3):
            r_dup = upsert_savings_instrument(valid_upd)
            self.assertEqual(r_dup["observation_id"], r_first["observation_id"])
        self.assertEqual(len(get_savings_rate_observations("SAV-NSC")), len(obs_after_first))


if __name__ == "__main__":
    unittest.main()
