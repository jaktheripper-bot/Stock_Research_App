"""Scorecard, Health Matrix, and Thesis Drift Display Components."""

import re
import streamlit as st
from analyzer import (
    extract_health_matrix,
    remove_health_matrix_text,
    strip_conclusion_sections,
    compare_revisions,
)
from normalizer import extract_citations_from_report
from db import get_report_revisions
from ui.charts import render_momentum_chart
from ui.formatters import format_inr

def render_material_badge(reason: str, is_regenerated: bool, citations_count: int = 0, target_container=None):
    """Renders responsive status badges detailing cache vs regeneration triggers and source attribution."""
    if not reason and not citations_count:
        return
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
    renderer = target_container if target_container is not None else st
    renderer.markdown("".join(badges_html), unsafe_allow_html=True)

def render_health_card_ui(report_text: str, target_container=None):
    """Renders the top executive summary health matrix badges and source attribution."""
    render_momentum_chart(st.session_state.get('last_history'), st.session_state.get('last_ticker', ''))
    citations = extract_citations_from_report(report_text) if report_text else []
    render_material_badge(
        st.session_state.get('material_reason', ''),
        st.session_state.get('is_regenerated', False),
        citations_count=len(citations),
        target_container=target_container
    )
    matrix = extract_health_matrix(report_text)
    if not matrix:
        return

    color_map = {
        "Disciplined": "#1b5e20", "Wide": "#1b5e20", "Clean": "#1b5e20",
        "Debt-Free": "#1b5e20", "Undervalued": "#1b5e20", "Temporary": "#1b5e20", "Stable": "#1b5e20",
        "Watchlist": "#b26a00", "Moderate": "#b26a00", "Fair": "#b26a00",
        "Neutral": "#b26a00", "Moderate Debt": "#b26a00", "Resilient": "#b26a00", "N/A": "#555555",
        "Strained": "#b71c1c", "Narrow": "#b71c1c", "Caution": "#b71c1c", 
        "High Risk": "#b71c1c", "Structural": "#b71c1c", "Stretched": "#b71c1c", 
        "Loss-Making": "#b71c1c", "High Debt": "#b71c1c", "Headwinds": "#b71c1c"
    }

    labels = [
        ("Capital Allocation", matrix.get("CapitalAllocation", "Disciplined")),
        ("Macro", matrix.get("Macro", "Neutral")),
        ("Moat", matrix.get("Moat", "Moderate")),
        ("Gov", matrix.get("Governance", "Clean")),
        ("Diagnostic", matrix.get("Diagnostic", "N/A")),
        ("Valuation", matrix.get("Valuation", "Fair")),
        ("Balance Sheet", matrix.get("BalanceSheet", "Resilient")),
    ]

    pills_html = ['<div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px;">']
    for title, val in labels:
        bg = color_map.get(val, "#333333")
        pills_html.append(
            f'<div style="background-color: {bg}; color: #ffffff; padding: 6px 12px; border-radius: 6px; '
            f'font-size: 13px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px;">'
            f'<span style="opacity: 0.8; font-weight: 400; text-transform: uppercase; font-size: 11px;">{title}:</span>'
            f'<span>{val}</span></div>'
        )
    pills_html.append('</div>')
    
    renderer = target_container if target_container is not None else st
    renderer.markdown("".join(pills_html), unsafe_allow_html=True)

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
            if st.button("Reset to Default Drift", key="btn_reset_drift", width="stretch"):
                st.session_state.pop("custom_diff", None)
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
            with st.expander(f"📁 {title}", expanded=expand_all):
                st.markdown(body_content)
        elif re.search(r"(?i)\b(?:Sources|Footnote|Citations|Regulatory Filings)\b", title):
            with st.expander(f"📚 {title}", expanded=True):
                st.markdown(body_content)
        else:
            # Diagnostic Summary or unclassified factual headers remain open
            st.markdown(sec)
