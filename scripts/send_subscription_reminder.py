#!/usr/bin/env python3
"""
scripts/send_subscription_reminder.py
==============================================================================
Daily Subscription Renewal, Covered-Services & Cost-Optimization Reminder.

Capabilities:
1. Reads canonical structured ledger `data/vendor_subscriptions.json`.
2. Dynamically evaluates rolling renewal dates, overdue receipt checks, active
   early-month billing windows, and Due-Date Pattern Lock progress.
3. Queries live runtime usage (PostgreSQL/SQLite storage, Gemini/Vertex AI
   spend, Resend daily email count) via `get_all_provider_constraints()`.
4. Formats a concise Plain-Text + Moatnomics HTML digest covering:
   - Upcoming renewals & immediate billing-window checks
   - Pattern Lock progress (tracks when daily reminders can graduate to pre-renewal)
   - Sub-services & workloads covered under each subscription
   - Cost vs. Performance Optimization Playbook (`OPEN` items)
5. Dispatches at most 1 email per IST date via Resend/SMTP (`--send-email`),
   guarded by a 20-hour distributed `job_lease` across PostgreSQL & SQLite.
==============================================================================
"""

from __future__ import annotations

import argparse
import calendar
import html
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

logger = logging.getLogger("equity_research.scripts.subscription_reminder")
try:
    os.chdir(ROOT_DIR)
except OSError as exc:
    logger.warning("Could not change working directory to %s: %s", ROOT_DIR, exc)

from core.config import get_secret
from core.db.connection import get_connection, get_placeholder, is_postgres_connection
from core.db.locks import ensure_lock_table_exists, job_lease, prune_zombie_leases, release_job_lease
from core.notify import (
    _dispatch_via_resend,
    _dispatch_via_smtp,
    _is_live_email_dispatch_allowed,
    get_admin_notification_email,
)

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_REGISTRY_PATH = ROOT_DIR / "data" / "vendor_subscriptions.json"
DEFAULT_DOC_PATH = ROOT_DIR / "docs" / "VENDOR_SUBSCRIPTIONS.md"
DAILY_REMINDER_LEASE_TTL_SECONDS = 72000  # 20 hours


