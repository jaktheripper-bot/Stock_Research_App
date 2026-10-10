#!/usr/bin/env python3
"""
Angel One SmartAPI Static IP & Proxy Egress Verifier
===================================================
A diagnostic CLI tool to:
1. Probe the exact outbound public IPv4 address seen by Angel One's firewalls.
2. Validate whether SMARTAPI_PROXY_URL is actively routing SmartAPI traffic.
3. Check status of Angel One API credentials (API Key, Client Code, PIN, TOTP).
4. Provide the exact IP to register in the Angel One Developer Portal.
"""

import os
import sys

# Ensure project root is in python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.ingestion.angel_one import AngelOneGateway, generate_rfc6238_totp
from core.config import get_secret


def main():
    print("=" * 70)
    print("🛰️  ANGEL ONE SMARTAPI STATIC IP & EGRESS VERIFIER")
    print("=" * 70)

    # 1. Probe Outbound IP
    print("\n[Step 1/3] Probing Outbound Egress IP...")
    probe = AngelOneGateway.probe_outbound_ip()
    outbound_ip = probe.get("outbound_ip", "Unknown")
    is_proxied = probe.get("is_proxied", False)
    proxy_url = probe.get("proxy_url_masked", "")

    if is_proxied:
        print(f"  • Proxy Mode:     ACTIVE (Selective SmartAPI Proxy)")
        print(f"  • Proxy Target:   {proxy_url}")
        print(f"  • Outbound IP:    🎯 {outbound_ip}")
    else:
        print(f"  • Proxy Mode:     DIRECT (No proxy configured)")
        print(f"  • Outbound IP:    🎯 {outbound_ip}")

    # 2. Check Credentials
    print("\n[Step 2/3] Checking Angel One Credentials...")
    api_key = get_secret("ANGEL_API_KEY") or os.environ.get("ANGEL_API_KEY")
    client_code = get_secret("ANGEL_CLIENT_CODE") or os.environ.get("ANGEL_CLIENT_CODE")
    pin = get_secret("ANGEL_PIN") or os.environ.get("ANGEL_PIN")
    totp_key = get_secret("ANGEL_TOTP_KEY") or os.environ.get("ANGEL_TOTP_KEY")

    def _mask(val: str) -> str:
        if not val:
            return "❌ Missing"
        if len(val) <= 4:
            return "****"
        return f"{val[:2]}...{val[-2:]} (✅ Set)"

    print(f"  • ANGEL_API_KEY:     {_mask(api_key)}")
    print(f"  • ANGEL_CLIENT_CODE: {_mask(client_code)}")
    print(f"  • ANGEL_PIN:         {_mask(pin)}")
    print(f"  • ANGEL_TOTP_KEY:    {_mask(totp_key)}")

    # 3. Test Authentication (if configured)
    print("\n[Step 3/3] Authenticating Session...")
    if AngelOneGateway.is_configured():
        print("  • Attempting handshake with Angel One SmartAPI auth gateway...")
        jwt = AngelOneGateway.authenticate(force_refresh=True)
        if jwt:
            print("  • Session Status:    ✅ VERIFIED ACTIVE (JWT token obtained)")
        else:
            print("  • Session Status:    ⚠️ FAILED (Check credentials or IP whitelisting)")
    else:
        print("  • Session Status:    ⏸️  Skipped (Credentials pending)")

    # 4. Actionable Instructions for Angel One Portal
    print("\n" + "=" * 70)
    print("📋 ACTION REQUIRED: REGISTER IN ANGEL ONE DEVELOPER PORTAL")
    print("=" * 70)
    print(f"1. Log in to your Angel One SmartAPI Developer Dashboard:")
    print(f"   👉 https://smartapi.angelone.in/")
    print(f"2. Edit your App or create a new App.")
    print(f"3. In the 'Primary Static IP' field, paste this exact IP:")
    print(f"\n      ⭐️  {outbound_ip}  ⭐️\n")
    print(f"4. Save changes. SmartAPI allows up to 5 static IPs.")
    print(f"   (If using Render, add both your local IP and your proxy static IP).")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
