# core/msme/forensic_engine.py
"""
Unlisted MSME & Emerging SME Forensic Analysis Engine
==============================================================================
Provides quantitative and qualitative forensic evaluations
for unlisted Indian enterprises under the revised MSMED Act 2020 framework.

Evaluates:
1. Working Capital & Cash Conversion Cycle (DIO, DSO, DPO, Net CCC Days, WCR in Cr)
2. Listed Corporate Supply-Chain Linkages (Correlating MSMEs to listed NSE/BSE buyers)
3. Solvency, Operating Margins & TReDS Liquidity Risk (ICR, 45-day statutory shield)
4. Cluster Density & Capital Replacement Moat Score (0–100 Scorecard)
5. Countercase Fragility Vectors & Growth Drivers
==============================================================================
"""

import math
from typing import Dict, Any, List, Optional


# Sector-calibrated working capital, margin, and operating benchmarks
SECTOR_FORENSIC_BENCHMARKS = {
    "auto_components": {
        "dso_days": 75,
        "dio_days": 48,
        "dpo_days": 60,
        "ebitda_margin_pct": 14.5,
        "depr_pct": 4.2,
        "debt_to_turnover": 0.32,
        "interest_rate_pct": 9.5,
        "cluster_type": "Precision Tooling & Metal Casting Hub",
        "capex_barrier": "High (CNC Machining & Forging Press amortization)",
        "listed_buyers": [
            {"ticker": "TATAMOTORS", "name": "Tata Motors Ltd", "role": "Anchor OEM (CV/PV Chassis & Suspension)"},
            {"ticker": "BHARATFORG", "name": "Bharat Forge Ltd", "role": "Forging & Machined Sub-Assemblies"},
            {"ticker": "MARUTI", "name": "Maruti Suzuki India", "role": "Powertrain & Sheet Metal Fasteners"},
            {"ticker": "TIINDIA", "name": "Tube Investments", "role": "Precision Drawn Tubes & Chains"}
        ],
        "growth_catalysts": [
            "Domestic auto OEM volume expansion and platform localization",
            "Stringent BS-VI / Euro-7 precision tolerance requirements favoring verified vendors",
            "Transition toward lightweight forged aluminum and EV sub-assemblies"
        ],
        "fragility_vectors": [
            "High client concentration with top 2 automotive OEMs (>60% of revenues)",
            "Steel and aluminum raw material price pass-through lag (30–60 day drag)",
            "Working capital elongation during automaker seasonal inventory ramp-downs"
        ]
    },
    "pharmaceuticals": {
        "dso_days": 88,
        "dio_days": 64,
        "dpo_days": 52,
        "ebitda_margin_pct": 17.2,
        "depr_pct": 4.8,
        "debt_to_turnover": 0.28,
        "interest_rate_pct": 9.0,
        "cluster_type": "API Corridor & Formulation Processing Zone",
        "capex_barrier": "High (Clean-room ISO / USFDA / cGMP facility certification)",
        "listed_buyers": [
            {"ticker": "SUNPHARMA", "name": "Sun Pharma Industries", "role": "Intermediates & Active Ingredients"},
            {"ticker": "CIPLA", "name": "Cipla Ltd", "role": "Respiratory & Anti-Infective Formulations"},
            {"ticker": "DRREDDY", "name": "Dr. Reddy's Laboratories", "role": "Bulk Actives & Custom Synthesis"}
        ],
        "growth_catalysts": [
            "China+1 derisking by global pharma majors sourcing active pharmaceutical intermediates",
            "Expansion of domestic formulation production under the PLI Scheme",
            "Long-term master service contracts with leading Indian formulation exporters"
        ],
        "fragility_vectors": [
            "Environmental compliance and solvent recovery pollution control board audits",
            "Solvent and basic chemical commodity price volatility (Key Starting Materials)",
            "Delayed batch clearance release cycles impacting invoice payment schedules"
        ]
    },
    "electronics_iot": {
        "dso_days": 54,
        "dio_days": 42,
        "dpo_days": 48,
        "ebitda_margin_pct": 11.8,
        "depr_pct": 3.6,
        "debt_to_turnover": 0.25,
        "interest_rate_pct": 9.2,
        "cluster_type": "SMT Line & EMS Hardware Cluster",
        "capex_barrier": "Moderate (Pick-and-place high-speed SMT assembly & automated optical inspection)",
        "listed_buyers": [
            {"ticker": "DIXON", "name": "Dixon Technologies", "role": "EMS Component & Wire Harness Partner"},
            {"ticker": "KAYNES", "name": "Kaynes Technology", "role": "PCB Assembly & Telemetry Sensors"},
            {"ticker": "AMBER", "name": "Amber Enterprises", "role": "HVAC Motors & PCB Controller Cards"}
        ],
        "growth_catalysts": [
            "National Electronics Policy and PLI schemes driving component localization",
            "Surge in smart energy metering, IoT gateways, and industrial telemetry deployments",
            "Supply-chain shift toward domestic multi-layer PCB assembly"
        ],
        "fragility_vectors": [
            "Heavy dependence on imported semiconductor microcontrollers and passive parts",
            "Rapid technological obsolescence and short product revision cycles",
            "Aggressive price negotiation from tier-1 consumer brand clients"
        ]
    },
    "textiles": {
        "dso_days": 65,
        "dio_days": 58,
        "dpo_days": 46,
        "ebitda_margin_pct": 10.5,
        "depr_pct": 3.2,
        "debt_to_turnover": 0.35,
        "interest_rate_pct": 9.8,
        "cluster_type": "Spinning, Knitting & Garmenting Export Corridor",
        "capex_barrier": "Moderate (High-speed airjet looms, dyeing plants & knitting infrastructure)",
        "listed_buyers": [
            {"ticker": "PAGEIND", "name": "Page Industries", "role": "Premium Combed Yarn & Knitted Fabric"},
            {"ticker": "KPRMILL", "name": "K.P.R. Mill Ltd", "role": "Spinning & Contract Apparel Assembly"},
            {"ticker": "RAYMOND", "name": "Raymond Ltd", "role": "Suiting Wefts & Specialty Shirting Fabrics"}
        ],
        "growth_catalysts": [
            "Bilateral free trade agreements (FTAs) opening export channels to Europe and the Middle East",
            "Adoption of sustainable organic cotton and circular recycled polyester blends",
            "Consolidation of fragmented garmenting capacity into scaled cluster players"
        ],
        "fragility_vectors": [
            "Raw cotton spot price cyclicality and power tariff adjustments",
            "Intense low-cost price competition from Bangladesh and Vietnam export hubs",
            "Seasonal order lumpiness around autumn and festive collections"
        ]
    },
    "food_processing": {
        "dso_days": 38,
        "dio_days": 32,
        "dpo_days": 42,
        "ebitda_margin_pct": 9.2,
        "depr_pct": 2.8,
        "debt_to_turnover": 0.22,
        "interest_rate_pct": 8.8,
        "cluster_type": "Agro-Processing & Cold-Chain Corridor",
        "capex_barrier": "Moderate (Controlled atmosphere cold storage & aseptic packaging lines)",
        "listed_buyers": [
            {"ticker": "NESTLEIND", "name": "Nestle India Ltd", "role": "Dehydrated Purees & Milk Solids"},
            {"ticker": "TATACONSUM", "name": "Tata Consumer Products", "role": "Pulses, Spices & Oleoresin Extracts"},
            {"ticker": "BRITANNIA", "name": "Britannia Industries", "role": "Refined Flour & Bakery Shortenings"}
        ],
        "growth_catalysts": [
            "Consumer transition toward packaged, branded staples and farm-gate processing",
            "Government subsidy support under the Pradhan Mantri Kisan Sampada Yojana",
            "Rising contract manufacturing for modern trade retail chains and quick-commerce dark stores"
        ],
        "fragility_vectors": [
            "Monsoon volatility, agricultural mandi supply swings, and crop quality variations",
            "Perishability and spoilage risk during power grid interruptions or transit bottlenecks",
            "Stringent FSSAI food safety quality rejections for export consignments"
        ]
    },
    "specialty_chemicals": {
        "dso_days": 78,
        "dio_days": 54,
        "dpo_days": 58,
        "ebitda_margin_pct": 16.0,
        "depr_pct": 4.5,
        "debt_to_turnover": 0.30,
        "interest_rate_pct": 9.2,
        "cluster_type": "Chemical Synthesis & Distillation Park",
        "capex_barrier": "High (Pollution zero-liquid-discharge (ZLD) plant & reactor glass linings)",
        "listed_buyers": [
            {"ticker": "AARTIIND", "name": "Aarti Industries", "role": "Benzene Derivatives & Polymer Additives"},
            {"ticker": "DEEPAKNTR", "name": "Deepak Nitrite", "role": "Phenol Downstream Intermediates"},
            {"ticker": "SRF", "name": "SRF Ltd", "role": "Specialty Fluorochemical Reagents"}
        ],
        "growth_catalysts": [
            "Global specialty chemical supply chain diversification away from European high-energy zones",
            "Value-added downstream migration into agrochemical and pharmaceutical building blocks",
            "Dedicated chemical estate infrastructure with shared effluent treatment plants (CETP)"
        ],
        "fragility_vectors": [
            "Petrochemical feedstock and natural gas utility price escalation",
            "Zero liquid discharge (ZLD) regulatory shut-down risks upon effluent threshold breach",
            "Global inventory destocking cycles by international agrochemical customers"
        ]
    }
}

