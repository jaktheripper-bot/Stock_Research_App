"""Scorecard, Health Matrix, and Thesis Drift Display Components."""

import re
import numpy as np
import streamlit as st
from analyzer import (
    extract_health_matrix,
    remove_health_matrix_text,
    strip_conclusion_sections,
    compare_revisions,
    calculate_52w_percentile,
    calculate_pe_percentile,
    get_valuation_quartile,
    calculate_overall_health_score,
)
from telemetry import track_user_action
from normalizer import extract_citations_from_report
from db import get_report_revisions, get_report_by_ticker_sync
from ui.charts import render_momentum_chart, render_pillar_drift_sparkline
from ui.formatters import format_inr


def get_material_badge_html(reason: str, is_regenerated: bool, citations_count: int = 0) -> str:
    """Generates responsive status badge HTML detailing cache vs regeneration triggers and source attribution."""
    if not reason and not citations_count:
        return ""
    badges_html = ['<div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; align-items: center;">']
    if reason:
        bg = "#fef3c7" if is_regenerated else "#ecfdf5"
        border = "#fde68a" if is_regenerated else "#a7f3d0"
        text_color = "#92400e" if is_regenerated else "#065f46"
        badges_html.append(
            f'<div style="background-color: {bg}; color: {text_color}; padding: 5px 12px; '
            f'border-radius: 6px; font-size: 13px; font-weight: 600; border: 1px solid {border};">'
            f'{reason}</div>'
        )
    if citations_count > 0:
        badges_html.append(
            f'<div style="background-color: rgba(37, 99, 235, 0.08); color: #2563eb; padding: 5px 12px; '
            f'border-radius: 6px; font-size: 13px; font-weight: 600; border: 1px solid rgba(37, 99, 235, 0.25); '
            f'display: inline-flex; align-items: center; gap: 6px;">'
            f'📎 <span><b>{citations_count}</b> Verified Primary Sources Grounded</span></div>'
        )
    badges_html.append('</div>')
    return "".join(badges_html)


def render_material_badge(reason: str, is_regenerated: bool, citations_count: int = 0, target_container=None):
    """Renders responsive status badges detailing cache vs regeneration triggers and source attribution."""
    html = get_material_badge_html(reason, is_regenerated, citations_count)
    if html:
        renderer = target_container if target_container is not None else st
        renderer.markdown(html, unsafe_allow_html=True)


