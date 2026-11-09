"""Platform API application factory."""

from fastapi import FastAPI

from adlc.api.routes import health
from adlc.config.settings import Settings
from adlc.db.engine import app_engine
from adlc.observability.logging import configure_logging


def create_app(settings: Settings) -> FastAPI:
    configure_logging(settings.log_level)
    app = FastAPI(title="ADLC Platform API", version="0.1.0")
    app.state.settings = settings
    app.state.engine = app_engine(settings)
    app.include_router(health.router)
    return app
