"""
Adversarial Stress-Testing Harness for All Engines
===================================================
Runs pathological, extreme, malformed, negative, NaN, Inf, and corrupt inputs 
against every analytical and cortex engine in the application to uncover failure modes.
"""

import sys
import os
import math
import traceback

# Ensure workspace root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

failures = []
passed = 0


def record_result(engine_name: str, test_case: str, success: bool, error: str = ""):
    global passed
    if success:
        passed += 1
        print(f"  [PASS] {test_case}")
    else:
        failures.append((engine_name, test_case, error))
        print(f"  [FAIL] {test_case} -> {error}")


print("=" * 80)
print("STARTING ADVERSARIAL STRESS TESTING ACROSS ALL ENGINES")
print("=" * 80)

# -------------------------------------------------------------------------
# 1. Angel One Gateway
# -------------------------------------------------------------------------
print("\n--- 1. Testing AngelOneGateway ---")
from core.ingestion.angel_one import AngelOneGateway, generate_rfc6238_totp

test_totp_cases = [
    ("None secret", None),
    ("Empty secret", ""),
    ("Non-base32 chars", "1289!@#$%^&*()_+~"),
    ("Lowercase with spaces", "   xsmb nohd 4mre woac r7kd 7bs3 zq  "),
    ("Non-string integer secret", 12345678),
]
for name, sec in test_totp_cases:
    try:
        res = generate_rfc6238_totp(sec)
        record_result("AngelOne.totp", name, True)
    except Exception as e:
        record_result("AngelOne.totp", name, False, str(e))

test_depth_cases = [
    ("None books", None, None),
    ("Empty books", [], []),
    ("Malformed book items", [None, "string", 123], [{}]),
    ("String values with commas & N/A", [{"price": "1,450.50", "quantity": "N/A"}], [{"price": "1,452.00", "quantity": "100"}]),
    ("NaN and Inf in depth", [{"price": float("nan"), "quantity": float("inf")}], [{"price": float("-inf"), "quantity": 0}]),
]
for name, b1, b2 in test_depth_cases:
    try:
        res = AngelOneGateway.compute_depth_analytics(b1, b2)
        record_result("AngelOne.depth", name, True)
    except Exception as e:
        record_result("AngelOne.depth", name, False, str(e))


# -------------------------------------------------------------------------
# 2. Garuda Reflex Engine
# -------------------------------------------------------------------------
print("\n--- 2. Testing GarudaReflexEngine ---")
from core.cortex.garuda import GarudaReflexEngine

test_garuda_cases = [
    ("None headline", "INFY", None, "", ""),
    ("Non-string symbol and headline", 12345, 67890, None, None),
    ("Empty headline with unicode", "", "🚀🔥 Quarterly Result 100% Dividend", "2026-10-10", "https://bse.com"),
    ("Huge text headline", "TCS", "Dividend " * 5000, "2026-10-10", ""),
]
for name, sym, hl, dt, url in test_garuda_cases:
    try:
        res = GarudaReflexEngine.classify_announcement(sym, hl, dt, url)
        record_result("Garuda.classify", name, True)
    except Exception as e:
        record_result("Garuda.classify", name, False, str(e))

test_feed_cases = [
    ("None feed", "INFY", None),
    ("Malformed feed with non-dicts", "TCS", [None, "string", 12345, {"headline": None}]),
    ("Empty dict elements", "RELIANCE", [{}, {}]),
]
for name, sym, feed in test_feed_cases:
    try:
        res = GarudaReflexEngine.process_feed(sym, feed)
        record_result("Garuda.feed", name, True)
    except Exception as e:
        record_result("Garuda.feed", name, False, str(e))


# -------------------------------------------------------------------------
# 3. Varan Engine
# -------------------------------------------------------------------------
print("\n--- 3. Testing VaranEngine ---")
from core.cortex.varan import VaranEngine

test_varan_dupont_cases = [
    ("Normal profitable", 1000.0, 5000.0, 8000.0, 4000.0),
    ("Zero sales & assets", 100.0, 0.0, 0.0, 0.0),
    ("Negative net worth / insolvent", 50.0, 500.0, 1000.0, -250.0),
    ("Negative profit & negative equity", -500.0, 200.0, 800.0, -1000.0),
    ("NaN and Inf", float("nan"), float("inf"), 1000.0, 500.0),
]
for name, p, s, a, e in test_varan_dupont_cases:
    try:
        res = VaranEngine.decompose_dupont(p, s, a, e)
        record_result("Varan.dupont", name, True)
    except Exception as e:
        record_result("Varan.dupont", name, False, str(e))

