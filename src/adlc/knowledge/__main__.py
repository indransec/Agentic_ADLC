"""``adlc-knowledge`` entry point: validate settings, load the folder, serve (feature 008)."""

import uvicorn

from adlc.config.errors import load_settings_or_exit
from adlc.config.settings import KnowledgeSettings
from adlc.knowledge.server import build_app
from adlc.observability.logging import configure_logging


def main() -> None:
    settings = load_settings_or_exit(KnowledgeSettings)
    configure_logging(settings.log_level)
    app = build_app(settings)
    uvicorn.run(app, host="0.0.0.0", port=settings.knowledge_port, log_config=None)  # noqa: S104


if __name__ == "__main__":
    main()
