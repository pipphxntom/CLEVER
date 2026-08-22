"""Security headers and body-size guard."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from gateway.config import settings

_MAX = settings.CONTEXT_MAX_BYTES + 16_384


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl:
            try:
                if int(cl) > _MAX:
                    return JSONResponse({"detail": "payload_too_large"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "bad_content_length"}, status_code=400)
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        if request.url.path.startswith("/v1/"):
            response.headers["Content-Security-Policy"] = "default-src 'none'"
        return response