test_varan_wc_cases = [
    ("Zero sales and zero cogs", 10.0, 10.0, 10.0, 0.0, 0.0),
    ("Negative receivables/payables", -50.0, 20.0, -100.0, 100.0, 80.0),
    ("NaN inputs in working capital", float("nan"), 10.0, 10.0, 100.0, 50.0),
]
for name, ar, inv, ap, s, cogs in test_varan_wc_cases:
    try:
        res = VaranEngine.compute_working_capital_cycle(ar, inv, ap, s, cogs)
        record_result("Varan.working_capital", name, True)
    except Exception as e:
        record_result("Varan.working_capital", name, False, str(e))

test_varan_delta_cases = [
    ("Empty annual lists", "TEST", [], [], [], [], [], {}),
    ("None balance sheet", "TEST", [100.0], [20.0], [10.0], [8.0], [2.0], None),
    ("Mismatched lengths with negative numbers", "TEST", [100.0, -50.0, 200.0], [10.0], [-20.0, 30.0], [], [5.0], {"total_equity_cr": -50.0}),
    ("String / invalid values in balance sheet", "TEST", [100.0], [20.0], [10.0], [8.0], [2.0], {"total_assets_cr": "invalid", "total_debt_cr": None}),
]
for name, sym, rev, eb, pat, cfo, cap, bs in test_varan_delta_cases:
    try:
        res = VaranEngine.compile_delta_packet(sym, rev, eb, pat, cfo, cap, bs)
        record_result("Varan.delta_packet", name, True)
    except Exception as e:
        record_result("Varan.delta_packet", name, False, str(e))


# -------------------------------------------------------------------------
# 4. Sutra Look-Through Engine
# -------------------------------------------------------------------------
print("\n--- 4. Testing SutraLookThroughEngine ---")
from core.cortex.sutra import SutraLookThroughEngine

test_sutra_cases = [
    ("None portfolios", None, None, None),
    ("Empty portfolios", [], [], []),
    ("Non-dict elements in lists", [None, "str", 123], [{"scheme_key": "PPFAS_FLEXICAP", "value_inr": 10000}], [None]),
    ("String values with commas & negative values", [{"symbol": "INFY", "value_inr": "50,000"}], [{"scheme_key": "HDFC_TOP100", "value_inr": -5000}], [{"asset_type": "GSEC", "value_inr": "N/A"}]),
    ("Total portfolio value zero", [{"symbol": "INFY", "value_inr": 0}], [], []),
    ("All assets negative", [{"symbol": "INFY", "value_inr": -10000}], [], []),
]
for name, eq, mf, fi in test_sutra_cases:
    try:
        res = SutraLookThroughEngine.audit_portfolio(eq, mf, fi)
        record_result("Sutra.audit_portfolio", name, True)
    except Exception as e:
        record_result("Sutra.audit_portfolio", name, False, str(e))


# -------------------------------------------------------------------------
# 5. Valuation Radar
# -------------------------------------------------------------------------
print("\n--- 5. Testing ValuationRadar ---")
from core.analysis.valuation_radar import compute_valuation_radar

test_radar_cases = [
    ("Zero price", 0.0, 20.0),
    ("Negative price", -150.0, 20.0),
    ("NaN price and PE", float("nan"), float("nan")),
    ("Inf price", float("inf"), 20.0),
    ("Equal discount and terminal growth rate (ZeroDivisionError)", 1000.0, 25.0, 40.0, 10.0, 20.0, 200.0, 0.05, 0.05),
    ("Discount rate less than terminal growth rate (Inversion)", 1000.0, 25.0, 40.0, 10.0, 20.0, 200.0, 0.03, 0.06),
    ("Zero discount rate", 1000.0, 25.0, 40.0, 10.0, 20.0, 200.0, 0.0, 0.04),
    ("Negative discount rate", 1000.0, 25.0, 40.0, 10.0, 20.0, 200.0, -0.05, 0.04),
    ("None EPS and negative PE", 500.0, -15.0, None, -5.0),
]
for item in test_radar_cases:
    name = item[0]
    args = item[1:]
    try:
        res = compute_valuation_radar(*args)
        record_result("ValuationRadar", name, True)
    except Exception as e:
        record_result("ValuationRadar", name, False, str(e))


