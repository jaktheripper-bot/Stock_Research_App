"""
Cross-Company Peer Comparison View with 3-Tier Disparity Gates.
Evaluates companies side-by-side with heuristic checks across:
1. Sector / Business Model Disparity
2. Lifecycle / Maturity Disparity (unprofitable vs dividend payer)
3. Scale Divergence (>= 100x market cap)
"""

import streamlit as st
import pandas as pd
from analyzer import compare_two_companies
from db import MANDATORY_SEBI_DISCLAIMER
from telemetry import track_user_action
from ui.formatters import format_inr


def render_peer_comparison_view():
    """Renders the institutional peer comparison view with 3-tier disparity evaluation."""
    st.markdown("### ⚖️ Cross-Company Peer Comparison Engine")
    st.caption(
        "Institutional side-by-side fundamental evaluation with automated 3-tier disparity sanity gates "
        "under SEBI Safe Harbor guidelines."
    )

    with st.form("peer_comparison_form"):
        col1, col2 = st.columns(2)
        with col1:
            comp_a = st.text_input(
                "Company / Ticker A:",
                value=st.session_state.get("comp_input_a", "INFY"),
                placeholder="e.g. INFY, RELIANCE, HDFCBANK...",
                help="Enter primary company name or BSE ticker symbol."
            )
        with col2:
            comp_b = st.text_input(
                "Company / Ticker B:",
                value=st.session_state.get("comp_input_b", "TCS"),
                placeholder="e.g. TCS, TATAMOTORS, ICICIBANK...",
                help="Enter secondary comparison company name or BSE ticker symbol."
            )

        submit_comp = st.form_submit_button("⚖️ Run Peer Comparison", type="primary", width="stretch")

    if submit_comp and comp_a and comp_b:
        clean_a = comp_a.strip().upper()
        clean_b = comp_b.strip().upper()
        if clean_a == clean_b:
            st.warning("Please enter two different companies to perform a peer comparison.")
        else:
            st.session_state["comp_input_a"] = clean_a
            st.session_state["comp_input_b"] = clean_b
            with st.spinner(f"Auditing exchange data and running disparity check for {clean_a} vs {clean_b}..."):
                try:
                    res = compare_two_companies(clean_a, clean_b)
                    track_user_action(
                        "PEER_COMPARISON",
                        ticker=f"{res['ticker_a']}_{res['ticker_b']}",
                        details={"ticker_a": res["ticker_a"], "ticker_b": res["ticker_b"], "is_disparate": res["disparity"]["is_disparate"]}
                    )
                    if res["disparity"]["is_disparate"]:
                        track_user_action(
                            "DISPARITY_WARNING",
                            ticker=f"{res['ticker_a']}_{res['ticker_b']}",
                            details={"warnings": res["disparity"]["warnings"]}
                        )
                    st.session_state["last_comparison"] = res
                except Exception as err:
                    st.error(f"### ❌ Comparison Failed: {err}")

    # Render comparison results
    if st.session_state.get("last_comparison"):
        c_res = st.session_state["last_comparison"]
        t_a = c_res["ticker_a"]
        t_b = c_res["ticker_b"]
        f_a = c_res["fund_a"]
        f_b = c_res["fund_b"]
        disp = c_res["disparity"]

        st.markdown("---")

        # 3-Tier Disparity Gate Warning Banner
        if disp.get("is_disparate"):
            st.warning("⚠️ **Heuristic Disparity Warning: Companies Operate Across Divergent Baselines**")
            for w in disp.get("warnings", []):
                st.markdown(f"• **{w}**")
            st.info(
                "ℹ️ **Normalized View Active:** Non-transferable accounting multiples (e.g. P/B for asset-light software "
                "or EV/EBITDA for banking) are de-emphasized. Focus on universal operational and governance health below."
            )
        else:
            st.success(
                f"✅ **Peer Compatibility Verified:** Both **{t_a}** and **{t_b}** operate in compatible "
                f"sector and scale profiles ({disp.get('sec_a', 'Compatible')})."
            )

        # Side-by-side header cards
        col_h1, col_h2 = st.columns(2)
        with col_h1:
            with st.container(border=True):
                st.subheader(f"{f_a.get('short_name', t_a)} ({t_a})")
                mc_a = f_a.get("market_cap") or 0
                pe_a_val = str(f_a.get("pe_ratio", "N/A"))
                m1, m2 = st.columns(2)
                m1.metric("Market Cap", format_inr(mc_a))
                if "Loss-Making" in pe_a_val or "Negative" in pe_a_val:
                    m2.metric("P/E Ratio", "Loss-Making", delta="- Negative EPS", delta_color="inverse")
                else:
                    m2.metric("P/E Ratio", pe_a_val)
                p_a = f_a.get("current_price") or f_a.get("currentValue") or "N/A"
                st.caption(f"**Sector:** {f_a.get('sector', 'N/A')} | **Live Price:** ₹{p_a}")

        with col_h2:
            with st.container(border=True):
                st.subheader(f"{f_b.get('short_name', t_b)} ({t_b})")
                mc_b = f_b.get("market_cap") or 0
                pe_b_val = str(f_b.get("pe_ratio", "N/A"))
                m3, m4 = st.columns(2)
                m3.metric("Market Cap", format_inr(mc_b))
                if "Loss-Making" in pe_b_val or "Negative" in pe_b_val:
                    m4.metric("P/E Ratio", "Loss-Making", delta="- Negative EPS", delta_color="inverse")
                else:
                    m4.metric("P/E Ratio", pe_b_val)
                p_b = f_b.get("current_price") or f_b.get("currentValue") or "N/A"
                st.caption(f"**Sector:** {f_b.get('sector', 'N/A')} | **Live Price:** ₹{p_b}")

        # 7-Pillar Institutional Health Comparison
        st.markdown("#### 🛡️ 7-Pillar Institutional Health Comparison")
        mat_a = c_res.get("matrix_a") or {}
        mat_b = c_res.get("matrix_b") or {}

        pillar_specs = [
            ("Macro Environment", "Macro", "Neutral"),
            ("Competitive Moat", "Moat", "Moderate"),
            ("Corporate Governance", "Governance", "Clean"),
            ("Drop Diagnostic", "Diagnostic", "Neutral"),
            ("Valuation Stance", "Valuation", "Fair"),
            ("Balance Sheet Leverage", "BalanceSheet", "Resilient"),
            ("Capital Allocation Track Record", "CapitalAllocation", "Disciplined"),
        ]

        rows = []
        for label, key, default_val in pillar_specs:
            val_a = mat_a.get(key, default_val) if mat_a else f"Pending ({t_a})"
            val_b = mat_b.get(key, default_val) if mat_b else f"Pending ({t_b})"
            rows.append({
                "Analytical Pillar": label,
                f"{t_a} Stance": val_a,
                f"{t_b} Stance": val_b
            })

        comp_df = pd.DataFrame(rows)
        st.dataframe(comp_df, width="stretch", hide_index=True)

        # Disparity Context Explainer
        with st.expander("ℹ️ How Cross-Company Disparity is Evaluated (Methodology)", expanded=False):
            st.markdown(
                """
                - **Axis 1 (Sector Mismatch):** Triggered when companies belong to distinct industries (e.g., Banks/NBFCs vs. SaaS). Capital structure and margin benchmarks diverge fundamentally.
                - **Axis 2 (Lifecycle Mismatch):** Triggered when comparing early-stage loss-making entities against cash-flow positive dividend payers.
                - **Axis 3 (Scale Divergence):** Triggered on $\\ge 100\\times$ market capitalization disparity where liquidity and institutional dynamics are non-equivalent.
                """
            )

        st.caption(f"🛡️ **Compliance Notice:** {MANDATORY_SEBI_DISCLAIMER}")
