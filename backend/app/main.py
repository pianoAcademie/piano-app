from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging

configure_logging(level=settings.log_level, json_logs=settings.log_json)

request_logger = logging.getLogger("app.request")

app = FastAPI(title="Piano Academie API", version="0.2.1")
app.include_router(api_router, prefix="/api/v1")


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("X-Frame-Options", "DENY")
    forwarded_proto = str(request.headers.get("x-forwarded-proto") or request.url.scheme or "").lower()
    if forwarded_proto == "https" or settings.frontend_base_url.startswith("https://"):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    started = perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((perf_counter() - started) * 1000, 2)
        request_logger.exception(
            "request_failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query": request.url.query,
                "duration_ms": duration_ms,
                "client_ip": request.client.host if request.client else None,
            },
        )
        raise

    duration_ms = round((perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id

    request_logger.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "query": request.url.query,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "client_ip": request.client.host if request.client else None,
        },
    )

    return response


@app.get("/health")
def healthcheck() -> dict[str, bool]:
    return {"ok": True}