# -------------------------------------------------------------------------
# 6. Sector Scoring
# -------------------------------------------------------------------------
print("\n--- 6. Testing SectorScoring ---")
from core.analysis.sector_scoring import detect_sector, evaluate_sector_fundamentals

test_detect_cases = [
    ("None ticker", None),
    ("Int ticker", 12345),
    ("Empty ticker with long industry text", "", "Banking and Financial NBFC lending"),
]
for name, t in test_detect_cases[:2]:
    try:
        res = detect_sector(t)
        record_result("SectorScoring.detect", name, True)
    except Exception as e:
        record_result("SectorScoring.detect", name, False, str(e))

test_sector_eval_cases = [
    ("None fundamentals", "INFY", None),
    ("Empty fundamentals", "TCS", {}),
    ("String / comma / N/A values in fundamentals", "HDFCBANK", {"roce": "N/A", "roe": "18.5%", "pe_ratio": "25,00", "debt_to_equity": None}),
    ("NaN in fundamentals", "SBIN", {"roce": float("nan"), "roe": float("inf")}),
]
for name, sym, fund in test_sector_eval_cases:
    try:
        res = evaluate_sector_fundamentals(sym, fund)
        record_result("SectorScoring.evaluate", name, True)
    except Exception as e:
        record_result("SectorScoring.evaluate", name, False, str(e))


# -------------------------------------------------------------------------
# 7. Institutional Flow
# -------------------------------------------------------------------------
print("\n--- 7. Testing InstitutionalFlow ---")
from core.analysis.institutional_flow import analyze_institutional_flow

test_flow_cases = [
    ("None quote data", None),
    ("Non-dict quote data", "string_data"),
    ("String and comma values in quote data", {"ltp": "1,450.25", "total_buy_qty": "10,000", "order_imbalance_ratio": "N/A"}),
    ("NaN and Inf in quote data", {"ltp": float("nan"), "order_imbalance_ratio": float("nan"), "bid_ask_spread_bps": float("inf")}),
    ("Zero and negative prices", {"ltp": -100.0, "lower_circuit": -110.0, "upper_circuit": -90.0}),
]
for name, q in test_flow_cases:
    try:
        res = analyze_institutional_flow(q)
        record_result("InstitutionalFlow", name, True)
    except Exception as e:
        record_result("InstitutionalFlow", name, False, str(e))


# -------------------------------------------------------------------------
# 8. Forensic Sieve
# -------------------------------------------------------------------------
print("\n--- 8. Testing ForensicSieve ---")
from core.analysis.forensic_sieve import evaluate_forensic_sieve
from core.cortex.chanakya import ChanakyaGate

test_sieve_cases = [
    ("None fundamentals", "INFY", None),
    ("Empty fundamentals", "TCS", {}),
    ("String and N/A values", "RELIANCE", {"operating_cash_flow_cr": "N/A", "ebitda_cr": "invalid", "market_cap_cr": "1,500,000"}),
    ("NaN in fundamentals", "WIPRO", {"operating_cash_flow_cr": float("nan"), "ebitda_cr": float("nan")}),
]
for name, sym, fund in test_sieve_cases:
    try:
        res = evaluate_forensic_sieve(sym, fund)
        record_result("ForensicSieve", name, True)
    except Exception as e:
        record_result("ForensicSieve", name, False, str(e))


# -------------------------------------------------------------------------
# 9. Bull Bear Thesis
# -------------------------------------------------------------------------
print("\n--- 9. Testing BullBearThesis ---")
from core.analysis.bull_bear import synthesize_bull_bear_thesis

test_bull_bear_cases = [
    ("None fundamentals", "INFY", None),
    ("Empty fundamentals", "TCS", {}),
    ("Corrupt valuation data with non-numeric fair_value", "HDFCBANK", {"roce": 15.0}, None, {"margin_of_safety_pct": 15.0, "fair_value": "N/A"}),
    ("String and comma values", "SBIN", {"roce": "20.5", "roe": "18.2", "debt_to_equity": "0.15"}),
]
for item in test_bull_bear_cases:
    name = item[0]
    sym = item[1]
    fund = item[2]
    sec = item[3] if len(item) > 3 else None
    val = item[4] if len(item) > 4 else None
    try:
        res = synthesize_bull_bear_thesis(sym, fund, valuation_data=val)
        record_result("BullBear", name, True)
    except Exception as e:
        record_result("BullBear", name, False, str(e))


