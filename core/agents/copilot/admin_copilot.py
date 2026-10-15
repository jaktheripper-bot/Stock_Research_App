"""
core/agents/copilot/admin_copilot.py
==============================================================================
Executive Admin Intelligence Copilot & Governance Engine.

Provides:
- Natural-language Q&A across live telemetry, session journeys, cash flows,
  support grievances, and system audit logs.
- Two-step confirmation architecture for administrative mutations:
  * Credit grants to users
  * Support grievance ticket status updates & resolution notes
  * Order refunds (Razorpay)
  * Synthetic test data purge
  * Comprehensive AMFI & Debt asset surveillance scans
  * Autonomous project health audits
- Google GenAI model cascade (`gemini-3.8-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`)
  with strict deterministic fallback for offline/test environments.
- Enforces institutional Moatnomics brand tone: clinical, objective, and surgical.
==============================================================================
"""

import os
import sys
import re
import json
import uuid
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from core.config import get_secret
from core.brand.moatnomics_house import get_system_prompt_context, MOATNOMICS_BRAND_HOUSE
from core.db import (
    init_db,
    get_all_billables,
    get_revenue_analytics_summary,
    process_refund,
    get_site_usage_summary,
    get_session_journeys,
    get_user_usage_analytics,
    get_support_tickets,
    get_open_tickets_count,
    update_ticket_status,
    add_ticket_response,
    get_ticket_by_id,
)
from core.notify import send_ticket_reply_email
from core.db.admin import (
    get_admin_user,
    list_admin_users,
    record_admin_audit,
    get_admin_audit_logs,
    admin_grant_user_credits,
)
from core.db.users import (
    get_user_by_email,
    get_user_by_id,
    get_user_transactions,
    get_user_usage_history,
)
from core.db.telemetry import purge_test_telemetry

logger = logging.getLogger("equity_research.core.agents.copilot.admin")


# ==============================================================================
# Supported Action Types & Permission Matrix
# ==============================================================================
class AdminActionType:
    GRANT_CREDITS = "GRANT_CREDITS"
    UPDATE_TICKET = "UPDATE_TICKET"
    REPLY_TICKET = "REPLY_TICKET"
    PROCESS_REFUND = "PROCESS_REFUND"
    PURGE_TEST_DATA = "PURGE_TEST_DATA"
    TRIGGER_ASSET_SCAN = "TRIGGER_ASSET_SCAN"
    TRIGGER_PROJECT_AUDIT = "TRIGGER_PROJECT_AUDIT"
    SYNC_AMFI = "SYNC_AMFI"


ALLOWED_ROLES_PER_ACTION = {
    AdminActionType.GRANT_CREDITS: {"owner", "admin"},
    AdminActionType.UPDATE_TICKET: {"owner", "admin"},
    AdminActionType.REPLY_TICKET: {"owner", "admin"},
    AdminActionType.PROCESS_REFUND: {"owner", "admin"},
    AdminActionType.PURGE_TEST_DATA: {"owner", "admin"},
    AdminActionType.TRIGGER_ASSET_SCAN: {"owner", "admin", "viewer"},
    AdminActionType.TRIGGER_PROJECT_AUDIT: {"owner", "admin", "viewer"},
    AdminActionType.SYNC_AMFI: {"owner", "admin"},
}


def _window_to_days(window: str) -> Optional[int]:
    w = (window or "30d").strip().lower()
    if w in ("24h", "1d"):
        return 1
    elif w == "7d":
        return 7
    elif w == "30d":
        return 30
    elif w == "90d":
        return 90
    return 30


# ==============================================================================
# Analytical Data Ingestion Tools (Live Dashboard State)
# ==============================================================================
def tool_get_admin_dashboard_kpis(window: str = "30d", exclude_tests: bool = True) -> Dict[str, Any]:
    """Retrieves live executive KPI counts across telemetry and revenue."""
    days = _window_to_days(window)
    try:
        usage = get_site_usage_summary(days=days, exclude_tests=exclude_tests) or {}
    except Exception as e:
        logger.warning(f"Error fetching usage summary: {e}")
        usage = {}

    try:
        revenue = get_revenue_analytics_summary(days=days, exclude_tests=exclude_tests) or {}
    except Exception as e:
        logger.warning(f"Error fetching revenue summary: {e}")
        revenue = {}

    try:
        open_tickets = get_open_tickets_count(exclude_tests=exclude_tests)
    except Exception as e:
        logger.warning(f"Error fetching open tickets count: {e}")
        open_tickets = 0

    return {
        "window": window,
        "exclude_tests": exclude_tests,
        "unique_sessions": usage.get("unique_sessions", 0),
        "total_actions": usage.get("total_actions", 0),
        "cache_efficiency_pct": usage.get("cache_efficiency_pct", 0.0),
        "total_cost_saved_usd": usage.get("total_cost_saved_usd", 0.0),
        "pdf_downloads": usage.get("pdf_downloads", 0),
        "bounce_rate_pct": usage.get("bounce_rate_pct", 0.0),
        "gross_revenue_inr": revenue.get("gross_revenue_inr", 0.0),
        "refund_sum_inr": revenue.get("refund_sum_inr", 0.0),
        "net_revenue_inr": revenue.get("net_revenue_inr", 0.0),
        "successful_transactions": revenue.get("successful_transactions", 0),
        "open_tickets_count": open_tickets,
        "top_routes": (usage.get("top_routes") or [])[:5],
        "top_tickers": (usage.get("top_tickers") or [])[:5],
    }


