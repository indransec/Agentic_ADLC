"""``make openapi``: write the platform API's OpenAPI document for the web application (022 T014).

Run with ``uv run python -m scripts.export_openapi [path]`` from the repository root (default path
``web/src/api/openapi.json``). The document is built in-process from the application factory with
throw-away settings: no database is opened and ``/openapi.json`` stays behind the session.
``tests/unit/api/test_openapi_fresh.py`` compares the committed file with :func:`render`.
"""

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from adlc.api.app import create_app
from adlc.config.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = REPO_ROOT / "web" / "src" / "api" / "openapi.json"
ROLES = REPO_ROOT / "adlc-specs" / "shared" / "roles.yaml"


def openapi_document() -> dict[str, Any]:
    """The API's OpenAPI document; settings are placeholders (nothing is connected)."""
    with tempfile.TemporaryDirectory(prefix="adlc-openapi-") as folder:
        accounts = Path(folder) / "accounts.yaml"
        accounts.write_text("accounts: []\n")
        settings = Settings.model_validate(
            {
                "env": "dev",
                "db_path": Path(folder) / "adlc.db",
                "session_secret": "openapi-export-" + "x" * 32,
                "accounts_file": accounts,
                "role_catalogue": ROLES,
            }
        )
        app = create_app(settings)
        try:
            return app.openapi()
        finally:
            app.state.engine.dispose()


def render(document: dict[str, Any]) -> str:
    """Stable text: sorted keys, two-space indent, a final newline."""
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    target = Path(argv[0]) if argv else DOCUMENT
    target.write_text(render(openapi_document()))
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