# -------------------------------------------------------------------------
# 10. Setu Matrix Engine
# -------------------------------------------------------------------------
print("\n--- 10. Testing SetuMatrixEngine ---")
from core.cortex.setu import SetuMatrixEngine

test_setu_cases = [
    ("None symbol and rating", None, 5.0, None, None),
    ("String rating not in spread map", "INFY", 6.5, None, "UNKNOWN_RATING"),
    ("NaN yields", "TCS", float("nan"), float("nan")),
    ("Negative and zero tax slab", "RELIANCE", 4.0, 8.5, "AAA", 7.05, 0.0, 0.0, -10.0),
]
for item in test_setu_cases:
    name = item[0]
    args = item[1:]
    try:
        res = SetuMatrixEngine.evaluate(*args)
        record_result("SetuMatrix", name, True)
    except Exception as e:
        record_result("SetuMatrix", name, False, str(e))


# -------------------------------------------------------------------------
# 11. Anvik Cortex Engine (engine.py)
# -------------------------------------------------------------------------
print("\n--- 11. Testing Cortex Engine (DynamicStatutoryYieldWedge, ReverseDcf, PEAD, Fiduciary) ---")
from core.cortex.engine import (
    DynamicStatutoryYieldWedge,
    ReverseDcfHurdleDeconstruct,
    PeadQuantDriftVelocity,
    FiduciaryGovernanceScoringIndex,
)

test_cortex_cases = [
    ("YieldWedge with zero EV and negative cash", DynamicStatutoryYieldWedge.evaluate, ("TEST", -500.0, 200.0, 0.0)),
    ("YieldWedge with NaN", DynamicStatutoryYieldWedge.evaluate, ("TEST", float("nan"), 10.0, 100.0)),
    ("ReverseDCF with zero FCF", ReverseDcfHurdleDeconstruct.evaluate, ("TEST", 1500.0, 0.0)),
    ("ReverseDCF with NaN price", ReverseDcfHurdleDeconstruct.evaluate, ("TEST", float("nan"), 50.0)),
    ("ReverseDCF with negative FCF", ReverseDcfHurdleDeconstruct.evaluate, ("TEST", 1500.0, -25.0)),
    ("PEAD with zero volume and zero PAT", PeadQuantDriftVelocity.evaluate, ("TEST", 0.0, 0.0, 0.0, 0.0, 0.0)),
    ("PEAD with NaN PAT", PeadQuantDriftVelocity.evaluate, ("TEST", float("nan"), 100.0, 5000.0, 1000.0, 50.0)),
    ("Fiduciary with extreme 100% RPT and pledge", FiduciaryGovernanceScoringIndex.evaluate, ("TEST", 100.0, 100.0, 50.0, 0.0, 200.0, True)),
]
for name, fn, args in test_cortex_cases:
    try:
        res = fn(*args)
        record_result("CortexEngine", name, True)
    except Exception as e:
        record_result("CortexEngine", name, False, str(e))


# -------------------------------------------------------------------------
# 12. Tax Calculator Engine
# -------------------------------------------------------------------------
print("\n--- 12. Testing TaxCalculator ---")
from core.analysis.tax_calculator import calculate_net_real_return, compare_asset_classes_post_tax

test_tax_cases = [
    ("Inflation -100% (Division by zero)", -100.0),
    ("Extreme inflation 1000%", 1000.0),
    ("Tax slab 100%", 30.0, 100.0),
    ("NaN inflation", float("nan")),
]
for item in test_tax_cases:
    name = item[0]
    args = item[1:]
    try:
        if len(args) == 1:
            res = calculate_net_real_return(10.0, 30.0, args[0])
        else:
            res = calculate_net_real_return(args[0], args[1])
        record_result("TaxCalculator", name, True)
    except Exception as e:
        record_result("TaxCalculator", name, False, str(e))

try:
    res = compare_asset_classes_post_tax(marginal_tax_slab_pct=float("nan"))
    record_result("TaxCalculator", "compare_asset_classes with NaN slab", True)
except Exception as e:
    record_result("TaxCalculator", "compare_asset_classes with NaN slab", False, str(e))


print("\n" + "=" * 80)
print(f"ADVERSARIAL STRESS TEST SUMMARY: {passed} PASSED, {len(failures)} FAILED")
print("=" * 80)
if failures:
    print("\nFAILURES IDENTIFIED:")
    for eng, name, err in failures:
        print(f"  • [{eng}] {name}: {err}")
else:
    print("\nALL ENGINES RESILIENT TO ADVERSARIAL STRESS!")