def _build_pillar_pills_html(matrix: dict, show_full: bool = True, color_blind: bool = False) -> str:
    """Builds responsive 7-pillar HTML badge cluster with ARIA accessibility and bias-reminder tooltips."""
    default_pillars = ["CapitalAllocation", "Moat", "Valuation"]
    all_pillars = [
        ("Capital Allocation", "CapitalAllocation", "Disciplined"),
        ("Macro", "Macro", "Neutral"),
        ("Moat", "Moat", "Moderate"),
        ("Governance", "Governance", "Clean"),
        ("Diagnostic", "Diagnostic", "N/A"),
        ("Valuation", "Valuation", "Fair"),
        ("Balance Sheet", "BalanceSheet", "Resilient"),
    ]

    # Standard Palette
    std_color_map = {
        "Disciplined": "#1b5e20", "Wide": "#1b5e20", "Clean": "#1b5e20",
        "Debt-Free": "#1b5e20", "Undervalued": "#1b5e20", "Temporary": "#1b5e20", "Stable": "#1b5e20",
        "Watchlist": "#b26a00", "Moderate": "#b26a00", "Fair": "#b26a00",
        "Neutral": "#b26a00", "Moderate Debt": "#b26a00", "Resilient": "#b26a00", "N/A": "#555555",
        "Strained": "#b71c1c", "Narrow": "#b71c1c", "Caution": "#b71c1c",
        "High Risk": "#b71c1c", "Structural": "#b71c1c", "Stretched": "#b71c1c",
        "Loss-Making": "#b71c1c", "High Debt": "#b71c1c", "Headwinds": "#b71c1c"
    }

    # High-contrast Accessible Palette (WCAG 2.2 AA compliant: Deep Teal/Navy, Amber Gold, Vermilion)
    accessible_color_map = {
        "Disciplined": "#0f766e", "Wide": "#0f766e", "Clean": "#0f766e",
        "Debt-Free": "#0f766e", "Undervalued": "#0f766e", "Temporary": "#0f766e", "Stable": "#0f766e",
        "Watchlist": "#d97706", "Moderate": "#d97706", "Fair": "#d97706",
        "Neutral": "#d97706", "Moderate Debt": "#d97706", "Resilient": "#0f766e", "N/A": "#475569",
        "Strained": "#dc2626", "Narrow": "#dc2626", "Caution": "#d97706",
        "High Risk": "#dc2626", "Structural": "#dc2626", "Stretched": "#dc2626",
        "Loss-Making": "#dc2626", "High Debt": "#dc2626", "Headwinds": "#dc2626"
    }

    # Semantic iconography mapping ensuring meaning is never conveyed by color alone
    icon_map = {
        "Disciplined": "💎", "Wide": "🏰", "Clean": "🛡️", "Debt-Free": "✅", "Undervalued": "💎",
        "Temporary": "⏳", "Stable": "🟢", "Resilient": "🛡️",
        "Watchlist": "👁️", "Moderate": "⚖️", "Fair": "⚖️", "Neutral": "🟡", "Moderate Debt": "⚖️", "N/A": "⚪",
        "Strained": "📉", "Narrow": "⚠️", "Caution": "⚠️", "High Risk": "🚨", "Structural": "⛔",
        "Stretched": "🔴", "Loss-Making": "❌", "High Debt": "🚨", "Headwinds": "🌪️"
    }

    bias_tips = {
        "CapitalAllocation": "Disposition bias: Disciplined capital allocation reduces premature exit of winners and sunk-cost rationalization of losers.",
        "Macro": "Overconfidence bias: Dynamic macro posture reminds analysts of external cyclical sensitivity.",
        "Moat": "Confirmation bias: Moat classification audits pricing power and customer lock-in across full cycles.",
        "Governance": "False equivalence: Peer governance screening flags statutory auditor churn and promoter pledging.",
        "Diagnostic": "Loss aversion: Distinguishes transient earnings shocks from permanent structural impairment.",
        "Valuation": "Anchoring bias: Multiples evaluated against historical bands rather than recent price drops.",
        "BalanceSheet": "Mental accounting: Scrutinizes leverage and debt service resilience rather than isolated profit numbers.",
    }

    active_colors = accessible_color_map if color_blind else std_color_map

    pills_html = ['<div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; align-items: center;">']
    for title, key, default_val in all_pillars:
        if not show_full and key not in default_pillars:
            continue
        val = matrix.get(key, default_val)
        bg = active_colors.get(val, "#333333")
        icon = icon_map.get(val, "•")
        tip = bias_tips.get(key, "")
        aria_label = f"{title}: {val}. {tip}"

        border_style = "2px solid #ffffff" if color_blind else "1px solid rgba(255,255,255,0.15)"

        pills_html.append(
            f'<div style="background-color: {bg}; color: #ffffff; padding: 6px 12px; border-radius: 6px; '
            f'font-size: 13px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px; '
            f'border: {border_style};" title="{tip}" aria-label="{aria_label}">'
            f'<span>{icon}</span>'
            f'<span style="opacity: 0.85; font-weight: 400; text-transform: uppercase; font-size: 11px;">{title}:</span>'
            f'<span>{val}</span>'
            f'</div>'
        )
    pills_html.append('</div>')
    return "".join(pills_html)