def tool_get_billables_summary(window: str = "30d", limit: int = 10, exclude_tests: bool = True) -> Dict[str, Any]:
    """Retrieves detailed billing ledger records and cash flow breakdown."""
    days = _window_to_days(window)
    rev_summary = get_revenue_analytics_summary(days=days, exclude_tests=exclude_tests) or {}
    all_billables = get_all_billables(status="all", limit=limit) or []
    
    recent_transactions = []
    for b in all_billables[:limit]:
        gross = float(b.get("amount_inr", 0.0) or 0.0)
        refunded = float(b.get("refund_amount_inr", 0.0) or 0.0)
        recent_transactions.append({
            "invoice_number": b.get("invoice_number"),
            "customer_email": b.get("customer_email"),
            "customer_name": b.get("customer_name"),
            "pack_type": b.get("pack_type"),
            "gross_amount_inr": gross,
            "refunded_amount_inr": refunded,
            "net_amount_inr": max(0.0, gross - refunded),
            "status": b.get("status"),
            "gateway_order_id": b.get("gateway_order_id"),
            "date": b.get("date"),
        })

    return {
        "summary": rev_summary,
        "recent_transactions": recent_transactions
    }


def tool_get_support_tickets_summary(status: str = "open", limit: int = 10, exclude_tests: bool = True) -> List[Dict[str, Any]]:
    """Retrieves recent user grievances and complaint dockets."""
    tickets = get_support_tickets(status=status, limit=limit, exclude_tests=exclude_tests) or []
    clean_tickets = []
    for t in tickets[:limit]:
        clean_tickets.append({
            "ticket_id": t.get("ticket_id"),
            "user_email": t.get("user_email"),
            "user_name": t.get("user_name"),
            "category": t.get("category"),
            "subject": t.get("subject"),
            "message": t.get("message"),
            "status": t.get("status"),
            "admin_notes": t.get("admin_notes"),
            "created_at": t.get("created_at")
        })
    return clean_tickets


def tool_lookup_user_account(identifier: str) -> Optional[Dict[str, Any]]:
    """Looks up user account profile, credits balance, and usage history."""
    clean_id = (identifier or "").strip().lower()
    if not clean_id:
        return None

    user = get_user_by_email(clean_id)
    if not user:
        user = get_user_by_id(clean_id)

    if not user:
        return None

    uid = user.get("id")
    txs = get_user_transactions(uid, limit=5) if uid else []
    usage = get_user_usage_history(uid, limit=5) if uid else []

    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "full_name": user.get("full_name"),
        "credits_balance": user.get("credits_balance", 0.0),
        "subscription_tier": user.get("subscription_tier"),
        "created_at": user.get("created_at"),
        "last_login_at": user.get("last_login_at"),
        "recent_transactions": txs,
        "recent_usage": usage
    }


