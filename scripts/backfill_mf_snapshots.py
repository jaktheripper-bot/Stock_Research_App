"""Idempotently backfill immutable MF disclosure snapshots and dossier evidence receipts from verified corpus rows."""

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.analysis.fund_overlap_auditor import compute_fund_forensic_lookthrough
from core.analysis.metric_contract import has_forbidden_vendor_token
from core.db.connection import get_db_connection, get_placeholder, init_db
from core.db.mutual_funds import (
    ALLOWED_DISCLOSURE_SOURCES,
    clean_dict_row,
    get_current_fund_disclosure,
    get_holdings_for_schemes_batch,
    parse_fund_disclosure_date,
    publish_mutual_fund_disclosure,
    resolve_legacy_slug_twins,
    save_fund_forensic_dossier,
)
from core.ingestion.mf_portfolio_ingest import (
    sync_legacy_slug_twins_from_verified_numeric,
)

logger = logging.getLogger(__name__)


def backfill_mf_snapshots(*, apply: bool = False) -> Dict[str, Any]:
    """Promote existing verified MF schemes + holdings into `mf_disclosure_snapshots` / `mf_current_disclosures`,
    mirror legacy slug twins from canonical numeric AMFI disclosures, and stamp `evidence_receipt_json` on
    existing dossiers that meet the >=70% eligible constituent coverage threshold.
    """
    init_db()
    conn = get_db_connection()
    cur = conn.cursor()
    p = get_placeholder()
    try:
        cur.execute("SELECT * FROM mutual_fund_schemes ORDER BY scheme_code")
        raw_schemes = [clean_dict_row(cur, r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

    scheme_codes = [s["scheme_code"] for s in raw_schemes]
    holdings_by_code = get_holdings_for_schemes_batch(scheme_codes) if scheme_codes else {}
    legacy_slugs = set(resolve_legacy_slug_twins(raw_schemes).keys())

    published_numeric: List[str] = []
    already_published: List[str] = []
    skipped: List[Dict[str, Any]] = []

    # 1. Publish verified canonical schemes first (numeric AMFI codes or standalone schemes)
    for row in raw_schemes:
        code = row["scheme_code"]
        if code in legacy_slugs:
            continue
        existing = get_current_fund_disclosure(code)
        if existing:
            already_published.append(code)
            continue
        holdings = holdings_by_code.get(code) or []
        if not holdings:
            skipped.append({"scheme_code": code, "reason": "no_holdings"})
            continue
        try:
            meta = json.loads(row.get("metadata_json") or "{}")
        except (TypeError, ValueError) as exc:
            logger.warning("Invalid metadata_json on %s: %s", code, exc)
            meta = {}
        source = str(meta.get("holdings_source") or "").strip()
        source_url = str(meta.get("holdings_source_url") or "").strip()
        as_on = meta.get("holdings_as_on") or row.get("last_portfolio_date")
        total_w = sum(float(h.get("weight_pct") or 0.0) for h in holdings if float(h.get("weight_pct") or 0.0) > 0)
        try:
            parsed_date = parse_fund_disclosure_date(as_on)
        except ValueError:
            parsed_date = None
        if not parsed_date or source not in ALLOWED_DISCLOSURE_SOURCES or not source_url:
            skipped.append({"scheme_code": code, "reason": "unverified_source_or_date"})
            continue
        if not (88.0 <= total_w <= 108.5):
            skipped.append({"scheme_code": code, "reason": f"weight_sum_out_of_bounds:{total_w:.2f}"})
            continue
        scheme_payload = {
            **row,
            "last_portfolio_date": parsed_date,
            "metadata": {
                **meta,
                "holdings_as_on": parsed_date,
                "holdings_source": source,
                "holdings_source_url": source_url,
            },
        }
        normalized_holdings = [
            {**h, "portfolio_date": parsed_date}
            for h in holdings
        ]
        if apply:
            publish_mutual_fund_disclosure(scheme_payload, normalized_holdings)
        published_numeric.append(code)

    # 2. Mirror legacy slug twins (e.g. PPFAS_FLEXICAP_DIR <- 122639) from canonical snapshots
    mirrored_twins = sync_legacy_slug_twins_from_verified_numeric() if apply else {}

    # 3. Backfill evidence_receipt_json on existing dossiers that have current snapshots and eligible coverage
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT scheme_code, dossier_text, audited_by, evidence_receipt_json
               FROM fund_forensic_dossiers
               ORDER BY scheme_code"""
        )
        dossiers = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    upgraded_dossiers: List[str] = []
    withheld_dossiers: List[str] = []
    for code, dossier_text, audited_by, existing_receipt_json in dossiers:
        snapshot = get_current_fund_disclosure(code)
        clean_text = str(dossier_text or "").strip()
        lowered_text = clean_text.lower()
        if (
            not snapshot
            or not clean_text
            or "margin of safety" in lowered_text
            or "promoter pledge" in lowered_text
            or has_forbidden_vendor_token(clean_text)
        ):
            withheld_dossiers.append(code)
            continue
        try:
            existing_receipt = json.loads(existing_receipt_json) if existing_receipt_json else {}
        except (TypeError, ValueError) as exc:
            logger.warning("Invalid existing receipt on %s: %s", code, exc)
            existing_receipt = {}
        if isinstance(existing_receipt, dict) and existing_receipt.get("snapshot_id") == snapshot["snapshot_id"]:
            continue
        lookthrough = compute_fund_forensic_lookthrough(code)
        receipt = lookthrough.get("evidence_receipt")
        if not lookthrough.get("has_sufficient_coverage") or not receipt or not receipt.get("snapshot_id"):
            withheld_dossiers.append(code)
            continue
        if apply:
            conn_scheme = get_db_connection()
            cur_scheme = conn_scheme.cursor()
            try:
                cur_scheme.execute(
                    f"SELECT active_share_pct FROM mutual_fund_schemes WHERE scheme_code={p}",
                    (code,),
                )
                s_row = cur_scheme.fetchone()
                active_share = s_row[0] if s_row else None
            finally:
                cur_scheme.close()
                conn_scheme.close()
            save_fund_forensic_dossier({
                "scheme_code": code,
                "dossier_text": dossier_text,
                "composite_health_score": lookthrough.get("composite_health_score"),
                "weighted_moat_score": lookthrough.get("weighted_moat_score"),
                "accounting_risk_index": lookthrough.get("accounting_risk_index"),
                "active_share_pct": active_share,
                "top_risky_holdings": lookthrough.get("top_risky_holdings", []),
                "top_quality_holdings": lookthrough.get("top_quality_holdings", []),
                "evidence_receipt": receipt,
                "audited_by": audited_by or "Gemini_Chief_Forensic_Officer",
            })
        upgraded_dossiers.append(code)

    return {
        "applied": apply,
        "published_canonical_count": len(published_numeric),
        "already_published_count": len(already_published),
        "mirrored_twins": mirrored_twins,
        "upgraded_dossiers": upgraded_dossiers,
        "withheld_dossiers": withheld_dossiers,
        "skipped_schemes_count": len(skipped),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist backfilled snapshots and receipts.")
    args = parser.parse_args()
    print(json.dumps(backfill_mf_snapshots(apply=args.apply), indent=2))


if __name__ == "__main__":
    main()
