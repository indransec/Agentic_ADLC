"""T025: the operator commands drive a real host and the traffic generator over HTTP."""

from collections.abc import Callable

import pytest

from pilot_tools import cli
from pilot_tools.traffic import Traffic, create_app
from tests.integration.conftest import Host, Packages, serve


def code(call: Callable[[], None]) -> int:
    with pytest.raises(SystemExit) as raised:
        call()
    return int(raised.value.code or 0)


def test_env_split_fault_and_traffic_commands(
    host: Callable[[str], Host], packages: Packages, capsys: pytest.CaptureFixture[str]
) -> None:
    dev, prod = host("dev"), host("prod-sim")
    with serve(dev.client.app) as dev_url, serve(prod.client.app) as prod_url:
        assert code(lambda: cli.env_main([dev_url, "create", "--package", packages.default])) == 0
        assert code(lambda: cli.env_main([dev_url, "status"])) == 0
        assert code(lambda: cli.env_main([dev_url, "infra"])) == 0
        assert code(lambda: cli.env_main([dev_url, "create", "--package", packages.default])) == 1
        assert code(lambda: cli.env_main([dev_url, "delete"])) == 0
        assert (
            code(
                lambda: cli.split_main(
                    [
                        "canary",
                        "--share",
                        "0.2",
                        "--stable",
                        packages.default,
                        "--candidate",
                        packages.variant,
                        "--host",
                        prod_url,
                    ]
                )
            )
            == 0
        )
        assert code(lambda: cli.split_main(["status", "--host", prod_url])) == 0
        assert (
            code(
                lambda: cli.fault_main(
                    ["model_swap", "trigger", "--share", "0.4", "--host", prod_url]
                )
            )
            == 0
        )
        assert code(lambda: cli.fault_main(["status", "--host", prod_url])) == 0
        assert code(lambda: cli.fault_main(["model_swap", "revert", "--host", prod_url])) == 0
        traffic = Traffic(prod_url, seed=1, size=20, rate=5.0)
        with serve(create_app(traffic)) as traffic_url:
            import os

            os.environ["PILOT_TRAFFIC_URL"] = traffic_url
            try:
                assert code(lambda: cli.traffic_main(["rate", "8"])) == 0
                assert code(lambda: cli.traffic_main(["start"])) == 0
                assert code(lambda: cli.traffic_main(["pause"])) == 0
                assert code(lambda: cli.traffic_main(["metrics"])) == 0
            finally:
                del os.environ["PILOT_TRAFFIC_URL"]
                traffic.stop()
    assert "sha256:" in capsys.readouterr().out
