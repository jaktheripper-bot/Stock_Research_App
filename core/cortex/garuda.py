"""
Garuda Event-Driven Micro-Snapshot Engine
========================================
Phase 4 Proprietary Architecture (Anvik Cortex Engine).

An event-driven corporate announcement classifier and surgical micro-snapshot reactor that:
1. Ingests raw BSE/NSE exchange corporate disclosures in real-time or batch.
2. Deterministically classifies announcements to specific 7-Pillar Dossier segments:
   - Pillar 1: Macro-Economic, Geopolitical & Environmental Overlays
   - Pillar 2: Industry Dynamics & Competitive Positioning (Concalls / Investor Presentations)
   - Pillar 3: Promoter Quality & Fundamental Health (Shareholding, Pledges, SAST)
   - Pillar 4: Capital Allocation & Cash Generation Engine (Dividends, Buybacks, Capex)
   - Pillar 5: Financial Fortress & Forensic Health (Quarterly Results, Audited Numbers)
   - Pillar 6: Corporate Governance & Forensic Integrity (Auditor Changes, Litigations, Board)
   - Pillar 7: Valuation Asymmetry & Margin of Safety (Credit Ratings, Cortex Updates)
3. Generates a surgical 'MicroSnapshotDelta' targeting only the affected pillar, eliminating
   wasteful, full 7-pillar batch regeneration.
4. Render-friendly: Stateless and callable on-demand via cron, webhook, or interval tick.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import hashlib
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class MicroSnapshotDelta:
    symbol: str
    target_pillar_id: int
    target_pillar_title: str
    catalyst_type: str
    urgency: str  # "IMMEDIATE_REFRESH", "ROUTINE_PATCH", "INFORMATIONAL"
    headline: str
    filing_date: str
    announcement_hash: str
    delta_snippet_md: str
    action_required: bool  # True if cache requires delta invalidation


class GarudaReflexEngine:
    """
    Event-Driven Micro-Snapshot Reactor for Indian Equities.
    """

    PILLAR_TITLES = {
        1: "Macro-Economic, Geopolitical & Environmental Overlays",
        2: "Industry Dynamics & Competitive Positioning",
        3: "Promoter Quality & Fundamental Health",
        4: "Capital Allocation & Cash Generation Engine",
        5: "Financial Fortress & Forensic Health",
        6: "Corporate Governance & Forensic Integrity",
        7: "Valuation Asymmetry & Margin of Safety",
    }

    # Taxonomy rules: (regex_pattern, pillar_id, catalyst_type, urgency)
    CLASSIFICATION_RULES = [
        # Pillar 6: Governance, Auditor, Board
        (r"(?i)\b(resignation|cessation|auditor|statutory\s+auditor|independent\s+director|investigation|sebi|show\s+cause|penalty)\b", 6, "GOVERNANCE_REGULATORY", "IMMEDIATE_REFRESH"),
        # Pillar 2: Concalls & Strategy (evaluated before earnings so concall transcripts are not hijacked)
        (r"(?i)\b(transcript|concall|investor\s+presentation|analyst\s+meet|audio\s+recording)\b", 2, "CONCALL_PRESENTATION", "ROUTINE_PATCH"),
        # Pillar 5: Financial Results
        (r"(?i)\b(financial\s+results|unaudited|audited\s+results|limited\s+review|earnings|q[1-4]|half\s+yearly)\b", 5, "FINANCIAL_EARNINGS", "IMMEDIATE_REFRESH"),
        # Pillar 4: Capital Allocation
        (r"(?i)\b(dividend|interim\s+dividend|buyback|bonus\s+issue|rights\s+issue|capex|capital\s+expenditure|acquisition|merger)\b", 4, "CAPITAL_ALLOCATION", "ROUTINE_PATCH"),
        # Pillar 3: Promoter & Shareholding
        (r"(?i)\b(shareholding\s+pattern|pledge|encumbrance|revocation|insider\s+trading|sast|promoter)\b", 3, "PROMOTER_SHAREHOLDING", "ROUTINE_PATCH"),
        # Pillar 7: Ratings & Valuation
        (r"(?i)\b(credit\s+rating|crisil|icra|care|downgrade|upgrade|valuation)\b", 7, "CREDIT_RATING_VALUATION", "ROUTINE_PATCH"),
        # Pillar 1: Default / Macro
        (r"(?i)\b(press\s+release|clarification|newspaper|general|bulletin)\b", 1, "MACRO_DISCLOSURE", "INFORMATIONAL"),
    ]

    @classmethod
    def classify_announcement(
        cls,
        symbol: str,
        headline: str,
        filing_date: str = "",
        details_url: str = "",
    ) -> MicroSnapshotDelta:
        """
        Classifies an announcement and builds a surgical micro-snapshot delta.
        Hardened against nulls, non-string types, and malformed inputs.
        """
        clean_symbol = str(symbol or "UNKNOWN").upper().strip()
        cleaned_hl = str(headline or "").strip()
        clean_date = str(filing_date or "").strip()
        clean_url = str(details_url or "").strip()

        hasher = hashlib.sha256(f"{clean_symbol}:{cleaned_hl}:{clean_date}".encode("utf-8"))
        ann_hash = hasher.hexdigest()[:12]

        target_pillar = 1
        catalyst = "GENERAL_DISCLOSURE"
        urgency = "INFORMATIONAL"

        for pattern, p_id, cat, urg in cls.CLASSIFICATION_RULES:
            if re.search(pattern, cleaned_hl):
                target_pillar = p_id
                catalyst = cat
                urgency = urg
                break

        pillar_title = cls.PILLAR_TITLES.get(target_pillar, "Corporate Disclosures")

        # Create structured markdown bulletin snippet
        date_str = clean_date if clean_date else datetime.now().strftime("%Y-%m-%d")
        badge_urgency = "🔴 CRITICAL NOTICE" if urgency == "IMMEDIATE_REFRESH" else "🔵 REGULATORY UPDATE"
        
        snippet = (
            f"\n> **{badge_urgency} ({date_str})** — `{clean_symbol}`  \n"
            f"> **Catalyst:** `{catalyst}` | **Filing Hash:** `{ann_hash}`  \n"
            f"> {cleaned_hl if cleaned_hl else 'Routine regulatory filing / disclosure'}\n"
        )
        if clean_url:
            snippet += f"> [Official BSE Disclosure Document]({clean_url})\n"

        action_required = urgency in ["IMMEDIATE_REFRESH", "ROUTINE_PATCH"]

        return MicroSnapshotDelta(
            symbol=clean_symbol,
            target_pillar_id=target_pillar,
            target_pillar_title=pillar_title,
            catalyst_type=catalyst,
            urgency=urgency,
            headline=cleaned_hl,
            filing_date=date_str,
            announcement_hash=ann_hash,
            delta_snippet_md=snippet,
            action_required=action_required,
        )

    @classmethod
    def process_feed(
        cls,
        symbol: str,
        announcements: Optional[List[Dict[str, Any]]],
    ) -> List[MicroSnapshotDelta]:
        """
        Processes a cohort of recent announcements and returns actionable deltas.
        Hardened against null feeds and non-dict feed elements.
        """
        deltas: List[MicroSnapshotDelta] = []
        safe_feed = [a for a in (announcements or []) if isinstance(a, dict)]
        for ann in safe_feed:
            hl = str(ann.get("headline") or ann.get("NEWS_SUB") or ann.get("subject") or "").strip()
            if not hl:
                continue
            f_date = str(ann.get("date") or ann.get("NEWS_DT") or "").strip()
            url = str(ann.get("url") or ann.get("ATTACHMENTNAME") or "").strip()
            delta = cls.classify_announcement(
                symbol=symbol,
                headline=hl,
                filing_date=f_date,
                details_url=url,
            )
            deltas.append(delta)
        return deltas
