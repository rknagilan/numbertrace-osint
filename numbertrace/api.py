"""FastAPI HTTP API + local dashboard. Bind to 127.0.0.1 by default (see `numbertrace serve`)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from numbertrace import __version__, history
from numbertrace.config import Settings, get_settings
from numbertrace.core.investigate import Investigator
from numbertrace.core.phone import MAX_INPUT_LENGTH, PhoneInputError
from numbertrace.core.ratelimit import RateLimiter
from numbertrace.models import Investigation, NormalizedNumber, ProviderInfo
from numbertrace.reporting import render_html

MAX_BODY_BYTES = 4096
MAX_REPORT_BODY_BYTES = 512_000  # report export posts a full investigation back


class NumberRequest(BaseModel):
    number: str = Field(min_length=1, max_length=MAX_INPUT_LENGTH)
    country: str | None = Field(default=None, min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")


class InvestigateRequest(NumberRequest):
    online: bool = True


def _static_dir() -> Path:
    return Path(str(resources.files("numbertrace") / "web" / "static"))


def create_app(settings: Settings | None = None, investigator: Investigator | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = investigator or Investigator(settings)
    limiter = RateLimiter(settings.api_rate_limit_per_minute)
    app = FastAPI(
        title="NumberTrace OSINT API",
        version=__version__,
        description="Single-number caller investigation. Results are unverified public evidence.",
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @app.middleware("http")
    async def guard(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        limit = MAX_REPORT_BODY_BYTES if request.url.path.startswith("/api/v1/report/") else MAX_BODY_BYTES
        length = request.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > limit):
            return JSONResponse({"error": "payload_too_large", "detail": f"max {limit} bytes"}, 413)
        if request.method == "POST" and length is None:
            body = await request.body()
            if len(body) > limit:
                return JSONResponse({"error": "payload_too_large"}, 413)
        if request.url.path.startswith(("/api/v1/investigate", "/api/v1/normalize")):
            key = request.client.host if request.client else "local"
            if not limiter.allow(key):
                return JSONResponse(
                    {
                        "error": "rate_limited",
                        "detail": "Too many requests. One investigation at a time.",
                    },
                    429,
                    headers={"Retry-After": str(limiter.retry_after(key))},
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def on_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({".".join(str(p) for p in e.get("loc", [])[1:]) for e in exc.errors()})
        return JSONResponse({"error": "invalid_request", "fields": fields}, 422)

    @app.exception_handler(PhoneInputError)
    async def on_phone(_: Request, exc: PhoneInputError) -> JSONResponse:
        return JSONResponse({"error": "invalid_number", "detail": str(exc)}, 422)

    @app.exception_handler(Exception)
    async def on_error(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"error": "internal_error", "detail": "Unexpected error (details not logged)."}, 500)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/providers", response_model=list[ProviderInfo])
    async def providers() -> list[ProviderInfo]:
        return engine.provider_info()

    @app.post("/api/v1/normalize", response_model=NormalizedNumber)
    async def normalize(req: NumberRequest) -> NormalizedNumber:
        return engine.normalize(req.number, req.country)

    @app.post("/api/v1/investigate", response_model=Investigation)
    async def investigate(req: InvestigateRequest) -> Investigation:
        n = engine.normalize(req.number, req.country)
        inv = await engine.run(req.number, region=req.country, online=req.online, number=n)
        if settings.history_enabled:
            history.record(inv)
        return inv

    @app.post("/api/v1/investigate/stream")
    async def investigate_stream(req: InvestigateRequest, request: Request) -> StreamingResponse:
        engine.normalize(req.number, req.country)  # validate before streaming

        async def gen() -> AsyncIterator[bytes]:
            async for event in engine.stream(req.number, region=req.country, online=req.online):
                if await request.is_disconnected():
                    break  # leaving the loop cancels the running providers
                yield (json.dumps(event) + "\n").encode()

        return StreamingResponse(gen(), media_type="application/x-ndjson")

    @app.post("/api/v1/report/html")
    async def report_html(inv: Investigation) -> Response:
        return Response(
            render_html(inv),
            media_type="text/html",
            headers={"Content-Disposition": "attachment; filename=numbertrace-report.html"},
        )

    @app.post("/api/v1/report/json")
    async def report_json(inv: Investigation) -> Response:
        return Response(
            inv.model_dump_json(indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=numbertrace-report.json"},
        )

    @app.get("/api/v1/history")
    async def get_history() -> Any:
        if not settings.history_enabled:
            return JSONResponse({"error": "history_disabled"}, 404)
        return history.load()

    @app.delete("/api/v1/history")
    async def delete_history() -> dict[str, bool]:
        return {"deleted": history.clear()}

    @app.get("/api/v1/config")
    async def ui_config() -> dict[str, Any]:
        return {
            "demo": settings.demo,
            "history_enabled": settings.history_enabled,
            "default_region": settings.default_region,
            "live_search": settings.has_live_search,
        }

    static = _static_dir()
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(static / "index.html")

    return app
