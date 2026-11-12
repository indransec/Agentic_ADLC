"""``adlc-tools``: validate settings, wait for the database, serve the eval store and the
enterprise mocks (feature 010)."""

import sys

import uvicorn

from adlc.config.errors import load_settings_or_exit
from adlc.config.settings import ToolsSettings
from adlc.db.engine import DatabaseUnavailable, app_engine, wait_for_database
from adlc.observability.logging import configure_logging
from adlc.tools.enterprise.app import build_tools


def main() -> None:
    settings = load_settings_or_exit(ToolsSettings)
    configure_logging(settings.log_level)
    engine = app_engine(settings)
    try:
        wait_for_database(engine, settings.db_connect_timeout)
    except DatabaseUnavailable as exc:
        print(f"adlc: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    app = build_tools(settings, engine)
    uvicorn.run(app, host="0.0.0.0", port=settings.tools_port, log_config=None)  # noqa: S104


if __name__ == "__main__":
    main()
