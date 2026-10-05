"""
core/auth/totp.py
==============================================================================
Zero-Dependency RFC 6238 Time-Based One-Time Password (TOTP) Implementation
Compatible with Google Authenticator, Authy, Apple Passwords & 1Password.

Follows zero-hallucination, high-performance, and standard crypto standards:
- Base32 decoding/encoding (RFC 4648)
- HMAC-SHA1 dynamic truncation (RFC 6238 / RFC 4226)
- Configurable window (±1 step = 30 seconds drift tolerance)
==============================================================================
"""

import os
import time
import hmac
import hashlib
import struct
import base64
import urllib.parse
from typing import Optional


def generate_totp_secret(length_bytes: int = 20) -> str:
    """
    Generates a cryptographically secure 160-bit (20 bytes) random secret,
    encoded in unpadded Base32 (32 characters).
    """
    raw_bytes = os.urandom(length_bytes)
    return base64.b32encode(raw_bytes).decode("ascii").rstrip("=")


def get_totp_code(secret: str, interval: int = 30, for_time: Optional[int] = None) -> str:
    """
    Computes standard 6-digit TOTP code for the given secret at `for_time` (default: now).
    """
    if for_time is None:
        for_time = int(time.time())
    counter = int(for_time // interval)

    # Pad unpadded base32 secret
    clean_secret = secret.strip().upper()
    padding_needed = (8 - len(clean_secret) % 8) % 8
    padded_secret = clean_secret + ("=" * padding_needed)

    try:
        key = base64.b32decode(padded_secret, casefold=True)
    except Exception as e:
        raise ValueError(f"Invalid Base32 TOTP secret: {e}")

    # 8-byte big-endian counter
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()

    # Dynamic truncation
    offset = digest[-1] & 0x0F
    binary_val = (
        ((digest[offset] & 0x7F) << 24)
        | ((digest[offset + 1] & 0xFF) << 16)
        | ((digest[offset + 2] & 0xFF) << 8)
        | (digest[offset + 3] & 0xFF)
    )
    code = binary_val % 1_000_000
    return str(code).zfill(6)


def verify_totp_code(secret: str, code: str, interval: int = 30, window: int = 1) -> bool:
    """
    Verifies a user-submitted 6-digit TOTP code against the secret.
    Allows ±`window` steps (default ±1 step = ±30s) to handle clock drift.
    Uses constant-time comparison to prevent timing side-channel attacks.
    """
    if not secret or not code:
        return False

    cleaned_code = str(code).strip().replace(" ", "").replace("-", "")
    if len(cleaned_code) != 6 or not cleaned_code.isdigit():
        return False

    now = int(time.time())
    for step in range(-window, window + 1):
        try:
            expected = get_totp_code(secret, interval, now + (step * interval))
            if hmac.compare_digest(expected, cleaned_code):
                return True
        except Exception:
            pass

    return False


def get_totp_uri(secret: str, account_email: str, issuer: str = "Stock Research App") -> str:
    """
    Builds the standard otpauth:// URI recognized by Google Authenticator and other 2FA apps.
    """
    clean_issuer = issuer.strip()
    clean_email = account_email.strip()
    encoded_label = urllib.parse.quote(f"{clean_issuer}:{clean_email}")
    params = {
        "secret": secret.strip().upper(),
        "issuer": clean_issuer,
        "algorithm": "SHA1",
        "digits": "6",
        "period": "30",
    }
    return f"otpauth://totp/{encoded_label}?{urllib.parse.urlencode(params)}"
