"""
Sutra Multi-Asset Portfolio Look-Through Engine
=============================================
Phase 5 Proprietary Architecture (Anvik Cortex Engine).

An institutional portfolio concentration, duplicate overlap, and forensic de-risking engine that:
1. Ingests multi-asset investor portfolios (Direct Equities + Mutual Funds + REITs + Sovereign Bonds).
2. Deconstructs mutual fund scheme portfolios down to underlying company holdings.
3. Uncovers hidden single-stock concentration across direct holdings and indirect fund holdings:
   True Exposure(X) = Direct_Weight(X) + SUM(Fund_Weight(f) * Holding_Weight_in_f(X))
4. Quantifies sector concentration risks, capital hierarchy seniority, and portfolio fiduciary health.
5. Emits non-advisory, descriptive de-risking diagnostics to eliminate redundant fund fees.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import math
import logging

logger = logging.getLogger(__name__)


def _safe_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    if isinstance(v, (int, float)):
        if math.isnan(v) or math.isinf(v):
            return default
        return float(v)
    try:
        clean = str(v).strip().replace(",", "").replace("%", "")
        f = float(clean)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return default


# Canonical top-holding profiles for prominent Indian mutual fund schemes (Fallback matrix)
SCHEME_TOP_HOLDINGS_REGISTRY: Dict[str, Dict[str, float]] = {
    # PPFAS Flexi Cap Fund Direct
    "PPFAS_FLEXICAP": {
        "HDFCBANK": 7.8, "BAJAJHLDNG": 6.4, "ITC": 6.1, "ICICIBANK": 5.8,
        "POWERGRID": 4.5, "COALINDIA": 4.2, "INFY": 3.8, "TCS": 3.2, "AXISBANK": 2.9,
    },
    # HDFC Top 100 Fund Direct
    "HDFC_TOP100": {
        "HDFCBANK": 9.8, "ICICIBANK": 8.5, "RELIANCE": 7.9, "INFY": 6.2,
        "LT": 5.1, "TCS": 4.8, "AXISBANK": 4.2, "SBIN": 3.9, "BHARTIARTL": 3.6,
    },
    # Mirae Asset Large & Midcap Fund
    "MIRAE_LARGEMID": {
        "HDFCBANK": 6.2, "ICICIBANK": 5.9, "RELIANCE": 5.1, "INFY": 4.2,
        "TCS": 3.5, "AXISBANK": 3.1, "BHARTIARTL": 2.8, "FEDERALBNK": 2.5,
    },
    # Nippon India Small Cap Fund
    "NIPPON_SMALLCAP": {
        "HDFCBANK": 1.2, "CRAFTSMAN": 2.8, "KAYNES": 2.5, "ELECON": 2.1,
        "SONACOMS": 1.9, "FINEORG": 1.8, "KPIGREEN": 1.6, "MARKSANS": 1.5,
    },
}

# Stock sector mapping registry
STOCK_SECTOR_MAP: Dict[str, str] = {
    "HDFCBANK": "Financial Services",
    "ICICIBANK": "Financial Services",
    "AXISBANK": "Financial Services",
    "SBIN": "Financial Services",
    "BAJAJHLDNG": "Financial Services",
    "INFY": "Information Technology",
    "TCS": "Information Technology",
    "RELIANCE": "Energy & Conglomerate",
    "ITC": "Consumer Goods & FMCG",
    "POWERGRID": "Utilities & Power",
    "COALINDIA": "Metals & Mining",
    "LT": "Infrastructure & Capital Goods",
    "BHARTIARTL": "Telecommunications",
    "CRAFTSMAN": "Precision Engineering",
    "KAYNES": "EMS & Defence Electronics",
    "ELECON": "Industrial Machinery",
    "SONACOMS": "Automotive Ancillaries",
    "FINEORG": "Specialty Chemicals",
    "KPIGREEN": "Renewables & Power Infra",
    "MARKSANS": "Healthcare & Pharmaceuticals",
}


@dataclass
class ConsolidatedStockExposure:
    symbol: str
    sector: str
    direct_weight_pct: float
    indirect_weight_pct: float
    total_exposure_pct: float
    total_value_inr: float
    holding_funds: List[str] = field(default_factory=list)
    concentration_flag: str = "BALANCED"  # "BALANCED", "ELEVATED", "CRITICAL_OVERWEIGHT"


@dataclass
class SectorExposure:
    sector: str
    weight_pct: float
    status: str  # "OPTIMAL", "CONCENTRATED_EXPOSURE"


@dataclass
class CapitalAllocationHierarchy:
    sovereign_gold_pct: float
    senior_debt_pct: float
    real_assets_reits_pct: float
    equity_direct_pct: float
    equity_funds_pct: float


@dataclass
class SutraLookThroughResult:
    total_portfolio_value_inr: float
    top_stock_exposures: List[ConsolidatedStockExposure] = field(default_factory=list)
    sector_exposures: List[SectorExposure] = field(default_factory=list)
    capital_hierarchy: CapitalAllocationHierarchy = field(default_factory=lambda: CapitalAllocationHierarchy(0, 0, 0, 0, 0))
    hidden_overlap_alerts: List[str] = field(default_factory=list)
    portfolio_fiduciary_health_score: float = 75.0
    summary: str = ""


class SutraLookThroughEngine:
    """
    Multi-Asset Look-Through and Concentration De-Risking Engine.
    """

    MAX_SAFE_SINGLE_STOCK_WEIGHT: float = 10.0
    MAX_SAFE_SECTOR_WEIGHT: float = 25.0

    @classmethod
    def audit_portfolio(
        cls,
        direct_equities: Optional[List[Dict[str, Any]]],
        mutual_funds: Optional[List[Dict[str, Any]]],
        fixed_income_and_sov: Optional[List[Dict[str, Any]]],
    ) -> SutraLookThroughResult:
        """
        Executes complete multi-asset look-through deconstruction.
        Hardened against nulls, non-dict items, strings with commas, and negative values.
        """
        safe_eq = [x for x in (direct_equities or []) if isinstance(x, dict)]
        safe_mf = [x for x in (mutual_funds or []) if isinstance(x, dict)]
        safe_fi = [x for x in (fixed_income_and_sov or []) if isinstance(x, dict)]

        total_direct_val = sum(max(0.0, _safe_float(x.get("value_inr"))) for x in safe_eq)
        total_mf_val = sum(max(0.0, _safe_float(x.get("value_inr"))) for x in safe_mf)
        total_sov_debt_val = sum(max(0.0, _safe_float(x.get("value_inr"))) for x in safe_fi)
        total_portfolio_val = max(1.0, total_direct_val + total_mf_val + total_sov_debt_val)

        # 1. Unpack consolidated company holdings
        # Map: symbol -> {"direct_val": float, "indirect_val": float, "funds": list}
        stock_map: Dict[str, Dict[str, Any]] = {}

        for de in safe_eq:
            sym = str(de.get("symbol") or "").upper().strip()
            val = max(0.0, _safe_float(de.get("value_inr")))
            if not sym or val <= 0:
                continue
            if sym not in stock_map:
                stock_map[sym] = {"direct_val": 0.0, "indirect_val": 0.0, "funds": []}
            stock_map[sym]["direct_val"] += val

        for mf in safe_mf:
            scheme_key = str(mf.get("scheme_key") or mf.get("symbol") or "").upper().strip()
            mf_val = max(0.0, _safe_float(mf.get("value_inr")))
            if not scheme_key or mf_val <= 0:
                continue

            holdings = SCHEME_TOP_HOLDINGS_REGISTRY.get(scheme_key, {})
            for sym, weight_in_fund in holdings.items():
                indirect_inr = (weight_in_fund / 100.0) * mf_val
                if sym not in stock_map:
                    stock_map[sym] = {"direct_val": 0.0, "indirect_val": 0.0, "funds": []}
                stock_map[sym]["indirect_val"] += indirect_inr
                if scheme_key not in stock_map[sym]["funds"]:
                    stock_map[sym]["funds"].append(scheme_key)

        # 2. Build Consolidated Stock Exposures
        exposures: List[ConsolidatedStockExposure] = []
        hidden_overlap_alerts: List[str] = []

        for sym, d in stock_map.items():
            tot_val = d["direct_val"] + d["indirect_val"]
            tot_pct = round((tot_val / total_portfolio_val) * 100.0, 2)
            dir_pct = round((d["direct_val"] / total_portfolio_val) * 100.0, 2)
            ind_pct = round((d["indirect_val"] / total_portfolio_val) * 100.0, 2)
            sector = STOCK_SECTOR_MAP.get(sym, "General Industry")

            if tot_pct >= 20.0:
                flag = "CRITICAL_OVERWEIGHT"
                hidden_overlap_alerts.append(
                    f"Severe single-stock concentration: {sym} constitutes {tot_pct:.1f}% of total portfolio "
                    f"(Direct: {dir_pct:.1f}%, Indirect via {len(d['funds'])} funds: {ind_pct:.1f}%)."
                )
            elif tot_pct >= cls.MAX_SAFE_SINGLE_STOCK_WEIGHT:
                flag = "ELEVATED"
                if len(d["funds"]) >= 2 and dir_pct > 0:
                    hidden_overlap_alerts.append(
                        f"Hidden overlap detected in {sym}: Total exposure {tot_pct:.1f}% exceeds safe single-stock ceiling ({cls.MAX_SAFE_SINGLE_STOCK_WEIGHT}%)."
                    )
            else:
                flag = "BALANCED"

            exposures.append(ConsolidatedStockExposure(
                symbol=sym,
                sector=sector,
                direct_weight_pct=dir_pct,
                indirect_weight_pct=ind_pct,
                total_exposure_pct=tot_pct,
                total_value_inr=round(tot_val, 2),
                holding_funds=d["funds"],
                concentration_flag=flag,
            ))

        # Sort exposures descending
        exposures.sort(key=lambda x: x.total_exposure_pct, reverse=True)

        # 3. Calculate Sector Exposures
        sector_weights: Dict[str, float] = {}
        for exp in exposures:
            sector_weights[exp.sector] = sector_weights.get(exp.sector, 0.0) + exp.total_exposure_pct

        sector_list: List[SectorExposure] = []
        for sec, wt in sector_weights.items():
            status = "CONCENTRATED_EXPOSURE" if wt > cls.MAX_SAFE_SECTOR_WEIGHT else "OPTIMAL"
            if status == "CONCENTRATED_EXPOSURE":
                hidden_overlap_alerts.append(
                    f"Sector crowding alert: {sec} accounts for {wt:.1f}% of portfolio (safe threshold: {cls.MAX_SAFE_SECTOR_WEIGHT}%)."
                )
            sector_list.append(SectorExposure(sector=sec, weight_pct=round(wt, 2), status=status))

        sector_list.sort(key=lambda x: x.weight_pct, reverse=True)

        # 4. Capital Hierarchy Breakdown
        sov_val = 0.0
        debt_val = 0.0
        reit_val = 0.0
        for fi in safe_fi:
            atype = str(fi.get("asset_type") or "").upper()
            v = max(0.0, _safe_float(fi.get("value_inr")))
            if "SOV" in atype or "GSEC" in atype or "SGB" in atype or "GOLD" in atype:
                sov_val += v
            elif "REIT" in atype or "REAL" in atype:
                reit_val += v
            else:
                debt_val += v

        hierarchy = CapitalAllocationHierarchy(
            sovereign_gold_pct=round((sov_val / total_portfolio_val) * 100.0, 2),
            senior_debt_pct=round((debt_val / total_portfolio_val) * 100.0, 2),
            real_assets_reits_pct=round((reit_val / total_portfolio_val) * 100.0, 2),
            equity_direct_pct=round((total_direct_val / total_portfolio_val) * 100.0, 2),
            equity_funds_pct=round((total_mf_val / total_portfolio_val) * 100.0, 2),
        )

        # 5. Portfolio Fiduciary Health Score
        health_score = 100.0
        for exp in exposures:
            if exp.concentration_flag == "CRITICAL_OVERWEIGHT":
                health_score -= 15.0
            elif exp.concentration_flag == "ELEVATED":
                health_score -= 5.0
        for sec in sector_list:
            if sec.status == "CONCENTRATED_EXPOSURE":
                health_score -= 5.0
        health_score = max(20.0, min(100.0, health_score))

        summary = (
            f"Portfolio Look-Through Audit: Analyzed ₹{total_portfolio_val:,.0f} across {len(safe_eq)} direct equities, "
            f"{len(safe_mf)} mutual funds, and {len(safe_fi)} fixed-income assets. "
            f"Top holding: {exposures[0].symbol if exposures else 'None'} ({exposures[0].total_exposure_pct if exposures else 0:.1f}%). "
            f"Fiduciary Health Score: {health_score:.1f}/100. Alerts: {len(hidden_overlap_alerts)}."
        )

        return SutraLookThroughResult(
            total_portfolio_value_inr=round(total_portfolio_val, 2),
            top_stock_exposures=exposures[:10],
            sector_exposures=sector_list,
            capital_hierarchy=hierarchy,
            hidden_overlap_alerts=hidden_overlap_alerts,
            portfolio_fiduciary_health_score=round(health_score, 1),
            summary=summary,
        )
