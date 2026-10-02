"""
Cross-Company Peer Comparison View with 3-Tier Disparity Gates.
Evaluates companies side-by-side with heuristic checks across:
1. Sector / Business Model Disparity
2. Lifecycle / Maturity Disparity (unprofitable vs dividend payer)
3. Scale Divergence (>= 100x market cap)
Provides tabbed institutional multiples and 7-pillar qualitative diagnostics.
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
                value=st.session_state.get("comp_input_a", "WIPRO"),
                placeholder="e.g. WIPRO, INFY, TCS, RELIANCE...",
                help="Enter primary company name or BSE ticker symbol."
            )
        with col2:
            comp_b = st.text_input(
                "Company / Ticker B:",
                value=st.session_state.get("comp_input_b", "HCL"),
                placeholder="e.g. HCL, TCS, TATAMOTORS, ICICIBANK...",
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
            prog_slot = st.empty()
            with prog_slot.container():
                prog_bar = st.progress(0.10, text=f"⚡ Initializing peer comparison for {clean_a} vs {clean_b}...")
                def on_comp_progress(pct: float, msg: str):
                    prog_bar.progress(pct, text=f"⚡ {msg}")
                try:
                    res = compare_two_companies(clean_a, clean_b, progress_callback=on_comp_progress)
                    prog_bar.progress(1.0, text="✅ Comparison complete!")
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
                finally:
                    prog_slot.empty()

    # Render comparison results
    if st.session_state.get("last_comparison"):
        c_res = st.session_state["last_comparison"]
        t_a = c_res["ticker_a"]
        t_b = c_res["ticker_b"]
        f_a = c_res["fund_a"]
        f_b = c_res["fund_b"]
        disp = c_res["disparity"]
        rep_a = c_res.get("rep_a")
        rep_b = c_res.get("rep_b")

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
                p_a = f_a.get("current_price") or f_a.get("currentValue") or "N/A"
                roe_a = f_a.get("roe", "N/A")
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Market Cap", format_inr(mc_a))
                if "Loss-Making" in pe_a_val or "Negative" in pe_a_val:
                    m2.metric("P/E Ratio", "Loss-Making", delta="- Negative EPS", delta_color="inverse")
                else:
                    m2.metric("P/E Ratio", pe_a_val)
                m3.metric("Live Price", f"₹{p_a}")
                m4.metric("ROE", roe_a)
                
                st.caption(
                    f"**Sector:** {f_a.get('sector', 'N/A')} | "
                    f"**52W Range:** ₹{f_a.get('52w_low', 'N/A')} – ₹{f_a.get('52w_high', 'N/A')} | "
                    f"**BSE Scrip:** `{f_a.get('scrip_code', 'N/A')}`"
                )

        with col_h2:
            with st.container(border=True):
                st.subheader(f"{f_b.get('short_name', t_b)} ({t_b})")
                mc_b = f_b.get("market_cap") or 0
                pe_b_val = str(f_b.get("pe_ratio", "N/A"))
                p_b = f_b.get("current_price") or f_b.get("currentValue") or "N/A"
                roe_b = f_b.get("roe", "N/A")
                
                m5, m6, m7, m8 = st.columns(4)
                m5.metric("Market Cap", format_inr(mc_b))
                if "Loss-Making" in pe_b_val or "Negative" in pe_b_val:
                    m6.metric("P/E Ratio", "Loss-Making", delta="- Negative EPS", delta_color="inverse")
                else:
                    m6.metric("P/E Ratio", pe_b_val)
                m7.metric("Live Price", f"₹{p_b}")
                m8.metric("ROE", roe_b)
                
                st.caption(
                    f"**Sector:** {f_b.get('sector', 'N/A')} | "
                    f"**52W Range:** ₹{f_b.get('52w_low', 'N/A')} – ₹{f_b.get('52w_high', 'N/A')} | "
                    f"**BSE Scrip:** `{f_b.get('scrip_code', 'N/A')}`"
                )

        # Missing Qualitative Dossier Informational Note
        missing_dossiers = []
        if not rep_a:
            missing_dossiers.append(t_a)
        if not rep_b:
            missing_dossiers.append(t_b)
        if missing_dossiers:
            st.info(
                f"ℹ️ **Qualitative Dossier Notice:** Research reports have not yet been synthesized in your database "
                f"for **{', '.join(missing_dossiers)}**. Financial and valuation ratios below are actively updated from live exchange feeds. "
                f"To unlock the full 7-pillar qualitative ratings, generate a report in the **Institutional Research Dossier** view."
            )

        # Tabbed Institutional Multi-Parameter View
        tab_mult, tab_pillars, tab_disparity = st.tabs([
            "📊 Financial & Valuation Multiples",
            "🛡️ 7-Pillar Institutional Health",
            "⚖️ 3-Tier Disparity Diagnostic"
        ])

        # --- TAB 1: Financial & Valuation Multiples ---
        with tab_mult:
            st.markdown("##### 📈 Head-to-Head Fundamental & Capital Efficiency Multiples")
            multiples_rows = [
                # Valuation Multiples
                {"Category": "Valuation", "Financial Metric": "Trailing P/E Ratio", f"{t_a}": f_a.get("pe_ratio", "N/A"), f"{t_b}": f_b.get("pe_ratio", "N/A"), "Institutional Dimension": "Price relative to trailing 12-month EPS"},
                {"Category": "Valuation", "Financial Metric": "Forward P/E Ratio", f"{t_a}": f_a.get("forward_pe", "N/A"), f"{t_b}": f_b.get("forward_pe", "N/A"), "Institutional Dimension": "Price relative to 1-year forward consensus EPS"},
                {"Category": "Valuation", "Financial Metric": "Price to Book (P/B)", f"{t_a}": f_a.get("price_to_book", "N/A"), f"{t_b}": f_b.get("price_to_book", "N/A"), "Institutional Dimension": "Market valuation vs stated book equity"},
                {"Category": "Valuation", "Financial Metric": "EV / EBITDA", f"{t_a}": f_a.get("ev_to_ebitda", "N/A"), f"{t_b}": f_b.get("ev_to_ebitda", "N/A"), "Institutional Dimension": "Capital structure-neutral enterprise cash multiple"},
                {"Category": "Valuation", "Financial Metric": "Dividend Yield", f"{t_a}": f_a.get("dividend_yield", "N/A"), f"{t_b}": f_b.get("dividend_yield", "N/A"), "Institutional Dimension": "Annual cash return distributed to equity holders"},

                # Profitability & Returns
                {"Category": "Profitability", "Financial Metric": "Return on Equity (ROE)", f"{t_a}": f_a.get("roe", "N/A"), f"{t_b}": f_b.get("roe", "N/A"), "Institutional Dimension": "Net profit generated per rupee of shareholder equity"},
                {"Category": "Profitability", "Financial Metric": "Operating Margin (OPM)", f"{t_a}": f_a.get("opm", "N/A"), f"{t_b}": f_b.get("opm", "N/A"), "Institutional Dimension": "Core operational profitability prior to interest & taxes"},
                {"Category": "Profitability", "Financial Metric": "Net Profit Margin (NPM)", f"{t_a}": f_a.get("npm", "N/A"), f"{t_b}": f_b.get("npm", "N/A"), "Institutional Dimension": "Bottom-line conversion of revenue into profit"},

                # Balance Sheet & Solvency
                {"Category": "Solvency", "Financial Metric": "Debt to Equity (D/E)", f"{t_a}": f_a.get("debt_to_equity", "N/A"), f"{t_b}": f_b.get("debt_to_equity", "N/A"), "Institutional Dimension": "Financial leverage (<0.50 preferred for non-banking)"},
                {"Category": "Solvency", "Financial Metric": "Current Ratio", f"{t_a}": f_a.get("current_ratio", "N/A"), f"{t_b}": f_b.get("current_ratio", "N/A"), "Institutional Dimension": "Short-term liquidity buffer (>1.20 healthy)"},

                # Scale & Trading Range
                {"Category": "Market Scale", "Financial Metric": "Market Capitalization", f"{t_a}": format_inr(mc_a), f"{t_b}": format_inr(mc_b), "Institutional Dimension": "Aggregate market equity value in INR Crores"},
                {"Category": "Market Scale", "Financial Metric": "Live Exchange Price", f"{t_a}": f"₹{p_a}", f"{t_b}": f"₹{p_b}", "Institutional Dimension": "Last traded price on BSE / NSE"},
                {"Category": "Market Scale", "Financial Metric": "52-Week Trading Band", f"{t_a}": f"₹{f_a.get('52w_low', 'N/A')} – ₹{f_a.get('52w_high', 'N/A')}", f"{t_b}": f"₹{f_b.get('52w_low', 'N/A')} – ₹{f_b.get('52w_high', 'N/A')}", "Institutional Dimension": "1-year cyclical market trading range"},
            ]
            mult_df = pd.DataFrame(multiples_rows)
            st.dataframe(mult_df, width="stretch", hide_index=True)

        # --- TAB 2: 7-Pillar Institutional Health ---
        with tab_pillars:
            st.markdown("##### 🛡️ 7-Pillar Institutional Health Comparison")
            mat_a = c_res.get("matrix_a") or {}
            mat_b = c_res.get("matrix_b") or {}

            pillar_specs = [
                ("Pillar 1: Macro Environment", "Macro", "Neutral", "Sector tailwinds, inflation/interest sensitivity, systemic risk exposure"),
                ("Pillar 2: Competitive Moat", "Moat", "Moderate", "Pricing power, barrier to entry, network effects, customer switching costs"),
                ("Pillar 3: Corporate Governance", "Governance", "Clean", "Accounting conservatism, auditor integrity, promoter pledge %, board independence"),
                ("Pillar 4: Drop Diagnostic", "Diagnostic", "Neutral", "Structural business deterioration vs temporary cyclical drawdown"),
                ("Pillar 5: Valuation Stance", "Valuation", "Fair", "Price relative to normalized intrinsic earnings power & margin of safety"),
                ("Pillar 6: Balance Sheet Leverage", "BalanceSheet", "Resilient", "Solvency risk, interest coverage resilience, net debt trajectory"),
                ("Pillar 7: Capital Allocation", "CapitalAllocation", "Disciplined", "ROCE vs Cost of Capital, reinvestment track record, capital return discipline"),
            ]

            rows = []
            for label, key, default_val, desc in pillar_specs:
                val_a = mat_a.get(key, default_val) if mat_a else f"Pending ({t_a})"
                val_b = mat_b.get(key, default_val) if mat_b else f"Pending ({t_b})"
                rows.append({
                    "Analytical Pillar": label,
                    f"{t_a} Stance": val_a,
                    f"{t_b} Stance": val_b,
                    "Evaluated Dimension": desc
                })

            comp_df = pd.DataFrame(rows)
            st.dataframe(comp_df, width="stretch", hide_index=True)

            with st.expander("🔍 Deep-Dive: Pillar Methodology & Evaluated Dimensions", expanded=False):
                for label, key, _, desc in pillar_specs:
                    st.markdown(f"**{label}**")
                    st.caption(f"• **Scope:** {desc}")
                    st.caption(f"• **{t_a}:** {mat_a.get(key, 'Unsynthesized')} | **{t_b}:** {mat_b.get(key, 'Unsynthesized')}")

        # --- TAB 3: 3-Tier Disparity Diagnostic ---
        with tab_disparity:
            st.markdown("##### ⚖️ 3-Tier Heuristic Disparity Diagnostic")
            st.caption(
                "Automated screening gates prevent false 1:1 multiple comparisons when companies operate "
                "across non-fungible business models, different capital structures, or divergent scales."
            )

            d_col1, d_col2, d_col3 = st.columns(3)
            with d_col1:
                with st.container(border=True):
                    st.markdown("**Axis 1: Sector Alignment**")
                    if disp.get("sector_mismatch"):
                        st.error(f"❌ Mismatch ({disp.get('sec_a')} vs {disp.get('sec_b')})")
                        st.caption("Accounting multiples cannot be directly compared across different industries.")
                    else:
                        st.success(f"✅ Compatible ({disp.get('sec_a', 'Aligned')})")
                        st.caption("Companies operate in compatible industrial sectors.")

            with d_col2:
                with st.container(border=True):
                    st.markdown("**Axis 2: Lifecycle / Maturity**")
                    if disp.get("lifecycle_mismatch"):
                        st.warning("⚠️ Lifecycle Divergence")
                        st.caption("One entity is unprofitable/early-stage while the other is mature and cash-flow positive.")
                    else:
                        st.success("✅ Lifecycle Aligned")
                        st.caption("Both companies share compatible earnings maturity postures.")

            with d_col3:
                with st.container(border=True):
                    st.markdown("**Axis 3: Scale & Liquidity**")
                    if disp.get("scale_mismatch"):
                        st.warning("⚠️ Scale Divergence (≥100×)")
                        st.caption("Large divergence in market cap creates non-comparable liquidity and capital structures.")
                    else:
                        st.success("✅ Scale Compatible (<100×)")
                        st.caption("Market capitalization disparity is within institutional comparability bounds.")

            with st.expander("ℹ️ Methodology Documentation", expanded=False):
                st.markdown(
                    """
                    - **Axis 1 (Sector Mismatch):** Triggered when companies belong to distinct industries (e.g., Banks/NBFCs vs. SaaS). Capital structure and margin benchmarks diverge fundamentally.
                    - **Axis 2 (Lifecycle Mismatch):** Triggered when comparing early-stage loss-making entities against cash-flow positive dividend payers.
                    - **Axis 3 (Scale Divergence):** Triggered on $\\ge 100\\times$ market capitalization disparity where liquidity and institutional dynamics are non-equivalent.
                    """
                )

        st.caption(f"🛡️ **Compliance Notice:** {MANDATORY_SEBI_DISCLAIMER}")
