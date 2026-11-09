"""``adlc-api`` entry point: validate settings, wait for the database, serve."""

import sys

import uvicorn

from adlc.api.app import create_app
from adlc.config.errors import load_settings_or_exit
from adlc.config.settings import Settings
from adlc.db.engine import DatabaseUnavailable, wait_for_database


def main() -> None:
    settings = load_settings_or_exit(Settings)
    app = create_app(settings)
    try:
        wait_for_database(app.state.engine, settings.db_connect_timeout)
    except DatabaseUnavailable as exc:
        print(f"adlc: {exc}", file=sys.stderr)
        sys.exit(1)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)  # noqa: S104  # container port


if __name__ == "__main__":
    main()