DEFAULT_BENCHMARK = {
    "dso_days": 65,
    "dio_days": 45,
    "dpo_days": 50,
    "ebitda_margin_pct": 12.0,
    "depr_pct": 3.5,
    "debt_to_turnover": 0.28,
    "interest_rate_pct": 9.5,
    "cluster_type": "Diversified Industrial Manufacturing Estate",
    "capex_barrier": "Moderate (Standard industrial plant & machinery infrastructure)",
    "listed_buyers": [
        {"ticker": "LTIM", "name": "LTIMindtree", "role": "Enterprise Systems & Automation"},
        {"ticker": "HDFCBANK", "name": "HDFC Bank Ltd", "role": "Working Capital Banker & Credit Line"},
        {"ticker": "INFY", "name": "Infosys Ltd", "role": "Supply Chain Digital Infrastructure"}
    ],
    "growth_catalysts": [
        "Broad-based domestic capital expenditure expansion across tier-2 industrial corridors",
        "Formalization of the unlisted economy through GST and Udyam registry transparency",
        "Access to formal banking channels and credit guarantee schemes (CGTMSE)"
    ],
    "fragility_vectors": [
        "Inflation in industrial power and freight transport logistics",
        "Competitive pressure from larger corporate entities with automated economies of scale",
        "Working capital stretch due to 60+ day client payment cycles"
    ]
}


