"""
Moatnomics - FastAPI Web Application.

High-performance Server-Side Rendered (SSR) equity research portal.
Provides:
- Razorpay-compliant public landing page & mandatory legal policies
- Zero-latency crawlable dossier URLs for Google SEO & GEO answer engines
- Interactive UPI and card checkout endpoints
- Instant PDF report export downloads
- Modular domain routers for Auth/Billing, Dossier Intelligence, Markets, and Admin.
"""

import os
import sys
import re
import json
import asyncio
import logging
import markdown
import csv
import io
import hmac
import hashlib
import statistics
import collections
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, HTTPException, Form, Header, BackgroundTasks, Query, Body
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
try:
    from brotli_asgi import BrotliMiddleware
except ImportError:
    BrotliMiddleware = None
from fastapi.middleware.cors import CORSMiddleware
from web.middleware.security_headers import SecurityHeadersMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

logger = logging.getLogger("equity_research.web")

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception as dot_err:
    logger.debug("dotenv load notice: %s", dot_err)

try:
    import toml
    _sec_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".streamlit", "secrets.toml")
    if os.path.exists(_sec_path):
        _sec = toml.load(_sec_path)
        for _k, _v in _sec.items():
            if isinstance(_v, str) and _k not in os.environ:
                os.environ[_k] = _v
except Exception as toml_err:
    logger.debug("secrets.toml load notice: %s", toml_err)

from pydantic import BaseModel

from core.db import (
    init_db,
    get_archived_reports_sync,
    get_all_equities_directory_sync,
    SECTOR_TAXONOMY,
    get_report_by_ticker_sync,
    get_report_revisions,
    get_or_create_user,
    get_user_by_id,
    get_user_by_email,
    get_user_credits_balance,
    deduct_user_credits,
    add_user_credits,
    is_ticker_unlocked_for_user,
    unlock_ticker_for_user,
    get_user_unlocked_tickers,
    get_active_discovery_reel,
    get_available_discovery_editions,
    save_discovery_reel,
    create_support_ticket,
    get_support_tickets,
    get_open_tickets_count,
    update_ticket_status,
    get_all_billables,
    get_revenue_analytics_summary,
    process_refund,
    get_site_usage_summary,
    get_session_journeys,
    get_user_usage_analytics,
    get_system_setting,
    set_system_setting,
    MANDATORY_SEBI_DISCLAIMER,
    IST,
)
from core.notify import dispatch_support_ticket_alert
from core.analysis import get_stock_fundamentals, get_historical_prices
from core.analysis.dossier_report_synthesis import generate_stock_report
from core.analysis.peer_comparison import compare_two_companies
from core.analysis.parser import (
    extract_health_matrix,
    compare_revisions,
    remove_health_matrix_text,
    wrap_html_with_collapsible_pillars,
    wrap_fund_dossier_with_collapsible_dimensions,
)
from core.analysis.metrics import calculate_52w_percentile, calculate_pe_percentile, get_valuation_quartile
from core.billing import (
    PRICING_PACKS,
    B2B_PACKS,
    get_plan_by_id,
    SUPPORTED_CURRENCIES,
    resolve_currency_for_request,
)
from normalizer import clean_ticker, extract_citations_from_report


from bse_master import (
    get_ticker_suggestions,
    resolve_canonical_symbol,
    resolve_bse_scrip_code,
    get_bse_scrips_cache,
)
from core.formatters import format_inr
from web.legal_content import POLICIES
from core.db.debt import (
    get_active_debt_securities,
    get_debt_security_by_isin,
    get_debt_securities_by_ticker,
    get_recent_rating_actions,
    get_rating_history,
    seed_default_debt_securities,
)
from core.analysis.debt_engine import evaluate_5_pillar_credit_posture
from core.db.mutual_funds import (
    get_active_mutual_funds,
    get_mutual_fund_scheme,
    get_scheme_holdings,
    get_schemes_by_holding,
    seed_default_mutual_funds,
    get_featured_daily_fund_dossier,
    get_fund_forensic_dossier,
)
from core.analysis.mutual_funds_engine import (
    evaluate_mutual_fund_comprehensive,
    evaluate_dual_sleeve_lookthrough,
    calculate_portfolio_overlap,
    calculate_active_share,
    calculate_fee_drag,
)
from core.analysis.fund_overlap_auditor import (
    audit_single_fund_daily,
    compute_fund_forensic_lookthrough,
    calculate_deep_dive_credit_cost,
)
from core.config import get_secret
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.msme.scheduler import register_jobs

# ==============================================================================
# Shared Web Utilities & Re-Exports (Preserving 100% Backwards Compatibility)
# ==============================================================================
from web.common import (
    templates,
    canonical_for,
    json_response_with_cache,
    resolve_app_base_url,
    _validate_request_origin,
    _get_client_ip,
    _get_user_signing_key,
    _generate_user_session_token,
    _validate_user_session_token,
    _get_current_web_user,
    _get_admin_signing_key,
    _generate_admin_token,
    _validate_admin_token,
    _is_admin_authenticated,
    _generate_pending_2fa_token,
    _validate_pending_2fa_token,
    _build_local_qr_data_uri,
    _is_user_subscribed,
    _can_access_today_discovery,
    _is_ticker_unlocked_for_request,
    _deep_dive_unlocked_for_request,
    _asset_unlock_key,
    _asset_unlocked_for_request,
    _unlock_asset_deep_dive,
    _pdf_account_ref,
    PDF_LOCKED_NOTICE,
    ADMIN_COOKIE_NAME,
    ADMIN_2FA_PENDING_COOKIE,
    USER_SESSION_COOKIE,
    ALLOWED_ORIGIN_HOSTS,
)


# ==============================================================================
# Background Autonomous Schedulers
# ==============================================================================
async def run_daily_discovery_scheduler():
    """
    Automated background BSE monitoring and screening scheduler:
    Coordinates scheduled tasks across multi-worker deployments using distributed job leases:
    - 08:30 AM IST: Daily 15-stock ingestion & mutual fund look-through saturation
    - 08:45 AM IST: Discovery Reel morning screening (500+ scrips)
    - 09:00 AM IST: Daily unlisted MSME cohort ingestion & Research Bouquet dispatch
    """
    logger.info("🌅 [Discovery Scheduler] Background BSE monitoring crawler & morning scheduler initiated.")
    last_stock_run_date = None
    last_discovery_run_date = None
    last_msme_run_date = None
    last_bouquet_run_date = None

    try:
        now = datetime.now(IST)
        today_str = now.strftime("%Y-%m-%d")
        from core.analysis.daily_stock_ingestion import ingest_daily_stock_cohort
        from core.msme.daily_ingest import ingest_daily_msme_cohort
        from core.agents.watchers.discovery_watcher import execute_discovery_screening
        from core.notify import dispatch_research_bouquet
        from core.db.distributed_lock import job_lease

        loop = asyncio.get_running_loop()
        is_past_830 = (now.hour > 8) or (now.hour == 8 and now.minute >= 30)
        is_past_845 = (now.hour > 8) or (now.hour == 8 and now.minute >= 45)
        is_past_900 = now.hour >= 9

        if is_past_830:
            with job_lease(f"mf_stock_ingest_{today_str}", ttl_seconds=7200, release_on_exit=False) as acquired:
                if acquired:
                    logger.info(f"🌅 [Discovery Scheduler] Past 08:30 AM IST on boot for {today_str}. Acquired lease. Triggering daily 15-stock ingestion...")
                    await loop.run_in_executor(None, ingest_daily_stock_cohort, today_str, 15, False)
                    logger.info(f"🌅 [Discovery Scheduler] 15-stock ingestion & mutual fund look-through re-audit completed for {today_str}.")
                else:
                    logger.info(f"🌅 [Discovery Scheduler] Lease for mf_stock_ingest_{today_str} held by another worker. Skipping boot ingestion.")
            last_stock_run_date = today_str

            if is_past_845:
                with job_lease(f"discovery_reel_{today_str}", ttl_seconds=7200, release_on_exit=False) as acquired:
                    if acquired:
                        logger.info(f"🌅 [Discovery Watcher] Past 08:45 AM IST on boot for {today_str}. Acquired lease. Running discovery screening...")
                        await execute_discovery_screening()
                        logger.info(f"🌅 [Discovery Watcher] Boot discovery screening completed for {today_str}.")
                    else:
                        logger.info(f"🌅 [Discovery Watcher] Lease for discovery_reel_{today_str} held by another worker. Skipping boot screening.")
                last_discovery_run_date = today_str

            if is_past_900:
                with job_lease(f"msme_daily_ingest_{today_str}", ttl_seconds=7200, release_on_exit=False) as acquired:
                    if acquired:
                        logger.info(f"🏭 [Discovery Scheduler] Past 09:00 AM IST on boot for {today_str}. Acquired lease. Triggering daily MSME cohort ingestion...")
                        await loop.run_in_executor(None, ingest_daily_msme_cohort, today_str, 15)
                        logger.info(f"🏭 [Discovery Scheduler] MSME cohort ingestion completed for {today_str}.")
                    else:
                        logger.info(f"🏭 [Discovery Scheduler] Lease for msme_daily_ingest_{today_str} held by another worker. Skipping boot MSME ingest.")
                last_msme_run_date = today_str

                with job_lease(f"morning_bouquet_{today_str}", ttl_seconds=7200, release_on_exit=False) as acquired:
                    if acquired:
                        logger.info(f"📬 [Research Bouquet] Past 09:00 AM IST on boot for {today_str}. Acquired lease. Dispatching morning bouquet...")
                        await loop.run_in_executor(None, dispatch_research_bouquet, today_str, None, False)
                        logger.info(f"📬 [Research Bouquet] Morning bouquet dispatch completed for {today_str}.")
                    else:
                        logger.info(f"📬 [Research Bouquet] Lease for morning_bouquet_{today_str} held by another worker. Skipping boot bouquet dispatch.")
                last_bouquet_run_date = today_str
        else:
            from core.db.discovery import get_active_discovery_reel
            yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            yesterday_existing = [
                x for x in get_active_discovery_reel(
                    edition_date=yesterday_str,
                    exclude_tests=True,
                    allow_fallback=False,
                )
            ]
            if not yesterday_existing:
                with job_lease(f"mf_stock_ingest_bootstrap_{yesterday_str}", ttl_seconds=7200, release_on_exit=False) as acquired:
                    if acquired:
                        logger.info(f"🌅 [Discovery Scheduler] Prior-day edition ({yesterday_str}) missing on pre-08:30 boot. Running catch-up ingestion...")
                        await loop.run_in_executor(None, ingest_daily_stock_cohort, yesterday_str, 15, False)
                        await execute_discovery_screening()
                        await loop.run_in_executor(None, ingest_daily_msme_cohort, yesterday_str, 15)
    except Exception as boot_err:
        logger.warning(f"🌅 [Discovery Scheduler] Catch-up check notice: {boot_err}")

    while True:
        try:
            await asyncio.sleep(60)
            now = datetime.now(IST)
            today_str = now.strftime("%Y-%m-%d")
            is_past_830 = (now.hour > 8) or (now.hour == 8 and now.minute >= 30)
            is_past_845 = (now.hour > 8) or (now.hour == 8 and now.minute >= 45)
            is_past_900 = now.hour >= 9
            loop = asyncio.get_running_loop()
            from core.db.distributed_lock import job_lease

            # 1. 08:30 AM MF Priority Stock Ingest
            if is_past_830 and last_stock_run_date != today_str:
                from core.analysis.daily_stock_ingestion import ingest_daily_stock_cohort
                with job_lease(f"mf_stock_ingest_{today_str}", ttl_seconds=7200, release_on_exit=False) as acquired:
                    if acquired:
                        logger.info(f"🌅 [Discovery Scheduler] 08:30 AM IST trigger reached for {today_str}. Acquired lease. Running daily 15-stock ingestion...")
                        await loop.run_in_executor(None, ingest_daily_stock_cohort, today_str, 15, False)
                        logger.info(f"🌅 [Discovery Scheduler] Daily 15-stock ingestion & mutual fund look-through re-audit completed for {today_str}.")
                    else:
                        logger.info(f"🌅 [Discovery Scheduler] Lease for mf_stock_ingest_{today_str} held by another worker. Skipping.")
                last_stock_run_date = today_str

            # 2. 08:45 AM Discovery Reel Screening
            if is_past_845 and last_discovery_run_date != today_str:
                from core.agents.watchers.discovery_watcher import execute_discovery_screening
                with job_lease(f"discovery_reel_{today_str}", ttl_seconds=7200, release_on_exit=False) as acquired:
                    if acquired:
                        logger.info(f"🌅 [Discovery Watcher] 08:45 AM IST trigger reached for {today_str}. Acquired lease. Running discovery screening...")
                        await execute_discovery_screening()
                        logger.info(f"🌅 [Discovery Watcher] Daily 08:45 AM discovery reel screening completed for {today_str}.")
                    else:
                        logger.info(f"🌅 [Discovery Watcher] Lease for discovery_reel_{today_str} held by another worker. Skipping.")
                last_discovery_run_date = today_str

            # 3. 09:00 AM MSME Ingestion
            if is_past_900 and last_msme_run_date != today_str:
                from core.msme.daily_ingest import ingest_daily_msme_cohort
                with job_lease(f"msme_daily_ingest_{today_str}", ttl_seconds=7200, release_on_exit=False) as acquired:
                    if acquired:
                        logger.info(f"🏭 [MSME Ingest] 09:00 AM IST trigger reached for {today_str}. Acquired lease. Running daily MSME cohort ingestion...")
                        await loop.run_in_executor(None, ingest_daily_msme_cohort, today_str, 15)
                        logger.info(f"🏭 [MSME Ingest] 09:00 AM IST unlisted MSME cohort ingestion completed for {today_str}.")
                    else:
                        logger.info(f"🏭 [MSME Ingest] Lease for msme_daily_ingest_{today_str} held by another worker. Skipping.")
                last_msme_run_date = today_str

            # 4. 09:00 AM Research Bouquet Morning Dispatch
            if is_past_900 and last_bouquet_run_date != today_str:
                from core.notify import dispatch_research_bouquet
                with job_lease(f"morning_bouquet_{today_str}", ttl_seconds=7200, release_on_exit=False) as acquired:
                    if acquired:
                        logger.info(f"📬 [Research Bouquet] 09:00 AM IST trigger reached for {today_str}. Acquired lease. Dispatching morning bouquet...")
                        await loop.run_in_executor(None, dispatch_research_bouquet, today_str, None, False)
                        logger.info(f"📬 [Research Bouquet] 09:00 AM IST morning bouquet dispatch completed for {today_str}.")
                    else:
                        logger.info(f"📬 [Research Bouquet] Lease for morning_bouquet_{today_str} held by another worker. Skipping.")
                last_bouquet_run_date = today_str
        except asyncio.CancelledError:
            logger.info("🌅 [Discovery Scheduler] Background scheduler cancelled.")
            break
        except Exception as e:
            logger.error(f"🌅 [Discovery Scheduler] Error in daily discovery scheduler: {e}")
            await asyncio.sleep(60)


