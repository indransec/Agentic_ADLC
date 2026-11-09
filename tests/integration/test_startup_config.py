"""US3: the API stops before serving when a required setting is missing (FR-014)."""

import os
import subprocess
import sys
from pathlib import Path


def test_missing_session_secret_exits_2(tmp_path: Path) -> None:
    accounts = tmp_path / "accounts.yaml"
    accounts.write_text("accounts: []\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("ADLC_")}
    env.update(
        {
            "ADLC_ENV": "dev",
            "ADLC_DB_HOST": "localhost",
            "ADLC_DB_APP_PASSWORD": "app-password-value-0001",
            "ADLC_ACCOUNTS_FILE": str(accounts),
        }
    )
    result = subprocess.run(
        [sys.executable, "-m", "adlc.api"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2
    assert result.stderr.startswith("adlc: configuration error")
    assert "ADLC_SESSION_SECRET: missing" in result.stderr
    assert "app-password-value-0001" not in result.stderr + result.stdout
    assert "Uvicorn running" not in result.stderr