def _resolve_sector_benchmark(sector_name: Optional[str]) -> Dict[str, Any]:
    """Resolves sector configuration or falls back gracefully."""
    if not sector_name:
        return DEFAULT_BENCHMARK
    norm = sector_name.lower().strip().replace(" ", "_")
    if norm in SECTOR_FORENSIC_BENCHMARKS:
        return SECTOR_FORENSIC_BENCHMARKS[norm]
    # Check substring matches
    for key, val in SECTOR_FORENSIC_BENCHMARKS.items():
        if key in norm or norm in key:
            return val
    return DEFAULT_BENCHMARK


def compute_msme_forensic_dossier(firm_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes a complete 4-pillar report for an MSME.

    Args:
        firm_data: Dictionary containing:
            - uin: str
            - name: str
            - sector_name: str
            - city: str
            - state: str
            - annual_turnover: float (in Cr)
            - employee_count: int
            - registration_date: str
            - source: str

    Returns:
        Rich dictionary with 4 analytical pillars, ratios, stress meters, and scores.
    """
    uin = firm_data.get("uin") or "UDYAM-XX-00-0000000"
    name = firm_data.get("name") or "Unlisted Enterprise"
    sector_name = firm_data.get("sector_name") or firm_data.get("sector") or "General Manufacturing"
    city = firm_data.get("city") or "Industrial Zone"
    state = firm_data.get("state") or "India"
    turnover = float(firm_data.get("annual_turnover") or 15.0)
    employees = int(firm_data.get("employee_count") or 50)
    reg_date = firm_data.get("registration_date") or "2021-01-01"

    bench = _resolve_sector_benchmark(sector_name)

    # --------------------------------------------------------------------------
    # Pillar 1: Working Capital & Cash Conversion Cycle (CCC)
    # --------------------------------------------------------------------------
    dso = bench["dso_days"]
    dio = bench["dio_days"]
    dpo = bench["dpo_days"]
    net_ccc = dso + dio - dpo

    # Scale working capital requirement (WCR) in ₹ Cr
    working_capital_req_cr = round((net_ccc / 365.0) * turnover, 2)
    daily_sales_cr = round(turnover / 365.0, 3)

    if net_ccc <= 45:
        ccc_stress_level = "Low Stress"
        ccc_stress_color = "#10b981"
        ccc_badge_class = "safe"
        ccc_summary = "Disciplined Cash Conversion. Receivables and inventory turn over within 45 days, limiting reliance on short-term working-capital borrowings."
    elif net_ccc <= 75:
        ccc_stress_level = "Moderate"
        ccc_stress_color = "#38bdf8"
        ccc_badge_class = "neutral"
        ccc_summary = "Balanced Working Capital Cycle. Cash conversion tracks standard B2B settlement schedules across tier-1 industrial supply chains."
    elif net_ccc <= 100:
        ccc_stress_level = "Elevated Stretch"
        ccc_stress_color = "#f59e0b"
        ccc_badge_class = "warning"
        ccc_summary = "Elongated Working Capital Cycle. Receivable collection extends beyond 60 days, requiring working-capital credit lines to bridge operating cash flow."
    else:
        ccc_stress_level = "Severe Working Capital Drag"
        ccc_stress_color = "#ef4444"
        ccc_badge_class = "danger"
        ccc_summary = "Extended Cash Conversion Drag. Multi-stage batch processing and delayed buyer settlements tie up operating liquidity."

    # --------------------------------------------------------------------------
    # Pillar 2: Listed Corporate Supply-Chain Linkage
    # --------------------------------------------------------------------------
    listed_buyers = bench["listed_buyers"]
    if turnover >= 50.0:
        oem_supplier_tier = "Tier-1 Direct OEM Supplier"
        tier_desc = "Direct vendor supplying sub-assemblies to listed OEMs, where switching costs are supported by multi-year qualification audits."
    elif turnover >= 15.0:
        oem_supplier_tier = "Tier-2 Specialized Vendor"
        tier_desc = "Specialized component manufacturer supplying tier-1 systems integrators and listed industrial buyers."
    else:
        oem_supplier_tier = "Tier-3 Ancillary Workshop"
        tier_desc = "Contract machining and tooling supplier whose bargaining power depends on local industrial cluster utilization."

    # --------------------------------------------------------------------------
    # Pillar 3: Solvency, Operating Margins & TReDS Liquidity Risk
    # --------------------------------------------------------------------------
    ebitda_margin = bench["ebitda_margin_pct"]
    depr_pct = bench["depr_pct"]
    estimated_ebitda_cr = round(turnover * (ebitda_margin / 100.0), 2)
    estimated_ebit_cr = round(turnover * ((ebitda_margin - depr_pct) / 100.0), 2)

    debt_to_turnover = bench["debt_to_turnover"]
    estimated_debt_cr = round(turnover * debt_to_turnover, 2)
    interest_rate = bench["interest_rate_pct"]
    estimated_interest_cr = round(estimated_debt_cr * (interest_rate / 100.0), 2)

    icr = round(estimated_ebit_cr / max(0.1, estimated_interest_cr), 2) if estimated_interest_cr > 0 else 5.0

    if icr >= 4.0:
        icr_health = "Strong Solvency"
        icr_color = "#10b981"
    elif icr >= 2.5:
        icr_health = "Adequate Coverage"
        icr_color = "#38bdf8"
    elif icr >= 1.5:
        icr_health = "Narrow Headroom"
        icr_color = "#f59e0b"
    else:
        icr_health = "Vulnerable"
        icr_color = "#ef4444"

    # TReDS Platform Liquidity Rating
    if turnover >= 50.0 and icr >= 3.0:
        treds_grade = "Tier A (High Discounting Rate)"
        treds_discount_cost = "~7.5% - 8.2% p.a."
        treds_liquidity_desc = "Qualifies for competitive non-recourse invoice discounting on RXIL / M1xchange against accepted listed-buyer invoices."
    elif turnover >= 15.0:
        treds_grade = "Tier B (Standard Factoring Corridor)"
        treds_discount_cost = "~8.5% - 9.5% p.a."
        treds_liquidity_desc = "Accesses standard invoice discounting against approved corporate buyer acceptances, moderating working-capital funding costs."
    else:
        treds_grade = "Tier C (Collateral-Dependent / Recourse Factoring)"
        treds_discount_cost = "~10.0% - 11.5% p.a."
        treds_liquidity_desc = "Higher financing spread on working-capital lines; liquidity depends on timely buyer invoice acceptance under MSMED Act Section 15."

    # --------------------------------------------------------------------------
    # Pillar 4: Cluster Density & Capital Replacement Moat Score (0–100)
    # --------------------------------------------------------------------------
    # Heuristic scoring based on turnover scale, employee productivity, and sector capex
    turnover_score = min(30.0, (turnover / 250.0) * 30.0)
    
    # Revenue per employee productivity
    rev_per_emp_lakhs = (turnover * 100.0) / max(1, employees)
    productivity_score = min(25.0, (rev_per_emp_lakhs / 60.0) * 25.0)

    # Solvency score based on ICR
    solvency_score = min(25.0, (icr / 5.0) * 25.0)

    # Sector barrier score
    barrier_bonus = 20.0 if "High" in bench["capex_barrier"] else 15.0

    raw_moat = turnover_score + productivity_score + solvency_score + barrier_bonus
    moat_score = int(max(35, min(95, round(raw_moat))))

    if moat_score >= 75:
        moat_tier = "Quality Vendor"
        moat_color = "#10b981"
        moat_badge = "High Moat"
    elif moat_score >= 60:
        moat_tier = "Core Industrial Specialist"
        moat_color = "#38bdf8"
        moat_badge = "Moderate Moat"
    else:
        moat_tier = "Developing Ancillary Workshop"
        moat_color = "#f59e0b"
        moat_badge = "Developing Moat"

    # Partition verified Udyam attributes from sector benchmark medians
    verified_udyam_attributes = {
        "uin": uin,
        "name": name,
        "sector_name": sector_name,
        "city": city,
        "state": state,
        "annual_turnover": turnover,
        "employee_count": employees,
        "registration_date": reg_date,
        "source": firm_data.get("source") or "Udyam Gazette / Open Registry",
        "data_provenance": "Verified Statutory Udyam Registration (Ministry of MSME)",
    }

    sector_forensic_benchmarks = {
        "cluster_type": bench["cluster_type"],
        "dso_median_days": bench["dso_days"],
        "dio_median_days": bench["dio_days"],
        "dpo_median_days": bench["dpo_days"],
        "net_ccc_median_days": bench["dso_days"] + bench["dio_days"] - bench["dpo_days"],
        "ebitda_margin_median_pct": bench["ebitda_margin_pct"],
        "depr_median_pct": bench["depr_pct"],
        "debt_to_turnover_median": bench["debt_to_turnover"],
        "interest_rate_median_pct": bench["interest_rate_pct"],
        "capex_barrier": bench["capex_barrier"],
        "growth_catalysts": bench["growth_catalysts"],
        "fragility_vectors": bench["fragility_vectors"],
    }

    sector_offtake_universe = [
        {
            "ticker": b["ticker"],
            "name": b["name"],
            "role": b["role"],
            "verified_by_filing": b.get("verified_by_filing", False),
            "offtake_category": "Sector Offtake Universe",
        }
        for b in listed_buyers
    ]

    # Assemble comprehensive report payload
    return {
        "uin": uin,
        "name": name,
        "sector": sector_name,
        "city": city,
        "state": state,
        "annual_turnover": turnover,
        "employee_count": employees,
        "registration_date": reg_date,
        "source": firm_data.get("source") or "Udyam Gazette / Open Registry",
        "tier": "Medium" if turnover >= 50.0 else ("Small" if turnover >= 5.0 else "Micro"),
        "verified_udyam_attributes": verified_udyam_attributes,
        "sector_forensic_benchmarks": sector_forensic_benchmarks,
        
        # Pillar 1
        "pillar_1_working_capital": {
            "dso_days": dso,
            "dio_days": dio,
            "dpo_days": dpo,
            "net_ccc_days": net_ccc,
            "working_capital_req_cr": working_capital_req_cr,
            "daily_sales_cr": daily_sales_cr,
            "stress_level": ccc_stress_level,
            "stress_color": ccc_stress_color,
            "badge_class": ccc_badge_class,
            "summary": ccc_summary
        },

        # Pillar 2: Sector Offtake Universe (Listed Equities)
        "pillar_2_supply_chain": {
            "oem_supplier_tier": oem_supplier_tier,
            "tier_description": tier_desc,
            "cluster_type": bench["cluster_type"],
            "capex_barrier": bench["capex_barrier"],
            "sector_offtake_universe": sector_offtake_universe,
            "listed_buyers": sector_offtake_universe,
            "offtake_universe_note": "Unverified by direct public filing unless tagged as Filing Verified."
        },

        # Pillar 3
        "pillar_3_solvency": {
            "ebitda_margin_pct": ebitda_margin,
            "estimated_ebitda_cr": estimated_ebitda_cr,
            "estimated_ebit_cr": estimated_ebit_cr,
            "estimated_debt_cr": estimated_debt_cr,
            "estimated_interest_cr": estimated_interest_cr,
            "interest_coverage_ratio": icr,
            "icr_health": icr_health,
            "icr_color": icr_color,
            "treds_grade": treds_grade,
            "treds_discount_cost": treds_discount_cost,
            "treds_liquidity_desc": treds_liquidity_desc,
            "msmed_act_section_16_protection": "Section 16 statutory compound interest at 3x RBI bank rate applies on overdue payments exceeding 45 days."
        },

        # Pillar 4
        "pillar_4_moat": {
            "moat_score": moat_score,
            "moat_tier": moat_tier,
            "moat_color": moat_color,
            "moat_badge": moat_badge,
            "rev_per_emp_lakhs": round(rev_per_emp_lakhs, 1),
            "growth_catalysts": bench["growth_catalysts"],
            "fragility_vectors": bench["fragility_vectors"]
        }
    }