async def run_daily_amfi_scheduler():
    """Automated background Multi-Asset Monitoring & AMFI Synchronization Scheduler.
    Runs catch-up initialization at boot, and executes full multi-asset pipeline nightly at 23:15 IST:
    1. AMFI Daily NAV Feed & Scheme Master Ingestion (Mutual Funds)
    2. National ETF Matrix Ingestion (all 436 AMFI ETFs across 9 categories)
    3. Always-On Multi-Asset Monitoring Scan (MF drift + Corporate Debt maturities/CRA watches)
    4. Sovereign Risk-Free Benchmarks & SDL Yield Curve Synchronization
    """
    logger.info("📊 [AMFI & Multi-Asset Scheduler] Background synchronizer initiated.")
    loop = asyncio.get_running_loop()

    # Pre-flight / Boot catch-up checks
    try:
        from core.db.sovereign import get_etf_matrix, refresh_daily_sovereign_benchmarks
        from core.ingestion.etf_ingest import ingest_all_amfi_etfs
        from core.analysis.asset_scanner import get_asset_scan_runs, run_comprehensive_asset_scan
        from core.db.agent_sessions import record_autonomous_event

        now = datetime.now(IST)
        today_str = now.strftime("%Y-%m-%d")

        # 1. ETF Universe Boot Check: Ensure all active AMFI ETFs are in database
        etf_count = len(get_etf_matrix(category=None))
        if etf_count < 400:
            logger.info(f"📊 [ETF Ingestion Boot] ETF matrix has {etf_count} records (<400). Running dynamic AMFI ETF sync...")
            etf_res = await loop.run_in_executor(None, ingest_all_amfi_etfs, True)
            logger.info(f"📊 [ETF Ingestion Boot] Synced {etf_res.get('persisted_to_db', 0)} ETFs into matrix.")

        # 2. Sovereign Benchmarks Boot Check: Ensure sovereign benchmarks are primed
        await loop.run_in_executor(None, refresh_daily_sovereign_benchmarks, today_str)

        # 3. Multi-Asset Monitoring & AMFI Catch-Up Check:
        # Runs if past 23:15 IST without today's scan OR if the last scan is older than yesterday
        from core.ingestion.amfi import ingest_amfi_daily_feed
        yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        recent_scans = get_asset_scan_runs(limit=1)
        last_scan_date = str(recent_scans[0].get("started_at", ""))[:10] if recent_scans else ""
        is_past_2315 = (now.hour > 23) or (now.hour == 23 and now.minute >= 15)
        if (is_past_2315 and last_scan_date != today_str) or (not last_scan_date or last_scan_date < yesterday_str):
            logger.info(f"📊 [Asset Scan Catch-up] Last scan ({last_scan_date or 'none'}) stale on boot. Executing AMFI & multi-asset catch-up...")
            await loop.run_in_executor(None, ingest_amfi_daily_feed, None, True)
            await loop.run_in_executor(None, run_comprehensive_asset_scan, "ALL_ASSETS", "catch_up_boot")

    except Exception as boot_err:
        logger.warning(f"📊 [AMFI & Multi-Asset Scheduler] Boot catch-up notice: {boot_err}")

    while True:
        try:
            now = datetime.now(IST)
            target = now.replace(hour=23, minute=15, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            logger.info(f"📊 [AMFI & Multi-Asset Scheduler] Next synchronization scheduled in {wait_seconds/3600:.2f} hours (at {target.strftime('%Y-%m-%d %H:%M:%S IST')}).")
            await asyncio.sleep(wait_seconds)

            today_str = datetime.now(IST).strftime("%Y-%m-%d")
            logger.info("📊 [AMFI & Multi-Asset Scheduler] Executing scheduled nightly synchronization...")

            from core.ingestion.amfi import ingest_amfi_daily_feed
            from core.ingestion.etf_ingest import ingest_all_amfi_etfs
            from core.analysis.asset_scanner import run_comprehensive_asset_scan
            from core.db.sovereign import refresh_daily_sovereign_benchmarks
            from core.db.agent_sessions import record_autonomous_event

            # 1. Sync Mutual Funds NAV Feed
            mf_res = await loop.run_in_executor(None, ingest_amfi_daily_feed, None, True)
            record_autonomous_event(
                event_type="AMFI_NAV_SYNC",
                ticker="AMFI_PORTAL",
                trigger_source="AMFI_NAV_SCHEDULER",
                action_taken="NAV_SYNC_AND_DELTA_CALC",
                summary=f"Nightly AMFI NAV synchronization completed: {mf_res.get('upserted', 0)} schemes updated.",
                metadata=mf_res
            )

            # 2. Sync National ETF Matrix
            etf_res = await loop.run_in_executor(None, ingest_all_amfi_etfs, True)
            record_autonomous_event(
                event_type="ETF_MATRIX_SYNC",
                ticker="AMFI_ETF_PORTAL",
                trigger_source="AMFI_NAV_SCHEDULER",
                action_taken="ETF_UNIVERSE_DISCOVERY",
                summary=f"Nightly AMFI ETF ingestion completed: {etf_res.get('persisted_to_db', 0)} ETFs synced across 9 categories.",
                metadata=etf_res
            )

            # 3. Multi-Asset Monitoring Scan (MF drift + Corporate Debt maturities/downgrade watches)
            scan_res = await loop.run_in_executor(None, run_comprehensive_asset_scan, "ALL_ASSETS", "nightly_cron")
            record_autonomous_event(
                event_type="MULTI_ASSET_MONITORING_SCAN",
                ticker="ALL_ASSETS",
                trigger_source="NIGHTLY_MONITORING_SCHEDULER",
                action_taken="MONITORING_SCAN_LEDGER_UPDATE",
                summary=f"Multi-asset scan completed: {scan_res.get('items_scanned', 0)} items scanned (MFs + Corporate Debt).",
                metadata=scan_res
            )

            # 4. Refresh Sovereign Yield Curve & SDL Disparity Matrix
            sov_res = await loop.run_in_executor(None, refresh_daily_sovereign_benchmarks, today_str)
            record_autonomous_event(
                event_type="SOVEREIGN_BENCHMARK_SYNC",
                ticker="RBI_AUCTION_CUTOFF",
                trigger_source="NIGHTLY_MONITORING_SCHEDULER",
                action_taken="SOVEREIGN_CURVE_AND_SDL_SYNC",
                summary=f"Sovereign risk-free benchmarks and SDL matrix refreshed for {today_str}.",
                metadata=sov_res
            )

            logger.info("📊 [AMFI & Multi-Asset Scheduler] Scheduled nightly synchronization pipeline fully completed.")
        except asyncio.CancelledError:
            logger.info("📊 [AMFI & Multi-Asset Scheduler] Background scheduler cancelled.")
            break
        except Exception as e:
            logger.error(f"📊 [AMFI & Multi-Asset Scheduler] Error in multi-asset synchronization: {e}")
            await asyncio.sleep(120)



async def run_daily_fund_audit_scheduler():
    """Automated background Mutual Fund Accounting Checkor (runs daily at 23:30 IST with boot catch-up)."""
    logger.info("🔍 [Fund Audit Scheduler] Background mutual fund accounting checkor initiated.")
    try:
        from core.analysis.fund_overlap_auditor import audit_single_fund_daily
        from core.db.connection import get_db_connection
        now = datetime.now(IST)
        yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT MAX(last_audited_at) FROM fund_forensic_dossiers")
            row = cur.fetchone()
            last_audit_date = str(row[0] or "")[:10] if row else ""
        finally:
            cur.close()
            conn.close()
        if not last_audit_date or last_audit_date < yesterday_str:
            logger.info(f"🔍 [Fund Audit Scheduler] Last fund audit ({last_audit_date or 'none'}) older than {yesterday_str}. Running catch-up audit...")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, audit_single_fund_daily, None, False)
    except Exception as boot_err:
        logger.warning(f"🔍 [Fund Audit Scheduler] Boot catch-up notice: {boot_err}")

    while True:
        try:
            now = datetime.now(IST)
            target = now.replace(hour=23, minute=30, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            logger.info(f"🔍 [Fund Audit Scheduler] Next fund audit scheduled in {wait_seconds/3600:.2f} hours (at {target.strftime('%Y-%m-%d %H:%M:%S IST')}).")
            await asyncio.sleep(wait_seconds)

            logger.info("🔍 [Fund Audit Scheduler] Executing scheduled nightly mutual fund accounting check...")
            from core.analysis.fund_overlap_auditor import audit_single_fund_daily
            from core.db.agent_sessions import record_autonomous_event
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(None, audit_single_fund_daily, None, False)

            if res:
                record_autonomous_event(
                    event_type="DAILY_FUND_AUDIT",
                    ticker=res.get("scheme_code", "UNKNOWN"),
                    trigger_source="AMFI_SCHEDULER_ROTATION",
                    action_taken="7_PILLAR_LOOKTHROUGH_AUDIT",
                    summary=f"Automated 7-pillar look-through audit completed for {res.get('scheme_name')} ({res.get('scheme_code')}). Health: {res.get('composite_health_score')}/100, Moat: {res.get('weighted_moat_score')}/100, ASRI: {res.get('accounting_risk_index')}%.",
                    metadata={
                        "composite_health_score": res.get("composite_health_score"),
                        "weighted_moat_score": res.get("weighted_moat_score"),
                        "accounting_risk_index": res.get("accounting_risk_index"),
                        "margin_of_safety_pct": res.get("margin_of_safety_pct")
                    }
                )
            logger.info(f"🔍 [Fund Audit Scheduler] Nightly fund accounting check completed for {res.get('scheme_code')}.")
        except asyncio.CancelledError:
            logger.info("🔍 [Fund Audit Scheduler] Background fund audit scheduler cancelled.")
            break
        except Exception as e:
            logger.error(f"🔍 [Fund Audit Scheduler] Error in fund audit scheduler: {e}")
            await asyncio.sleep(180)


async def run_daily_project_audit_scheduler():
    """Automated background Project Auditor (runs nightly at 03:00 IST)."""
    logger.info("🛡️ [Project Auditor Scheduler] Background project auditor initiated.")
    while True:
        try:
            now = datetime.now(IST)
            target = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            logger.info(f"🛡️ [Project Auditor Scheduler] Next audit scheduled in {wait_seconds/3600:.2f} hours (at {target.strftime('%Y-%m-%d %H:%M:%S IST')}).")
            await asyncio.sleep(wait_seconds)

            logger.info("🛡️ [Project Auditor Scheduler] Executing scheduled nightly project audit...")
            from core.audit.project_auditor import audit_project_full
            await audit_project_full(use_ai=True)
            logger.info("🛡️ [Project Auditor Scheduler] Nightly project audit completed.")
        except asyncio.CancelledError:
            logger.info("🛡️ [Project Auditor Scheduler] Background scheduler cancelled.")
            break
        except Exception as e:
            logger.error(f"🛡️ [Project Auditor Scheduler] Error in project audit scheduler: {e}")
            await asyncio.sleep(180)


async def warmup_task():
    """Primes local database connections and cache pools."""
    if os.environ.get("TESTING") == "1" or "pytest" in sys.modules:
        logger.info("🧪 Test environment detected: skipping live network warm-up task.")
        return
    logger.info("🚀 Starting warm‑up task: preloading local database connections...")
    try:
        init_db()
        logger.info("🚀 Warm‑up task completed: DB connection and schema caches primed.")
    except Exception as e:
        logger.warning(f"Warm‑up task warning: {e}")


# ==============================================================================
# Application Lifespan & Initialization
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    env = (os.environ.get("ENVIRONMENT") or "").strip().lower()
    is_render = (os.environ.get("RENDER") or "").strip().lower() in ["true", "1"]
    if env == "production" or is_render:
        secret_key = (os.environ.get("SECRET_KEY") or get_secret("SECRET_KEY") or "").strip()
        if not secret_key or len(secret_key) < 32 or secret_key == "stock_research_user_session_salt_2026":
            raise RuntimeError(
                "CRITICAL PRODUCTION BOOT FAILURE: SECRET_KEY is missing, insecure, or shorter than 32 characters. "
                "Declare a high-entropy SECRET_KEY (minimum 32 characters) in production environment variables."
            )
        admin_key = (os.environ.get("ADMIN_API_KEY") or get_secret("ADMIN_API_KEY") or "").strip()
        admin_pwd = (os.environ.get("ADMIN_PASSWORD") or get_secret("ADMIN_PASSWORD") or "").strip()
        if not admin_key or not admin_pwd:
            logger.warning("Production Notice: ADMIN_API_KEY or ADMIN_PASSWORD should be declared in production.")

    init_db()

    try:
        from core.db.mutual_funds import get_active_mutual_funds, seed_default_mutual_funds
        if not get_active_mutual_funds():
            seed_default_mutual_funds()
    except Exception as e:
        logger.warning(f"Initial mutual fund bootstrap seed skipped: {e}")

    try:
        from core.db.debt import seed_default_debt_securities
        seed_default_debt_securities()
    except Exception as e:
        logger.warning(f"Initial debt bootstrap seed skipped: {e}")

    try:
        from core.msme.seed import get_active_msme_firms_count, seed_default_msme_firms
        if get_active_msme_firms_count() == 0:
            seed_default_msme_firms()
    except Exception as e:
        logger.warning(f"Initial MSME bootstrap seed skipped: {e}")

    try:
        from core.db.safety_radar import seed_default_safety_radar_products
        seed_default_safety_radar_products()
    except Exception as e:
        logger.warning(f"Initial Safety Radar bootstrap seed skipped: {e}")

    is_testing = os.environ.get("TESTING") == "1" or "pytest" in sys.modules
    scheduler = None
    discovery_task = None
    amfi_task = None
    fund_audit_task = None
    audit_task = None
    bse_task = None

    if not is_testing:
        asyncio.create_task(warmup_task())
        scheduler = AsyncIOScheduler()
        register_jobs(scheduler)
        scheduler.start()
        discovery_task = asyncio.create_task(run_daily_discovery_scheduler())
        amfi_task = asyncio.create_task(run_daily_amfi_scheduler())
        fund_audit_task = asyncio.create_task(run_daily_fund_audit_scheduler())
        audit_task = asyncio.create_task(run_daily_project_audit_scheduler())
        from core.agents.watchers.bse_watcher import run_bse_watcher_loop
        bse_task = asyncio.create_task(run_bse_watcher_loop())

    try:
        yield
    finally:
        if discovery_task:
            discovery_task.cancel()
        if amfi_task:
            amfi_task.cancel()
        if fund_audit_task:
            fund_audit_task.cancel()
        if audit_task:
            audit_task.cancel()
        if bse_task:
            bse_task.cancel()
        if scheduler:
            scheduler.shutdown()


app = FastAPI(
    title="Moatnomics",
    description="Multi-asset investment research. Less noise, more nuance.",
    version="2.0.0",
    lifespan=lifespan
)

# Static files mounting
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Middleware setup
if BrotliMiddleware is not None:
    app.add_middleware(BrotliMiddleware, minimum_size=500)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://moatnomics.com",
        "https://www.moatnomics.com",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda request, exc: Response(content="Rate limit exceeded", status_code=429))