def render_health_card_ui(report_text: str, target_container=None):
    """
    Renders executive summary 7-pillar health matrix badges, cognitive bias mitigations,
    longitudinal drift sparklines, and Charlie Munger pre-mortem decision logging.
    """
    matrix = extract_health_matrix(report_text) if report_text else {}
    if not matrix:
        return

    citations = extract_citations_from_report(report_text) if report_text else []
    mat_html = get_material_badge_html(
        st.session_state.get('material_reason', ''),
        st.session_state.get('is_regenerated', False),
        citations_count=len(citations)
    )

    # 1. Check if streaming is currently in progress
    is_streaming = st.session_state.get("stream_pending", False)

    # If streaming in progress, render lightweight badges directly to target container and return
    if is_streaming:
        pills = _build_pillar_pills_html(matrix, show_full=True, color_blind=False)
        combined = f"{mat_html}{pills}"
        renderer = target_container if target_container is not None else st
        renderer.markdown(combined, unsafe_allow_html=True)
        return

    # 2. Static / Active Dossier View: Render full interactive ergonomics
    ticker = st.session_state.get('last_ticker', '')
    fund = st.session_state.get('last_fundamentals', {})

    # Top Momentum Chart (if available)
    if st.session_state.get('last_history') is not None:
        render_momentum_chart(st.session_state.get('last_history'), ticker)

    # Behavioral UI Controls Strip (Progressive Disclosure & WCAG Accessibility)
    c_ctrl1, c_ctrl2, c_ctrl3 = st.columns([1.5, 1.5, 2.5])
    with c_ctrl1:
        cb_mode = st.toggle(
            "👁️ Accessible Palette",
            value=st.session_state.get('color_blind', False),
            key="cb_palette_toggle",
            help="WCAG 2.2 AA compliant high-contrast colorways with explicit semantic symbols for color-blind accessibility."
        )
        st.session_state['color_blind'] = cb_mode

    with c_ctrl2:
        show_full = st.toggle(
            "🔍 All 7 Pillars",
            value=st.session_state.get('show_full_pillars', False),
            key="show_all_pillars_toggle",
            help="Toggle between top 3 strategic pillars (Moat, Capital Allocation, Valuation) and all 7 detailed diagnostic pillars."
        )
        st.session_state['show_full_pillars'] = show_full

    with c_ctrl3:
        show_sparkline = st.toggle(
            "📈 Thesis Drift Sparkline",
            value=st.session_state.get('show_drift_sparkline', True),
            key="show_drift_sparkline_toggle",
            help="Display longitudinal 7-pillar drift trajectory across quarterly revisions."
        )
        st.session_state['show_drift_sparkline'] = show_sparkline

    # Anchoring Bias Guardrail: Valuation & 52-Week Range Percentiles
    revisions = get_report_revisions(ticker) if ticker else []
    price_val = fund.get("current_price")
    low_52 = fund.get("fifty_two_week_low") or fund.get("52w_low")
    high_52 = fund.get("fifty_two_week_high") or fund.get("52w_high")
    if (low_52 is None or high_52 is None or low_52 == "N/A" or high_52 == "N/A"):
        hist_df = st.session_state.get("last_history")
        if hist_df is not None and hasattr(hist_df, "empty") and not hist_df.empty and "Close" in hist_df.columns:
            try:
                low_52 = float(hist_df["Close"].min())
                high_52 = float(hist_df["Close"].max())
            except Exception:
                pass
    pe_val = fund.get("pe_ratio")

    pct_52w = calculate_52w_percentile(price_val, low_52, high_52)
    pct_pe = calculate_pe_percentile(pe_val, revisions)
    pe_quartile = get_valuation_quartile(pct_pe)

    guardrail_items = []
    if pct_52w is not None:
        guardrail_items.append(f"<b>52-Wk Range Position:</b> {pct_52w}% (₹{float(low_52):,.1f} – ₹{float(high_52):,.1f})")
    if pct_pe is not None:
        guardrail_items.append(f"<b>P/E Valuation Band:</b> {pct_pe}%-ile ({pe_quartile['label']})")

    if guardrail_items:
        guard_text = " • ".join(guardrail_items)
        st.markdown(
            f"""
            <div style="background: rgba(15, 23, 42, 0.45); border-left: 3px solid #3b82f6; 
                        padding: 6px 12px; border-radius: 0 6px 6px 0; margin-bottom: 12px; font-size: 12px; color: #cbd5e1;"
                 title="Anchoring Bias Guardrail: Decouples absolute price swings from distribution percentiles and intrinsic value.">
                ⚓ <span style="font-weight: 600; color: #93c5fd;">Anchoring Bias Guardrail:</span> {guard_text}
            </div>
            """,
            unsafe_allow_html=True
        )

    # 3. Render 7-Pillar Health Matrix Badges
    pills_html = _build_pillar_pills_html(matrix, show_full=show_full, color_blind=cb_mode)
    combined_html = f"{mat_html}{pills_html}"
    renderer = target_container if target_container is not None else st
    renderer.markdown(combined_html, unsafe_allow_html=True)

    # 4. Longitudinal Drift Sparkline (if enabled)
    if show_sparkline and ticker:
        render_pillar_drift_sparkline(ticker, revisions=revisions)

    # 5. Pre-Mortem Inversion Engine (Charlie Munger Anti-Thesis)
    with st.expander("⚡ Pre-Mortem Inversion Engine (Charlie Munger Anti-Thesis)", expanded=False):
        st.caption(
            "**Behavioral Intervention (Confirmation Bias & Narrative Seduction):** "
            "Force backward reasoning from a state of guaranteed thesis failure. "
            "Identify what existential shock could invalidate this company's moat before cementing conviction."
        )
        c_pm1, c_pm2 = st.columns([2.5, 1])
        with c_pm1:
            failure_vector = st.selectbox(
                "Primary Hypothetical Failure Vector:",
                [
                    "Customer / Geographic Concentration Risk (e.g., Top 3 clients >35% revenue)",
                    "Regulatory / Policy Vulnerability (e.g., import tariffs, export duties, PLI scheme expiration)",
                    "Operating Margin Squeeze / Raw Material Inflation (e.g., >200 bps margin contraction)",
                    "Capital Misallocation / Debt-Fueled Acquisition",
                    "Technological Obsolescence / Moat Decay",
                    "Custom Operational Vulnerability..."
                ],
                key="select_premortem_vector"
            )
            analyst_notes = st.text_area(
                "Analyst Anti-Thesis Rationale:",
                placeholder="Articulate specific operational failure scenarios (e.g., loss of principal client, margin compression)...",
                key="txt_premortem_notes",
                height=75
            )
        with c_pm2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("🔒 Commit Pre-Mortem", key="btn_commit_premortem", type="secondary", width="stretch", help="Immutably timestamps your counter-thesis into the decision ledger to combat Hindsight Bias and Narrative Seduction."):
                if ticker:
                    track_user_action(
                        "PREMORTEM",
                        ticker,
                        details={
                            "failure_vector": failure_vector,
                            "anti_thesis_rationale": analyst_notes
                        }
                    )
                    st.toast(f"🔒 Pre-Mortem counter-thesis anchored for {ticker}!", icon="🛡️")
                    st.success(f"Anti-thesis recorded in immutable audit ledger.")




