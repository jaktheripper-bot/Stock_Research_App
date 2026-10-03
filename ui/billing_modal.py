"""
Billing, Pricing Tiers, and Razorpay Checkout Modal Dialogs.

Implements the user credit top-up dialog with approved pricing tiers:
- Single Pass: ₹299
- Analyst 3-Pack: ₹699 (Most Popular)
- Portfolio 10-Pack: ₹1,799
- Pro Monthly: ₹999/mo
- Pro Annual: ₹8,999/yr
- B2B Bulk: ₹5,999 (50 units) & ₹16,999 (150 units)
"""

import time
import streamlit as st
from typing import Optional

from core.billing import (
    PRICING_PACKS,
    B2B_PACKS,
    get_plan_by_id,
    create_razorpay_order,
    process_successful_payment,
    generate_invoice_html,
    is_razorpay_configured,
)
from core.auth import get_current_user, refresh_current_user
from telemetry import track_user_action


@st.dialog("Purchase Research Credits", width="large")
def render_top_up_dialog(default_plan_id: Optional[str] = None):
    """
    Renders the multi-tier research credit checkout modal.
    Allows on-demand pack selection, subscription activation, and UPI/Card checkout.
    """
    user = get_current_user()
    if not user:
        st.warning("Please sign in first to attach purchased credits to your account.")
        if st.button("Sign In / Register", type="primary", width="stretch"):
            st.session_state["show_login_dialog"] = True
            st.rerun()
        return

    # Check if user is currently reviewing an order checkout
    active_order = st.session_state.get("active_checkout_order")
    if active_order:
        _render_checkout_step(user, active_order)
        return

    st.markdown(
        """
        <div style="background: rgba(14, 165, 233, 0.08); border-left: 4px solid #0ea5e9; padding: 12px 16px; border-radius: 6px; margin-bottom: 20px;">
            <div style="font-weight: 700; color: #0284c7; font-size: 14px;">COMPUTATIONAL RESEARCH CREDITS</div>
            <div style="font-size: 13px; color: #64748b; margin-top: 2px;">
                Credits power live 7-pillar AI syntheses, multi-scenario valuations, and exchange audit filings.
                Archived dossiers, quote feeds, and PDF exports are always 100% free.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    tab_packs, tab_subs, tab_bulk = st.tabs(["⚡ On-Demand Packs", "⭐ Pro Subscriptions", "🏢 Enterprise Bulk"])

    # 1. On-Demand Packs Tab
    with tab_packs:
        cols = st.columns(3)
        packs = [PRICING_PACKS["single_pass"], PRICING_PACKS["analyst_3pack"], PRICING_PACKS["portfolio_10pack"]]
        for idx, pack in enumerate(packs):
            with cols[idx]:
                _render_pack_card(pack, user)

    # 2. Subscriptions Tab
    with tab_subs:
        s_cols = st.columns(2)
        subs = [PRICING_PACKS["pro_monthly"], PRICING_PACKS["pro_annual"]]
        for s_idx, sub in enumerate(subs):
            with s_cols[s_idx]:
                _render_pack_card(sub, user)

    # 3. Enterprise Bulk Tab
    with tab_bulk:
        st.markdown("#### Institutional Desks & Advisory Teams")
        st.caption("High-volume packs for wealth managers, corporate research desks, and family offices.")
        b_cols = st.columns(2)
        bulk_items = list(B2B_PACKS.values())
        for b_idx, bulk in enumerate(bulk_items):
            with b_cols[b_idx]:
                with st.container(border=True):
                    st.subheader(bulk["name"])
                    st.markdown(f"### ₹{bulk['amount_inr']:,}")
                    st.caption(f"**{bulk['credits']} Credits** ({bulk['effective_per_stock']})")
                    st.write(f"🏢 Best for: {bulk['target']}")
                    if st.button(f"Purchase {bulk['name']}", key=f"btn_bulk_{bulk['id']}", width="stretch"):
                        _initialize_checkout(bulk["id"], user)
                        st.rerun()

    st.markdown("---")
    st.caption(
        "🔒 **SEBI Educational Safe Harbor & GST Compliance:** Purchases represent computational research processing credits under SAC 998314. "
        "Non-advisory software utility. Prices are inclusive of applicable GST."
    )


def _render_pack_card(pack: dict, user: dict):
    """Renders a single pricing card container."""
    is_pop = pack.get("is_popular", False)
    border_style = "border: 2px solid #0284c7;" if is_pop else ""
    
    with st.container(border=True):
        if is_pop:
            st.markdown(
                '<span style="background: #0284c7; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 700; text-transform: uppercase;">Most Popular</span>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f'<span style="background: rgba(100, 116, 139, 0.15); color: #64748b; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 700;">{pack.get("badge", "Pack")}</span>',
                unsafe_allow_html=True
            )

        st.markdown(f"### {pack['name']}")
        
        cycle = f"/{pack['billing_period']}" if pack.get("billing_period") else ""
        st.markdown(f"<div style='font-size: 26px; font-weight: 800;'>₹{pack['amount_inr']:,}<span style='font-size: 14px; font-weight: 500; color: #64748b;'>{cycle}</span></div>", unsafe_allow_html=True)
        st.caption(f"🪙 **{pack['credits']} Research Credits** • {pack.get('effective_per_stock', '')}")
        st.markdown(f"<p style='font-size: 13px; color: #475569;'>{pack['description']}</p>", unsafe_allow_html=True)

        features = pack.get("features", [])
        for feat in features:
            st.markdown(f"<div style='font-size: 12px; margin-bottom: 4px;'>✓ {feat}</div>", unsafe_allow_html=True)

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        btn_type = "primary" if is_pop else "secondary"
        if st.button(f"Select {pack['name']}", key=f"btn_sel_{pack['id']}", type=btn_type, width="stretch"):
            _initialize_checkout(pack["id"], user)
            st.rerun()


def _initialize_checkout(plan_id: str, user: dict):
    """Creates a payment order and stages checkout state."""
    try:
        order = create_razorpay_order(
            plan_id=plan_id,
            user_id=user["id"],
            user_email=user["email"]
        )
        st.session_state["active_checkout_order"] = order
        track_user_action("CHECKOUT_START", details={"plan_id": plan_id, "amount_inr": order["amount_inr"]})
    except Exception as e:
        st.error(f"Could not initiate checkout: {e}")


def _render_checkout_step(user: dict, order: dict):
    """Renders the payment execution view (UPI QR / Card / Sandbox simulation)."""
    plan = order.get("plan", {})
    amount_inr = order.get("amount_inr", 0)
    is_sim = order.get("is_simulated", True)

    st.markdown("### 💳 Complete Payment")
    
    col_summary, col_pay = st.columns([1, 1])

    with col_summary:
        with st.container(border=True):
            st.markdown("#### Order Summary")
            st.write(f"**Item:** {plan.get('name', 'Research Credits')}")
            st.write(f"**Research Units:** {plan.get('credits', 1.0)} Credits")
            st.write(f"**Account:** {user.get('email')}")
            st.markdown("---")
            
            # Tax breakdown (Inclusive GST 18%)
            base_amt = round(amount_inr / 1.18, 2)
            gst_amt = round(amount_inr - base_amt, 2)
            st.markdown(f"<div style='display:flex; justify-content:space-between; font-size:13px;'><span>Base Price:</span><span>₹{base_amt:.2f}</span></div>", unsafe_allow_html=True)
            st.markdown(f"<div style='display:flex; justify-content:space-between; font-size:13px;'><span>GST (18% SAC 998314):</span><span>₹{gst_amt:.2f}</span></div>", unsafe_allow_html=True)
            st.markdown(f"<div style='display:flex; justify-content:space-between; font-size:16px; font-weight:700; margin-top:8px;'><span>Total Payable:</span><span>₹{amount_inr:.2f}</span></div>", unsafe_allow_html=True)

        if st.button("← Choose Different Plan", width="stretch"):
            st.session_state.pop("active_checkout_order", None)
            st.rerun()

    with col_pay:
        with st.container(border=True):
            st.markdown("#### Pay via UPI / Card")
            st.markdown(
                """
                <div style="text-align: center; padding: 12px; background: rgba(0,0,0,0.03); border-radius: 8px; margin-bottom: 12px;">
                    <div style="font-size: 32px;">📱</div>
                    <div style="font-size: 13px; font-weight: 600;">Scan UPI QR (GPay / PhonePe / PayTM)</div>
                    <div style="font-size: 11px; color: #64748b;">Instant credit fulfillment & automated receipt</div>
                </div>
                """,
                unsafe_allow_html=True
            )

            sim_payment_id = f"pay_{int(time.time())}_{user['id'][:6]}"
            sim_sig = f"sig_sim_{order['id']}_{sim_payment_id}"

            # If simulated sandbox (dev or keys pending)
            if is_sim:
                st.info("💡 **Sandbox Mode Active:** Click below to simulate instant UPI / Card payment verification.")
                if st.button(f"⚡ Confirm Sandbox Payment (₹{amount_inr:,})", type="primary", width="stretch"):
                    ok, new_bal, inv_num, msg = process_successful_payment(
                        user_id=user["id"],
                        plan_id=plan["id"],
                        order_id=order["id"],
                        payment_id=sim_payment_id,
                        signature=sim_sig
                    )
                    if ok:
                        refresh_current_user()
                        st.session_state.pop("active_checkout_order", None)
                        st.session_state["last_invoice_number"] = inv_num
                        st.session_state["last_payment_success"] = {
                            "invoice_number": inv_num,
                            "plan_name": plan["name"],
                            "amount_inr": amount_inr,
                            "credits_added": plan["credits"],
                            "payment_id": sim_payment_id,
                            "date": time.strftime("%d-%b-%Y %H:%M IST")
                        }
                        track_user_action("PAYMENT_SUCCESS", details={"plan_id": plan["id"], "amount_inr": amount_inr, "invoice": inv_num})
                        st.toast(f"Payment successful! Added {plan['credits']} credits.", icon="🎉")
                        st.rerun()
                    else:
                        st.error(f"Payment processing error: {msg}")
            else:
                # Live Razorpay Modal Trigger
                import streamlit.components.v1 as components
                st.caption("🔒 Secure 256-bit encrypted checkout via UPI (GPay/PhonePe), Card, or NetBanking.")
                
                order_key_id = order.get("key_id", "")
                order_amt_paise = order.get("amount", int(amount_inr * 100))
                order_id_val = order.get("id") or order.get("order_id", "")
                plan_name_val = plan.get("name", "Research Credits")
                plan_credits_val = plan.get("credits", 1)
                plan_id_val = plan.get("id", "single_pass")
                user_name_val = user.get("full_name") or "Investor"
                user_email_val = user.get("email") or ""

                checkout_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                  <meta charset="utf-8">
                  <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
                  <style>
                    body {{ margin: 0; padding: 0; background: transparent; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
                    .rzp-btn {{
                      background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%);
                      color: white;
                      border: none;
                      padding: 14px 20px;
                      font-size: 15px;
                      font-weight: 700;
                      border-radius: 8px;
                      cursor: pointer;
                      width: 100%;
                      box-sizing: border-box;
                      box-shadow: 0 4px 14px rgba(14, 165, 233, 0.4);
                      transition: all 0.2s ease;
                      display: flex;
                      align-items: center;
                      justify-content: center;
                      gap: 8px;
                    }}
                    .rzp-btn:hover {{
                      transform: translateY(-1px);
                      box-shadow: 0 6px 20px rgba(14, 165, 233, 0.5);
                    }}
                  </style>
                </head>
                <body>
                  <button id="rzp-btn" class="rzp-btn">
                    ⚡ Pay ₹{amount_inr:,} via Razorpay (UPI / Card)
                  </button>
                  <script>
                    var options = {{
                      "key": "{order_key_id}",
                      "amount": "{order_amt_paise}",
                      "currency": "INR",
                      "name": "Stock Research App",
                      "description": "{plan_name_val} — {plan_credits_val} Research Credits",
                      "order_id": "{order_id_val}",
                      "prefill": {{
                        "name": "{user_name_val}",
                        "email": "{user_email_val}"
                      }},
                      "theme": {{
                        "color": "#0ea5e9"
                      }},
                      "handler": function (response) {{
                        var base = window.parent.location.origin + window.parent.location.pathname;
                        var redirectUrl = base + 
                          "?payment_success=1" + 
                          "&order_id=" + encodeURIComponent(response.razorpay_order_id) + 
                          "&payment_id=" + encodeURIComponent(response.razorpay_payment_id) + 
                          "&signature=" + encodeURIComponent(response.razorpay_signature) + 
                          "&plan_id=" + encodeURIComponent("{plan_id_val}");
                        window.parent.location.href = redirectUrl;
                      }}
                    }};
                    var rzpInstance = new Razorpay(options);
                    document.getElementById('rzp-btn').onclick = function(e) {{
                      rzpInstance.open();
                      e.preventDefault();
                    }};
                    // Auto open
                    setTimeout(function() {{
                      try {{ rzpInstance.open(); }} catch(e) {{}}
                    }}, 400);
                  </script>
                </body>
                </html>
                """
                components.html(checkout_html, height=75)


def handle_payment_callback():
    """Checks and processes Razorpay payment redirect callback from query params."""
    try:
        params = st.query_params
        if params.get("payment_success"):
            order_id = params.get("order_id")
            payment_id = params.get("payment_id")
            signature = params.get("signature")
            plan_id = params.get("plan_id", "single_pass")

            user = get_current_user()
            user_id = user["id"] if user else "guest_web_user"

            if order_id and payment_id and signature:
                ok, new_bal, inv_num, msg = process_successful_payment(
                    user_id=user_id,
                    plan_id=plan_id,
                    order_id=order_id,
                    payment_id=payment_id,
                    signature=signature
                )
                if ok:
                    refresh_current_user()
                    plan = get_plan_by_id(plan_id) or {}
                    credits_added = plan.get("credits", 1.0)
                    st.session_state["last_invoice_number"] = inv_num
                    st.session_state["last_payment_success"] = {
                        "invoice_number": inv_num,
                        "plan_name": plan.get("name", "Research Credits"),
                        "amount_inr": plan.get("amount_inr", 0),
                        "credits_added": credits_added,
                        "payment_id": payment_id,
                        "date": time.strftime("%d-%b-%Y %H:%M IST")
                    }
                    st.toast(f"🎉 Payment Confirmed! Added {credits_added} credits (Balance: {new_bal:.1f}). Invoice: {inv_num}", icon="✅")
                    track_user_action("PAYMENT_SUCCESS", details={"plan_id": plan_id, "invoice": inv_num})
                else:
                    st.error(f"Payment confirmation error: {msg}")

            # Clear payment query params so it doesn't trigger again on reload
            st.query_params.clear()
            st.rerun()
    except Exception as e:
        logger.error(f"Error handling payment callback: {e}")

