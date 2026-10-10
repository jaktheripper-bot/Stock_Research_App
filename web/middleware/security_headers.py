# web/middleware/security_headers.py
"""Middleware to inject security‑related HTTP headers.
Ensures a baseline of CSP, HSTS, Referrer‑Policy, X‑Content‑Type‑Options, and Permissions‑Policy.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        # Content Security Policy – restrict sources while permitting inline UI logic and CDNs
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://checkout.razorpay.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://lapi.razorpay.com https://cdn.jsdelivr.net; "
            "frame-ancestors 'none';"
        )
        response.headers["Content-Security-Policy"] = csp
        # Strict Transport Security – 6 months, include subdomains, preload
        response.headers["Strict-Transport-Security"] = "max-age=15552000; includeSubDomains; preload"
        # Referrer Policy – no referrer
        response.headers["Referrer-Policy"] = "no-referrer"
        # X-Content-Type-Options – nosniff
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Permissions-Policy – disable risky features
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), fullscreen=*, payment=()"
        )
        return response
