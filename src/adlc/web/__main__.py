"""``adlc-web``: run the ui process (feature 022) with uvicorn.

Listens on ``ADLC_UI_PORT``; ``--host`` is ``127.0.0.1`` by default (``0.0.0.0`` in compose).
uvicorn's own access log is off: it would record query strings; ``adlc.web`` logs method, path
and status only.
"""

import argparse
import logging
import sys

import uvicorn

from adlc.config.settings import UiSettings
from adlc.web.server import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="adlc-web", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None, help="default: ADLC_UI_PORT")
    args = parser.parse_args(argv)
    settings = UiSettings()
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    uvicorn.run(
        create_app(settings),
        host=args.host,
        port=args.port or settings.ui_port,
        access_log=False,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
