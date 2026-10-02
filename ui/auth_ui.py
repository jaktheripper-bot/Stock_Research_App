"""
Authentication, User Profile Chip, and Credit Ledger Modal Dialogs.

Provides:
- Sidebar user profile chip with credit balance and Pro badge
- Login modal with Google OAuth and Email Magic Link (granting 2 welcome credits)
- Audit ledger modal displaying credit consumption and invoice downloads
"""

import streamlit as st
from typing import Optional

from core.auth import (
    get_current_user,
    is_authenticated,
    sign_out_user,
    send_magic_link,
    get_google_oauth_url,
    refresh_current_user,
)
from core.db import (
    get_user_transactions,
    get_user_usage_history,
)
from core.billing import generate_invoice_html
from telemetry import track_user_action


def render_auth_sidebar_chip():
    """
    Renders the persistent user profile, credit counter, and top-up trigger
    at the top of the sidebar.
    """
    user = get_current_user()

    if not user:
        # Unauthenticated / Guest State
        with st.container(border=True):
            st.markdown(
                """
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                    <div style="background: rgba(14, 165, 233, 0.15); width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 16px;">
                        👤
                    </div>
                    <div>
                        <div style="font-weight: 700; font-size: 13px;">Guest Investor</div>
                        <div style="font-size: 11px; color: #0284c7; font-weight: 600;">🎁 2 Free Credits on Sign-In</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Sign In / Register", key="btn_sidebar_signin", type="primary", width="stretch"):
                render_login_dialog()
    else:
        # Authenticated State
        credits_bal = user.get("credits_balance", 0.0)
        is_pro = user.get("is_pro", False)
        sub_tier = user.get("subscription_tier", "free")
        name = user.get("full_name") or user.get("email", "").split("@")[0]

        pro_badge_html = (
            '<span style="background: linear-gradient(135deg, #f59e0b, #d97706); color: white; padding: 2px 7px; border-radius: 10px; font-size: 10px; font-weight: 800; margin-left: 6px;">PRO</span>'
            if is_pro else ""
        )

        with st.container(border=True):
            st.markdown(
                f"""
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div style="background: #0f172a; color: white; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700;">
                            {name[:1].upper()}
                        </div>
                        <div>
                            <div style="font-weight: 700; font-size: 13px; line-height: 1.2;">
                                {name}{pro_badge_html}
                            </div>
                            <div style="font-size: 11px; color: #64748b;">{user.get('email')}</div>
                        </div>
                    </div>
                </div>
                <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 6px; padding: 6px 10px; display: flex; justify-content: space-between; align-items: center; margin: 8px 0;">
                    <span style="font-size: 12px; font-weight: 600; color: #047857;">Research Balance</span>
                    <span style="font-size: 14px; font-weight: 800; color: #047857;">🪙 {credits_bal:.1f} Credits</span>
                </div>
                """,
                unsafe_allow_html=True
            )

            c_top, c_led, c_out = st.columns([1.2, 1.2, 0.8])
            with c_top:
                if st.button("💳 Top Up", key="btn_user_topup", width="stretch", help="Purchase on-demand packs or Pro subscription"):
                    from ui.billing_modal import render_top_up_dialog
                    render_top_up_dialog()
            with c_led:
                if st.button("📜 Ledger", key="btn_user_ledger", width="stretch", help="View consumption history and tax invoices"):
                    render_ledger_dialog()
            with c_out:
                if st.button("🚪", key="btn_user_signout", width="stretch", help="Sign out of account"):
                    sign_out_user()
                    track_user_action("SIGN_OUT", details={"email": user.get("email")})
                    st.toast("Signed out successfully.", icon="👋")
                    st.rerun()


def check_and_render_auth_dialogs():
    """Renders active modal dialogs (login, top-up, ledger) if flagged in session state."""
    if st.session_state.get("show_login_dialog"):
        st.session_state.pop("show_login_dialog", None)
        render_login_dialog()
    if st.session_state.get("show_top_up_dialog"):
        st.session_state.pop("show_top_up_dialog", None)
        from ui.billing_modal import render_top_up_dialog
        render_top_up_dialog()
    if st.session_state.get("show_ledger_dialog"):
        st.session_state.pop("show_ledger_dialog", None)
        render_ledger_dialog()


@st.dialog("Sign In to Research Platform", width="small")
def render_login_dialog():
    """
    Renders the authentication modal dialog.
    Supports Google OAuth and frictionless verified email magic link sign-in.
    """
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 16px;">
            <div style="font-size: 20px; font-weight: 800;">Welcome to Stock Research AI</div>
            <div style="font-size: 13px; color: #64748b; margin-top: 4px;">
                Institutional equity thesis & multi-quarter drift surveillance.
            </div>
            <div style="background: rgba(16, 185, 129, 0.1); color: #047857; font-weight: 700; font-size: 12px; padding: 6px 12px; border-radius: 20px; display: inline-block; margin-top: 10px;">
                🎁 2 Free Research Credits granted on sign-up
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    oauth_url = get_google_oauth_url()
    if oauth_url:
        st.markdown(
            f"""
            <a href="{oauth_url}" target="_self" style="text-decoration: none;">
                <div style="display: flex; align-items: center; justify-content: center; gap: 10px; background: white; border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px; font-weight: 600; color: #1e293b; font-size: 14px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); margin-bottom: 16px;">
                    <svg width="18" height="18" viewBox="0 0 24 24"><path fill="#4285F4" d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.8-2.4 3.66v3.05h3.88c2.27-2.09 3.66-5.17 3.66-9.15z"/><path fill="#34A853" d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.35 24 12 24z"/><path fill="#FBBC05" d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.17 0 9.99 0 12s.45 3.83 1.25 5.42l4.03-3.15z"/><path fill="#EA4335" d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.35 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98z"/></svg>
                    Continue with Google
                </div>
            </a>
            """,
            unsafe_allow_html=True
        )

        st.markdown(
            '<div style="text-align: center; color: #94a3b8; font-size: 12px; margin-bottom: 16px;">— OR SIGN IN WITH EMAIL —</div>',
            unsafe_allow_html=True
        )

    with st.form("signin_email_form", clear_on_submit=False):
        email_val = st.text_input("Enter your work or personal email:", placeholder="investor@example.com")
        submit_btn = st.form_submit_button("Continue with Email", type="primary", width="stretch")

    if submit_btn and email_val:
        ok, msg = send_magic_link(email_val)
        if ok:
            track_user_action("SIGN_IN_SUCCESS", details={"email": email_val.strip().lower()})
            st.session_state.pop("show_login_dialog", None)
            st.toast("Signed in! 2 Free Research Credits added to your account.", icon="🎁")
            st.rerun()
        else:
            st.error(msg)

    st.markdown(
        """
        <div style="font-size: 11px; color: #94a3b8; text-align: center; margin-top: 16px;">
            🔒 Safe-harbor privacy: Zero personal financial credentials or portfolio holdings collected.
        </div>
        """,
        unsafe_allow_html=True
    )


@st.dialog("Account Usage & Transaction Ledger", width="large")
def render_ledger_dialog():
    """
    Renders the credit consumption audit ledger and purchase transaction history.
    Allows downloading official SEBI/GST-compliant tax invoices.
    """
    user = get_current_user()
    if not user:
        st.warning("Please sign in to inspect your transaction ledger.")
        return

    st.markdown(f"### Account: {user.get('email')}")
    st.markdown(f"**Current Balance:** 🪙 `{user.get('credits_balance', 0.0):.2f}` Credits | **Tier:** `{user.get('subscription_tier', 'free').upper()}`")

    tab_usage, tab_invoices = st.tabs(["📊 Credit Usage History", "🧾 Purchase Invoices"])

    with tab_usage:
        usage_history = get_user_usage_history(user["id"], limit=50)
        if not usage_history:
            st.info("No credit consumption recorded yet. Synthesizing fresh dossiers will log here.")
        else:
            st.markdown(f"**Recent Actions ({len(usage_history)} events):**")
            for item in usage_history:
                ticker = item["ticker"]
                action = item["action"]
                consumed = item["credits_consumed"]
                bal_after = item["balance_after"]
                dt = item["date"]

                if consumed > 0:
                    badge = f"<span style='color: #e11d48; font-weight:700;'>-{consumed:.2f} cr</span>"
                elif consumed < 0:
                    badge = f"<span style='color: #059669; font-weight:700;'>+{abs(consumed):.2f} cr</span>"
                else:
                    badge = "<span style='color: #64748b; font-weight:600;'>0.00 cr (Pro)</span>"

                st.markdown(
                    f"""
                    <div style="display:flex; justify-content:space-between; align-items:center; padding: 8px 12px; border-bottom: 1px solid rgba(0,0,0,0.06); font-size:13px;">
                        <div>
                            <strong>{ticker}</strong> — <code>{action}</code>
                            <div style="font-size:11px; color:#64748b;">{dt}</div>
                        </div>
                        <div style="text-align: right;">
                            {badge}<br>
                            <span style="font-size:11px; color:#64748b;">Bal: {bal_after:.1f}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    with tab_invoices:
        txs = get_user_transactions(user["id"], limit=20)
        if not txs:
            st.info("No purchase transactions found.")
        else:
            st.markdown(f"**Purchases & Invoices ({len(txs)}):**")
            for tx in txs:
                inv_num = tx.get("invoice_number", "INV-UNKNOWN")
                amt = tx.get("amount_inr", 0.0)
                credits_added = tx.get("credits_added", 0.0)
                pack = tx.get("pack_type", "TOPUP")
                dt = tx.get("date", "")
                pay_id = tx.get("payment_id", "sim_pay")

                with st.container(border=True):
                    c1, c2, c3 = st.columns([2, 1, 1])
                    with c1:
                        st.markdown(f"**{pack}** — `₹{amt:,.2f}`")
                        st.caption(f"Invoice: {inv_num} • {dt}")
                    with c2:
                        st.markdown(f"**+{credits_added:.1f} Credits**")
                        st.caption(f"Status: {tx.get('status', 'success').upper()}")
                    with c3:
                        inv_html = generate_invoice_html(
                            invoice_number=inv_num,
                            user_email=user["email"],
                            plan_name=pack,
                            amount_inr=amt,
                            credits_added=credits_added,
                            payment_id=pay_id or "Direct Grant",
                            date_str=dt
                        )
                        st.download_button(
                            "📄 Download Invoice",
                            data=inv_html,
                            file_name=f"{inv_num}.html",
                            mime="text/html",
                            key=f"dl_inv_{tx['id']}",
                            width="stretch"
                        )
