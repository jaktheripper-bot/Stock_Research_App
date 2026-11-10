#!/usr/bin/env python3
"""CLI & automated scheduled importer/verifier for Indian Fixed Savings, Term Deposits,
Statutory Small Savings, High-Yield Savings Accounts, and Retirement Instruments.

Usage examples:
    python3 scripts/import_savings_rates.py --check
    python3 scripts/import_savings_rates.py --apply
    python3 scripts/import_savings_rates.py --apply --force
    python3 scripts/import_savings_rates.py --auto-fetch
    python3 scripts/import_savings_rates.py --file data/savings_rates/baseline_savings_universe.json --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.db.connection import init_db
from core.db.savings import (
    BASELINE_SAVINGS_JSON_PATH,
    activate_due_future_savings_rates,
    compute_material_terms_snapshot,
    get_savings_instrument_by_id,
    inspect_savings_universe_readonly,
    load_baseline_savings_payload,
    seed_baseline_savings_universe,
    seed_tax_rule_versions,
    upsert_savings_instrument,
    validate_savings_provenance,
    validate_tax_rule_provenance,
    verify_and_sync_automated_savings_rates,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("import_savings_rates")


def build_check_report(file_path: Path) -> Dict[str, Any]:
    """Read-only diff, provenance, terms-hash, and staleness preview (performs zero DB initialization or writes)."""
    payload = load_baseline_savings_payload(file_path)
    incoming = payload.get("instruments", [])
    tax_rules = payload.get("tax_rule_versions", [])
    existing_map = {item["instrument_id"]: item for item in inspect_savings_universe_readonly()}

    provenance_errors = []
    diffs = []
    for item in incoming:
        inst_id = str(item.get("instrument_id") or "").strip().upper()
        cur = existing_map.get(inst_id)
        candidate = dict(cur or {})
        candidate.update(item)
        try:
            validate_savings_provenance(candidate)
        except ValueError as exc:
            provenance_errors.append({"instrument_id": inst_id, "error": str(exc)})
            continue

        if not cur:
            diffs.append(
                {
                    "instrument_id": inst_id,
                    "action": "NEW_INSTRUMENT",
                    "old_rate": None,
                    "new_rate": float(candidate["base_rate_pct"]),
                    "effective_from": candidate.get("effective_from"),
                }
            )
        elif abs(float(cur["base_rate_pct"]) - float(candidate["base_rate_pct"])) >= 1e-6 or abs(
            float(cur.get("senior_citizen_bonus_bps") or 0.0)
            - float(candidate.get("senior_citizen_bonus_bps") or 0.0)
        ) >= 1e-6:
            diffs.append(
                {
                    "instrument_id": inst_id,
                    "action": "RATE_CHANGE",
                    "old_rate": float(cur["base_rate_pct"]),
                    "new_rate": float(candidate["base_rate_pct"]),
                    "old_effective_from": cur.get("effective_from"),
                    "effective_from": candidate.get("effective_from"),
                }
            )
        else:
            _, cur_hash = compute_material_terms_snapshot(cur)
            _, cand_hash = compute_material_terms_snapshot(candidate)
            if cur_hash != cand_hash:
                diffs.append(
                    {
                        "instrument_id": inst_id,
                        "action": "TERMS_OR_EVIDENCE_CHANGE",
                        "old_rate": float(cur["base_rate_pct"]),
                        "new_rate": float(candidate["base_rate_pct"]),
                        "effective_from": cur.get("effective_from"),
                    }
                )

    for tv in tax_rules:
        try:
            validate_tax_rule_provenance(tv)
        except ValueError as exc:
            provenance_errors.append({"rule_version": tv.get("rule_version"), "error": str(exc)})

    stale = [
        {
            "instrument_id": inst["instrument_id"],
            "status": inst["staleness"]["status"],
            "badge": inst["staleness"]["badge_label"],
            "effective_from": inst["effective_from"],
        }
        for inst in existing_map.values()
        if inst.get("staleness", {}).get("status") != "FRESH"
    ]

    return {
        "mode": "CHECK_ONLY",
        "read_only": True,
        "source_file": str(file_path),
        "incoming_count": len(incoming),
        "active_db_count": len(existing_map),
        "pending_diffs": diffs,
        "provenance_errors": provenance_errors,
        "staleness_alerts": stale,
    }


def run_check(file_path: Path) -> int:
    report = build_check_report(Path(file_path))
    print(json.dumps(report, indent=2))
    return 1 if report["provenance_errors"] else 0


def run_apply(
    file_path: Path,
    force: bool = False,
    *,
    override_reason: str | None = None,
    override_operator: str | None = None,
    reference_date: str | None = None,
) -> Dict[str, Any]:
    """Apply a JSON rate payload into the active DB while honoring monotonic effective_from guards.

    - Baseline file (`baseline_savings_universe.json`): preserves newer DB rates/revisions unless `force=True`.
    - Custom bulletin file: advances newer/same-date revisions (`revision_seq + 1` on same-date),
      stores future-dated rates as `SCHEDULED_FUTURE`, and rejects older `effective_from` regressions
      unless `force=True` with explicit `override_reason` and `override_operator`.
    """
    init_db()
    target_path = Path(file_path)
    if target_path.resolve() == BASELINE_SAVINGS_JSON_PATH.resolve():
        return seed_baseline_savings_universe(
            file_path=target_path,
            force_overwrite=bool(force),
            override_reason=override_reason,
            override_operator=override_operator,
            reference_date=reference_date,
        )

    payload = load_baseline_savings_payload(target_path)
    items = payload.get("instruments", payload if isinstance(payload, list) else [])
    tax_versions = payload.get("tax_rule_versions", []) if isinstance(payload, dict) else []
    inserted = 0
    rate_updated = 0
    terms_updated = 0
    scheduled_future = 0
    skipped_older = 0
    metadata_synced = 0
    try:
        tax_saved = seed_tax_rule_versions(tax_versions=tax_versions) if tax_versions else 0
        for entry in items:
            inst_id = str(entry.get("instrument_id") or "").strip().upper()
            existing = get_savings_instrument_by_id(inst_id, reference_date=reference_date) or {}
            merged = dict(existing)
            merged.update(entry)
            res = upsert_savings_instrument(
                merged,
                force_overwrite=bool(force or entry.get("force_overwrite")),
                override_reason=entry.get("override_reason") or override_reason,
                override_operator=entry.get("override_operator") or override_operator,
                baseline_seed=False,
                reference_date=reference_date,
            )
            st = res["status"]
            if st == "INSERTED":
                inserted += 1
            elif st == "RATE_UPDATED":
                rate_updated += 1
            elif st == "TERMS_OR_EVIDENCE_UPDATED":
                terms_updated += 1
            elif st == "SCHEDULED_FUTURE_RATE":
                scheduled_future += 1
            elif st == "SKIPPED_OLDER_EFFECTIVE_DATE":
                skipped_older += 1
            else:
                metadata_synced += 1
        return {
            "status": "SUCCESS",
            "total_processed": len(items),
            "inserted": inserted,
            "rate_updated": rate_updated,
            "terms_updated": terms_updated,
            "scheduled_future": scheduled_future,
            "skipped_older_effective_date": skipped_older,
            "metadata_synced": metadata_synced,
            "tax_versions_saved": tax_saved,
        }
    except Exception as exc:
        logger.error("Failed applying custom savings bulletin %s: %s", target_path, exc)
        return {
            "status": "ERROR",
            "error": str(exc),
            "total_processed": 0,
            "inserted": inserted,
            "rate_updated": rate_updated,
            "terms_updated": terms_updated,
            "scheduled_future": scheduled_future,
            "skipped_older_effective_date": skipped_older,
            "metadata_synced": metadata_synced,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import and verify Indian fixed savings & deposit rates.")
    parser.add_argument("--file", type=str, default=str(BASELINE_SAVINGS_JSON_PATH), help="Path to JSON rate file.")
    parser.add_argument("--check", action="store_true", help="Read-only dry-run diff & staleness check (0 DB writes).")
    parser.add_argument("--apply", action="store_true", help="Apply JSON rate updates into DB + rate observations.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Explicitly authorize overwriting active rates with older effective_from dates or baseline reseeds.",
    )
    parser.add_argument(
        "--reason",
        type=str,
        default=None,
        help="Mandatory operator justification (>= 8 chars) when --force is used.",
    )
    parser.add_argument(
        "--operator",
        type=str,
        default=None,
        help="Mandatory operator identity when --force is used (e.g. cli:rahul_sharma).",
    )
    parser.add_argument(
        "--reference-date",
        type=str,
        default=None,
        help="Optional YYYY-MM-DD reference date for scheduled future rate evaluation.",
    )
    parser.add_argument(
        "--activate-due",
        action="store_true",
        help="Promote any matured SCHEDULED_FUTURE rate observations as of --reference-date / today.",
    )
    parser.add_argument(
        "--auto-fetch",
        action="store_true",
        help="Run automated inbox + certifi-verified public statutory rate verification.",
    )
    parser.add_argument("--no-network", action="store_true", help="Disable outbound HTTPS probes in --auto-fetch.")
    args = parser.parse_args()

    target_file = Path(args.file)

    if args.activate_due:
        init_db()
        summary = activate_due_future_savings_rates(reference_date=args.reference_date)
        print(json.dumps(summary, indent=2))
        return 0

    if args.auto_fetch:
        init_db()
        allow_net = not args.no_network and os.environ.get("TESTING") != "1"
        summary = verify_and_sync_automated_savings_rates(
            edition_date=args.reference_date,
            allow_network=allow_net,
        )
        print(json.dumps(summary, indent=2))
        return 0 if summary.get("status") == "SUCCESS" else 1

    if args.apply:
        summary = run_apply(
            target_file,
            force=bool(args.force),
            override_reason=args.reason,
            override_operator=args.operator,
            reference_date=args.reference_date,
        )
        print(json.dumps(summary, indent=2))
        return 0 if summary.get("status") == "SUCCESS" else 1

    return run_check(target_file)


if __name__ == "__main__":
    raise SystemExit(main())
