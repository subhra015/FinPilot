"""FastAPI application factory (Layer 1 skeleton only).

No business endpoints exist yet. This module establishes secure HTTP defaults:
explicit CORS origins (never wildcard), security headers with CSP frame-
ancestors, HSTS only in production (where HTTPS is required), and interactive
docs disabled outside deliberately-enabled environments (SEC-13, SEC-14, SEC-20).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .config import Settings, load_settings
from .logging_config import configure_logging

_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "Permissions-Policy": (
        "accelerometer=(), camera=(), geolocation=(), microphone=(), payment=()"
    ),
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach baseline security headers to every response."""

    def __init__(self, app: Any, *, hsts: bool) -> None:
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if self._hsts:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app from validated settings."""

    settings = settings or load_settings()
    configure_logging(settings)

    docs_enabled = bool(settings.docs_enabled)
    app = FastAPI(
        title="FinPilot AI API",
        version="0.1.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.settings = settings

    origins = settings.cors_origins
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Requested-With"],
        )

    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env.value}

    return app