def tool_get_admin_audit_trail(limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieves recent immutable administrative audit records."""
    logs = get_admin_audit_logs(limit=limit) or []
    items = []
    for lg in logs[:limit]:
        items.append({
            "id": lg.get("id"),
            "admin_email": lg.get("admin_email"),
            "action": lg.get("action"),
            "target_type": lg.get("target_type"),
            "target_id": lg.get("target_id"),
            "details": lg.get("details_parsed") or lg.get("details"),
            "created_at": lg.get("created_at"),
            "ip_address": lg.get("ip_address")
        })
    return items


# ==============================================================================
# Two-Step Confirmation Action Proposal Generator
# ==============================================================================
def create_action_proposal(
    action_type: str,
    title: str,
    summary: str,
    payload: Dict[str, Any],
    impact_level: str = "MEDIUM",
    impact_warning: Optional[str] = None
) -> Dict[str, Any]:
    """
    Constructs an interactive action proposal payload requiring explicit admin confirmation.
    Enforces that NO destructive or financial state mutation executes automatically.
    """
    prop_id = f"prop_{uuid.uuid4().hex[:10]}"
    return {
        "proposal_id": prop_id,
        "action_type": action_type,
        "title": title,
        "summary": summary,
        "impact_level": impact_level.upper(),
        "impact_warning": impact_warning or "",
        "payload": payload,
        "requires_confirmation": True,
        "status": "AWAITING_CONFIRMATION",
        "created_at": datetime.now(timezone.utc).isoformat()
    }


# ==============================================================================
# Confirmed Action Execution Engine
# ==============================================================================
def execute_confirmed_admin_action(
    action_type: str,
    payload: Dict[str, Any],
    admin_user: Dict[str, Any],
    client_ip: str = "127.0.0.1",
    user_agent: str = ""
) -> Dict[str, Any]:
    """
    Executes an action ONLY after the administrator has reviewed the proposal
    and explicitly clicked 'Confirm & Execute'.
    Enforces RBAC permissions and writes an immutable audit record.
    """
    if not admin_user or not admin_user.get("email"):
        return {"success": False, "error": "Unauthorized: Admin session required."}

    admin_email = admin_user.get("email").strip().lower()
    admin_role = (admin_user.get("role") or "viewer").strip().lower()

    allowed_roles = ALLOWED_ROLES_PER_ACTION.get(action_type, {"owner"})
    if admin_role not in allowed_roles:
        err_msg = f"Forbidden: Action '{action_type}' requires role in {list(allowed_roles)}. Current role is '{admin_role}'."
        record_admin_audit(
            admin_email=admin_email,
            action="UNAUTHORIZED_ACTION_ATTEMPT",
            target_type="action_proposal",
            target_id=action_type,
            details={"error": err_msg, "payload": payload},
            ip_address=client_ip,
            user_agent=user_agent
        )
        return {"success": False, "error": err_msg}

    # 1. GRANT_CREDITS
    if action_type == AdminActionType.GRANT_CREDITS:
        target_user = str(payload.get("target_user") or payload.get("user_email") or payload.get("user_id") or "").strip()
        try:
            credits_val = float(payload.get("credits", 2.0))
            if credits_val <= 0 or credits_val > 1000.0:
                return {"success": False, "error": "Credits must be between 0.1 and 1000.0."}
        except (ValueError, TypeError):
            return {"success": False, "error": "Invalid credits amount."}

        reason_code = str(payload.get("reason") or "TASK_REMEDY").strip()
        admin_note = str(payload.get("admin_note") or "Executed via Admin Executive Copilot").strip()
        ticket_id = payload.get("ticket_id")
        task_ticker = payload.get("task_ticker")
        resolve_ticket = bool(payload.get("resolve_ticket", True if ticket_id else False))

        res = admin_grant_user_credits(
            admin_email=admin_email,
            target_user_identifier=target_user,
            credits_amount=credits_val,
            reason_code=reason_code,
            admin_note=admin_note,
            ticket_id=ticket_id,
            task_ticker=task_ticker,
            resolve_ticket=resolve_ticket,
            ip_address=client_ip,
            user_agent=user_agent
        )
        return res

    # 2. UPDATE_TICKET
    elif action_type == AdminActionType.UPDATE_TICKET:
        ticket_id = str(payload.get("ticket_id") or "").strip()
        new_status = str(payload.get("status") or "resolved").strip().lower()
        admin_notes = payload.get("admin_notes")

        if not ticket_id:
            return {"success": False, "error": "Ticket ID is required."}

        ok = update_ticket_status(ticket_id=ticket_id, new_status=new_status, admin_notes=admin_notes)
        if ok:
            record_admin_audit(
                admin_email=admin_email,
                action="UPDATE_TICKET_VIA_COPILOT",
                target_type="ticket",
                target_id=ticket_id,
                details={"new_status": new_status, "admin_notes": admin_notes},
                ip_address=client_ip,
                user_agent=user_agent
            )
            return {
                "success": True,
                "ticket_id": ticket_id,
                "status": new_status,
                "message": f"Support ticket {ticket_id} status successfully updated to '{new_status}'."
            }
        else:
            return {"success": False, "error": f"Failed to update support ticket {ticket_id}."}

    # 2B. REPLY_TICKET
    elif action_type == AdminActionType.REPLY_TICKET:
        ticket_id = str(payload.get("ticket_id") or "").strip()
        reply_message = str(payload.get("reply_message") or "").strip()
        new_status = str(payload.get("status") or "resolved").strip().lower()
        dispatch_email = bool(payload.get("dispatch_email", True))

        if not ticket_id or not reply_message:
            return {"success": False, "error": "Ticket ID and reply message are required."}

        ticket = get_ticket_by_id(ticket_id, include_responses=False)
        if not ticket:
            return {"success": False, "error": f"Ticket {ticket_id} not found."}

        email_dispatched = False
        if dispatch_email:
            email_dispatched = send_ticket_reply_email(ticket, reply_message)

        add_ticket_response(
            ticket_id=ticket_id,
            message=reply_message,
            sender_email=admin_email,
            sender_name="Moatnomics Service Desk",
            sender_type="admin",
            email_dispatched=email_dispatched
        )
        update_ticket_status(ticket_id=ticket_id, new_status=new_status)

        record_admin_audit(
            admin_email=admin_email,
            action="REPLY_TICKET_VIA_COPILOT",
            target_type="ticket",
            target_id=ticket_id,
            details={
                "recipient_email": ticket.get("user_email"),
                "new_status": new_status,
                "email_dispatched": email_dispatched,
                "reply_preview": reply_message[:100]
            },
            ip_address=client_ip,
            user_agent=user_agent
        )
        return {
            "success": True,
            "ticket_id": ticket_id,
            "message": f"Successfully replied to ticket {ticket_id}. Email dispatched: {'Yes' if email_dispatched else 'Mock/Logged'}."
        }

    # 3. PROCESS_REFUND
    elif action_type == AdminActionType.PROCESS_REFUND:
        order_id = str(payload.get("order_id") or "").strip()
        user_email = str(payload.get("user_email") or "").strip()
        reason = str(payload.get("reason") or "Executive Copilot Refund Request").strip()

        if not order_id or not user_email:
            return {"success": False, "error": "Both order_id and user_email are required for refunds."}

        res = process_refund(gateway_order_id=order_id, user_email=user_email, reason=reason)
        if res.get("success"):
            record_admin_audit(
                admin_email=admin_email,
                action="REFUND_VIA_COPILOT",
                target_type="order",
                target_id=order_id,
                details={"user_email": user_email, "amount": res.get("refund_amount", 0.0), "reason": reason},
                ip_address=client_ip,
                user_agent=user_agent
            )
            return {
                "success": True,
                "order_id": order_id,
                "refund_amount": res.get("refund_amount", 0.0),
                "message": f"Refund of ₹{res.get('refund_amount', 0.0)} processed successfully for order {order_id}."
            }
        else:
            record_admin_audit(
                admin_email=admin_email,
                action="REFUND_FAILED_VIA_COPILOT",
                target_type="order",
                target_id=order_id,
                details={"user_email": user_email, "error": res.get("error")},
                ip_address=client_ip,
                user_agent=user_agent
            )
            return {"success": False, "error": res.get("error", "Refund processing failed.")}

    # 4. PURGE_TEST_DATA
    elif action_type == AdminActionType.PURGE_TEST_DATA:
        counts = purge_test_telemetry()
        record_admin_audit(
            admin_email=admin_email,
            action="PURGE_TEST_DATA_VIA_COPILOT",
            target_type="system",
            target_id="all_test_artifacts",
            details=counts,
            ip_address=client_ip,
            user_agent=user_agent
        )
        return {
            "success": True,
            "counts": counts,
            "message": (
                f"Purge completed: removed {counts.get('events_purged', 0)} test telemetry events, "
                f"{counts.get('tickets_purged', 0)} test tickets, and "
                f"{counts.get('transactions_purged', 0)} test transactions."
            )
        }

    # 5. TRIGGER_ASSET_SCAN
    elif action_type == AdminActionType.TRIGGER_ASSET_SCAN:
        try:
            from core.analysis.asset_scanner import run_comprehensive_asset_scan
            res = run_comprehensive_asset_scan()
            record_admin_audit(
                admin_email=admin_email,
                action="TRIGGER_ASSET_SCAN_VIA_COPILOT",
                target_type="system",
                target_id="asset_scanner",
                details=res,
                ip_address=client_ip,
                user_agent=user_agent
            )
            return {
                "success": True,
                "summary": res,
                "message": f"Asset surveillance scan complete: {res.get('total_scanned', 0)} assets scanned ({res.get('new_assets', 0)} new, {res.get('changed_assets', 0)} updated)."
            }
        except Exception as e:
            logger.error(f"Asset scan error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # 6. TRIGGER_PROJECT_AUDIT
    elif action_type == AdminActionType.TRIGGER_PROJECT_AUDIT:
        try:
            from core.audit.project_auditor import audit_project_full
            mode = "quick" if payload.get("quick", True) else "full"
            audit_res = audit_project_full(quick=(mode == "quick"))
            audit_id = audit_res.get("audit_id", "AUD-COMPLETED")
            score = audit_res.get("overall_score", 0.0)
            record_admin_audit(
                admin_email=admin_email,
                action="TRIGGER_PROJECT_AUDIT_VIA_COPILOT",
                target_type="system",
                target_id=audit_id,
                details={"score": score, "mode": mode},
                ip_address=client_ip,
                user_agent=user_agent
            )
            return {
                "success": True,
                "audit_id": audit_id,
                "score": score,
                "message": f"Autonomous project health audit completed: ID {audit_id}, Score: {score:.1f}/100."
            }
        except Exception as e:
            logger.error(f"Project audit error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # 7. SYNC_AMFI
    elif action_type == AdminActionType.SYNC_AMFI:
        try:
            from core.ingestion.amfi import ingest_amfi_daily_feed
            limit = payload.get("limit")
            res = ingest_amfi_daily_feed(limit=limit, direct_growth_only=True)
            record_admin_audit(
                admin_email=admin_email,
                action="SYNC_AMFI_VIA_COPILOT",
                target_type="system",
                target_id="amfi_nav_feed",
                details=res,
                ip_address=client_ip,
                user_agent=user_agent
            )
            return {
                "success": True,
                "summary": res,
                "message": f"AMFI feed sync complete: {res.get('schemes_updated', 0)} schemes updated."
            }
        except Exception as e:
            logger.error(f"AMFI sync error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    else:
        return {"success": False, "error": f"Unknown action type '{action_type}'."}


# ==============================================================================
# Deterministic Intent Parser & Q&A Fallback
# ==============================================================================
def parse_deterministic_admin_query(
    user_message: str,
    admin_user: Dict[str, Any],
    kpis: Dict[str, Any]
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Parses administrative questions and commands when Gemini is offline,
    in test environments, or when deterministic intent matches high confidence.
    """
    msg = user_message.lower().strip()

    # 1. Action Intent: Purge Test Data
    if any(k in msg for k in ["purge", "clean"]) and any(k in msg for k in ["test", "synthetic", "dummy"]):
        proposal = create_action_proposal(
            action_type=AdminActionType.PURGE_TEST_DATA,
            title="Purge Synthetic Test Data",
            summary="Delete all synthetic telemetry events, automated test tickets (@example.com, @test.com), and test orders from reports.db.",
            payload={},
            impact_level="HIGH",
            impact_warning="This action irreversibly removes test records from the active database to ensure only real visitor data is reported."
        )
        reply = (
            "⚠️ **Action Proposal Prepared: Purge Synthetic Test Data**\n\n"
            "I have formulated a database cleanup proposal to scrub all automated test events, "
            "test support tickets, and dummy transactions.\n\n"
            "Please review the action details below and click **Confirm & Execute** to commit changes."
        )
        return reply, proposal

    # 2. Action Intent: Grant Credits
    if any(k in msg for k in ["grant", "give", "allocate", "credit"]) and any(k in msg for k in ["credit", "balance", "token"]):
        # Extract target email
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", user_message)
        target_email = email_match.group(0) if email_match else ""

        # Extract numeric credit amount
        num_matches = re.findall(r"\b(\d+(?:\.\d+)?)\b", user_message)
        credits_val = 2.0
        if num_matches:
            for n in num_matches:
                val = float(n)
                if val > 0 and val <= 500:
                    credits_val = val
                    break

        # Extract ticket reference if present
        tkt_match = re.search(r"(TKT-[A-Za-z0-9]+)", user_message, re.IGNORECASE)
        ticket_id = tkt_match.group(1).upper() if tkt_match else None

        if not target_email and ticket_id:
            # Look up ticket to find user email
            tickets = get_support_tickets(status="all", limit=50, exclude_tests=False)
            for t in tickets:
                if t.get("ticket_id") == ticket_id:
                    target_email = t.get("user_email", "")
                    break

        if not target_email:
            return (
                "⚠️ **Target User Required**\n\n"
                "To grant remedial research credits, please specify the recipient user's email address "
                "(e.g., `Grant 5 credits to user@example.com`).",
                None
            )

        proposal = create_action_proposal(
            action_type=AdminActionType.GRANT_CREDITS,
            title=f"Grant {credits_val} Credits to {target_email}",
            summary=f"Allocate {credits_val} research credits to account `{target_email}` (Reason: TASK_REMEDY).",
            payload={
                "target_user": target_email,
                "credits": credits_val,
                "reason": "TASK_REMEDY",
                "admin_note": f"Granted via Admin Executive Copilot by {admin_user.get('email', 'admin')}",
                "ticket_id": ticket_id,
                "resolve_ticket": bool(ticket_id)
            },
            impact_level="MEDIUM",
            impact_warning=f"This will increment the user's research credit balance by +{credits_val} and create a zero-revenue ledger entry."
        )
        reply = (
            f"📋 **Action Proposal Prepared: Grant {credits_val} Credits**\n\n"
            f"I have prepared an administrative proposal to allocate **{credits_val} research credits** "
            f"to user **{target_email}**."
            + (f" Linked ticket: `{ticket_id}` (will be marked resolved)." if ticket_id else "") + "\n\n"
            "Please review the summary below and click **Confirm & Execute** to finalize."
        )
        return reply, proposal

    # 3. Action Intent: Resolve / Update Ticket
    if any(k in msg for k in ["resolve", "close", "update", "mark"]) and any(k in msg for k in ["ticket", "tkt", "complaint", "grievance"]):
        tkt_match = re.search(r"(TKT-[A-Za-z0-9]+)", user_message, re.IGNORECASE)
        ticket_id = tkt_match.group(1).upper() if tkt_match else None

        if not ticket_id:
            return (
                "⚠️ **Ticket ID Required**\n\n"
                "Please specify the ticket reference ID you would like to update (e.g., `Resolve ticket TKT-1234ABCD`).",
                None
            )

        new_status = "resolved" if any(k in msg for k in ["resolve", "close", "done", "fixed"]) else "in_progress"
        proposal = create_action_proposal(
            action_type=AdminActionType.UPDATE_TICKET,
            title=f"Mark Ticket {ticket_id} as {new_status.title()}",
            summary=f"Update status of support grievance {ticket_id} to '{new_status}'.",
            payload={
                "ticket_id": ticket_id,
                "status": new_status,
                "admin_notes": f"Status updated via Admin Copilot by {admin_user.get('email', 'admin')}"
            },
            impact_level="LOW",
            impact_warning="This will update the ticket record and log an immutable entry in the administrative audit trail."
        )
        reply = (
            f"📋 **Action Proposal Prepared: Update Ticket {ticket_id}**\n\n"
            f"I have prepared a proposal to update support grievance **{ticket_id}** status to **{new_status.upper()}**.\n\n"
            "Click **Confirm & Execute** below to commit this update."
        )
        return reply, proposal

    # 4. Action Intent: Refund Order
    if any(k in msg for k in ["refund", "reimburse", "reverse payment"]):
        order_match = re.search(r"(order_[A-Za-z0-9]+)", user_message, re.IGNORECASE)
        order_id = order_match.group(1) if order_match else None
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", user_message)
        target_email = email_match.group(0) if email_match else ""

        if not order_id:
            return (
                "⚠️ **Order ID Required**\n\n"
                "To initiate a payment refund, please provide the Gateway Order ID (e.g., `Refund order_12345 for user@example.com`).",
                None
            )

        proposal = create_action_proposal(
            action_type=AdminActionType.PROCESS_REFUND,
            title=f"Process Refund for Order {order_id}",
            summary=f"Initiate Razorpay payment refund for order `{order_id}` (Customer: {target_email or 'Account Holder'}).",
            payload={
                "order_id": order_id,
                "user_email": target_email or "unknown@customer.com",
                "reason": "Executive Copilot Refund Request"
            },
            impact_level="HIGH",
            impact_warning="This initiates an online reversal on Razorpay and recalculates net cash receipts in reports.db."
        )
        reply = (
            f"⚠️ **Action Proposal Prepared: Process Payment Refund**\n\n"
            f"I have prepared an order refund proposal for **{order_id}**.\n\n"
            "Please verify the recipient details below and click **Confirm & Execute**."
        )
        return reply, proposal

    # 5. Action Intent: Asset Surveillance Scan
    if any(k in msg for k in ["scan", "surveillance", "refresh assets", "sync amfi", "scan funds"]):
        action = AdminActionType.SYNC_AMFI if "amfi" in msg else AdminActionType.TRIGGER_ASSET_SCAN
        title = "Sync AMFI Daily NAV Feed" if action == AdminActionType.SYNC_AMFI else "Trigger Comprehensive Asset Surveillance Scan"
        proposal = create_action_proposal(
            action_type=action,
            title=title,
            summary="Scan mutual fund portfolios, debt securities, and sovereign bond curves for portfolio shifts and fresh pricing.",
            payload={},
            impact_level="LOW",
            impact_warning="Surveillance scan inspects live AMFI and NSE debt feeds and updates the local security catalog."
        )
        reply = (
            f"📡 **Action Proposal Prepared: {title}**\n\n"
            "Ready to trigger background asset surveillance.\n"
            "Click **Confirm & Execute** to start the scan."
        )
        return reply, proposal

    # 6. Action Intent: Run Project Health Audit
    if any(k in msg for k in ["project audit", "run audit", "system audit", "health check"]):
        proposal = create_action_proposal(
            action_type=AdminActionType.TRIGGER_PROJECT_AUDIT,
            title="Execute Autonomous Project Health Audit",
            summary="Run the 5-pillar autonomous system verification suite (Strategy, Code Hygiene, CSS Design Tokens, Link Health, AST anti-patterns).",
            payload={"quick": True},
            impact_level="LOW",
            impact_warning="Executes deterministic audit probes and generates an immutable Markdown audit dossier."
        )
        reply = (
            "🛡️ **Action Proposal Prepared: Project Health Audit**\n\n"
            "Ready to initiate the 5-pillar autonomous architecture and brand audit.\n"
            "Click **Confirm & Execute** to run."
        )
        return reply, proposal

    # 7. Analytical Q&A: Revenue, Billables & Cash Flow
    if any(k in msg for k in ["revenue", "billable", "sales", "cash", "inflow", "gross", "net", "money", "gst", "tax"]):
        gross = kpis.get("gross_revenue_inr", 0.0)
        refunds = kpis.get("refund_sum_inr", 0.0)
        net = kpis.get("net_revenue_inr", 0.0)
        orders = kpis.get("successful_transactions", 0)
        window = kpis.get("window", "30d")

        return (
            f"💰 **Cash Flow & Revenue Diagnostics ({window.upper()} Window):**\n\n"
            f"- **Gross Receipts:** ₹{gross:,.2f}\n"
            f"- **Processed Refunds:** ₹{refunds:,.2f}\n"
            f"- **Net Cash Inflow:** ₹{net:,.2f} *(Gross less refunds)*\n"
            f"- **Successful Orders:** {orders}\n"
            f"- **Entity Registration / Tax Accounting:** Independent software platform; zero synthetic GST splits.\n\n"
            "Would you like me to pull up recent transaction invoices or inspect customer accounts?",
            None
        )

    # 8. Analytical Q&A: Site Usage, Sessions & Traffic
    if any(k in msg for k in ["session", "traffic", "visitor", "user", "bounce", "footprint", "action", "usage"]):
        sessions = kpis.get("unique_sessions", 0)
        actions = kpis.get("total_actions", 0)
        bounce = kpis.get("bounce_rate_pct", 0.0)
        window = kpis.get("window", "30d")
        routes = ", ".join([f"`{r.get('route', 'unknown')}` ({r.get('count', 0)})" for r in kpis.get("top_routes", [])]) or "No route history recorded."
        tickers = ", ".join([f"`{t.get('ticker', 'N/A')}` ({t.get('count', 0)})" for t in kpis.get("top_tickers", [])]) or "No ticker searches recorded."

        return (
            f"🌐 **Executive Telemetry & Site Usage ({window.upper()} Window):**\n\n"
            f"- **Unique Sessions:** {sessions:,} distinct visitor footprints\n"
            f"- **Total Actions:** {actions:,} queries, dockets & exports\n"
            f"- **Bounce Rate:** {bounce:.1f}%\n"
            f"- **Top Visited Routes:** {routes}\n"
            f"- **Top Researched Tickers:** {tickers}\n\n"
            "Would you like to examine device breakdowns or funnel conversion?",
            None
        )

    # 9. Analytical Q&A: Cache Efficiency & Cost Savings
    if any(k in msg for k in ["cache", "saving", "cost", "api cost", "efficiency"]):
        cache_pct = kpis.get("cache_efficiency_pct", 0.0)
        cost_saved = kpis.get("total_cost_saved_usd", 0.0)
        window = kpis.get("window", "30d")

        return (
            f"⚡ **Cache Mitigation & Latency Diagnostics ({window.upper()} Window):**\n\n"
            f"- **Cache Efficiency:** {cache_pct:.1f}% instant zero-cost serves\n"
            f"- **Estimated API Cost Saved:** ${cost_saved:,.2f} USD\n"
            f"- **Heuristic Baseline:** Grounded at ~$0.015 generation cost mitigated per cached analytical query.\n\n"
            "High cache efficiency guarantees sub-10ms response times for repeat security searches.",
            None
        )

    # 10. Analytical Q&A: Support Grievances & Complaints
    if any(k in msg for k in ["ticket", "support", "grievance", "complaint", "issue"]):
        open_count = kpis.get("open_tickets_count", 0)
        recent_tickets = tool_get_support_tickets_summary(status="open", limit=3, exclude_tests=True)

        if not recent_tickets:
            tkt_lines = "No open support grievances currently pending review."
        else:
            tkt_lines = "\n".join([
                f"- **{t['ticket_id']}** ({t['user_email']}): *\"{t['subject']}\"* — `{t['category']}`"
                for t in recent_tickets
            ])

        return (
            f"📬 **Support Grievances & Complaints Docket:**\n\n"
            f"- **Unresolved Open Tickets:** {open_count}\n"
            f"{tkt_lines}\n\n"
            "You can ask me to resolve a ticket or grant remedial research credits to any affected user.",
            None
        )

    # 11. Analytical Q&A: Team, Admin Access & 2FA
    if any(k in msg for k in ["team", "admin", "whitelist", "2fa", "access", "role", "who"]):
        admins = list_admin_users()
        lines = []
        for a in admins:
            totp = "✅ 2FA Active" if a.get("totp_enabled") else "⚠️ 2FA Pending"
            lines.append(f"- **{a.get('email')}** — Role: `{a.get('role', 'admin').upper()}` ({totp})")
        team_str = "\n".join(lines) if lines else "No team records found."

        return (
            f"👥 **Administrator Access Control & Security Whitelist:**\n\n"
            f"{team_str}\n\n"
            "Access is enforced via RFC 6238 TOTP authentication and session-bound tokens.",
            None
        )

    # 12. Analytical Q&A: Audit Trail
    if any(k in msg for k in ["audit log", "audit trail", "logs", "who did what", "history"]):
        logs = tool_get_admin_audit_trail(limit=5)
        if not logs:
            log_str = "No recent administrative actions recorded in the audit trail."
        else:
            log_str = "\n".join([
                f"- `{l.get('created_at', '')[:19]}`: **{l.get('admin_email')}** executed `{l.get('action')}` on `{l.get('target_type')}:{l.get('target_id')}`"
                for l in logs
            ])

        return (
            f"📜 **Recent Administrative Audit Trail:**\n\n"
            f"{log_str}\n\n"
            "All actions executed via this Copilot or the Admin UI are logged immutably.",
            None
        )

    # Default Helpful Response
    return (
        "🤖 **Moatnomics Executive Admin Copilot**\n\n"
        "I provide institutional diagnostics across live dashboard telemetry and can coordinate administrative mutations:\n\n"
        "**What you can ask me:**\n"
        "- 📊 *\"What are our unique sessions and top routes this month?\"*\n"
        "- 💰 *\"Summarize our net cash inflow and recent billables.\"*\n"
        "- 📬 *\"Show me open support tickets and complaints.\"*\n"
        "- ⚡ *\"What is our cache hit rate and estimated API savings?\"*\n"
        "- 👥 *\"Who has admin access and is 2FA enabled?\"*\n\n"
        "**What I can do for you (Requires 1-Click Confirmation):**\n"
        "- 🎁 *\"Grant 5 credits to rahul@example.com for downtime remedy\"*\n"
        "- ✅ *\"Mark ticket TKT-7A4B2C as resolved\"*\n"
        "- 🧹 *\"Purge test telemetry and dummy tickets from the dashboard\"*\n"
        "- 💳 *\"Process refund for order_12345\"*\n"
        "- 📡 *\"Trigger asset surveillance scan\"*",
        None
    )


# ==============================================================================
# Multi-Turn Turn Processor (Google GenAI Cascade + Fallback)
# ==============================================================================
async def process_admin_copilot_turn(
    admin_user: Dict[str, Any],
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Coordinates an administrative copilot conversation turn.
    1. Collects live telemetry and financial metrics.
    2. Invokes Google GenAI with cascade (`gemini-3.8-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`).
    3. Detects if an action proposal is returned.
    4. Seamlessly falls back to deterministic execution if LLM unavailable or offline.
    """
    clean_msg = (message or "").strip()
    if not clean_msg:
        return {
            "reply": "Please provide an administrative query or operational request.",
            "action_proposal": None,
            "status": "EMPTY_INPUT"
        }

    ctx = context or {}
    window = ctx.get("window", "30d")
    exclude_tests = not bool(ctx.get("include_tests", 0))

    # Fetch fresh live dashboard metrics
    kpis = tool_get_admin_dashboard_kpis(window=window, exclude_tests=exclude_tests)

    # Check for deterministic execution triggers first if testing
    is_testing = os.environ.get("TESTING") == "1" or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    api_key = get_secret("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if is_testing or not api_key:
        reply, proposal = parse_deterministic_admin_query(clean_msg, admin_user, kpis)
        return {
            "reply": reply,
            "action_proposal": proposal,
            "status": "COMPLETED_DETERMINISTIC"
        }

    # Attempt Generative AI Cascade
    try:
        from google.genai import Client, types as genai_types
        client = Client(api_key=api_key)

        history_items = history or []
        history_str = "\n".join([f"{h.get('role', 'user').upper()}: {h.get('content', '')}" for h in history_items[-5:]])

        system_prompt = f"""
{get_system_prompt_context()}

ROLE: You are the Executive Administrator Copilot for {MOATNOMICS_BRAND_HOUSE['brand_name']}.
You serve the platform owner and verified administrators.
Your tone is clinical, objective, surgical, and empirical. Never use conversational filler, hype, or colloquialisms.

AUTHENTICATED ADMIN CONTEXT:
- Email: {admin_user.get('email')}
- Role: {admin_user.get('role', 'admin').upper()}

LIVE DASHBOARD METRICS ({kpis.get('window', '30d').upper()} Window, Clean Real Data={kpis.get('exclude_tests')}):
- Unique Sessions: {kpis.get('unique_sessions')}
- Total User Actions: {kpis.get('total_actions')}
- Cache Efficiency: {kpis.get('cache_efficiency_pct')}%
- Estimated API Cost Saved: ${kpis.get('total_cost_saved_usd'):.2f} USD
- PDF Research Dossiers Exported: {kpis.get('pdf_downloads')}
- Gross Cash Receipts: ₹{kpis.get('gross_revenue_inr', 0.0):.2f}
- Processed Refunds: ₹{kpis.get('refund_sum_inr', 0.0):.2f}
- Net Cash Inflow: ₹{kpis.get('net_revenue_inr', 0.0):.2f}
- Open Support Grievances: {kpis.get('open_tickets_count')}
- Top Routes: {json.dumps(kpis.get('top_routes'))}
- Top Researched Tickers: {json.dumps(kpis.get('top_tickers'))}

OPERATIONAL DIRECTIVES:
1. When answering questions about metrics, cite exact, grounded numbers from the LIVE DASHBOARD METRICS above.
2. We are an independent software tool and NOT registered anywhere. There are NO GST splits or fake SAC codes. Net cash inflow = Gross less refunds.
3. If the administrator asks you to make ANY change (e.g. grant credits, update a ticket, issue a refund, purge test data, scan assets):
   - You MUST formulate an action proposal.
   - At the end of your response, output a markdown block with language tag `proposal` containing valid JSON with this exact schema:
   ```proposal
   {{
     "action_type": "GRANT_CREDITS" | "UPDATE_TICKET" | "PROCESS_REFUND" | "PURGE_TEST_DATA" | "TRIGGER_ASSET_SCAN" | "TRIGGER_PROJECT_AUDIT",
     "title": "Short title describing the action",
     "summary": "Clear clinical summary of the operation",
     "impact_level": "LOW" | "MEDIUM" | "HIGH",
     "impact_warning": "Warning about database/financial impact",
     "payload": {{ ... relevant parameters like target_user, credits, ticket_id, status, order_id ... }}
   }}
   ```
4. Do NOT execute destructive or financial mutations directly without this proposal block. The web UI will render a two-step confirmation card for the admin to click.

RECENT CONVERSATION HISTORY:
{history_str}
"""
        agent_reply = None
        for model_name in ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]:
            try:
                resp = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model_name,
                        contents=f"{system_prompt}\n\nADMIN: {clean_msg}\nEXECUTIVE COPILOT:",
                        config=genai_types.GenerateContentConfig(
                            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True)
                        )
                    ),
                    timeout=10.0
                )
                if resp and resp.text:
                    agent_reply = resp.text
                    break
            except Exception as model_err:
                logger.debug(f"Admin Copilot model {model_name} attempt note: {model_err}")
                continue

        if not agent_reply:
            raise RuntimeError("Gemini models failed to respond.")

        # Extract proposal JSON block if present
        action_proposal = None
        proposal_pattern = re.search(r"```(?:proposal|json)?\s*(\{\s*\"action_type\"[\s\S]*?\})\s*```", agent_reply)
        if proposal_pattern:
            try:
                raw_json = proposal_pattern.group(1)
                parsed = json.loads(raw_json)
                action_type = parsed.get("action_type")
                if action_type:
                    action_proposal = create_action_proposal(
                        action_type=action_type,
                        title=parsed.get("title", f"Execute {action_type}"),
                        summary=parsed.get("summary", ""),
                        payload=parsed.get("payload", {}),
                        impact_level=parsed.get("impact_level", "MEDIUM"),
                        impact_warning=parsed.get("impact_warning", "")
                    )
                    # Strip raw json block from user display text
                    clean_reply = agent_reply[:proposal_pattern.start()].strip() + "\n\n" + agent_reply[proposal_pattern.end():].strip()
                    agent_reply = clean_reply.strip()
            except Exception as parse_err:
                logger.warning(f"Error parsing Gemini proposal block: {parse_err}")

        # If LLM didn't produce proposal block but message is clearly an action, use deterministic proposal
        if not action_proposal:
            _, fallback_prop = parse_deterministic_admin_query(clean_msg, admin_user, kpis)
            if fallback_prop:
                action_proposal = fallback_prop

        return {
            "reply": agent_reply,
            "action_proposal": action_proposal,
            "status": "COMPLETED_GENAI"
        }

    except Exception as e:
        logger.warning(f"Admin Copilot LLM generation error: {e}. Executing deterministic fallback.")
        reply, proposal = parse_deterministic_admin_query(clean_msg, admin_user, kpis)
        return {
            "reply": reply,
            "action_proposal": proposal,
            "status": "COMPLETED_FALLBACK"
        }
