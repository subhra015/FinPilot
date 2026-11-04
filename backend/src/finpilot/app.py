"""FastAPI application factory with security headers and safe error handling (Layer 1, Layer 3).

Establishes secure HTTP defaults:
- Explicit CORS origins (never wildcard).
- Security headers with CSP frame-ancestors, nosniff, and HSTS in production.
- Safe error responses that sanitize internal paths, SQL details, and secrets (SEC-06, SEC-07).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .api import (
    account_router,
    auth_router,
    evaluation_router,
    ledger_router,
    model_router,
    portfolio_router,
    risk_router,
)
from .config import Settings, load_settings
from .logging_config import configure_logging
from .schemas.errors import (
    AuthenticationRequiredError,
    DomainValidationError,
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
    PermissionDeniedError,
    ResourceNotFoundError,
    sanitize_error_message,
)

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

    # Global Safe Exception Handlers (SEC-06, SEC-07)
    @app.exception_handler(DomainValidationError)
    async def domain_validation_handler(
        request: Request, exc: DomainValidationError
    ) -> JSONResponse:
        details = (
            [ErrorDetail(field=exc.field, message=str(exc), code=exc.code.value)]
            if exc.field
            else []
        )
        resp = ErrorResponse(error=str(exc), code=exc.code, details=details)
        return JSONResponse(status_code=422, content=resp.model_dump())

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            ErrorDetail(
                field=".".join(str(loc) for loc in err.get("loc", []) if loc != "body"),
                message=sanitize_error_message(err.get("msg", "Invalid value")),
                code=ErrorCode.VALIDATION_ERROR.value,
            )
            for err in exc.errors()
        ]
        resp = ErrorResponse(
            error="Request validation failed.",
            code=ErrorCode.VALIDATION_ERROR,
            details=details,
        )
        return JSONResponse(status_code=422, content=resp.model_dump())

    @app.exception_handler(AuthenticationRequiredError)
    async def authentication_required_handler(
        request: Request, exc: AuthenticationRequiredError
    ) -> JSONResponse:
        resp = ErrorResponse(error=str(exc), code=ErrorCode.UNAUTHORIZED)
        return JSONResponse(status_code=401, content=resp.model_dump())

    @app.exception_handler(PermissionDeniedError)
    async def permission_denied_handler(
        request: Request, exc: PermissionDeniedError
    ) -> JSONResponse:
        resp = ErrorResponse(error=str(exc), code=ErrorCode.PERMISSION_DENIED)
        return JSONResponse(status_code=403, content=resp.model_dump())

    @app.exception_handler(ResourceNotFoundError)
    async def resource_not_found_handler(
        request: Request, exc: ResourceNotFoundError
    ) -> JSONResponse:
        resp = ErrorResponse(error=str(exc), code=ErrorCode.RESOURCE_NOT_FOUND)
        return JSONResponse(status_code=404, content=resp.model_dump())

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger = logging.getLogger("finpilot.app")
        logger.error(
            "Unhandled exception occurred: path=%s, error=%s",
            request.url.path,
            sanitize_error_message(str(exc)),
            exc_info=True,
        )
        resp = ErrorResponse(
            error="An unexpected internal server error occurred.",
            code=ErrorCode.INTERNAL_ERROR,
        )
        return JSONResponse(status_code=500, content=resp.model_dump())

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env.value}

    # API Routers (SEC-01, Layer 12)
    app.include_router(auth_router, prefix="/api")
    app.include_router(account_router, prefix="/api")
    app.include_router(portfolio_router, prefix="/api")
    app.include_router(ledger_router, prefix="/api")
    app.include_router(risk_router, prefix="/api")
    app.include_router(model_router, prefix="/api")
    app.include_router(evaluation_router, prefix="/api")

    return app
