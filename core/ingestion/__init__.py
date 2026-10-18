"""Data ingestion gateways and parsers for Stock Research App."""
from core.ingestion.angel_one import AngelOneGateway
from core.auth.totp import generate_rfc6238_totp
from core.ingestion.amfi import ingest_amfi_daily_feed

__all__ = [
    "AngelOneGateway",
    "generate_rfc6238_totp",
    "ingest_amfi_daily_feed",
]
