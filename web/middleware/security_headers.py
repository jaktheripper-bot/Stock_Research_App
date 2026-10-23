# web/middleware/security_headers.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://checkout.razorpay.com https://cdn.razorpay.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://lapi.razorpay.com https://api.razorpay.com https://checkout.razorpay.com https://cdn.razorpay.com https://lumberjack.razorpay.com https://cdn.jsdelivr.net; "
            "frame-src 'self' https://api.razorpay.com https://checkout.razorpay.com; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none';"
        )
        response.headers["Content-Security-Policy"] = csp
        response.headers["Strict-Transport-Security"] = "max-age=15552000; includeSubDomains; preload"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        response.headers["Permissions-Policy"] = (
            'geolocation=(), microphone=(), camera=(), fullscreen=(self), '
            'payment=(self "https://checkout.razorpay.com" "https://api.razorpay.com"), '
            'focus-without-user-activation=()'
        )
        if (
            request.method == "GET"
            and request.headers.get("X-Moatnomics-Prefetch") == "1"
            and response.status_code == 200
            and "text/html" in response.headers.get("content-type", "")
            and "Cache-Control" not in response.headers
        ):
            response.headers["Cache-Control"] = "private, max-age=15"
        return response
