"""Platform API application factory."""

from fastapi import FastAPI
from opentelemetry.sdk.trace.export import SpanExporter

from adlc.api.auth import install_auth
from adlc.api.deps import Services
from adlc.api.errors import install_errors
from adlc.api.routes import auth, health, inbox, runs, usecases
from adlc.config.settings import Settings
from adlc.db.engine import app_engine
from adlc.identity.local import LocalIdentityProvider
from adlc.observability.logging import configure_logging
from adlc.observability.tracing import setup_tracing


def create_app(settings: Settings, span_exporter: SpanExporter | None = None) -> FastAPI:
    """Build the API. Raises if the role catalogue or account file is invalid.

    ``span_exporter`` replaces the OTLP exporter (tests only).
    """
    configure_logging(settings.log_level)
    provider = LocalIdentityProvider.from_files(
        accounts_file=settings.accounts_file,
        role_catalogue=settings.role_catalogue,
        env=settings.env,
        session_secret=settings.session_secret.get_secret_value(),
        session_ttl=settings.session_ttl,
    )
    app = FastAPI(title="ADLC Platform API", version="0.1.0")
    app.state.settings = settings
    app.state.engine = app_engine(settings)
    install_auth(app, provider)
    install_errors(app)
    app.state.services = Services(settings, app.state.engine)  # built on first use
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(usecases.router)
    app.include_router(inbox.router)
    app.include_router(runs.router)
    app.include_router(runs.detail_router())  # last: its run-id path matches anything
    setup_tracing(app, settings, span_exporter)
    return app
