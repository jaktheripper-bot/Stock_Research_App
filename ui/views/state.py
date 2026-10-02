"""Session state management, deep linking synchronization, and research execution pipeline."""

import re
import json
import logging
import platform
import traceback
from datetime import datetime
import streamlit as st

from core.db import (
    IST,
    get_report_by_ticker,
    record_usage_event,
)
from core.analysis import (
    get_stock_fundamentals,
    evaluate_material_change,
    get_historical_prices,
)
from bse_master import get_ticker_suggestions
from telemetry import track_user_action

logger = logging.getLogger("equity_research.ui.views.state")

def sanitize_ticker_input(q: str) -> str:
    """Sanitizes ticker queries by stripping non-alphanumeric characters except dots and hyphens."""
    return re.sub(r"[^\w\s\.-]", "", q or "").strip()[:40]

def set_active_dossier_state(
    ticker: str,
    report_text: str = None,
    report_date: str = None,
    fundamentals: dict = None,
    material_reason: str = "📂 Loaded from Archived Research Dossier",
    is_regenerated: bool = False,
    viewing_snapshot: dict = None,
    custom_diff: dict = None,
    history_df=None
):
    """Atomically synchronizes all report, chart, and surveillance session state for a given ticker."""
    clean_t = (ticker or "").strip().upper()
    st.session_state["last_ticker"] = clean_t
    st.session_state["last_report"] = report_text
    st.session_state["last_report_date"] = report_date
    st.session_state["last_fundamentals"] = fundamentals or {}
    st.session_state["material_reason"] = material_reason
    st.session_state["is_regenerated"] = is_regenerated
    st.session_state["cached_pdf_bytes"] = None
    st.session_state["pdf_cache_id"] = None
    st.session_state["sb_archive_sync_ticker"] = clean_t

    if history_df is not None:
        st.session_state["last_history"] = history_df
        st.session_state["last_history_ticker"] = clean_t
    else:
        st.session_state["last_history"] = None
        st.session_state["last_history_ticker"] = None

    if viewing_snapshot:
        st.session_state["viewing_snapshot"] = viewing_snapshot
    else:
        st.session_state.pop("viewing_snapshot", None)

    if custom_diff:
        st.session_state["custom_diff"] = custom_diff
    else:
        st.session_state.pop("custom_diff", None)

    if st.session_state.get("pending_price_delta") and st.session_state["pending_price_delta"].get("ticker") != clean_t:
        st.session_state.pop("pending_price_delta", None)

    # Sync URL query parameters for deep-linking and browser reload persistence
    try:
        if clean_t:
            st.query_params["ticker"] = clean_t
        else:
            st.query_params.pop("ticker", None)
    except Exception:
        pass

    # Institutional UX: Track recently researched stocks for quick 1-click lookup
    if clean_t:
        existing_recents = st.session_state.get("recent_searches", [])
        updated = [t for t in existing_recents if t != clean_t]
        updated.insert(0, clean_t)
        st.session_state["recent_searches"] = updated[:6]

def restore_dossier_from_url():
    """Silently restores dossier from archive if ticker is present in URL query parameters on reload."""
    if not st.session_state.get("last_report") and "ticker" in st.query_params:
        try:
            init_url_ticker = sanitize_ticker_input(st.query_params.get("ticker", "")).upper()
            if init_url_ticker:
                c_init = get_report_by_ticker(init_url_ticker)
                if c_init and c_init.get("report_text"):
                    c_fund = {
                        "ticker": c_init.get("ticker", init_url_ticker),
                        "short_name": c_init.get("short_name", init_url_ticker),
                        "current_price": str(c_init.get("baseline_price") or "N/A"),
                        "pe_ratio": str(c_init.get("baseline_pe") or "N/A"),
                        "market_cap": c_init.get("baseline_mcap") or 0,
                        "is_fallback": False
                    }
                    set_active_dossier_state(
                        ticker=init_url_ticker,
                        report_text=c_init["report_text"],
                        report_date=c_init.get("formatted_date"),
                        fundamentals=c_fund,
                        material_reason=f"Archived Snapshot ({c_init.get('formatted_date', 'Prior Date')})",
                        is_regenerated=False,
                        history_df=get_historical_prices(init_url_ticker)
                    )
        except Exception:
            pass

