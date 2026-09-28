"""Technical Charting Components for Stock Research App."""

import streamlit as st
from analyzer import get_historical_prices

def generate_pdf_chart_image(df, ticker: str):
    """Generates a high-resolution static PNG of the 6-month momentum and 50-DMA for PDF embedding."""
    if df is None or not hasattr(df, "empty") or df.empty or "Date" not in df.columns or "Close" not in df.columns:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import pandas as pd
        import re as re_mod

        plot_df = df.copy()
        plot_df["Date"] = pd.to_datetime(plot_df["Date"])
        plot_df = plot_df.sort_values("Date")

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 3.6), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
        fig.patch.set_facecolor('#ffffff')

        # Price & 50-DMA
        ax1.set_facecolor('#ffffff')
        ax1.plot(plot_df["Date"], plot_df["Close"], color="#2563eb", linewidth=1.6, label="Close Price")
        if "SMA50" in plot_df.columns and not plot_df["SMA50"].dropna().empty:
            ax1.plot(plot_df["Date"], plot_df["SMA50"], color="#d97706", linewidth=1.3, linestyle="--", label="50-DMA")
        
        ax1.set_title(f"6-Month Price Momentum & 50-DMA ({ticker})", fontsize=10, fontweight="bold", pad=6)
        ax1.set_ylabel("Price (INR)", fontsize=8)
        ax1.legend(loc="upper left", frameon=True, fontsize=8)
        ax1.grid(True, linestyle=":", alpha=0.5)

        # Volume
        ax2.set_facecolor('#ffffff')
        if "Volume" in plot_df.columns:
            ax2.bar(plot_df["Date"], plot_df["Volume"], color="#94a3b8", alpha=0.6, width=1.5)
        ax2.set_ylabel("Vol", fontsize=7)
        ax2.grid(True, linestyle=":", alpha=0.5)

        plt.tight_layout()
        clean_name = re_mod.sub(r'[^a-zA-Z0-9]', '_', ticker)
        local_img_path = f"_pdf_chart_{clean_name}.png"
        plt.savefig(local_img_path, dpi=180, bbox_inches="tight")
        plt.close(fig)
        return local_img_path
    except Exception:
        return None

def render_momentum_chart(df, ticker: str):
    """Renders a responsive 6-month price momentum chart with on-the-fly fallback and dynamic inference explainer."""
    import altair as alt
    import pandas as pd

    # Fallback fetch if viewing an archived report or if cached chart belongs to a different stock
    cached_chart_ticker = st.session_state.get("last_history_ticker")
    if (df is None or not hasattr(df, "empty") or df.empty or cached_chart_ticker != ticker) and ticker:
        with st.spinner(f"Loading price momentum for {ticker}..."):
            df = get_historical_prices(ticker)
            if df is not None and not df.empty:
                st.session_state["last_history"] = df
                st.session_state["last_history_ticker"] = ticker

    if df is None or not hasattr(df, "empty") or df.empty or "Date" not in df.columns or "Close" not in df.columns:
        if ticker:
            st.caption(f"ℹ️ Trailing 6-month price momentum chart unavailable for {ticker} (exchange feed unlisted).")
        return

    base = alt.Chart(df).encode(
        x=alt.X("Date:T", title="Date", axis=alt.Axis(format="%b %Y", labelAngle=0, grid=False))
    )

    price_line = base.mark_line(color="#2563eb", strokeWidth=2).encode(
        y=alt.Y("Close:Q", scale=alt.Scale(zero=False), title="Price (₹ INR)"),
        tooltip=[
            alt.Tooltip("Date:T", format="%Y-%m-%d", title="Date"),
            alt.Tooltip("Close:Q", format=".2f", title="Close Price (₹ INR)"),
            alt.Tooltip("SMA50:Q", format=".2f", title="50-DMA [50-Day Moving Average] (₹ INR)")
        ]
    )

    sma_line = base.mark_line(color="#f59e0b", strokeWidth=1.5, strokeDash=[4, 4]).encode(
        y=alt.Y("SMA50:Q", scale=alt.Scale(zero=False)),
        tooltip=[
            alt.Tooltip("Date:T", format="%Y-%m-%d", title="Date"),
            alt.Tooltip("SMA50:Q", format=".2f", title="50-DMA [50-Day Moving Average] (₹ INR)")
        ]
    )

    vol_max = df["Volume"].max() if "Volume" in df.columns and df["Volume"].max() > 0 else 1
    vol_bars = base.mark_bar(opacity=0.18, color="#64748b").encode(
        y=alt.Y("Volume:Q", axis=None, scale=alt.Scale(domain=[0, vol_max * 4]))
    )

    chart = (
        alt.layer(vol_bars, price_line, sma_line)
        .properties(
            title=f"6-Month Price Momentum & 50-DMA [50-Day Moving Average] ({ticker})",
            height=300
        )
        .resolve_scale(y="independent")
        .configure(background="transparent")
        .configure_view(strokeOpacity=0)
    )

    st.altair_chart(chart, width="stretch")

    # Dynamic Technical Inference Explainer
    valid_sma = df.dropna(subset=["SMA50", "Close"])
    if not valid_sma.empty:
        latest_row = valid_sma.iloc[-1]
        c_price = float(latest_row["Close"])
        sma_val = float(latest_row["SMA50"])
        diff_pct = ((c_price - sma_val) / sma_val) * 100.0

        if diff_pct >= 1.5:
            posture = "Bullish Intermediate Momentum"
            color_border = "#10b981"
            bg_color = "rgba(16, 185, 129, 0.08)"
            inference = (
                f"Trading <strong>{abs(diff_pct):.1f}% above</strong> its 50-DMA "
                f"(50-Day Moving Average). The price is sustaining upward momentum, with the 50-DMA line functioning "
                f"as dynamic intermediate support (price floor)."
            )
        elif diff_pct <= -1.5:
            posture = "Corrective / Consolidation Posture"
            color_border = "#f59e0b"
            bg_color = "rgba(245, 158, 11, 0.08)"
            inference = (
                f"Trading <strong>{abs(diff_pct):.1f}% below</strong> its 50-DMA "
                f"(50-Day Moving Average). The price faces intermediate overhead resistance, indicating "
                f"cooling demand or consolidation before a trend reversal."
            )
        else:
            posture = "Inflection / Mean-Reversion Zone"
            color_border = "#3b82f6"
            bg_color = "rgba(59, 130, 246, 0.08)"
            inference = (
                f"Trading within <strong>{abs(diff_pct):.1f}% of its 50-DMA</strong> "
                f"(50-Day Moving Average). The stock is consolidating directly along its 10-week intermediate mean."
            )

        st.markdown(
            f"""
            <div style="border-left: 3px solid {color_border}; background-color: {bg_color}; 
                        padding: 10px 14px; border-radius: 0 6px 6px 0; margin-top: -6px; margin-bottom: 16px;">
                <div style="font-size: 13px; font-weight: 700; color: #f8fafc; margin-bottom: 4px;">
                    Technical Posture: {posture}
                </div>
                <div style="font-size: 13px; color: #cbd5e1; line-height: 1.5;">
                    Current Close: <strong>₹{c_price:,.2f}</strong> vs 50-DMA: <strong>₹{sma_val:,.2f}</strong>. {inference}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
