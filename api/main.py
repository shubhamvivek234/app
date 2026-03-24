"""
Phase 0.8 + Phase 3.3 + Phase 4 + Phase 5.8 — FastAPI application factory.
- CORSMiddleware with explicit allowed_origins (never wildcard *)
- Security headers + trace_id middleware
- Structured (JSON) logging in production
- Sentry SDK integration with performance tracing (Phase 4)
- Prometheus metrics via prometheus-fastapi-instrumentator (Phase 4)
- slowapi rate limiting with Redis backend (Phase 3.3)
- Startup: create DB indexes, close pools on shutdown
"""
import os
import logging
import structlog
from contextlib import asynccontextmanager

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.middleware import SecurityHeadersMiddleware, TraceIDMiddleware
from api.health import router as health_router
from api.routes.auth import router as auth_router
from api.routes.posts import router as posts_router
from api.routes.upload import router as upload_router
from api.routes.accounts import router as accounts_router
from api.routes.webhooks import router as webhooks_router
from api.routes.stream import router as stream_router
from api.routes.public_api import router as public_api_router
from api.routes.user_webhooks import router as user_webhooks_router
from api.routes.admin import router as admin_router
from api.routes.user import router as user_router
from api.routes.payments import router as payments_router
from api.routes.ai import router as ai_router
from api.routes.bulk_upload import router as bulk_upload_router
from api.routes.timeslots import router as timeslots_router
from db.mongo import close_client
from db.redis_client import close_pools
from db.indexes import create_all_indexes
from db.audit_events import ensure_indexes as create_audit_indexes
from utils.log_scrub import configure_scrubbing


def _configure_sentry() -> None:
    """Initialise Sentry SDK — no-op if SENTRY_DSN is unset."""
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("ENV", "development"),
        release=os.getenv("SENTRY_RELEASE", "2.9.0"),
        # Performance tracing — 20% sample rate in prod
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.2")),
        profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.05")),
        integrations=[
            FastApiIntegration(),
            StarletteIntegration(),
            LoggingIntegration(
                level=logging.WARNING,       # breadcrumb threshold
                event_level=logging.ERROR,   # capture as Sentry event
            ),
        ],
        # Strip PII — do not send IP addresses or user emails
        send_default_pii=False,
    )


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
    import os as _os
    from db.mongo import get_client as _get_client
    _configure_logging()
    _configure_sentry()
    await create_all_indexes()
    # Phase 7.5.1 — audit_events TTL + query indexes
    _client = await _get_client()
    _db = _client[_os.environ["DB_NAME"]]
    await create_audit_indexes(_db)
    yield
    await close_client()
    await close_pools()


from api.limiter import limiter  # noqa: E402 — must be after route imports to avoid circular


def create_app() -> FastAPI:
    app = FastAPI(
        title="SocialEntangler API",
        version="2.9.0",
        docs_url="/api/docs" if os.getenv("ENV") != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # Rate limiting (Phase 3.3)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
    app.include_router(public_api_router, prefix="/api/v1")    # Phase 5.8
    app.include_router(user_webhooks_router, prefix="/api/v1") # Phase 5.8
    app.include_router(admin_router, prefix="/api/v1")         # Phase 9
    app.include_router(user_router, prefix="/api/v1")          # user account / GDPR
    app.include_router(payments_router, prefix="/api/v1")      # checkout + billing
    app.include_router(ai_router, prefix="/api/v1")            # AI content generation
    app.include_router(bulk_upload_router, prefix="/api/v1")   # bulk CSV upload
    app.include_router(timeslots_router, prefix="/api/v1")     # timeslots CRUD

    # Prometheus metrics — exposes /metrics (Prometheus scrape endpoint)
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=True,           # honour ENABLE_METRICS env var
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/health", "/ready", "/metrics"],
        inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    return app


app = create_app()