def _parse_iso_date(raw: Optional[str]) -> Optional[date]:
    if not raw or not isinstance(raw, str):
        return None
    try:
        return datetime.strptime(raw.strip()[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        logger.warning("Invalid ISO date %r in subscription registry: %s", raw, exc)
        return None


def _add_one_month_clamped(base_year: int, base_month: int, anchor_day: int) -> date:
    if base_month == 12:
        next_year, next_month = base_year + 1, 1
    else:
        next_year, next_month = base_year, base_month + 1
    max_day = calendar.monthrange(next_year, next_month)[1]
    return date(next_year, next_month, min(anchor_day, max_day))


def load_subscription_registry(registry_path: Path = DEFAULT_REGISTRY_PATH) -> Dict[str, Any]:
    with open(registry_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or "subscriptions" not in data:
        raise ValueError(f"Malformed subscription registry at {registry_path}")
    return data


def evaluate_subscription_due_state(sub: Dict[str, Any], ref_date: date) -> Dict[str, Any]:
    """Computes dynamic due state, next expected date, and urgency for a single subscription."""
    pattern_status = str(sub.get("pattern_status") or "UNCONFIRMED").upper()
    cycle = str(sub.get("billing_cycle") or "monthly_arrears").lower()
    anchor_day = sub.get("anchor_day")
    last_paid = _parse_iso_date(sub.get("last_paid_date"))
    period_end = _parse_iso_date(sub.get("last_paid_period_end"))

    next_expected: Optional[date] = None
    days_until: Optional[int] = None
    state = "PATTERN_UNCONFIRMED"
    headline = "Verify billing portal / next invoice to lock in due-date pattern"

    if pattern_status == "CONFIRMED":
        if cycle in ("monthly_arrears", "monthly_anchor") and isinstance(anchor_day, int):
            if last_paid:
                next_expected = _add_one_month_clamped(last_paid.year, last_paid.month, anchor_day)
            else:
                max_d = calendar.monthrange(ref_date.year, ref_date.month)[1]
                candidate = date(ref_date.year, ref_date.month, min(anchor_day, max_d))
                next_expected = (
                    candidate
                    if candidate >= ref_date
                    else _add_one_month_clamped(ref_date.year, ref_date.month, anchor_day)
                )

            days_until = (next_expected - ref_date).days
            if days_until < 0:
                state = "RECEIPT_CHECK_OVERDUE"
                headline = (
                    f"Expected charge {next_expected.isoformat()} ({abs(days_until)}d ago) — "
                    f"confirm charge & log receipt"
                )
            elif days_until == 0:
                state = "DUE_TODAY"
                headline = f"Due TODAY ({next_expected.isoformat()})"
            elif days_until <= 7:
                state = "DUE_SOON"
                headline = f"Due in {days_until} day(s) ({next_expected.isoformat()})"
            else:
                state = "SCHEDULED"
                headline = f"Next charge {next_expected.isoformat()} (in {days_until} days)"

        elif cycle == "annual":
            if period_end:
                next_expected = period_end
            else:
                a_month = int(sub.get("anchor_month") or 1)
                a_day = int(anchor_day or 1)
                next_expected = date(ref_date.year + 1, a_month, a_day)

            lead_days = int(sub.get("auto_renew_lead_days") or 30)
            days_until = (next_expected - ref_date).days
            auto_renew_date = next_expected - timedelta(days=lead_days)
            if days_until < 0:
                state = "RECEIPT_CHECK_OVERDUE"
                headline = f"Annual expiry {next_expected.isoformat()} passed — confirm renewal"
            elif ref_date >= auto_renew_date:
                state = "DUE_SOON"
                headline = (
                    f"Within {lead_days}d auto-renew window (renews {auto_renew_date.isoformat()}, "
                    f"expires {next_expected.isoformat()})"
                )
            else:
                state = "SCHEDULED"
                headline = (
                    f"Expires {next_expected.isoformat()} (auto-renew {auto_renew_date.isoformat()}, "
                    f"{days_until}d out)"
                )

        elif cycle == "prepaid_balance":
            state = "BALANCE_MONITORED"
            headline = "Prepaid balance — top up only when credits drop below $5"

    else:
        win = sub.get("expected_window_days") or []
        if len(win) == 2 and int(win[0]) <= ref_date.day <= int(win[1]) and not (win[0] == 1 and win[1] == 31):
            state = "VERIFY_BILLING_WINDOW_NOW"
            headline = (
                f"Active billing window now (Day {win[0]}–{win[1]} of month) — "
                f"check card/portal for invoice to lock anchor day"
            )
        elif cycle == "prepaid_balance":
            state = "PATTERN_UNCONFIRMED"
            headline = "Confirm current prepaid credit balance & auto-top-up status"
        else:
            state = "PATTERN_UNCONFIRMED"
            headline = "Unconfirmed monthly anchor — check billing portal or drop next receipt"

    return {
        **sub,
        "computed_state": state,
        "next_expected_iso": next_expected.isoformat() if next_expected else None,
        "days_until": days_until,
        "status_headline": headline,
    }


def _collect_live_runtime_metrics() -> List[Dict[str, str]]:
    """Safely collects live DB storage, LLM spend, and email quota telemetry."""
    snapshots: List[Dict[str, str]] = []
    try:
        from core.analytics.provider_quotas import get_all_provider_constraints

        quota_data = get_all_provider_constraints()
        for p in quota_data.get("providers", []):
            pid = p.get("id")
            if pid in ("supabase_db", "gemini_api", "email_provider", "host_runtime"):
                snapshots.append(
                    {
                        "name": str(p.get("name") or pid),
                        "status": str(p.get("status") or "UNKNOWN"),
                        "primary": str(p.get("primary_metric") or "N/A"),
                        "secondary": str(p.get("secondary_metric") or ""),
                    }
                )
    except Exception as exc:
        logger.warning("Live provider quota probe skipped or degraded: %s", exc)
    return snapshots


# Small savings rates (PPF, SCSS, NSC, ...) are reset by the Finance Ministry once a quarter,
# announced around the quarter's last day. The official pages cannot be read automatically any more
# (moved / JavaScript-only / TLS failures), so the owner confirms each quarter's rates by hand.
SAVINGS_REVIEW_LEAD_DAYS = 6


def collect_savings_rate_review(target_date: date) -> Dict[str, Any]:
    """Small-savings rates due for the quarterly check, plus official-page checks that are failing.

    Never invents rates: on a database error the section says it is unavailable.
    """
    try:
        from core.db.savings import PROBE_VERIFIED, get_active_savings_instruments, get_savings_probe_health

        instruments = get_active_savings_instruments(category="SMALL_SAVINGS")
        health = get_savings_probe_health()
    except Exception as err:
        logger.warning("Savings rate review unavailable: %s", err)
        return {"available": False, "error": str(err)[:200]}

    schemes = []
    for inst in instruments:
        review_dt = _parse_iso_date(inst.get("next_review_date"))
        if review_dt is None:
            continue
        days_left = (review_dt - target_date).days
        if days_left < 0:
            state = "OVERDUE"
        elif days_left <= SAVINGS_REVIEW_LEAD_DAYS:
            state = "DUE"
        else:
            state = "OK"
        schemes.append({
            "instrument_id": inst.get("instrument_id"),
            "scheme_name": inst.get("scheme_name") or inst.get("instrument_id"),
            "base_rate_pct": inst.get("base_rate_pct"),
            "effective_from": inst.get("effective_from"),
            "next_review_date": review_dt.isoformat(),
            "days_left": days_left,
            "state": state,
        })
    schemes.sort(key=lambda x: (x["days_left"], str(x["instrument_id"])))
    failing = [
        {"instrument_id": pid, **info}
        for pid, info in sorted((health.get("probes") or {}).items())
        if isinstance(info, dict) and info.get("status") != PROBE_VERIFIED
    ]
    action = [x for x in schemes if x["state"] != "OK"]
    return {
        "available": True,
        "schemes": schemes,
        "action_needed": action,
        "overdue": any(x["state"] == "OVERDUE" for x in action),
        "failing_probes": failing,
        "probes_checked_on": health.get("checked_on"),
    }


SAVINGS_UPDATE_HOWTO = (
    "When the Finance Ministry announces the new quarter's rates, update base_rate_pct, "
    "effective_from and next_review_date for each scheme in "
    "data/savings_rates/baseline_savings_universe.json (if rates are unchanged, still move "
    "effective_from and next_review_date to the new quarter), then run "
    "`python3 scripts/import_savings_rates.py --check` and `--apply`."
)


def build_reminder_report(
    ref_date: Optional[date] = None,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    include_live_metrics: bool = True,
    include_savings_review: bool = True,
) -> Dict[str, Any]:
    """Compiles the complete daily subscription, covered-services & optimization report."""
    target_date = ref_date or datetime.now(IST).date()
    registry = load_subscription_registry(registry_path)

    evaluated_subs = [
        evaluate_subscription_due_state(s, target_date)
        for s in registry.get("subscriptions", [])
    ]
    free_accounts = registry.get("free_tier_accounts", [])
    open_optimizations = [
        opt for opt in registry.get("optimizations", [])
        if str(opt.get("status") or "OPEN").upper() == "OPEN"
    ]

    confirmed_count = sum(1 for s in evaluated_subs if s.get("pattern_status") == "CONFIRMED")
    total_tracked = len(evaluated_subs)
    unconfirmed_subs = [s for s in evaluated_subs if s.get("pattern_status") != "CONFIRMED"]
    all_patterns_fixed = len(unconfirmed_subs) == 0

    urgent_items = [
        s for s in evaluated_subs
        if s["computed_state"] in ("DUE_TODAY", "DUE_SOON", "RECEIPT_CHECK_OVERDUE", "VERIFY_BILLING_WINDOW_NOW")
    ]

    live_metrics = _collect_live_runtime_metrics() if include_live_metrics else []
    savings_review = (
        collect_savings_rate_review(target_date) if include_savings_review else {"available": False}
    )

    if any(s["computed_state"] in ("DUE_TODAY", "RECEIPT_CHECK_OVERDUE") for s in evaluated_subs):
        subj_prefix = "[Action Needed]"
    elif any(s["computed_state"] == "DUE_SOON" for s in evaluated_subs):
        subj_prefix = "[Renewal Due Soon]"
    elif savings_review.get("overdue"):
        subj_prefix = "[Savings Rates Overdue]"
    elif savings_review.get("action_needed"):
        subj_prefix = "[Confirm Savings Rates]"
    elif not all_patterns_fixed:
        subj_prefix = f"[Pattern Lock {confirmed_count}/{total_tracked}]"
    else:
        subj_prefix = "[All Patterns Confirmed]"

    subject = (
        f"{subj_prefix} Moatnomics Subscriptions & Cost Optimization Brief — "
        f"{target_date.isoformat()}"
    )

    return {
        "edition_date": target_date.isoformat(),
        "subject": subject,
        "confirmed_count": confirmed_count,
        "total_tracked": total_tracked,
        "all_patterns_fixed": all_patterns_fixed,
        "urgent_items": urgent_items,
        "unconfirmed_subs": unconfirmed_subs,
        "evaluated_subs": evaluated_subs,
        "free_accounts": free_accounts,
        "open_optimizations": open_optimizations,
        "live_metrics": live_metrics,
        "payment_history": registry.get("payment_history", []),
        "savings_review": savings_review,
    }


def render_reminder_text(report: Dict[str, Any]) -> str:
    lines: List[str] = [
        "========================================================================",
        f"MOATNOMICS — SUBSCRIPTION RENEWAL & OPTIMIZATION BRIEF ({report['edition_date']} IST)",
        "========================================================================",
        f"Pattern Lock Progress: {report['confirmed_count']} / {report['total_tracked']} Subscriptions Confirmed",
    ]
    if report["all_patterns_fixed"]:
        lines.append(
            "STATUS: All due-date patterns are now CONFIRMED! Ready to switch this daily "
            "reminder to a 7-day / 1-day pre-renewal schedule whenever you approve."
        )
    else:
        pending_names = ", ".join(s["vendor"] for s in report["unconfirmed_subs"])
        lines.append(f"Still Unconfirmed: {pending_names} (drop receipts or check portals to lock).")

    lines.append("")
    lines.append("1. IMMEDIATE RENEWALS & BILLING WINDOWS")
    lines.append("------------------------------------------------------------------------")
    if report["urgent_items"]:
        for item in report["urgent_items"]:
            lines.append(
                f"• [{item['computed_state']}] {item['vendor']} ({item['account_label']}): "
                f"{item['status_headline']} | Est: {item.get('estimated_monthly_cost', 'N/A')} | "
                f"{item.get('billing_url', '')}"
            )
    else:
        lines.append("• Zero renewals or active billing windows due in the next 7 days.")

    lines.append("")
    lines.append("2. ALL TRACKED SUBSCRIPTIONS & SUB-SERVICES COVERED")
    lines.append("------------------------------------------------------------------------")
    for s in report["evaluated_subs"]:
        lines.append(
            f"■ {s['vendor']} [{s['pattern_status']}] — {s['status_headline']}"
        )
        lines.append(f"  Cost / Method: {s.get('estimated_monthly_cost')} | Card: {s.get('payment_method')}")
        for li in s.get("billable_line_items", []):
            lines.append(f"    - Billed Item: {li}")
        for wl in s.get("project_workloads", []):
            lines.append(f"    - Workload:    {wl}")

    lines.append("")
    lines.append("3. ZERO-COST / FREE-TIER ACCOUNTS & QUOTA CEILINGS")
    lines.append("------------------------------------------------------------------------")
    for fa in report["free_accounts"]:
        workloads_joined = "; ".join(fa.get("project_workloads", []))
        lines.append(
            f"• {fa['vendor']} ({fa['billing_model']}) — Ceiling: {fa['quota_ceiling']} | "
            f"Covers: {workloads_joined}"
        )

    if report["live_metrics"]:
        lines.append("")
        lines.append("4. LIVE RUNTIME QUOTA & USAGE TELEMETRY")
        lines.append("------------------------------------------------------------------------")
        for lm in report["live_metrics"]:
            lines.append(f"• {lm['name']} [{lm['status']}]: {lm['primary']} ({lm['secondary']})")

    if report["open_optimizations"]:
        lines.append("")
        lines.append("5. OPEN COST vs. PERFORMANCE OPTIMIZATIONS")
        lines.append("------------------------------------------------------------------------")
        for opt in report["open_optimizations"]:
            lines.append(f"• [{opt['id']}] {opt['service']}: {opt['recommendation']}")
            lines.append(f"    Savings:  {opt['cost_impact']}")
            lines.append(f"    Tradeoff: {opt['tradeoff']}")

    sr = report.get("savings_review") or {}
    if sr.get("available") and (sr.get("action_needed") or sr.get("failing_probes")):
        lines.append("")
        lines.append("6. SMALL SAVINGS RATES (QUARTERLY CHECK)")
        lines.append("------------------------------------------------------------------------")
        for x in sr.get("action_needed", []):
            when = (
                f"review date {x['next_review_date']} passed {-x['days_left']} day(s) ago"
                if x["state"] == "OVERDUE"
                else f"review date {x['next_review_date']} (in {x['days_left']} day(s))"
            )
            lines.append(
                f"• [{x['state']}] {x['scheme_name']} ({x['instrument_id']}): {x['base_rate_pct']}% "
                f"since {x['effective_from']}; {when}"
            )
        if sr.get("action_needed"):
            lines.append(f"  How to update: {SAVINGS_UPDATE_HOWTO}")
        for f in sr.get("failing_probes", []):
            lines.append(
                f"• Automatic check for {f['instrument_id']} failing since {f.get('failing_since')}: "
                f"{f.get('status')} ({f.get('reason')}) — {f.get('url')}"
            )
    elif sr.get("available") is False and sr.get("error"):
        lines.append("")
        lines.append(f"6. SMALL SAVINGS RATES: check unavailable ({sr['error']}).")

    lines.append("")
    lines.append("Ledger File: docs/VENDOR_SUBSCRIPTIONS.md | Data: data/vendor_subscriptions.json")
    return "\n".join(lines)


def render_reminder_html(report: Dict[str, Any]) -> str:
    esc = html.escape

    urgent_rows = ""
    if report["urgent_items"]:
        for s in report["urgent_items"]:
            badge_bg = "#8B2635" if s["computed_state"] in ("DUE_TODAY", "RECEIPT_CHECK_OVERDUE") else "#9A6700"
            urgent_rows += f"""
            <div style="background:#FFFFFF;border-left:4px solid {badge_bg};padding:12px 14px;border-radius:6px;margin-bottom:10px;border:1px solid #D9E3E8;">
              <div style="font-size:11px;font-weight:700;color:{badge_bg};text-transform:uppercase;letter-spacing:0.06em;">{esc(s['computed_state'])}</div>
              <div style="font-size:15px;font-weight:700;color:#0B2337;margin-top:2px;">{esc(s['vendor'])} <span style="font-weight:400;color:#52606D;font-size:13px;">({esc(s['account_label'])})</span></div>
              <div style="font-size:13px;color:#282F33;margin-top:4px;">{esc(s['status_headline'])} &bull; <strong>{esc(str(s.get('estimated_monthly_cost') or ''))}</strong></div>
              <div style="margin-top:6px;"><a href="{esc(str(s.get('billing_url') or '#'))}" style="color:#0E3D32;font-size:12px;font-weight:600;text-decoration:none;">Open Billing Portal &rarr;</a></div>
            </div>
            """
    else:
        urgent_rows = """
        <div style="background:#FFFFFF;border-left:4px solid #0E3D32;padding:12px 14px;border-radius:6px;border:1px solid #D9E3E8;font-size:13px;color:#282F33;">
          Zero renewals or billing windows due in the next 7 days.
        </div>
        """

    sub_cards = ""
    for s in report["evaluated_subs"]:
        status_pill_bg = "#0E3D32" if s["pattern_status"] == "CONFIRMED" else "#7C4D12"
        items_html = "".join(
            f"<li style='margin:2px 0;'><strong>Billed:</strong> {esc(li)}</li>"
            for li in s.get("billable_line_items", [])
        )
        workloads_html = "".join(
            f"<li style='margin:2px 0;'><strong>Covers:</strong> {esc(wl)}</li>"
            for wl in s.get("project_workloads", [])
        )
        sub_cards += f"""
        <div style="background:#FFFFFF;border:1px solid #D9E3E8;border-radius:6px;padding:12px 14px;margin-bottom:10px;">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
            <strong style="font-size:14px;color:#0B2337;">{esc(s['vendor'])}</strong>
            <span style="background:{status_pill_bg};color:#F7F5EE;font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;">{esc(s['pattern_status'])}</span>
          </div>
          <div style="font-size:12px;color:#282F33;margin-top:4px;">{esc(s['status_headline'])}</div>
          <div style="font-size:12px;color:#52606D;margin-top:2px;">Est: {esc(str(s.get('estimated_monthly_cost') or ''))} &bull; Payment: {esc(str(s.get('payment_method') or ''))}</div>
          <ul style="margin:8px 0 0 0;padding-left:18px;font-size:12px;color:#282F33;line-height:1.45;">
            {items_html}
            {workloads_html}
          </ul>
        </div>
        """

    metrics_html = ""
    if report["live_metrics"]:
        metric_items = "".join(
            f"<li style='margin:4px 0;'><strong>{esc(m['name'])}</strong> ({esc(m['status'])}): {esc(m['primary'])} — <span style='color:#52606D;'>{esc(m['secondary'])}</span></li>"
            for m in report["live_metrics"]
        )
        metrics_html = f"""
        <h3 style="font-size:14px;color:#0B2337;text-transform:uppercase;letter-spacing:0.05em;margin:22px 0 8px;">Live Quota &amp; Spend Snapshot</h3>
        <div style="background:#FFFFFF;border:1px solid #D9E3E8;border-radius:6px;padding:12px 16px;font-size:12px;color:#282F33;">
          <ul style="margin:0;padding-left:18px;line-height:1.5;">{metric_items}</ul>
        </div>
        """

    opt_cards = ""
    for opt in report["open_optimizations"]:
        opt_cards += f"""
        <div style="background:#FFFFFF;border:1px solid #D9E3E8;border-left:3px solid #0E3D32;border-radius:6px;padding:10px 14px;margin-bottom:8px;font-size:12px;">
          <div style="font-weight:700;color:#0B2337;">[{esc(opt['id'])}] {esc(opt['service'])}</div>
          <div style="color:#282F33;margin-top:3px;">{esc(opt['recommendation'])}</div>
          <div style="color:#0E3D32;font-weight:600;margin-top:4px;">Impact: {esc(opt['cost_impact'])}</div>
          <div style="color:#52606D;margin-top:2px;">Tradeoff: {esc(opt['tradeoff'])}</div>
        </div>
        """

    savings_html = ""
    sr = report.get("savings_review") or {}
    if sr.get("available") and (sr.get("action_needed") or sr.get("failing_probes")):
        due_rows = ""
        for x in sr.get("action_needed", []):
            colour = "#8B2635" if x["state"] == "OVERDUE" else "#9A6700"
            when = (
                f"Review date {x['next_review_date']} passed {-x['days_left']} day(s) ago"
                if x["state"] == "OVERDUE"
                else f"Review date {x['next_review_date']} (in {x['days_left']} day(s))"
            )
            due_rows += (
                f"<li style='margin:4px 0;'><strong style='color:{colour};'>{esc(x['state'])}</strong> "
                f"{esc(str(x['scheme_name']))} ({esc(str(x['instrument_id']))}): "
                f"<strong>{esc(str(x['base_rate_pct']))}%</strong> since {esc(str(x['effective_from']))} — {esc(when)}</li>"
            )
        probe_rows = "".join(
            f"<li style='margin:4px 0;'>Automatic check for <strong>{esc(str(f['instrument_id']))}</strong> failing since "
            f"{esc(str(f.get('failing_since')))}: {esc(str(f.get('status')))} ({esc(str(f.get('reason')))})</li>"
            for f in sr.get("failing_probes", [])
        )
        howto = (
            f"<div style='margin-top:8px;color:#52606D;'>{esc(SAVINGS_UPDATE_HOWTO)}</div>"
            if sr.get("action_needed") else ""
        )
        savings_html = f"""
        <h3 style="font-size:14px;color:#0B2337;text-transform:uppercase;letter-spacing:0.05em;margin:22px 0 8px;">Small Savings Rates (Quarterly Check)</h3>
        <div style="background:#FFFFFF;border:1px solid #D9E3E8;border-left:3px solid #9A6700;border-radius:6px;padding:12px 16px;font-size:12px;color:#282F33;">
          <ul style="margin:0;padding-left:18px;line-height:1.5;">{due_rows}{probe_rows}</ul>
          {howto}
        </div>
        """

    graduation_banner = (
        "<div style='background:#E6F4EA;border:1px solid #0E3D32;color:#0E3D32;padding:10px 14px;border-radius:6px;font-size:12px;font-weight:600;margin-bottom:16px;'>"
        "All subscription due-date patterns are CONFIRMED. Ready to switch from Daily to Pre-Renewal (7d &amp; 1d prior) whenever you approve."
        "</div>"
        if report["all_patterns_fixed"]
        else (
            f"<div style='background:#FFF8E7;border:1px solid #D9A441;color:#5C4008;padding:10px 14px;border-radius:6px;font-size:12px;margin-bottom:16px;'>"
            f"<strong>Pattern Lock Progress: {report['confirmed_count']} / {report['total_tracked']} Confirmed.</strong> "
            f"Remaining to verify: {esc(', '.join(s['vendor'] for s in report['unconfirmed_subs']))}."
            f"</div>"
        )
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#F7F5EE;color:#282F33;margin:0;padding:20px;">
  <div style="max-width:680px;margin:0 auto;background:#F7F5EE;">
    <div style="background:#0B2337;color:#F7F5EE;padding:20px 24px;border-radius:8px;border-bottom:3px solid #C7E268;margin-bottom:16px;">
      <div style="font-size:11px;font-weight:700;color:#C7E268;text-transform:uppercase;letter-spacing:0.08em;">Moatnomics Infrastructure Ops</div>
      <h2 style="margin:4px 0 0;font-family:'Playfair Display',Georgia,serif;font-size:20px;color:#F7F5EE;">Subscription Renewal &amp; Cost Optimization Brief</h2>
      <div style="font-size:12px;color:#D9E3E8;margin-top:4px;">Edition Date: {esc(report['edition_date'])} &bull; 9:00 PM IST Daily Tracker</div>
    </div>

    {graduation_banner}

    <h3 style="font-size:14px;color:#0B2337;text-transform:uppercase;letter-spacing:0.05em;margin:0 0 8px;">1. Immediate Renewals &amp; Active Billing Windows</h3>
    {urgent_rows}

    <h3 style="font-size:14px;color:#0B2337;text-transform:uppercase;letter-spacing:0.05em;margin:22px 0 8px;">2. Subscriptions &amp; Covered Workloads</h3>
    {sub_cards}

    {metrics_html}

    {savings_html}

    <h3 style="font-size:14px;color:#0B2337;text-transform:uppercase;letter-spacing:0.05em;margin:22px 0 8px;">3. Cost vs. Performance Optimizations (Open)</h3>
    {opt_cards}

    <div style="font-size:11px;color:#52606D;text-align:center;margin-top:20px;padding-top:12px;border-top:1px solid #D9E3E8;">
      Canonical Ledger: <code>docs/VENDOR_SUBSCRIPTIONS.md</code> &bull; Drop new PDF invoices into your Antigravity thread to lock in unconfirmed billing dates.
    </div>
  </div>
</body>
</html>"""


def _is_reminder_lease_already_held(lease_name: str) -> bool:
    """Checks whether an unexpired daily reminder lease already exists (even from the same PID)."""
    ensure_lock_table_exists()
    prune_zombie_leases(job_name=lease_name)
    conn = get_connection()
    is_pg = is_postgres_connection(conn)
    cur = conn.cursor()
    p = get_placeholder()
    now_iso = datetime.now(IST).isoformat()
    active_cmp = f"expires_at >= {p}" if is_pg else f"datetime(expires_at) >= datetime({p})"
    try:
        cur.execute(
            f"SELECT 1 FROM distributed_job_locks WHERE job_name = {p} AND {active_cmp} LIMIT 1",
            (lease_name, now_iso),
        )
        return cur.fetchone() is not None
    except Exception as exc:
        logger.warning("Failed checking existing reminder lease %s: %s", lease_name, exc)
        return False
    finally:
        cur.close()
        try:
            conn.close()
        except Exception as close_exc:
            logger.debug("Connection close notice in _is_reminder_lease_already_held: %s", close_exc)


def dispatch_subscription_reminder_email(
    report: Dict[str, Any],
    force: bool = False,
) -> Dict[str, Any]:
    """Dispatches the compiled subscription reminder email once per IST date."""
    edition_date = report["edition_date"]
    lease_name = f"vendor_subscription_reminder_{edition_date}"

    def _send_payload() -> Dict[str, Any]:
        recipient = get_admin_notification_email()
        sender = (
            get_secret("SMTP_FROM")
            or get_secret("RESEND_FROM")
            or "Moatnomics Service Desk <desk@moatnomics.com>"
        )
        text_body = render_reminder_text(report)
        html_body = render_reminder_html(report)

        if get_secret("RESEND_API_KEY"):
            ok = _dispatch_via_resend(sender, recipient, report["subject"], text_body, html=html_body)
            provider = "resend"
        elif get_secret("SMTP_HOST") and get_secret("SMTP_USER") and get_secret("SMTP_PASSWORD"):
            ok = _dispatch_via_smtp(sender, recipient, report["subject"], text_body, html=html_body)
            provider = "smtp"
        else:
            logger.warning("No outgoing email credentials configured for subscription reminder.")
            return {
                "status": "UNCONFIGURED",
                "delivered": False,
                "edition_date": edition_date,
            }

        if not ok:
            raise RuntimeError(f"Email dispatch via {provider} returned False for {edition_date}")

        live_mode = _is_live_email_dispatch_allowed()
        return {
            "status": "SENT" if live_mode else "SANDBOX_LOGGED",
            "delivered": True,
            "provider": provider,
            "edition_date": edition_date,
        }

    if force:
        return _send_payload()

    if _is_reminder_lease_already_held(lease_name):
        logger.info(
            "Subscription reminder lease %s already held; skipping duplicate email.",
            lease_name,
        )
        return {
            "status": "SKIPPED_ALREADY_SENT",
            "delivered": False,
            "edition_date": edition_date,
        }

    with job_lease(
        lease_name,
        ttl_seconds=DAILY_REMINDER_LEASE_TTL_SECONDS,
        release_on_exit=False,
        release_on_failure=True,
    ) as acquired:
        if not acquired:
            logger.info(
                "Subscription reminder lease %s already held; skipping duplicate email.",
                lease_name,
            )
            return {
                "status": "SKIPPED_ALREADY_SENT",
                "delivered": False,
                "edition_date": edition_date,
            }
        outcome = _send_payload()
        if outcome.get("status") != "SENT":
            release_job_lease(lease_name)
        return outcome


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s IST [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Compile and optionally email the daily Moatnomics subscription & optimization reminder."
    )
    parser.add_argument(
        "--date",
        help="Optional IST reference date (YYYY-MM-DD); defaults to today in Asia/Kolkata.",
    )
    parser.add_argument(
        "--send-email",
        action="store_true",
        help="Dispatch email to ADMIN_ALERT_EMAIL (guarded by 20h distributed daily job lease).",
    )
    parser.add_argument(
        "--live-email",
        action="store_true",
        help="Enable live email dispatch outside CI (sets ENABLE_LIVE_EMAIL_DISPATCH=1; still guarded by daily job lease unless --force is passed).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass the daily distributed job lease when --send-email is set.",
    )
    parser.add_argument(
        "--no-live-metrics",
        action="store_true",
        help="Skip querying live DB/LLM quota metrics (offline registry-only mode).",
    )
    args = parser.parse_args(argv)

    if args.live_email:
        os.environ["ENABLE_LIVE_EMAIL_DISPATCH"] = "1"

    ref_date = _parse_iso_date(args.date) if args.date else datetime.now(IST).date()
    if args.date and ref_date is None:
        logger.error("Invalid --date argument: %s (expected YYYY-MM-DD)", args.date)
        return 2

    report = build_reminder_report(
        ref_date=ref_date,
        include_live_metrics=not args.no_live_metrics,
    )
    print(render_reminder_text(report))

    if args.send_email:
        try:
            result = dispatch_subscription_reminder_email(report, force=args.force)
            logger.info("Email dispatch result: %s", result)
            if result["status"] == "UNCONFIGURED":
                return 1
        except Exception as exc:
            logger.error("Subscription reminder email dispatch failed: %s", exc)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
