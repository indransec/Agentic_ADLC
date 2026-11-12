"""``adlc-pilot-bridge``: validate settings, serve the pilot-facing MCP servers (feature 010)."""

import uvicorn

from adlc.config.errors import load_settings_or_exit
from adlc.config.settings import BridgeSettings
from adlc.observability.logging import configure_logging
from adlc.tools.bridge.app import build_bridge


def main() -> None:
    settings = load_settings_or_exit(BridgeSettings)
    configure_logging(settings.log_level)
    app = build_bridge(settings)
    uvicorn.run(app, host="0.0.0.0", port=settings.bridge_port, log_config=None)  # noqa: S104


if __name__ == "__main__":
    main()