def render_thesis_drift_panel(ticker: str, custom_diff_data: dict = None):
    """Renders the Thesis Drift Surveillance panel comparing two discrete report revisions."""
    if custom_diff_data:
        diff = custom_diff_data["diff"]
        rev_a = custom_diff_data["rev_a"]
        rev_b = custom_diff_data["rev_b"]
        is_custom = True
    else:
        revisions = get_report_revisions(ticker)
        if len(revisions) < 2:
            return
        rev_b = revisions[0]
        rev_a = revisions[1]
        diff = compare_revisions(rev_a, rev_b)
        is_custom = False

    if diff["migration_count"] == 0 and not diff["value_trap_detected"] and not is_custom:
        return  # No drift to display

    # If custom diff active, show notice bar with reset button
    if is_custom:
        c1, c2 = st.columns([3, 1])
        with c1:
            st.info(f"⚖️ **Custom Differential Surveillance:** Comparing **{custom_diff_data.get('label_a', 'State A')}** vs **{custom_diff_data.get('label_b', 'State B')}**.")
        with c2:
            if st.button("✕ Close Differential", key="btn_reset_drift", width="stretch", help="Return to latest active dossier view"):
                st.session_state.pop("custom_diff", None)
                rec = get_report_by_ticker_sync(ticker)
                if rec:
                    from ui.views.state import set_active_dossier_state
                    set_active_dossier_state(
                        ticker=ticker,
                        report_text=rec.get("report_text"),
                        report_date=rec.get("formatted_date"),
                        fundamentals={
                            "short_name": rec.get("short_name", ticker),
                            "ticker": ticker,
                            "market_cap": rec.get("baseline_mcap", "Archived"),
                            "pe_ratio": rec.get("baseline_pe", "N/A"),
                            "sector": "General Industry",
                            "current_price": rec.get("baseline_price", "N/A")
                        },
                        material_reason="📂 Returned to Active Dossier"
                    )
                st.rerun()

    # Value Trap Alert Banner
    if diff["value_trap_detected"]:
        st.markdown(
            f"""
            <div style="background-color: rgba(183, 28, 28, 0.12); border: 1px solid #ef4444; border-radius: 8px;
                        padding: 12px 16px; margin-bottom: 16px;">
                <div style="font-size: 14px; font-weight: 700; color: #fca5a5; margin-bottom: 4px;">
                    ⚠️ Value Trap Signal Detected
                </div>
                <div style="font-size: 13px; color: #cbd5e1; line-height: 1.5;">
                    {diff['value_trap_detail']}.
                    This divergence pattern — qualitative pillar erosion concurrent with valuation expansion —
                    is a historically documented risk factor warranting independent investigation.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    migration_label = f"{diff['migration_count']} Pillar Migration{'s' if diff['migration_count'] != 1 else ''} Detected"
    with st.expander(f"📊 Thesis Drift Surveillance ({migration_label})", expanded=diff["value_trap_detected"] or is_custom):
        st.caption(f"Comparing: **{diff['state_a_date']}** → **{diff['state_b_date']}** | Trigger: _{diff['revision_trigger']}_")

        # Pillar migration badges
        if diff["pillar_migrations"]:
            pills = ['<div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px;">']
            for m in diff["pillar_migrations"]:
                if m["direction"] == "downgrade":
                    bg, icon = "#7f1d1d", "🔻"
                elif m["direction"] == "upgrade":
                    bg, icon = "#14532d", "🔺"
                else:
                    bg, icon = "#1e3a5f", "🔄"
                pills.append(
                    f'<div style="background-color: {bg}; color: #ffffff; padding: 6px 12px; border-radius: 6px; '
                    f'font-size: 13px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px;">'
                    f'{icon} <span style="opacity: 0.8; font-weight: 400; text-transform: uppercase; font-size: 11px;">'
                    f'{m["label"]}:</span> {m["from"]} → {m["to"]}</div>'
                )
            pills.append('</div>')
            st.markdown("".join(pills), unsafe_allow_html=True)
        elif is_custom:
            st.info("✓ **Zero Qualitative Pillar Migrations Detected:** The core investment thesis classifications across all 7 pillars remain identical between these two revisions.")

        # Quantitative metric delta table
        st.markdown("**Quantitative Baseline Shift**")
        delta_rows = []
        for key in ["baseline_price", "baseline_pe", "baseline_mcap"]:
            d = diff["metric_deltas"].get(key, {})
            pct = d.get("pct_change", 0.0)
            arrow = "▲" if pct > 0 else "▼" if pct < 0 else "—"

            sa = d.get("state_a", "N/A")
            sb = d.get("state_b", "N/A")
            if key == "baseline_price":
                sa = f"₹{d['num_a']:,.2f}" if d.get("num_a", 0) > 0 else "N/A"
                sb = f"₹{d['num_b']:,.2f}" if d.get("num_b", 0) > 0 else "N/A"
            elif key == "baseline_mcap":
                sa = format_inr(d.get("num_a")) if d.get("num_a", 0) > 0 else "N/A"
                sb = format_inr(d.get("num_b")) if d.get("num_b", 0) > 0 else "N/A"

            delta_rows.append(f"| {d.get('label', key)} | {sa} | {sb} | {arrow} {abs(pct):.1f}% |")

        table_md = "| Metric | State A | State B | Δ Change |\n| :--- | :--- | :--- | :--- |\n" + "\n".join(delta_rows)
        st.markdown(table_md)
        st.caption("_Thesis drift tracking is a descriptive diagnostic tool. Pillar migrations reflect changes in publicly available exchange data and do not constitute investment advice._")

def render_dual_speed_report(markdown_text: str, expand_all: bool = False):
    """
    Renders report in a mobile-optimized dual-speed layout:
    - Diagnostic Summary & Takeaways: open above the fold
    - Analytical Pillars 1 to 7: nested inside st.expander containers
    """
    cleaned = strip_conclusion_sections(remove_health_matrix_text(markdown_text))
    sections = re.split(r"(?m)(?=^#{1,4}\s+)", cleaned)
    sections = [s.strip() for s in sections if s.strip()]

    if len(sections) <= 2:
        st.markdown(cleaned)
        return

    for sec in sections:
        lines = sec.splitlines()
        first_line = lines[0].strip()
        title = re.sub(r"^#+\s*", "", first_line).strip()
        body_content = chr(10).join(lines[1:]).strip() if len(lines) > 1 else sec

        # Strict exclusion of any conclusion or monitorables headers
        if re.search(r"(?i)\b(?:Conclusion|Key Monitorables|Actionable Guidance|Diagnostic Synthesis)\b", title):
            continue

        # Nest Pillars 1 through 7 into accordions
        if re.search(r"(?i)\bPillars?\s*\d+", title):
            clean_title = re.sub(r"^[📁📚\s]+", "", title)
            with st.expander(f"📁 {clean_title}", expanded=expand_all):
                st.markdown(body_content)
        elif re.search(r"(?i)\b(?:Sources|Footnote|Citations|Regulatory Filings)\b", title):
            clean_title = re.sub(r"^[📁📚\s]+", "", title)
            with st.expander(f"📚 {clean_title}", expanded=True):
                st.markdown(body_content)
        else:
            # Diagnostic Summary or unclassified factual headers remain open
            st.markdown(sec)
