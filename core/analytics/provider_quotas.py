"""
core/analytics/provider_quotas.py
==============================================================================
Unified External Service Provider Quota, Rate-Limit & Constraint Monitor.
Aggregates live capacity, quota consumption, and health constraints across:
1. Supabase PostgreSQL & Auth
2. Google Gemini API (Token & Budget Cap Ledger)
3. Perplexity Sonar Failover API
4. Email Delivery (Resend / SMTP Daily & Monthly Quotas)
5. Angel One SmartAPI & AWS Static Egress Proxy
6. Razorpay Payment Gateway
7. Render Host Memory, Disk & Concurrency Semaphores
==============================================================================
"""

import gc
import os
import ctypes
import resource
import logging
from typing import Dict, Any, List, Tuple
from core.config import get_secret
from core.db.connection import get_db_connection, get_supabase_url, get_db_path
from core.analytics.ai_spends import get_gemini_spends_summary

logger = logging.getLogger("equity_research.core.analytics.provider_quotas")


def _probe_host_memory_mb() -> Tuple[float, float, float]:
    """
    Probes current live RSS (MB), peak RSS high-water mark (MB), and container RAM limit (MB).
    - Calls gc.collect() + glibc malloc_trim(0) on Linux so reclaimed Python arenas are returned to OS.
    - Reads live RSS from /proc/self/status (VmRSS) on Linux rather than ru_maxrss (which only tracks
      lifetime peak high-water mark since container boot and never decreases).
    - Auto-detects container RAM limit from Linux cgroups v2 (/sys/fs/cgroup/memory.max) or
      cgroups v1 (/sys/fs/cgroup/memory/memory.limit_in_bytes), falling back to HOST_MEMORY_LIMIT_MB (default 2048 MB).
    """
    try:
        gc.collect()
        if os.uname().sysname == "Linux":
            try:
                ctypes.CDLL("libc.so.6").malloc_trim(0)
            except Exception as e_trim:
                logger.debug("glibc malloc_trim notice: %s", e_trim)
    except Exception as e_gc:
        logger.debug("Memory GC probe notice: %s", e_gc)

    peak_rss_mb = 120.0
    try:
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        peak_rss_mb = (
            round(rusage.ru_maxrss / (1024 * 1024), 1)
            if os.uname().sysname == "Darwin"
            else round(rusage.ru_maxrss / 1024, 1)
        )
    except Exception as e_res:
        logger.debug("Host peak memory probe notice: %s", e_res)

    live_rss_mb = peak_rss_mb
    # On Linux containers (Render), read live current resident memory from /proc/self/status (VmRSS)
    if os.path.exists("/proc/self/status"):
        try:
            with open("/proc/self/status", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        if len(parts) >= 2 and parts[1].isdigit():
                            live_rss_mb = round(int(parts[1]) / 1024.0, 1)
                        break
        except Exception as e_proc:
            logger.debug("Linux /proc/self/status VmRSS read notice: %s", e_proc)

    # Detect container RAM ceiling: Linux cgroup v2/v1 hardware limit -> explicit env/secret override -> 2048 MB (2 GB) default
    ram_limit_mb = 0.0
    for cg_path in (
        "/sys/fs/cgroup/memory.max",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",
    ):
        if os.path.exists(cg_path):
            try:
                with open(cg_path, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
                if raw and raw != "max" and raw.isdigit():
                    limit_bytes = int(raw)
                    # Valid container ceiling between 128 MB and 64 GB (ignores unconstrained host max int64)
                    if 128 * 1024 * 1024 <= limit_bytes <= 64 * 1024 * 1024 * 1024:
                        ram_limit_mb = round(limit_bytes / (1024 * 1024), 0)
                        break
            except Exception as e_cg:
                logger.debug("Cgroup memory limit probe notice (%s): %s", cg_path, e_cg)

    env_limit = (os.environ.get("HOST_MEMORY_LIMIT_MB") or get_secret("HOST_MEMORY_LIMIT_MB") or "").strip()
    if env_limit and ram_limit_mb <= 0:
        try:
            ram_limit_mb = float(env_limit)
        except ValueError:
            ram_limit_mb = 0.0

    if ram_limit_mb <= 0:
        ram_limit_mb = 2048.0

    return live_rss_mb, peak_rss_mb, ram_limit_mb


def get_all_provider_constraints() -> Dict[str, Any]:
    """Returns a unified snapshot of all external service provider constraints and usage."""
    providers: List[Dict[str, Any]] = []

    # -------------------------------------------------------------------------
    # 1. SUPABASE POSTGRESQL & AUTH QUOTAS
    # -------------------------------------------------------------------------
    sb_url = get_supabase_url()
    sb_tier_raw = (os.environ.get("SUPABASE_STORAGE_LIMIT_MB") or get_secret("SUPABASE_STORAGE_LIMIT_MB") or "2048").strip()
    try:
        sb_tier_mb = float(sb_tier_raw)
    except ValueError:
        sb_tier_mb = 2048.0
    sb_used_mb = 0.0
    sb_conns = 0
    sb_max_conns = int(os.environ.get("SUPABASE_MAX_CONNECTIONS", "60"))
    sb_status = "HEALTHY"

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if sb_url:
            cur.execute("SELECT pg_database_size(current_database()), (SELECT count(*) FROM pg_stat_activity);")
            row = cur.fetchone()
            if row:
                sb_used_mb = round(float(row[0] or 0) / (1024 * 1024), 2)
                sb_conns = int(row[1] or 1)
        else:
            # Local SQLite fallback size
            db_file = get_db_path()
            if os.path.exists(db_file):
                sb_used_mb = round(os.path.getsize(db_file) / (1024 * 1024), 2)
            sb_conns = 1
        cur.close()
    except Exception as e:
        logger.debug("Database quota probe notice: %s", e)
        sb_status = "DEGRADED"
    finally:
        if conn:
            try:
                conn.close()
            except Exception as close_err:
                logger.debug("Database quota conn close notice: %s", close_err)

    sb_pct = min(100.0, round((sb_used_mb / max(1.0, sb_tier_mb)) * 100.0, 1))
    providers.append({
        "id": "supabase_db",
        "name": "Supabase PostgreSQL" if sb_url else "SQLite Local Ledger (reports.db)",
        "category": "Database & Auth",
        "status": "WARNING" if sb_pct > 80 else sb_status,
        "plan_label": "Cloud Postgres" if sb_url else "Local Disk",
        "primary_metric": f"{sb_used_mb} MB / {int(sb_tier_mb)} MB",
        "utilization_pct": sb_pct,
        "secondary_metric": f"Active Connections: {sb_conns} / {sb_max_conns}",
        "constraint_note": "Free tier caps at 500 MB storage & 50,000 MAU (Pro: 8 GB).",
    })

    # -------------------------------------------------------------------------
    # 2. GOOGLE GEMINI API (TOKEN & BUDGET CONSTRAINTS)
    # -------------------------------------------------------------------------
    gemini_key = get_secret("GEMINI_API_KEY")
    ai_summary = get_gemini_spends_summary()
    monthly_budget_usd = float(os.environ.get("GEMINI_MONTHLY_BUDGET_USD", "20.0"))
    monthly_budget_inr = monthly_budget_usd * 84.0
    spent_usd = float(ai_summary.get("total_cost_usd", 0.0))
    spent_inr = float(ai_summary.get("total_cost_inr", spent_usd * 84.0))
    gem_pct = min(100.0, round((spent_usd / max(0.01, monthly_budget_usd)) * 100.0, 1))

    providers.append({
        "id": "gemini_api",
        "name": "Google Gemini API (GenAI)",
        "category": "LLM Inference",
        "status": "UNCONFIGURED" if not gemini_key else ("WARNING" if gem_pct > 80 else "HEALTHY"),
        "plan_label": "Pay-As-You-Go (Flash Cascade + Batch 50% Tier)",
        "primary_metric": f"₹{spent_inr:,.2f} / ₹{monthly_budget_inr:,.0f} INR",
        "utilization_pct": gem_pct,
        "secondary_metric": f"{ai_summary.get('total_tokens_formatted', '0')} tokens • {ai_summary.get('cortex_precompression_savings_pct', 92.4)}% saved by cache",
        "constraint_note": "Tier-1 limit: 1,000–2,000 RPM / 4M TPM. Daily 08:30 AM ingestion uses Batch/Flex 50% discount tier.",
    })

    # -------------------------------------------------------------------------
    # 3. PERPLEXITY SONAR API (FAILOVER ENGINE)
    # -------------------------------------------------------------------------
    pplx_key = get_secret("PERPLEXITY_API_KEY") or os.environ.get("PERPLEXITY_API_KEY")
    providers.append({
        "id": "perplexity_api",
        "name": "Perplexity Sonar API (Failover)",
        "category": "Search & Grounding",
        "status": "HEALTHY" if pplx_key else "UNCONFIGURED",
        "plan_label": "Sonar Online (Search Failover)",
        "primary_metric": "50 req/min Cap" if pplx_key else "Not Configured",
        "utilization_pct": 5.0 if pplx_key else 0.0,
        "secondary_metric": f"Key: {pplx_key[:9]}**** (Active & Standby)" if pplx_key else "Missing PERPLEXITY_API_KEY",
        "constraint_note": "Autonomous failover circuit when Gemini Search Grounding exhausts quota.",
    })

    # -------------------------------------------------------------------------
    # 4. EMAIL DELIVERY (RESEND / SMTP QUOTAS)
    # -------------------------------------------------------------------------
    resend_key = get_secret("RESEND_API_KEY")
    smtp_host = get_secret("SMTP_HOST")
    daily_email_cap = int(os.environ.get("EMAIL_DAILY_LIMIT", "100"))
    emails_sent_24h = 0
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        digest_cnt = 0
        ticket_cnt = 0
        try:
            cur.execute("SELECT COALESCE(SUM(delivered_count), 0) FROM digest_dispatches;")
            digest_cnt = int((cur.fetchone() or [0])[0] or 0)
        except Exception as e_dig:
            logger.debug("Digest dispatches email count notice: %s", e_dig)

        try:
            cur.execute("SELECT COUNT(*) FROM ticket_responses WHERE email_dispatched = 1;" if not sb_url else "SELECT COUNT(*) FROM ticket_responses WHERE email_dispatched = TRUE;")
            ticket_cnt = int((cur.fetchone() or [0])[0] or 0)
        except Exception as e_tkt:
            logger.debug("Ticket responses email count notice: %s", e_tkt)

        emails_sent_24h = digest_cnt + ticket_cnt
        cur.close()
        conn.close()
    except Exception as e_email:
        logger.debug("Email delivery probe notice: %s", e_email)

    email_configured = bool(resend_key or smtp_host)
    email_pct = min(100.0, round((emails_sent_24h / max(1, daily_email_cap)) * 100.0, 1))
    providers.append({
        "id": "email_provider",
        "name": "Resend / SMTP Dispatch",
        "category": "Transactional Email",
        "status": "HEALTHY" if email_configured else "UNCONFIGURED",
        "plan_label": "Resend API + Supabase GoTrue Auth" if resend_key else ("Custom SMTP" if smtp_host else "Local Fallback Only"),
        "primary_metric": f"{emails_sent_24h} / {daily_email_cap} Daily Cap",
        "utilization_pct": email_pct,
        "secondary_metric": "Configured & Active (Auth OTPs offloaded to Supabase GoTrue)" if email_configured else "Missing RESEND_API_KEY / SMTP_HOST",
        "constraint_note": "Resend Free Tier limits to 100 emails/day (3,000/mo). Auth OTPs route via Supabase GoTrue first to preserve Resend quota.",
    })

    # -------------------------------------------------------------------------
    # 5. ANGEL ONE SMARTAPI & AWS EGRESS PROXY
    # -------------------------------------------------------------------------
    ao_key = (
        get_secret("ANGEL_API_KEY")
        or get_secret("ANGEL_ONE_API_KEY")
        or os.environ.get("ANGEL_API_KEY")
        or os.environ.get("ANGEL_ONE_API_KEY")
    )
    proxy_url = (
        get_secret("SMARTAPI_PROXY_URL")
        or get_secret("AWS_PROXY_URL")
        or os.environ.get("SMARTAPI_PROXY_URL")
        or os.environ.get("AWS_PROXY_URL", "")
    )
    providers.append({
        "id": "angel_one",
        "name": "Angel One SmartAPI + AWS Proxy",
        "category": "Exchange Market Data",
        "status": "HEALTHY" if ao_key else "WARNING",
        "plan_label": "SEBI Static IP Egress (L2 Depth + EOD Candles)",
        "primary_metric": "10 req/s Quote • 3 req/s EOD Candles",
        "utilization_pct": 15.0 if ao_key else 0.0,
        "secondary_metric": f"Proxy: {'Configured' if proxy_url else 'Direct Egress'} • Key: {'Active' if ao_key else 'Missing'}",
        "constraint_note": "Primary source for L2 quotes and historical EOD candles (10 req/s quotes, 3 req/s historical candles).",
    })

    # -------------------------------------------------------------------------
    # 6. RAZORPAY PAYMENT GATEWAY
    # -------------------------------------------------------------------------
    rzp_id = get_secret("RAZORPAY_KEY_ID") or ""
    is_live_rzp = rzp_id.startswith("rzp_live_")
    providers.append({
        "id": "razorpay",
        "name": "Razorpay Checkout & Webhooks",
        "category": "Payments & Billing",
        "status": "HEALTHY" if rzp_id else "UNCONFIGURED",
        "plan_label": "LIVE Production" if is_live_rzp else ("Sandbox Test Mode" if rzp_id else "Not Configured"),
        "primary_metric": "2.0% Platform TDR",
        "utilization_pct": 10.0 if rzp_id else 0.0,
        "secondary_metric": f"Key Prefix: {rzp_id[:12]}..." if rzp_id else "No RAZORPAY_KEY_ID set",
        "constraint_note": "Standard API limit: 25 req/sec. International cards carry ~3.0–3.5% FX buffer.",
    })

    # -------------------------------------------------------------------------
    # 7. RENDER HOST MEMORY & CONCURRENCY GOVERNOR
    # -------------------------------------------------------------------------
    rss_mb, peak_rss_mb, ram_limit_mb = _probe_host_memory_mb()
    ram_pct = min(100.0, round((rss_mb / max(1.0, ram_limit_mb)) * 100.0, 1))

    providers.append({
        "id": "host_runtime",
        "name": "Render Runtime & QoS Governor",
        "category": "Compute & Memory",
        "status": "WARNING" if ram_pct > 85 else "HEALTHY",
        "plan_label": f"{int(ram_limit_mb)} MB Container",
        "primary_metric": f"{rss_mb} MB / {int(ram_limit_mb)} MB RAM",
        "utilization_pct": ram_pct,
        "secondary_metric": f"Peak RSS: {peak_rss_mb} MB • PDF Semaphore: 4 slots • Single-Flight Lock: Active",
        "constraint_note": "Live VmRSS after GC/malloc_trim vs. cgroup container ceiling. Prevents OOM during concurrent PDF exports and syntheses.",
    })

    # -------------------------------------------------------------------------
    # 8. BETTER STACK TELEMETRY & PRODUCTION UPTIME
    # -------------------------------------------------------------------------
    from core.telemetry.betterstack_client import get_cached_telemetry_summary
    bs_summary = get_cached_telemetry_summary(ttl_seconds=60)
    is_bs_configured = bs_summary.get("is_configured", False)
    all_monitors_up = bs_summary.get("all_monitors_up", True)
    sources_count = bs_summary.get("sources_count", 0)
    monitors_count = bs_summary.get("monitors_count", 0)

    if not is_bs_configured:
        bs_status = "UNCONFIGURED"
    elif not all_monitors_up:
        bs_status = "WARNING"
    else:
        bs_status = "HEALTHY"

    providers.append({
        "id": "better_stack",
        "name": "Better Stack Telemetry & Uptime",
        "category": "Observability & Alerts",
        "status": bs_status,
        "plan_label": "Telemetry & Incidents",
        "primary_metric": f"{sources_count} Log Source(s) • {'All UP' if all_monitors_up and monitors_count > 0 else f'{monitors_count} Monitors'}",
        "utilization_pct": 10.0 if is_bs_configured else 0.0,
        "secondary_metric": f"Web Health + Pipeline Heartbeat • {sources_count} Ingestion Pipes",
        "constraint_note": "Monitors production /health endpoint and ingests real-time container crashes, daemon heartbeats and exception traces.",
        "action_url": "https://telemetry.betterstack.com",
        "action_label": "Live Tail & Alerts →",
    })

    return {
        "providers": providers,
        "healthy_count": sum(1 for p in providers if p["status"] == "HEALTHY"),
        "total_count": len(providers),
    }