app.add_middleware(SlowAPIMiddleware)


class HeadMethodMiddleware(BaseHTTPMiddleware):
    """Transparently handles HEAD requests for uptime monitors and link crawlers."""
    async def dispatch(self, request: Request, call_next):
        if request.method == "HEAD":
            request.scope["method"] = "GET"
            response = await call_next(request)
            return Response(
                status_code=response.status_code,
                headers=dict(response.headers),
                background=response.background,
            )
        return await call_next(request)

app.add_middleware(HeadMethodMiddleware)


class CrawlerLogMiddleware(BaseHTTPMiddleware):
    """Logs fetches by known search/AI crawlers (they never run the browser telemetry script)."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            path = request.url.path
            if request.method in ("GET", "HEAD") and not path.startswith(("/static", "/api", "/admin")):
                from telemetry import classify_bot
                bot = classify_bot(request.headers.get("user-agent", ""))
                if bot:
                    from core.db.telemetry import record_crawler_hit
                    asyncio.get_running_loop().run_in_executor(
                        None, record_crawler_hit, bot[0], bot[1], path, response.status_code
                    )
        except Exception as crawl_err:
            logger.debug("Crawler log notice: %s", crawl_err)
        return response

app.add_middleware(CrawlerLogMiddleware)


# ==============================================================================
# Modular Routers Integration
# ==============================================================================
from core.msme.router import router as msme_router
app.include_router(msme_router, prefix="/api/msme")

from web.routers.auth_billing import router as auth_billing_router
from web.routers.dossier import router as dossier_router
from web.routers.markets import router as markets_router
from web.routers.admin import router as admin_router

app.include_router(auth_billing_router)
app.include_router(dossier_router)
app.include_router(markets_router)
app.include_router(admin_router)


# ==============================================================================
# SSR HTML Page Routes
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
def home_page(request: Request):
    """Public home & landing page with live stock search, discovery reel, and featured dossiers."""
    code = request.query_params.get("code")
    if code:
        return RedirectResponse(url=f"/auth/callback?code={urllib.parse.quote(code)}", status_code=303)

    try:
        archives = get_archived_reports_sync()
    except Exception as e:
        logger.error(f"Error fetching archives: {e}")
        archives = []

    try:
        all_equities = get_all_equities_directory_sync()
    except Exception as e:
        logger.error(f"Error fetching all equities for home: {e}")
        all_equities = []

    user = _get_current_web_user(request)
    can_access_today = _can_access_today_discovery(request, user)
    now = datetime.now(IST)
    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    is_past_9am = now.hour >= 9

    target_ed = today_str if (can_access_today and is_past_9am) else yesterday_str
    try:
        discovery_stocks = get_active_discovery_reel(edition_date=target_ed, allow_fallback=True)
    except Exception as e:
        logger.error(f"Error fetching discovery reel for home: {e}")
        discovery_stocks = []

    featured = archives[:9] if archives else []
    total_count = len(all_equities) if all_equities else (len(archives) if archives else 143)
    curr_ed = discovery_stocks[0]["edition_date"] if discovery_stocks else target_ed
    is_yesterday = (curr_ed == yesterday_str) or (not is_past_9am) or (curr_ed < today_str)

    sector_counts = collections.Counter(e.get("sector_slug", "DIVERSIFIED") for e in all_equities)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "active_page": "home",
            "featured_reports": featured,
            "all_equities": all_equities,
            "total_equities": total_count,
            "sector_options": SECTOR_TAXONOMY,
            "sector_counts": dict(sector_counts),
            "discovery_stocks": discovery_stocks,
            "total_reports": total_count,
            "pricing_packs": PRICING_PACKS,
            "is_yesterday_edition": is_yesterday,
            "can_access_today": can_access_today,
            "today_date": today_str,
            "yesterday_date": yesterday_str,
        }
    )


@app.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: Optional[str] = None,
    type: Optional[str] = None,
    asset_class: Optional[str] = None
):
    """Multi-asset unified search discovery page across Equities, Mutual Funds, and Corporate Debt/NCDs."""
    init_db()
    query_str = (q or "").strip()
    selected_type = (type or asset_class or "ALL").strip().upper()

    search_res = {
        "query": query_str,
        "total_matches": 0,
        "results": [],
        "categories": {"equities": [], "mutual_funds": [], "corporate_debt": []}
    }
    if query_str:
        from core.search.product_search import search_investment_products
        search_res = search_investment_products(query_str, product_type=selected_type, limit_per_category=20)

    return templates.TemplateResponse(
        request=request,
        name="search_results.html",
        context={
            "active_page": "search",
            "query": query_str,
            "selected_type": selected_type,
            "search_results": search_res,
        }
    )


@app.get("/api/search/products")
def api_search_products(
    q: str = Query(..., min_length=1, description="Search query string"),
    asset_class: str = Query("all", description="Asset class filter: 'all', 'equity', 'mutual_fund', 'debt'"),
    limit: int = Query(25, ge=1, le=100)
):
    """Public Omni-Product Search API across Equities, Mutual Funds, and Corporate Debt/NCDs."""
    init_db()
    from core.search.product_search import search_all_products
    matches = search_all_products(q, asset_class=asset_class, limit=limit)
    return json_response_with_cache({
        "status": "success",
        "query": q,
        "asset_class": asset_class,
        "count": len(matches),
        "results": matches
    }, max_age=60)



@app.get("/discovery", response_class=HTMLResponse)
def discovery_page(request: Request, edition: Optional[str] = Query(None)):
    """The Morning Discovery Reel: nightly screening of under-the-radar equities."""
    user = _get_current_web_user(request)
    can_access_today = _can_access_today_discovery(request, user)

    now = datetime.now(IST)
    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    is_past_9am = now.hour >= 9

    # Calculate countdown until next 09:00 AM IST drop
    target_9am = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now >= target_9am:
        target_9am += timedelta(days=1)
    seconds_until_9am = int((target_9am - now).total_seconds())
    hours_until_9am = seconds_until_9am // 3600
    mins_until_9am = (seconds_until_9am % 3600) // 60

    try:
        available_editions = get_available_discovery_editions(exclude_tests=True)
    except Exception as e:
        logger.error(f"Error fetching discovery editions: {e}")
        available_editions = []

    if edition:
        selected_edition = edition
    else:
        # Default edition selection:
        # If user is subscribed and today's edition exists past 9:00 AM, show today's edition!
        if can_access_today and is_past_9am and today_str in available_editions:
            selected_edition = today_str
        elif today_str in available_editions and is_past_9am:
            # Free user visiting /discovery: default to yesterday's archive so they can read in full with yesterday's badge, while seeing the top banner pointing to today's live Pro edition!
            selected_edition = yesterday_str if yesterday_str in available_editions else (available_editions[1] if len(available_editions) > 1 else today_str)
        else:
            # Before 9:00 AM or today not yet in DB: show yesterday's edition
            selected_edition = yesterday_str if yesterday_str in available_editions else (available_editions[0] if available_editions else today_str)

    try:
        discovery_stocks = get_active_discovery_reel(edition_date=selected_edition, allow_fallback=True)
    except Exception as e:
        logger.error(f"Error fetching discovery reel: {e}")
        discovery_stocks = []

    actual_edition = discovery_stocks[0]["edition_date"] if discovery_stocks else selected_edition
    is_today_edition = (actual_edition == today_str and is_past_9am)
    is_yesterday_edition = (actual_edition == yesterday_str) or (not is_past_9am) or (actual_edition < today_str)
    is_locked_for_user = (is_today_edition and not can_access_today)

    return templates.TemplateResponse(
        request=request,
        name="discovery.html",
        context={
            "active_page": "discovery",
            "discovery_stocks": discovery_stocks,
            "available_editions": available_editions,
            "current_edition": actual_edition,
            "today_date": today_str,
            "yesterday_date": yesterday_str,
            "is_today_edition": is_today_edition,
            "is_yesterday_edition": is_yesterday_edition,
            "is_locked_for_user": is_locked_for_user,
            "can_access_today": can_access_today,
            "is_past_9am": is_past_9am,
            "seconds_until_9am": seconds_until_9am,
            "hours_until_9am": hours_until_9am,
            "mins_until_9am": mins_until_9am,
        }
    )


@app.get("/pricing", response_class=HTMLResponse)
def pricing_page(request: Request):
    """Public pricing and checkout page displaying single-pass, credit packs, and Pro memberships."""
    detected_currency = resolve_currency_for_request(request)
    return templates.TemplateResponse(
        request=request,
        name="pricing.html",
        context={
            "active_page": "pricing",
            "pricing_packs": PRICING_PACKS,
            "b2b_packs": B2B_PACKS,
            "supported_currencies": SUPPORTED_CURRENCIES,
            "detected_currency": detected_currency,
        }
    )


@app.get("/dossier/{ticker}", response_class=HTMLResponse)
def dossier_page(request: Request, ticker: str):
    """
    Canonical stock research dossier page.
    Renders 7-pillar qualitative matrix, valuation multiples, and exchange citations.
    If uncompiled, serves the pending compilation queue template instead of a raw 404 JSON.
    """
    clean_t = clean_ticker(ticker)
    if not clean_t:
        return RedirectResponse(url="/")

    # Canonicalize ticker symbol (e.g. 'MANALI PETROCHEM' or '500268' -> 'MANALIPETC')
    canonical = resolve_canonical_symbol(clean_t) or clean_t
    if canonical != clean_t:
        return RedirectResponse(url=f"/dossier/{canonical}", status_code=302)

    rep = get_report_by_ticker_sync(canonical)
    if not rep or not rep.get("report_text"):
        # Resolve company details for the pending template
        scrip = resolve_bse_scrip_code(canonical) or "N/A"
        cached = get_bse_scrips_cache()
        company_name = canonical
        if cached:
            for c_name, c_code in cached.get("names", {}).items():
                if str(c_code) == str(scrip):
                    company_name = c_name.title()
                    break

        suggestions = get_ticker_suggestions(clean_t, n=4)

        # Phase 2: Equity-to-Debt Contagion Bridge for pending equities
        linked_debt = []
        contagion_alert = None
        try:
            from core.db.debt import get_debt_securities_for_equity
            linked_debt = get_debt_securities_for_equity(canonical)
            if linked_debt:
                from core.analysis.debt_engine import evaluate_equity_cross_contagion
                contagion_alert = evaluate_equity_cross_contagion(linked_debt[0], fetch_live_fundamentals=False)
        except Exception as e:
            logger.debug(f"Linked debt query notice for pending {canonical}: {e}")

        return templates.TemplateResponse(
            request=request,
            name="dossier_pending.html",
            context={
                "ticker": canonical,
                "display_ticker": canonical,
                "company_name": company_name,
                "scrip_code": scrip,
                "suggestions": suggestions,
                "active_page": "dossier",
                "linked_debt": linked_debt,
                "contagion_alert": contagion_alert,
            }
        )

    # Ingest verified citations footnotes
    raw_md = rep.get("report_text", "")
    citations = rep.get("citations") or []
    if not citations and rep.get("citations_json"):
        try:
            citations = json.loads(rep.get("citations_json"))
        except Exception as e:
            logger.debug("Failed parsing citations_json in stock_dossier: %s", e)
            citations = []
    if not citations and raw_md:
        citations = extract_citations_from_report(raw_md)

    # Separate narrative prose from footnotes so they don't appear duplicated as unstyled markdown
    prose_md = raw_md
    if citations:
        parts = re.split(r"(?im)^\s*#+\s*.*(?:Verified Regulatory Sources|Footnote Citations)", raw_md)
        if len(parts) > 1 and len(parts[0].strip()) > 300:
            prose_md = parts[0].rstrip()

    # Strip redundant Health Matrix markdown list so only top colored badge pills appear
    prose_md = remove_health_matrix_text(prose_md)

    # Determine deep-dive unlock status (Pillars 03 & 05 + Thesis Drift)
    web_user = _get_current_web_user(request)
    is_deep_dive_unlocked = False
    if _is_admin_authenticated(request):
        is_deep_dive_unlocked = True
    elif os.environ.get("TESTING") == "1" and (request.headers.get("x-unlock-preview") == "1" or request.query_params.get("unlocked") == "1"):
        is_deep_dive_unlocked = True
    elif web_user:
        is_deep_dive_unlocked = is_ticker_unlocked_for_user(web_user.get("id", ""), canonical)

    # Convert report markdown into semantic HTML
    html_content = markdown.markdown(
        prose_md,
        extensions=["tables", "fenced_code", "nl2br"]
    )
    scrip_code = rep.get("scrip_code") or resolve_bse_scrip_code(canonical) or ""
    html_content = wrap_html_with_collapsible_pillars(
        html_content,
        scrip_code=scrip_code,
        is_deep_dive_unlocked=is_deep_dive_unlocked,
        ticker=canonical
    )

    mcap = rep.get("baseline_mcap")
    # format_inr() already prefixes the rupee symbol.
    mcap_formatted = format_inr(mcap) if mcap else "N/A"

    # 7-Pillar Health Matrix
    matrix = extract_health_matrix(raw_md)

    # Multi-Quarter Revisions & Thesis Drift Monitoring
    revisions = get_report_revisions(canonical) or []
    diff_data = None
    if len(revisions) >= 2:
        try:
            diff_data = compare_revisions(revisions[1], revisions[0])
        except Exception as e:
            logger.debug(f"Differential revision comparison notice: {e}")

    # Anchoring Bias Guardrail: Valuation & 52-Week Percentiles
    fund = {}
    try:
        fund = get_stock_fundamentals(canonical) or {}
    except Exception as fund_err:
        logger.debug("Fundamentals lookup notice for %s: %s", canonical, fund_err)

    price_val = rep.get("baseline_price") or fund.get("current_price")
    low_52 = fund.get("fifty_two_week_low") or fund.get("52w_low")
    high_52 = fund.get("fifty_two_week_high") or fund.get("52w_high")
    pe_val = rep.get("baseline_pe") or fund.get("pe_ratio")

    pct_52w = calculate_52w_percentile(price_val, low_52, high_52)
    pct_pe = calculate_pe_percentile(pe_val, revisions)
    pe_quartile = get_valuation_quartile(pct_pe)

    # Ingest 6-Month Price Momentum & 50-DMA Trend History
    chart_data = None
    chart_json = "{}"
    pead_data = None
    try:
        df_hist = get_historical_prices(canonical, period="6mo")
        from core.analysis.fundamentals import compute_pead_drift_band
        pead_data = compute_pead_drift_band(rep, df_hist)

        if df_hist is not None and not df_hist.empty and "Close" in df_hist.columns and "Date" in df_hist.columns:
            import pandas as pd
            dates = []
            closes = []
            sma50 = []
            for _, row in df_hist.iterrows():
                d_val = row["Date"]
                d_str = d_val.strftime("%d %b") if hasattr(d_val, "strftime") else str(d_val)[:10]
                dates.append(d_str)
                c_val = row.get("Close")
                closes.append(round(float(c_val), 2) if c_val is not None and pd.notna(c_val) else None)
                s_val = row.get("SMA50")
                sma50.append(round(float(s_val), 2) if s_val is not None and pd.notna(s_val) else None)

            latest_close = closes[-1] if closes else None
            latest_sma = next((s for s in reversed(sma50) if s is not None), None)
            trend_badge = None
            trend_status = "neutral"
            trend_inference = None
            if latest_close and latest_sma:
                diff_pct = ((latest_close - latest_sma) / latest_sma) * 100
                if diff_pct >= 0:
                    trend_badge = f"+{diff_pct:.1f}% vs 50-DMA"
                    trend_status = "bullish"
                    trend_inference = f"Trading {trend_badge}. Momentum remains constructive above the 50-day accumulation trendline."
                else:
                    trend_badge = f"{diff_pct:.1f}% vs 50-DMA"
                    trend_status = "bearish"
                    trend_inference = f"Trading {trend_badge}. Consolidation below 50-DMA indicates valuation compression or intermediate mean-reversion."

            chart_data = {
                "dates": dates,
                "closes": closes,
                "sma50": sma50,
                "latest_close": latest_close,
                "latest_sma": latest_sma,
                "trend_badge": trend_badge,
                "trend_status": trend_status,
                "trend_inference": trend_inference
            }
            chart_json = json.dumps(chart_data)
    except Exception as e:
        logger.debug(f"Momentum chart generation notice for {canonical}: {e}")

    # Phase 2: Equity-to-Debt Contagion Bridge
    linked_debt = []
    contagion_alert = None
    try:
        from core.db.debt import get_debt_securities_for_equity
        linked_debt = get_debt_securities_for_equity(canonical)
        if linked_debt:
            from core.analysis.debt_engine import evaluate_equity_cross_contagion
            contagion_alert = evaluate_equity_cross_contagion(linked_debt[0])
    except Exception as e:
        logger.debug(f"Linked debt query notice for {canonical}: {e}")

    # Phase 1 Upgrade: Equity Intelligence (Sector, Flow, Forensics, Valuation Radar, Bull/Bear)
    equity_intel = None
    try:
        from core.analysis.equity_dossier import compile_equity_dossier, _safe_float
        if price_val is not None and _safe_float(fund.get("current_price"), 0.0) <= 0:
            parsed_price = _safe_float(str(price_val).replace("₹", ""), 0.0)
            if parsed_price > 0:
                fund["current_price"] = parsed_price
        if pe_val is not None and _safe_float(fund.get("pe_ratio"), 0.0) <= 0:
            parsed_pe = _safe_float(str(pe_val).replace("x", ""), 0.0)
            if parsed_pe > 0:
                fund["pe_ratio"] = parsed_pe
        if scrip_code and not fund.get("scrip_code"):
            fund["scrip_code"] = scrip_code
        equity_intel = compile_equity_dossier(
            ticker=canonical,
            fundamentals=fund,
            company_name=rep.get("short_name", canonical),
            industry_str=rep.get("industry", ""),
        )
        if equity_intel and equity_intel.get("epistemic_ledger"):
            from core.analysis.epistemic_schema import build_equity_epistemic_ledger
            equity_intel["epistemic_ledger"] = build_equity_epistemic_ledger(
                ticker=canonical,
                stock_data=fund,
                equity_intel=equity_intel,
                formatted_date=str(rep.get("formatted_date") or "Latest Filing"),
            )
    except Exception as e:
        logger.debug(f"Equity dossier intelligence compilation notice for {canonical}: {e}")

    user_countercase = None
    user_thesis_checkpoint = None
    if web_user and web_user.get("id"):
        try:
            from core.db.users import get_user_thesis_entries
            saved_theses = get_user_thesis_entries(str(web_user["id"]), canonical)
            user_countercase = saved_theses.get("COUNTERCASE")
            user_thesis_checkpoint = saved_theses.get("THESIS_CHECKPOINT")
        except Exception as e:
            logger.debug(f"User thesis lookup notice for {canonical}: {e}")

    return templates.TemplateResponse(
        request=request,
        name="dossier.html",
        context={
            "ticker": clean_t,
            "short_name": rep.get("short_name", clean_t),
            "current_price": str(rep.get("baseline_price") or "N/A"),
            "pe_ratio": str(rep.get("baseline_pe") or "N/A"),
            "market_cap_str": mcap_formatted,
            "scrip_code": scrip_code if str(scrip_code or "").strip().isdigit() else "N/A",
            "formatted_date": rep.get("formatted_date", "Archived"),
            "report_html": html_content,
            "citations": citations,
            "matrix": matrix,
            "diff": diff_data,
            "revisions_count": len(revisions),
            "pct_52w": pct_52w,
            "low_52": low_52,
            "high_52": high_52,
            "pct_pe": pct_pe,
            "pe_quartile": pe_quartile,
            "chart_data": chart_data,
            "chart_json": chart_json,
            "pead_data": pead_data,
            "linked_debt": linked_debt,
            "contagion_alert": contagion_alert,
            "is_deep_dive_unlocked": is_deep_dive_unlocked,
            "web_user": web_user,
            "user_countercase": user_countercase,
            "user_thesis_checkpoint": user_thesis_checkpoint,
            "equity_intel": equity_intel,
            "epistemic_ledger": equity_intel.get("epistemic_ledger") if equity_intel else None,
        }
    )


@app.get("/compare", response_class=HTMLResponse)
async def compare_page(
    request: Request,
    a: Optional[str] = "INFY",
    b: Optional[str] = "TCS",
    compare_error: Optional[str] = None
):
    """Cross-company peer comparison and 3-tier disparity diagnostic."""
    clean_a = clean_ticker(a if a is not None else "INFY")
    clean_b = clean_ticker(b if b is not None else "TCS")
    canonical_a = resolve_canonical_symbol(clean_a) or clean_a
    canonical_b = resolve_canonical_symbol(clean_b) or clean_b

    error_msg = compare_error
    if not clean_a or not clean_b:
        error_msg = error_msg or "Please provide two valid stock ticker symbols to initiate peer comparison."
    elif canonical_a == canonical_b:
        error_msg = error_msg or f"Cannot compare a company against itself ({canonical_a}). Please select two distinct entities for peer comparison."
    else:
        # Verify both tickers are recognized BSE/NSE securities or archived dossiers before scraping
        unrecognized = []
        for sym in (canonical_a, canonical_b):
            scrip = resolve_bse_scrip_code(sym)
            has_rep = get_report_by_ticker_sync(sym)
            if (not scrip or scrip == "N/A") and not has_rep:
                unrecognized.append(sym)
        if unrecognized:
            suggestions = []
            for u in unrecognized:
                suggestions.extend(get_ticker_suggestions(u, limit=3))
            hint = f" Did you mean: {', '.join(dict.fromkeys(suggestions))}?" if suggestions else ""
            error_msg = (
                f"Unrecognized or unlisted ticker symbol(s): {', '.join(unrecognized)}. "
                f"Please select listed BSE/NSE companies for peer comparison.{hint}"
            )

    comp_data = {
        "ticker_a": canonical_a,
        "ticker_b": canonical_b,
        "fund_a": {},
        "fund_b": {},
        "matrix_a": {},
        "matrix_b": {},
        "disparity": {"is_disparate": False, "warnings": []}
    }

    if not error_msg:
        try:
            comp_data = await compare_two_companies(canonical_a, canonical_b)
        except Exception as e:
            logger.error(f"Error comparing companies {canonical_a} vs {canonical_b}: {e}")
            error_msg = f"Unable to retrieve verified peer metrics for {canonical_a} vs {canonical_b}: {e}"

    for f_key in ["fund_a", "fund_b"]:
        m = comp_data.get(f_key, {}).get("market_cap")
        if m:
            comp_data[f_key]["market_cap_str"] = format_inr(m)

    comparison = comp_data.get("comparison")
    if not comparison:
        def _build_pillars(m):
            if not isinstance(m, dict):
                return {}
            return {
                "moat": m.get("moat") or m.get("Moat"),
                "management": m.get("management") or m.get("Management") or m.get("CapitalAllocation") or m.get("capital_allocation"),
                "financials": m.get("financials") or m.get("Financials") or m.get("BalanceSheet") or m.get("balance_sheet"),
                "valuation": m.get("valuation") or m.get("Valuation"),
                "macro": m.get("macro") or m.get("Macro"),
                "forensic": m.get("forensic") or m.get("Forensic") or m.get("Governance") or m.get("governance"),
                "diagnostic": m.get("diagnostic") or m.get("Diagnostic"),
            }
        comparison = {
            "company_a": {
                "ticker": canonical_a,
                "fundamentals": comp_data.get("fund_a", {}),
                "pillars": _build_pillars(comp_data.get("matrix_a", {}))
            },
            "company_b": {
                "ticker": canonical_b,
                "fundamentals": comp_data.get("fund_b", {}),
                "pillars": _build_pillars(comp_data.get("matrix_b", {}))
            }
        }

    return templates.TemplateResponse(
        request=request,
        name="compare.html",
        context={
            "active_page": "compare",
            "ticker_a": canonical_a,
            "ticker_b": canonical_b,
            "compared": not bool(error_msg),
            "compare_error": error_msg,
            "comparison": comparison,
            "fund_a": comp_data.get("fund_a", {}),
            "fund_b": comp_data.get("fund_b", {}),
            "matrix_a": comp_data.get("matrix_a", {}),
            "matrix_b": comp_data.get("matrix_b", {}),
            "disparity": comp_data.get("disparity", {"is_disparate": False, "warnings": []})
        }
    )


@app.get("/debt", response_class=HTMLResponse)
def debt_directory_page(
    request: Request,
    seniority: Optional[str] = None,
    instrument_type: Optional[str] = None,
    min_rating: Optional[str] = None,
    q: Optional[str] = None
):
    """Corporate Debt, NCDs, and SDIs under the SEBI ₹10,000 face value framework."""
    init_db()
    query_str = (q or "").strip()
    if query_str:
        from core.search.product_search import search_debt_securities
        raw_matches = search_debt_securities(query_str, limit=50)
        securities = []
        for m in raw_matches:
            sec = get_debt_security_by_isin(m["identifier"])
            if sec:
                securities.append(sec)
    else:
        securities = get_active_debt_securities(
            seniority=seniority,
            instrument_type=instrument_type,
            min_rating=min_rating
        )

    recent_actions = get_recent_rating_actions(limit=8)
    valid_ytms = [
        float(s["ytm_pct"])
        for s in securities
        if s.get("ytm_pct") is not None and float(s["ytm_pct"]) > 0
    ]
    avg_ytm = f"{statistics.mean(valid_ytms):.2f}" if valid_ytms else "9.85"

    from core.db.sovereign import get_sovereign_curve_analytics
    from core.analysis.asset_scanner import get_asset_scan_runs
    try:
        curve_analytics = get_sovereign_curve_analytics()
        benchmark_10y = f"{curve_analytics.get('benchmark_10y_gsec', 7.12):.2f}"
    except Exception as e:
        logger.warning("Failed getting sovereign curve analytics: %s", e)
        benchmark_10y = "7.12"

    last_scans = get_asset_scan_runs(limit=1)
    last_scan_info = last_scans[0] if last_scans else None

    return templates.TemplateResponse(
        request=request,
        name="debt_directory.html",
        context={
            "active_page": "debt",
            "securities": securities,
            "avg_ytm": avg_ytm,
            "benchmark_10y_gsec": benchmark_10y,
            "last_scan_info": last_scan_info,
            "recent_actions": recent_actions,
            "current_seniority": seniority,
            "current_type": instrument_type,
            "current_rating": min_rating,
            "query": query_str,
        }
    )



@app.get("/debt/{isin}", response_class=HTMLResponse)
def debt_dossier_page(request: Request, isin: str):
    """5-Pillar Credit & Solvency Dossier for a corporate bond or SDI."""
    init_db()
    clean_isin = isin.strip().upper()
    sec = get_debt_security_by_isin(clean_isin)
    if not sec:
        raise HTTPException(status_code=404, detail=f"Corporate debt security with ISIN '{clean_isin}' not found.")

    rating_history = get_rating_history(clean_isin)
    posture = evaluate_5_pillar_credit_posture(sec, rating_history=rating_history)
    is_deep_dive_unlocked = _asset_unlocked_for_request(request, "DEBT", clean_isin)

    from core.analysis.epistemic_schema import build_multi_asset_epistemic_ledger
    epistemic_ledger = build_multi_asset_epistemic_ledger(
        asset_class="DEBT",
        entity_id=clean_isin,
        context={
            "issuer_name": sec.get("issuer_name") or clean_isin,
            "credit_rating": sec.get("credit_rating") or posture.get("credit_rating") or "AAA",
            "ytm": posture.get("ytm_pct") or sec.get("ytm") or "N/A",
            "coupon_rate": sec.get("coupon_rate") or posture.get("coupon_pct") or "N/A",
            "modified_duration": (posture.get("duration_profile") or {}).get("modified_duration_years", "N/A"),
        },
        formatted_date=str(sec.get("last_updated") or "Latest Filing")[:10],
    )

    return templates.TemplateResponse(
        request=request,
        name="debt_dossier.html",
        context={
            "active_page": "debt",
            "security": sec,
            "posture": posture,
            "rating_history": rating_history,
            "is_deep_dive_unlocked": is_deep_dive_unlocked,
            "unlock_kind": "DEBT",
            "unlock_id": clean_isin,
            "epistemic_ledger": epistemic_ledger,
        }
    )


@app.get("/stocks", response_class=RedirectResponse)
def stocks_alias_redirect(request: Request):
    """Permanent canonical redirect from /stocks to /equities preserving query parameters."""
    target_url = "/equities"
    if request.url.query:
        target_url = f"/equities?{request.url.query}"
    return RedirectResponse(url=target_url, status_code=301)


@app.get("/reports", response_class=RedirectResponse)
@app.get("/reports/", response_class=RedirectResponse)
def reports_alias_redirect(request: Request):
    """Permanent canonical redirect from /reports to /equities preserving query parameters."""
    target_url = "/equities"
    if request.url.query:
        target_url = f"/equities?{request.url.query}"
    return RedirectResponse(url=target_url, status_code=301)


@app.get("/equities", response_class=HTMLResponse)
def equities_directory_page(
    request: Request,
    q: Optional[str] = None,
    sector: Optional[str] = None,
    market_cap: Optional[str] = None,
    sort: Optional[str] = "mcap_desc",
):
    """Equities Directory & Screener."""
    init_db()
    all_equities = get_all_equities_directory_sync()
    total_equities = len(all_equities)

    total_mcap_cr = sum(e.get("market_cap_cr", 0.0) for e in all_equities)
    total_mcap_lakh_cr = total_mcap_cr / 100000.0 if total_mcap_cr else 210.0

    roce_vals = [e["roce"] for e in all_equities if e.get("roce") is not None]
    median_roce = round(statistics.median(roce_vals), 1) if roce_vals else 18.2

    pe_vals = [e["pe_float"] for e in all_equities if e.get("pe_float") is not None and e["pe_float"] > 0]
    median_pe = round(statistics.median(pe_vals), 1) if pe_vals else 24.5

    sector_counts = collections.Counter(e.get("sector_slug", "DIVERSIFIED") for e in all_equities)

    featured_equity = None
    for cand_ticker in ["INFY", "TCS", "RELIANCE", "HDFCBANK", "LT"]:
        cand = next((e for e in all_equities if e["ticker"] == cand_ticker), None)
        if cand:
            featured_equity = cand
            break
    if not featured_equity and all_equities:
        featured_equity = all_equities[0]

    filtered = list(all_equities)
    query_str = (q or "").strip()
    if query_str:
        q_lower = query_str.lower()
        filtered = [
            e for e in filtered
            if q_lower in e["ticker"].lower()
            or q_lower in e.get("name", "").lower()
            or q_lower in e.get("company_name", "").lower()
            or q_lower in e.get("industry", "").lower()
            or q_lower in e.get("sector", "").lower()
        ]

    sec_filter = (sector or "").strip().upper()
    if sec_filter:
        filtered = [e for e in filtered if e.get("sector_slug", "").upper() == sec_filter]

    tier_filter = (market_cap or "").strip().upper()
    if tier_filter in ["MEGA", "LARGE", "MID", "SMALL"]:
        filtered = [e for e in filtered if e.get("market_cap_tier_slug", "").upper() == tier_filter]
    elif tier_filter in ["RECENT", "NEW", "INDUCTED"]:
        filtered = [e for e in filtered if e.get("is_recently_inducted")]

    recent_inductions_count = sum(1 for e in all_equities if e.get("is_recently_inducted"))

    sort_key = (sort or "mcap_desc").strip().lower()
    if sort_key == "mcap_asc":
        filtered.sort(key=lambda x: (x.get("market_cap_cr", 0.0) <= 0, x.get("market_cap_cr", 0.0)))
    elif sort_key == "roce_desc":
        filtered.sort(key=lambda x: (x.get("roce") is not None, x.get("roce") or -999.0), reverse=True)
    elif sort_key == "pe_asc":
        filtered.sort(key=lambda x: (x.get("pe_float") is not None and x.get("pe_float") > 0, -(x.get("pe_float") or 999999.0)), reverse=True)
    elif sort_key == "name_asc":
        filtered.sort(key=lambda x: x.get("name", "").lower())
    elif sort_key == "rev_desc":
        filtered.sort(key=lambda x: x.get("revision_count", 1), reverse=True)
    else:
        filtered.sort(key=lambda x: x.get("market_cap_cr", 0.0), reverse=True)

    return templates.TemplateResponse(
        request=request,
        name="equities_directory.html",
        context={
            "active_page": "equities",
            "equities": filtered,
            "total_equities": total_equities,
            "total_mcap_lakh_cr": total_mcap_lakh_cr,
            "median_roce": median_roce,
            "median_pe": median_pe,
            "featured_equity": featured_equity,
            "sector_options": SECTOR_TAXONOMY,
            "sector_counts": dict(sector_counts),
            "recent_inductions_count": recent_inductions_count,
            "current_sector": sec_filter or None,
            "current_tier": tier_filter or None,
            "current_sort": sort_key,
            "query": query_str,
        }
    )


@app.get("/funds", response_class=HTMLResponse)
def fund_directory_page(
    request: Request,
    category: Optional[str] = None,
    broad_category: Optional[str] = None,
    q: Optional[str] = None
):
    """Public Mutual Fund Look-Through directory & screener under SEBI disclosure norms."""
    init_db()
    query_str = (q or "").strip()
    if query_str:
        from core.search.product_search import search_mutual_funds
        raw_matches = search_mutual_funds(query_str, limit=50)
        schemes = []
        for m in raw_matches:
            s = get_mutual_fund_scheme(m["identifier"])
            if s:
                schemes.append(s)
            else:
                nav_val = float(str(m.get("details", {}).get("nav", "0")).replace("₹", "").replace(",", "") or 0.0)
                schemes.append({
                    "scheme_code": m["identifier"],
                    "scheme_name": m["title"],
                    "fund_house": m.get("subtitle", "").split("•")[0].strip(),
                    "category": m.get("details", {}).get("category", "Mutual Fund"),
                    "aum_crores": 0.0,
                    "nav": nav_val,
                    "ter_direct_pct": 0.75,
                    "ter_regular_pct": 1.50,
                    "active_share_pct": 70.0
                })
    else:
        schemes = get_active_mutual_funds(category=category, broad_category=broad_category)

    total_aum = sum(s.get("aum_crores", 0.0) for s in schemes)
    drag_vals = [(s.get("ter_regular_pct", 1.5) - s.get("ter_direct_pct", 0.7)) * 100 for s in schemes]
    avg_drag_bps = round(sum(drag_vals) / len(drag_vals), 0) if drag_vals else 75
    featured_fund = get_featured_daily_fund_dossier()

    return templates.TemplateResponse(
        request=request,
        name="fund_directory.html",
        context={
            "active_page": "funds",
            "schemes": schemes,
            "total_aum": total_aum,
            "avg_drag_bps": int(avg_drag_bps),
            "current_category": broad_category or category,
            "query": query_str,
            "featured_fund": featured_fund
        }
    )


@app.get("/funds/compare/overlap", response_class=HTMLResponse)
def fund_overlap_page(
    request: Request,
    scheme_a: Optional[str] = None,
    scheme_b: Optional[str] = None
):
    """True Diversification & Portfolio Overlap Diagnostic Tool."""
    init_db()
    all_funds = get_active_mutual_funds()

    scheme_a_code = (scheme_a or "PPFAS_FLEXICAP_DIR").strip().upper()
    scheme_b_code = (scheme_b or "MIRAE_LARGECAP_DIR").strip().upper()

    overlap_res = None
    if scheme_a_code and scheme_b_code:
        h_a = get_scheme_holdings(scheme_a_code)
        h_b = get_scheme_holdings(scheme_b_code)
        s_a = get_mutual_fund_scheme(scheme_a_code) or {}
        s_b = get_mutual_fund_scheme(scheme_b_code) or {}
        name_a = s_a.get("scheme_name", scheme_a_code)
        name_b = s_b.get("scheme_name", scheme_b_code)
        overlap_res = calculate_portfolio_overlap(h_a, h_b, name_a=name_a, name_b=name_b)

    return templates.TemplateResponse(
        request=request,
        name="fund_overlap.html",
        context={
            "active_page": "funds",
            "all_funds": all_funds,
            "scheme_a_code": scheme_a_code,
            "scheme_b_code": scheme_b_code,
            "overlap_res": overlap_res,
        }
    )


@app.get("/funds/{scheme_code}", response_class=HTMLResponse)
def fund_dossier_page(request: Request, scheme_code: str):
    """6-Pillar Mutual Fund Look-Through Dossier & Report Generation."""
    init_db()
    clean_code = scheme_code.strip().upper()
    scheme = get_mutual_fund_scheme(clean_code)
    if not scheme:
        from core.ingestion.amfi import search_amfi_master_directory
        amfi_matches = search_amfi_master_directory(clean_code, limit=1)
        if amfi_matches:
            scheme = get_mutual_fund_scheme(clean_code) or amfi_matches[0]

    if not scheme:
        raise HTTPException(status_code=404, detail=f"Mutual fund scheme with code '{clean_code}' not found.")

    dossier = evaluate_mutual_fund_comprehensive(clean_code)
    if not dossier:
        raise HTTPException(status_code=500, detail="Failed to generate mutual fund look-through dossier.")

    forensic_dossier = get_fund_forensic_dossier(clean_code)
    if not forensic_dossier:
        try:
            forensic_dossier = audit_single_fund_daily(clean_code)
        except Exception as e:
            logger.warning(f"Could not generate full report on-demand for {clean_code}: {e}")

    is_deep_dive_unlocked = _asset_unlocked_for_request(request, "FUND", clean_code)
    forensic_locked = False
    if forensic_dossier and not is_deep_dive_unlocked:
        forensic_dossier = None
        forensic_locked = True

    forensic_dossier_html = ""
    if forensic_dossier and forensic_dossier.get("dossier_text"):
        forensic_dossier_html = wrap_fund_dossier_with_collapsible_dimensions(
            forensic_dossier.get("dossier_text", ""),
            scheme_code=clean_code,
            scheme_name=dossier.get("scheme", {}).get("scheme_name", "")
        )

    credit_quote = None
    try:
        credit_quote = calculate_deep_dive_credit_cost(clean_code)
    except Exception as e:
        logger.warning(f"Could not calculate credit quote for {clean_code}: {e}")

    from core.analysis.epistemic_schema import build_multi_asset_epistemic_ledger
    sch_obj = dossier.get("scheme") or {}
    as_obj = dossier.get("active_share") or {}
    epistemic_ledger = build_multi_asset_epistemic_ledger(
        asset_class="MUTUAL_FUND",
        entity_id=clean_code,
        context={
            "scheme_name": sch_obj.get("scheme_name") or clean_code,
            "aum": sch_obj.get("aum_crores") or "N/A",
            "nav": sch_obj.get("nav") or "N/A",
            "ter": sch_obj.get("ter_direct_pct") or "N/A",
            "active_share": as_obj.get("active_share_pct") or sch_obj.get("active_share_pct") or "N/A",
        },
        formatted_date=str(sch_obj.get("last_updated") or "Latest Filing")[:10],
    )

    return templates.TemplateResponse(
        request=request,
        name="fund_dossier.html",
        context={
            "active_page": "funds",
            "scheme": dossier["scheme"],
            "lookthrough": dossier["lookthrough"],
            "active_share": dossier["active_share"],
            "fee_drag": dossier["fee_drag"],
            "risk_capture": dossier["risk_capture"],
            "forensic_dossier": forensic_dossier,
            "forensic_dossier_html": forensic_dossier_html,
            "credit_quote": credit_quote,
            "is_deep_dive_unlocked": is_deep_dive_unlocked,
            "forensic_locked": forensic_locked,
            "unlock_kind": "FUND",
            "unlock_id": clean_code,
            "epistemic_ledger": epistemic_ledger,
        }
    )


@app.get("/sovereign", response_class=HTMLResponse)
def sovereign_page(request: Request):
    """Sovereign Risk-Free Benchmarks & Par Yield Curve page."""
    from core.analysis.sovereign_engine import evaluate_sovereign_curve
    init_db()
    curve_data = evaluate_sovereign_curve()
    return templates.TemplateResponse(
        request=request,
        name="sovereign_curve.html",
        context={
            "active_page": "sovereign",
            "analytics": curve_data
        }
    )


@app.get("/etfs", response_class=HTMLResponse)
def etfs_page(
    request: Request,
    category: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None)
):
    """National ETF Matrix & Tracking Error Monitoring page."""
    from core.analysis.etf_matrix_engine import evaluate_etf_matrix
    init_db()
    matrix_data = evaluate_etf_matrix(category=category, query=q, sort_by=sort_by)
    return templates.TemplateResponse(
        request=request,
        name="etf_matrix.html",
        context={
            "active_page": "etfs",
            "current_category": category or "ALL",
            "current_query": q or "",
            "current_sort": sort_by or "aum_desc",
            "data": matrix_data
        }
    )


@app.get("/etfs/{symbol}", response_class=HTMLResponse)
def etf_dossier_page(request: Request, symbol: str):
    """ETF Dossier with live premium/discount tracking and arbitrage monitoring."""
    from core.analysis.etf_matrix_engine import get_etf_detail
    init_db()
    clean_sym = symbol.strip().upper()
    detail = get_etf_detail(clean_sym)
    if not detail:
        raise HTTPException(status_code=404, detail=f"ETF '{clean_sym}' not found in master matrix.")

    return templates.TemplateResponse(
        request=request,
        name="etf_dossier.html",
        context={
            "active_page": "etfs",
            "symbol": clean_sym,
            "data": detail,
            "etf": detail["etf"],
            "amc_issuer": detail["amc_issuer"],
            "category_label": detail["category_label"],
            "aum_formatted": detail["aum_formatted"],
            "arbitrage": detail["arbitrage_analysis"],
            "replication": detail["replication_audit"],
            "liquidity": detail["liquidity_audit"],
            "countercase_risks": detail["countercase_risks"],
            "peers": detail["peers"],
            "forensic_notes": detail["forensic_notes"]
        }
    )


@app.get("/calculator/tax", response_class=HTMLResponse)
async def tax_calculator_page(
    request: Request,
    tax_slab: Optional[str] = Query("30.0"),
    inflation: Optional[str] = Query("5.0"),
):
    """Render Post-Tax Real Return Matrix across Indian asset classes."""
    try:
        parsed_slab = float(tax_slab) if tax_slab not in (None, "") else 30.0
    except (ValueError, TypeError):
        parsed_slab = 30.0

    try:
        parsed_inflation = float(inflation) if inflation not in (None, "") else 5.0
    except (ValueError, TypeError):
        parsed_inflation = 5.0

    # Clamp to realistic Indian statutory & macroeconomic bounds
    clamped_slab = max(0.0, min(42.74, parsed_slab))
    clamped_inflation = max(0.0, min(25.0, parsed_inflation))

    from core.analysis.net_real_tax_calculator import calculate_post_tax_matrix
    matrix = calculate_post_tax_matrix(
        marginal_tax_slab_pct=clamped_slab,
        inflation_pct=clamped_inflation,
    )
    return templates.TemplateResponse(
        request,
        "tax_calculator.html",
        {
            "request": request,
            "matrix": matrix,
            "assets": matrix,
            "tax_slab": clamped_slab,
            "current_slab": clamped_slab,
            "inflation": clamped_inflation,
            "current_inflation": clamped_inflation,
            "active_page": "tax_calculator",
        },
    )


@app.get("/msme", response_class=HTMLResponse)
def msme_directory_page(
    request: Request,
    sector: Optional[str] = None,
    state: Optional[str] = None,
    tier: Optional[str] = None,
    q: Optional[str] = None
):
    """Unlisted MSME & Emerging SME Directory under the MSMED Act 2020."""
    init_db()
    from core.msme.seed import get_active_msme_firms_count, seed_default_msme_firms
    if get_active_msme_firms_count() == 0:
        seed_default_msme_firms()

    from core.msme.utils import build_search_query, classify_msme_tier
    from core.db.connection import get_db_connection, get_supabase_url
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        use_pg = bool(get_supabase_url())
        placeholder = "%s" if use_pg else "?"

        where, values = build_search_query(
            {"q": q, "sector": sector, "state": state, "tier": tier},
            placeholder=placeholder
        )

        sql = f"""
            SELECT uin, name, sector_name, city, state, annual_turnover,
                   employee_count, registration_date, source
            FROM msme_firms
            WHERE {where}
            ORDER BY annual_turnover DESC, name ASC
            LIMIT 100
        """
        cur.execute(sql, values)
        rows = cur.fetchall()

        cur.execute("SELECT COUNT(*), COALESCE(SUM(annual_turnover), 0), COUNT(DISTINCT state) FROM msme_firms")
        stat_row = cur.fetchone()
        total_firms = stat_row[0] if stat_row else 0
        total_turnover = round(float(stat_row[1]), 1) if stat_row and stat_row[1] else 0.0
        states_count = stat_row[2] if stat_row else 0

        cur.execute("SELECT COUNT(*) FROM msme_firms WHERE annual_turnover < 5.0 OR annual_turnover IS NULL")
        micro_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM msme_firms WHERE annual_turnover >= 5.0 AND annual_turnover < 50.0")
        small_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM msme_firms WHERE annual_turnover >= 50.0")
        medium_count = cur.fetchone()[0]

        cur.execute("SELECT DISTINCT sector_name FROM msme_firms WHERE sector_name IS NOT NULL AND sector_name != '' ORDER BY sector_name ASC")
        sectors = [r[0] for r in cur.fetchall()]

        cur.execute("SELECT DISTINCT state FROM msme_firms WHERE state IS NOT NULL AND state != '' ORDER BY state ASC")
        states = [r[0] for r in cur.fetchall()]
    finally:
        try:
            cur.close()
        except Exception as e:
            logger.debug(f"Cursor close notice in msme_directory_page: {e}")
        try:
            conn.close()
        except Exception as e:
            logger.debug(f"Connection close notice in msme_directory_page: {e}")

    firms = []
    for r in rows:
        turnover = float(r[5]) if r[5] is not None else None
        firms.append({
            "uin": r[0],
            "name": r[1],
            "sector": r[2],
            "city": r[3],
            "state": r[4],
            "annual_turnover": turnover,
            "employee_count": int(r[6]) if r[6] is not None else None,
            "registration_date": r[7],
            "source": r[8],
            "tier": classify_msme_tier(turnover)
        })

    return templates.TemplateResponse(
        request=request,
        name="msme_directory.html",
        context={
            "active_page": "msme",
            "firms": firms,
            "total_firms": total_firms,
            "total_turnover": total_turnover,
            "states_count": states_count,
            "micro_count": micro_count,
            "small_count": small_count,
            "medium_count": medium_count,
            "sectors": sectors,
            "states": states,
            "current_sector": sector,
            "current_state": state,
            "current_tier": tier,
            "current_q": q or ""
        }
    )


@app.get("/msme/{uin}", response_class=HTMLResponse)
def msme_dossier_page(request: Request, uin: str):
    """4-Pillar Report for an Unlisted MSME / Emerging SME."""
    init_db()
    from core.msme.router import get_msme_detail
    dossier = get_msme_detail(uin)
    if not dossier:
        raise HTTPException(status_code=404, detail=f"MSME enterprise with UIN '{uin}' not found")

    return templates.TemplateResponse(
        request=request,
        name="msme_dossier.html",
        context={
            "request": request,
            "active_page": "msme",
            "dossier": dossier
        }
    )


@app.get("/reits", response_class=HTMLResponse)
def reits_page(request: Request, structure: Optional[str] = Query(None)):
    """SEBI SM REITs, Mainboard REITs, InvITs & SGB Secondary Parity directory."""
    from core.analysis.sm_reit_invit_engine import audit_reit_portfolio
    from core.analysis.sgb_engine import evaluate_sgb_market
    init_db()
    reit_audit = audit_reit_portfolio(structure_type=structure)
    sgb_audit = evaluate_sgb_market()
    return templates.TemplateResponse(
        request=request,
        name="reit_directory.html",
        context={
            "active_page": "reits",
            "current_structure": structure,
            "reit_audit": reit_audit,
            "sgb_audit": sgb_audit
        }
    )


@app.get("/reits/{symbol}", response_class=HTMLResponse)
def reit_dossier_page(request: Request, symbol: str):
    """REIT & InvIT Dossier with Sec 115UA tax waterfall and NDCF payout purity."""
    from core.analysis.sm_reit_invit_engine import get_reit_detail
    init_db()
    clean_sym = symbol.strip().upper()
    detail = get_reit_detail(clean_sym)
    if not detail:
        raise HTTPException(status_code=404, detail=f"REIT/InvIT '{clean_sym}' not found in master registry.")

    canonical_sym = detail["reit"]["symbol"]
    is_deep_dive_unlocked = _asset_unlocked_for_request(request, "REIT", canonical_sym)

    from core.analysis.epistemic_schema import build_multi_asset_epistemic_ledger
    reit_obj = detail.get("reit") or {}
    port_obj = detail.get("portfolio_audit") or {}
    wf_obj = detail.get("tax_waterfall") or {}
    slabs = wf_obj.get("slabs") or []
    std_slab = next((s for s in slabs if abs(float(s.get("slab_rate_pct", 0)) - 30.0) < 0.5), slabs[0] if slabs else {})
    epistemic_ledger = build_multi_asset_epistemic_ledger(
        asset_class="REIT",
        entity_id=canonical_sym,
        context={
            "name": reit_obj.get("name") or canonical_sym,
            "ndcf_distribution": reit_obj.get("annual_dpu_inr") or reit_obj.get("distribution_yield_pct") or "N/A",
            "wale": port_obj.get("wale_years") or reit_obj.get("wale_years") or "N/A",
            "ltv_pct": (port_obj.get("capital_structure") or {}).get("ltv_ratio_pct") or reit_obj.get("ltv_ratio_pct") or "N/A",
            "post_tax_yield": std_slab.get("net_post_tax_yield_pct", "N/A"),
        },
        formatted_date=str(reit_obj.get("last_updated") or "Latest Filing")[:10],
    )

    return templates.TemplateResponse(
        request=request,
        name="reit_dossier.html",
        context={
            "active_page": "reits",
            "symbol": canonical_sym,
            "data": detail,
            "reit": detail["reit"],
            "tax_waterfall": detail["tax_waterfall"],
            "ndcf_audit": detail["ndcf_audit"],
            "portfolio_audit": detail["portfolio_audit"],
            "countercase_risks": detail["countercase_risks"],
            "peers": detail["peers"],
            "forensic_notes": detail["forensic_notes"],
            "is_deep_dive_unlocked": is_deep_dive_unlocked,
            "epistemic_ledger": epistemic_ledger,
        }
    )


@app.get("/opportunities", response_class=HTMLResponse)
def opportunities_terminal_page(request: Request, persona: Optional[str] = Query(None)):
    """Cross-Asset Opportunity Terminal & Arbitrage Scanner."""
    from core.analysis.opportunity_terminal import get_normalized_opportunity_universe, BENCHMARK_10Y_GSEC_YIELD
    init_db()
    universe = get_normalized_opportunity_universe(persona_filter=persona)

    sgb_yields = [x["gross_yield_pct"] for x in universe if x.get("asset_class") == "SGB"]
    peak_sgb = max(sgb_yields) if sgb_yields else 8.85
    real_asset_yields = [x["gross_yield_pct"] for x in universe if x.get("seniority_tier") == "REAL_ASSET"]
    peak_real_asset = max(real_asset_yields) if real_asset_yields else 10.20

    summary = {
        "total_items": len(universe),
        "benchmark_yield": BENCHMARK_10Y_GSEC_YIELD,
        "peak_sgb_yield": peak_sgb,
        "peak_real_asset_yield": peak_real_asset
    }

    return templates.TemplateResponse(
        request=request,
        name="opportunity_terminal.html",
        context={
            "active_page": "opportunities",
            "current_persona": persona,
            "summary": summary
        }
    )


@app.get("/safety-radar", response_class=HTMLResponse)
def safety_radar_page(request: Request, category: Optional[str] = Query(None)):
    """Retail Safety & Shadow-Banking Diagnostic Radar page."""
    from core.analysis.retail_safety_radar import audit_alternative_yield_radar
    init_db()
    radar_data = audit_alternative_yield_radar(category=category)
    return templates.TemplateResponse(
        request=request,
        name="safety_radar.html",
        context={
            "active_page": "safety_radar",
            "current_category": category,
            "data": radar_data
        }
    )


@app.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    """Terms and Conditions page."""
    return templates.TemplateResponse(
        request=request,
        name="policy.html",
        context={"policy": POLICIES["terms"], "active_page": "terms"}
    )


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    """Privacy Policy page."""
    return templates.TemplateResponse(
        request=request,
        name="policy.html",
        context={"policy": POLICIES["privacy"], "active_page": "privacy"}
    )


@app.get("/refund-policy", response_class=HTMLResponse)
async def refund_policy_page(request: Request):
    """Cancellation and Refund Policy page."""
    return templates.TemplateResponse(
        request=request,
        name="policy.html",
        context={"policy": POLICIES["refund-policy"], "active_page": "refund"}
    )


@app.get("/contact", response_class=HTMLResponse)
async def contact_page(
    request: Request,
    ticket_id: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
):
    """Interactive Support Desk, Complaints, and Two-Way Ticket Status Lookup page."""
    init_db()
    tracked_ticket = None
    lookup_error = None
    if ticket_id and email:
        from core.db import get_ticket_by_id
        clean_tid = ticket_id.strip().upper()
        clean_em = email.strip().lower()
        t_obj = get_ticket_by_id(clean_tid)
        if t_obj and str(t_obj.get("user_email", "")).strip().lower() == clean_em:
            tracked_ticket = t_obj
        else:
            lookup_error = f"No matching ticket found for ID '{clean_tid}' and email '{clean_em}'."

    return templates.TemplateResponse(
        request=request,
        name="contact.html",
        context={
            "active_page": "contact",
            "tracked_ticket": tracked_ticket,
            "lookup_error": lookup_error,
            "lookup_ticket_id": (ticket_id or "").strip().upper(),
            "lookup_email": (email or "").strip().lower(),
        }
    )


_CONTACT_RATE_BUCKETS: Dict[str, List[float]] = {}

_DISPOSABLE_EMAIL_DOMAINS = {
    "nolettersbox.com", "mailinator.com", "guerrillamail.com", "tempmail.com",
    "10minutemail.com", "yopmail.com", "trashmail.com", "sharklasers.com",
}


def _is_bot_gibberish_ticket(name: str, subject: str, message: str) -> bool:
    """Detects automated scanner payloads (e.g. NARTYTRYUT802262NERTHRRTH / MERTYHR802262MAVNGHJTH)."""
    # 1. Message or subject is a single unbroken 16+ char alphanumeric token with no spaces
    if (" " not in message and len(message) >= 16 and message.isalnum()) or (
        " " not in subject and len(subject) >= 16 and subject.isalnum()
    ):
        return True
    # 2. Shared 5+ digit correlation token injected across name, subject, and message
    import re as _re
    name_digits = set(_re.findall(r"\d{5,}", name))
    subj_digits = set(_re.findall(r"\d{5,}", subject))
    msg_digits = set(_re.findall(r"\d{5,}", message))
    if name_digits and (name_digits & subj_digits) and (name_digits & msg_digits):
        return True
    return False


@app.post("/contact", response_class=HTMLResponse)
async def submit_contact_ticket(
    request: Request,
    background_tasks: BackgroundTasks,
    user_email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
    user_name: Optional[str] = Form(""),
    category: Optional[str] = Form("general"),
    website_url: Optional[str] = Form(""),
):
    """Processes user complaint/support ticket, logs to audit ledger, and alerts admin."""
    import time as _time
    clean_email = str(user_email).strip().lower()[:160]
    clean_subj = str(subject).strip()[:250]
    clean_msg = str(message).strip()[:5000]
    clean_name = str(user_name or "").strip()[:100]
    clean_cat = str(category or "general").strip().lower()[:40]
    email_domain = clean_email.split("@")[-1] if "@" in clean_email else ""

    if not _validate_request_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")

    # Silent honeypot & bot-gibberish rejection
    if (
        str(website_url or "").strip()
        or email_domain in _DISPOSABLE_EMAIL_DOMAINS
        or _is_bot_gibberish_ticket(clean_name, clean_subj, clean_msg)
    ):
        logger.warning(
            f"Spam/bot ticket rejected on /contact: {clean_email} (domain='{email_domain}', honeypot='{str(website_url or '')[:50]}')"
        )
        return templates.TemplateResponse(
            request=request,
            name="contact.html",
            context={
                "active_page": "contact",
                "error_msg": "Please provide a valid email address and a clear, multi-word description of your inquiry.",
                "form_name": clean_name,
                "form_email": clean_email,
                "form_subj": clean_subj,
                "form_msg": clean_msg,
                "form_cat": clean_cat,
            },
            status_code=400,
        )

    if not clean_email or "@" not in clean_email or not clean_subj or not clean_msg:
        return templates.TemplateResponse(
            request=request,
            name="contact.html",
            context={
                "active_page": "contact",
                "error_msg": "Please provide a valid email address, subject, and detailed message.",
                "form_name": clean_name,
                "form_email": clean_email,
                "form_subj": clean_subj,
                "form_msg": clean_msg,
                "form_cat": clean_cat,
            }
        )

    if os.environ.get("TESTING") != "1":
        client_ip = _get_client_ip(request)
        rate_key = f"{client_ip}:{clean_email}"
        now_ts = _time.time()
        window_hits = [ts for ts in _CONTACT_RATE_BUCKETS.get(rate_key, []) if (now_ts - ts) < 600]
        if len(window_hits) >= 5:
            return templates.TemplateResponse(
                request=request,
                name="contact.html",
                context={
                    "active_page": "contact",
                    "error_msg": "Too many support requests submitted recently. Please wait a few minutes before submitting another ticket.",
                    "form_name": clean_name,
                    "form_email": clean_email,
                    "form_subj": clean_subj,
                    "form_msg": clean_msg,
                    "form_cat": clean_cat,
                },
                status_code=429,
            )
        window_hits.append(now_ts)
        _CONTACT_RATE_BUCKETS[rate_key] = window_hits

    res = create_support_ticket(
        user_email=clean_email,
        subject=clean_subj,
        message=clean_msg,
        user_name=clean_name,
        category=clean_cat,
        source="web_contact_form"
    )

    if not res.get("success"):
        return templates.TemplateResponse(
            request=request,
            name="contact.html",
            context={
                "active_page": "contact",
                "error_msg": f"Failed to submit ticket: {res.get('error', 'Database error')}",
                "form_name": clean_name,
                "form_email": clean_email,
                "form_subj": clean_subj,
                "form_msg": clean_msg,
                "form_cat": clean_cat,
            }
        )

    background_tasks.add_task(dispatch_support_ticket_alert, res)

    from core.db.telemetry import record_usage_event
    record_usage_event(
        event_type="SUPPORT_TICKET_SUBMITTED",
        details={"ticket_id": res.get("ticket_id"), "category": clean_cat, "email": clean_email}
    )

    return templates.TemplateResponse(
        request=request,
        name="contact.html",
        context={
            "active_page": "contact",
            "success_ticket": res,
        }
    )


@app.post("/contact/reply", response_class=HTMLResponse)
async def user_reply_to_support_ticket(
    request: Request,
    ticket_id: str = Form(...),
    user_email: str = Form(...),
    reply_message: str = Form(...),
):
    """Allows a user to post a follow-up reply directly onto their support ticket thread."""
    if not _validate_request_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")
    init_db()
    from core.db import get_ticket_by_id, add_ticket_response, update_ticket_status
    clean_tid = str(ticket_id or "").strip().upper()[:40]
    clean_em = str(user_email or "").strip().lower()[:160]
    clean_msg = str(reply_message or "").strip()[:5000]

    t_obj = get_ticket_by_id(clean_tid)
    if not t_obj or str(t_obj.get("user_email", "")).strip().lower() != clean_em:
        return templates.TemplateResponse(
            request=request,
            name="contact.html",
            context={
                "active_page": "contact",
                "lookup_error": "Could not verify ticket ownership. Please check your Ticket ID and Email.",
                "lookup_ticket_id": clean_tid,
                "lookup_email": clean_em,
            }
        )

    if clean_msg:
        add_ticket_response(
            ticket_id=clean_tid,
            responder_email=clean_em,
            responder_role="user",
            message=clean_msg,
            email_sent=False
        )
        if str(t_obj.get("status", "")).upper() in ("RESOLVED", "CLOSED"):
            update_ticket_status(clean_tid, "IN_PROGRESS", "Re-opened by user follow-up reply on /contact.")

    updated_ticket = get_ticket_by_id(clean_tid)
    return templates.TemplateResponse(
        request=request,
        name="contact.html",
        context={
            "active_page": "contact",
            "tracked_ticket": updated_ticket,
            "lookup_ticket_id": clean_tid,
            "lookup_email": clean_em,
        }
    )


@app.get("/shipping-policy", response_class=HTMLResponse)
async def shipping_policy_page(request: Request):
    """Shipping & Instant Digital Delivery Policy page."""
    return templates.TemplateResponse(
        request=request,
        name="policy.html",
        context={"policy": POLICIES["shipping-policy"], "active_page": "shipping"}
    )


@app.get("/disclaimer", response_class=HTMLResponse)
async def disclaimer_page(request: Request):
    """Mandatory SEBI Safe-Harbor Disclaimer page."""
    return templates.TemplateResponse(
        request=request,
        name="policy.html",
        context={"policy": POLICIES["disclaimer"], "active_page": "disclaimer"}
    )


@app.get("/health")
@app.get("/healthz")
async def healthz():
    """Health check endpoint with caching (short‑lived)."""
    data = {"status": "healthy", "service": "Moatnomics Web Server", "timestamp": datetime.now(IST).isoformat()}
    return json_response_with_cache(data, max_age=30)


@app.get("/sitemap.xml", response_class=Response)
async def sitemap_xml():
    """Generates automated XML sitemap for Google/Perplexity/Bing search crawlers."""
    archives = get_archived_reports_sync()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    base_url = (os.environ.get("CANONICAL_DOMAIN") or "https://moatnomics.com").rstrip("/")
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f'  <url><loc>{base_url}/</loc><lastmod>{now_iso}</lastmod><changefreq>hourly</changefreq><priority>1.0</priority></url>',
        f'  <url><loc>{base_url}/discovery</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>',
        f'  <url><loc>{base_url}/opportunities</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>',
        f'  <url><loc>{base_url}/search</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>',
        f'  <url><loc>{base_url}/equities</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>',
        f'  <url><loc>{base_url}/compare</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/debt</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/funds</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/sovereign</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/etfs</loc><lastmod>{now_iso}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/calculator/tax</loc><lastmod>{now_iso}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/reits</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/safety-radar</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/msme</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/pricing</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base_url}/terms</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
        f'  <url><loc>{base_url}/privacy</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
        f'  <url><loc>{base_url}/refund-policy</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
        f'  <url><loc>{base_url}/contact</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
        f'  <url><loc>{base_url}/shipping-policy</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
        f'  <url><loc>{base_url}/disclaimer</loc><lastmod>{now_iso}</lastmod><priority>0.5</priority></url>',
    ]

    for a in archives:
        t = a.get("ticker")
        if t:
            raw_ts = a.get("raw_timestamp")
            if raw_ts:
                try:
                    if isinstance(raw_ts, str):
                        dt = datetime.fromisoformat(raw_ts.replace('Z', '+00:00'))
                    else:
                        dt = raw_ts
                    lastmod_date = dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
                except Exception as e:
                    logger.debug("Failed parsing raw_ts for sitemap: %s", e)
                    lastmod_date = now_iso
            else:
                lastmod_date = now_iso
            xml_lines.append(
                f'  <url><loc>{base_url}/dossier/{t}</loc><lastmod>{lastmod_date}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>'
            )

    try:
        from core.db.sovereign import get_etf_matrix
        top_etfs = get_etf_matrix(limit=30)
        for etf in top_etfs:
            sym = etf.get("symbol")
            if sym:
                xml_lines.append(
                    f'  <url><loc>{base_url}/etfs/{sym}</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>'
                )
    except Exception as etf_sitemap_err:
        logger.debug(f"Sitemap ETF append notice: {etf_sitemap_err}")

    try:
        from core.db.reits import get_all_reits_and_invits
        all_reits = get_all_reits_and_invits()
        for r in all_reits:
            sym = r.get("symbol")
            if sym:
                xml_lines.append(
                    f'  <url><loc>{base_url}/reits/{sym}</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>'
                )
    except Exception as reit_sitemap_err:
        logger.debug(f"Sitemap REIT append notice: {reit_sitemap_err}")

    try:
        from core.db.debt import get_active_debt_securities
        all_debt = get_active_debt_securities(limit=150)
        for d in all_debt:
            isin_val = d.get("isin")
            if isin_val:
                xml_lines.append(
                    f'  <url><loc>{base_url}/debt/{isin_val}</loc><lastmod>{now_iso}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>'
                )
    except Exception as debt_sitemap_err:
        logger.debug(f"Sitemap Debt append notice: {debt_sitemap_err}")

    try:
        from core.msme.seed import get_active_msme_firms_count
        from core.db.connection import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT uin FROM msme_firms LIMIT 100")
            for (m_uin,) in cur.fetchall():
                xml_lines.append(
                    f'  <url><loc>{base_url}/msme/{m_uin}</loc><lastmod>{now_iso}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>'
                )
        finally:
            try:
                cur.close()
            except Exception as e:
                logger.debug(f"Cursor close notice in sitemap_xml: {e}")
            try:
                conn.close()
            except Exception as e:
                logger.debug(f"Connection close notice in sitemap_xml: {e}")
    except Exception as msme_sitemap_err:
        logger.debug(f"Sitemap MSME append notice: {msme_sitemap_err}")

    xml_lines.append('</urlset>')
    return Response(content="\n".join(xml_lines), media_type="application/xml")


@app.get("/robots.txt", response_class=Response)
async def robots_txt():
    """Provides search engine crawler directives and XML sitemap index pointer."""
    base_url = (os.environ.get("CANONICAL_DOMAIN") or "https://moatnomics.com").rstrip("/")
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /admin\n\n"
        f"Sitemap: {base_url}/sitemap.xml\n"
    )
    return Response(content=content, media_type="text/plain")


@app.get("/.well-known/security.txt", response_class=Response)
@app.get("/security.txt", response_class=Response)
async def security_txt():
    """RFC 9116 Vulnerability Disclosure Policy pointing strictly to the on-site support desk."""
    base_url = (os.environ.get("CANONICAL_DOMAIN") or "https://moatnomics.com").rstrip("/")
    expires_iso = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%dT00:00:00.000Z")
    content = (
        f"Contact: {base_url}/contact\n"
        f"Expires: {expires_iso}\n"
        "Preferred-Languages: en\n"
        f"Canonical: {base_url}/.well-known/security.txt\n"
        f"Policy: {base_url}/terms\n"
    )
    return Response(content=content, media_type="text/plain; charset=utf-8")
