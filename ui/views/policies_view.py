"""
Legal Policies, Regulatory Safe Harbor, and Merchant Compliance Views.

Renders mandatory policies required by Razorpay merchant onboarding & SEBI Safe-Harbor:
- Terms and Conditions
- Privacy Policy
- Refund & Cancellation Policy
- Shipping & Delivery (Instant Digital Delivery)
- Contact Us
- SEBI Regulatory Disclaimer
"""

import streamlit as st
from web.legal_content import POLICIES


def render_policies_view():
    """Renders the comprehensive compliance policies page in Streamlit."""
    col_back, col_title = st.columns([1, 5])
    with col_back:
        if st.button("← Back to Dossier", key="btn_back_from_policies", type="secondary", width="stretch"):
            st.session_state["active_view"] = "dossier"
            st.query_params.clear()
            st.rerun()

    st.markdown("## 📜 Legal, Regulatory & Merchant Compliance")
    st.caption("Mandatory statutory disclosures complying with Information Technology Act, 2000, Consumer Protection Rules, 2020, and SEBI Safe Harbor.")

    # Determine default selected tab from query params if present
    req_page = st.query_params.get("page") or st.query_params.get("policy") or "terms"
    req_page = req_page.lower().replace("-policy", "")
    if req_page in ["refund_policy", "refund"]:
        default_idx = 2
    elif req_page in ["shipping_policy", "shipping"]:
        default_idx = 3
    elif req_page in ["privacy", "privacy_policy"]:
        default_idx = 1
    elif req_page in ["contact", "contact_us"]:
        default_idx = 4
    elif req_page in ["disclaimer", "sebi"]:
        default_idx = 5
    else:
        default_idx = 0

    tab_terms, tab_privacy, tab_refund, tab_shipping, tab_contact, tab_sebi = st.tabs([
        "📄 Terms & Conditions",
        "🔒 Privacy Policy",
        "💳 Refund Policy",
        "⚡ Delivery Policy",
        "📞 Contact Us",
        "⚖️ SEBI Safe Harbor"
    ])

    with tab_terms:
        policy = POLICIES.get("terms", {})
        st.subheader(policy.get("title", "Terms and Conditions"))
        st.caption(f"Last Updated: {policy.get('last_updated', 'October 2026')}")
        st.html(policy.get("content_html", ""))

    with tab_privacy:
        policy = POLICIES.get("privacy", {})
        st.subheader(policy.get("title", "Privacy Policy"))
        st.caption(f"Last Updated: {policy.get('last_updated', 'October 2026')}")
        st.html(policy.get("content_html", ""))

    with tab_refund:
        policy = POLICIES.get("refund", {})
        st.subheader(policy.get("title", "Refund & Cancellation Policy"))
        st.caption(f"Last Updated: {policy.get('last_updated', 'October 2026')}")
        st.html(policy.get("content_html", ""))

    with tab_shipping:
        policy = POLICIES.get("shipping", {})
        st.subheader(policy.get("title", "Shipping & Delivery Policy"))
        st.caption(f"Last Updated: {policy.get('last_updated', 'October 2026')}")
        st.html(policy.get("content_html", ""))

    with tab_contact:
        policy = POLICIES.get("contact", {})
        st.subheader(policy.get("title", "Contact Us"))
        st.caption(f"Last Updated: {policy.get('last_updated', 'October 2026')}")
        st.html(policy.get("content_html", ""))

    with tab_sebi:
        policy = POLICIES.get("disclaimer", {})
        st.subheader(policy.get("title", "SEBI Non-Advisory Safe Harbor"))
        st.caption(f"Last Updated: {policy.get('last_updated', 'October 2026')}")
        st.html(policy.get("content_html", ""))

    st.markdown("---")
    st.info("🔒 **Entity Identification:** Stock Research App • Service Accounting Code (SAC): **998314** (Information Technology Software Services). All compute credits and syntheses are delivered digitally in real-time.")
