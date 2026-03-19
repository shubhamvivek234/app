"""
Phase 0.8 — FastAPI application factory.
- CORSMiddleware with explicit allowed_origins (never wildcard *)
- Security headers + trace_id middleware
- Structured (JSON) logging in production
- Startup: create DB indexes, close pools on shutdown
"""
import os
import logging
import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import SecurityHeadersMiddleware, TraceIDMiddleware
from api.health import router as health_router
from api.routes.auth import router as auth_router
from api.routes.posts import router as posts_router
from api.routes.upload import router as upload_router
from api.routes.accounts import router as accounts_router
from api.routes.webhooks import router as webhooks_router
from api.routes.stream import router as stream_router
from db.mongo import close_client
from db.redis_client import close_pools
from db.indexes import create_all_indexes
from utils.log_scrub import configure_scrubbing


def _configure_logging() -> None:
    """JSON logs in production, human-readable in dev."""
    is_prod = os.getenv("ENV", "development") == "production"
    configure_scrubbing()

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if is_prod:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    await create_all_indexes()
    yield
    await close_client()
    await close_pools()


def create_app() -> FastAPI:
    app = FastAPI(
        title="SocialEntangler API",
        version="2.9.0",
        docs_url="/api/docs" if os.getenv("ENV") != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # CORS — explicit origins only, never wildcard
    allowed_origins = [
        o.strip()
        for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Trace-ID"],
    )

    # Security headers + trace_id (order matters — outermost first)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(TraceIDMiddleware)

    # Routes
    app.include_router(health_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(posts_router, prefix="/api/v1")
    app.include_router(upload_router, prefix="/api/v1")
    app.include_router(accounts_router, prefix="/api/v1")
    app.include_router(webhooks_router, prefix="/api/v1")
    app.include_router(stream_router, prefix="/api/v1")

    return app


app = create_app()