def execute_stock_research(query: str, selected_language: str = "English (India)", force_refresh: bool = False):
    """Executes the 5-phase data ingestion, validation, delta-gating, and synthesis pipeline for a stock query."""
    st.session_state.pop("viewing_snapshot", None)
    st.session_state.pop("custom_diff", None)
    st.session_state.pop("pending_price_delta", None)
    clean_query = sanitize_ticker_input(query)
    if not clean_query or len(clean_query) < 2:
        st.error("Please enter a valid company name or stock ticker (minimum 2 characters).")
        return
    try:
        stock_data = get_stock_fundamentals(clean_query)
        resolved_ticker = stock_data.get("ticker", clean_query)
        scrip = stock_data.get("scrip_code", "")
        record_usage_event("SEARCH", resolved_ticker)

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_hist = executor.submit(get_historical_prices, resolved_ticker)
            def _fetch_delta_and_cache():
                c = get_report_by_ticker(resolved_ticker)
                eval_res = evaluate_material_change(c, stock_data, scrip)
                if len(eval_res) == 4:
                    s_regen, r_reason, l_ann, c_type = eval_res
                else:
                    s_regen, r_reason, l_ann = eval_res
                    c_type = "NONE" if not s_regen else "EXPIRED"
                return c, s_regen, r_reason, l_ann, c_type
            future_disclosures = executor.submit(_fetch_delta_and_cache)

            hist_df = future_hist.result()
            cached, should_regen, reason, latest_ann, change_type = future_disclosures.result()

        if force_refresh:
            should_regen = True
            reason = "⚡ User Requested Fresh Live Synthesis"
            change_type = "FORCE_REFRESH"

        st.session_state["last_history"] = hist_df
        st.session_state["last_history_ticker"] = resolved_ticker

        # Instant silent pull if verified report exists and no material change detected
        if not should_regen and selected_language == "English (India)" and cached and cached.get("report_text"):
            track_user_action("CACHE_HIT", resolved_ticker, cost_saved_usd=0.036, details={"reason": reason})
            set_active_dossier_state(
                ticker=resolved_ticker,
                report_text=cached["report_text"],
                report_date=cached.get("formatted_date"),
                fundamentals=stock_data,
                material_reason=reason,
                is_regenerated=False,
                history_df=hist_df
            )
            st.rerun(scope="app")
        elif change_type == "PRICE_DELTA" and selected_language == "English (India)" and cached and cached.get("report_text"):
            # Price shifted >= 5%, but business fundamentals, moat, and governance remain unchanged.
            # Silently mount verified dossier immediately for zero wait time,
            # and stage a smart notification banner offering surgical update.
            track_user_action("CACHE_HIT", resolved_ticker, cost_saved_usd=0.036, details={"reason": reason, "delta": True})
            st.session_state["pending_price_delta"] = {
                "reason": reason,
                "stock_data": stock_data,
                "cached": cached,
                "ticker": resolved_ticker,
                "language": selected_language,
                "hist_df": hist_df,
            }
            set_active_dossier_state(
                ticker=resolved_ticker,
                report_text=cached["report_text"],
                report_date=cached.get("formatted_date"),
                fundamentals=stock_data,
                material_reason=reason,
                is_regenerated=False,
                history_df=hist_df
            )
            st.rerun(scope="app")
        else:
            # Gate fresh live AI synthesis by user authentication & credit balance
            from core.auth import get_current_user, refresh_current_user
            from core.db import deduct_user_credits

            user = get_current_user()
            if not user:
                st.warning("🔒 **Authentication Required:** Please sign in to run a fresh 7-pillar institutional AI synthesis. New accounts receive **2 Free Welcome Credits** immediately!")
                st.session_state["show_login_dialog"] = True
                return

            can_proceed, new_bal, gate_msg = deduct_user_credits(user["id"], resolved_ticker, "LIVE_SYNTHESIS", 1.0)
            if not can_proceed:
                st.warning(f"🪙 **Insufficient Research Credits:** {gate_msg}")
                st.session_state["show_top_up_dialog"] = True
                return

            refresh_current_user()
            st.toast(f"1.0 Research Credit consumed. Remaining: {new_bal:.1f}", icon="🪙")

            track_user_action("FULL_SYNTHESIS", resolved_ticker, details={"reason": reason})
            prog_slot = st.empty()
            prog_slot.progress(0.80, text=f"⚡ {reason}. Initializing 7-Pillar Institutional AI Synthesis...")
            set_active_dossier_state(
                ticker=resolved_ticker,
                report_text=None,
                fundamentals=stock_data,
                material_reason=reason,
                is_regenerated=True,
                history_df=hist_df
            )
            st.session_state["stream_pending"] = True
            st.session_state["stream_language"] = selected_language
            st.rerun(scope="app")
    except Exception as err:
        st.session_state["last_report"] = None
        err_str = str(err).lower()
        if isinstance(err, ValueError) or "scrip code" in err_str or "not found" in err_str:
            st.warning(f"⚠️ **Stock Not Located:** Could not find verified BSE/NSE exchange listings for **'{clean_query}'**.")
            suggestions = get_ticker_suggestions(clean_query)
            if suggestions:
                st.info(f"💡 **Did you mean:** {', '.join(suggestions)}?")
            else:
                st.caption("ℹ️ Examples of valid inputs: `INFY`, `TCS`, `RELIANCE`, or the 6-digit BSE Scrip Code like `500209`.")
        else:
            stage = getattr(err, "stage", "Pipeline Engine")
            diag_payload = {
                "timestamp_ist": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
                "query_entered": clean_query,
                "error_stage": stage,
                "error_type": type(err).__name__,
                "error_message": str(err),
                "technical_details": getattr(err, "technical_details", ""),
                "system": {"python": platform.python_version(), "os": platform.system()},
                "traceback_tail": traceback.format_exc().splitlines()[-4:] if 'traceback' in globals() else []
            }
            st.error(f"### ❌ Data Pipeline Stopped at: {stage}")
            st.markdown(f"**Error:** {err}")
            with st.expander("📋 Technical Diagnostic Details", expanded=False):
                st.code(json.dumps(diag_payload, indent=2), language="json")
