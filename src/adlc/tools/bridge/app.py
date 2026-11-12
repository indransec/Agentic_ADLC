"""The pilot bridge (feature 010, research R-01): every server whose registry ``host`` is
``bridge``, wrapping the pilot's own operations. It is the only service on both networks and
holds no database, model or knowledge settings."""

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from starlette.applications import Starlette

from adlc.config.settings import BridgeSettings
from adlc.tools.bridge import environments, evaluation, git_repo, stores
from adlc.tools.bridge.git_repo import GitRepos
from adlc.tools.bridge.pilot import Pilot, PilotUrls
from adlc.tools.bridge.records import Records
from adlc.tools.catalogue import CATALOGUE
from adlc.tools.mcp_app import Handler, ResourceSpec, ServerTools, build_app
from adlc.tools.registry import Registry

log = logging.getLogger("adlc.tools.bridge")
HOST = "bridge"


def pilot_from(settings: BridgeSettings) -> Pilot:
    return Pilot(
        PilotUrls(
            settings.bridge_pilot_dev_url,
            settings.bridge_pilot_test_url,
            settings.bridge_pilot_prodsim_url,
            settings.bridge_pilot_lab_url,
            settings.bridge_pilot_traffic_url,
        )
    )


def all_handlers(pilot: Pilot, settings: BridgeSettings, records: Records) -> dict[str, Handler]:
    data = Path(settings.bridge_data_dir)
    layout_cache: list[str] = []

    def layout() -> list[str]:
        if not layout_cache:
            layout_cache.extend(pilot.request("GET", pilot.urls.lab, "/layout")["files"])
        return list(layout_cache)

    repos = GitRepos(data / "git", layout, records)
    return {
        **environments.handlers(pilot),
        **git_repo.handlers(repos),
        **stores.handlers(pilot, repos, data, records),
        **evaluation.handlers(pilot, Path(settings.redteam_suite)),
    }


def resources(pilot: Pilot) -> dict[str, tuple[ResourceSpec, ...]]:
    def reader(environment: str) -> Any:
        return lambda: environments.definitions(pilot, environment)

    return {
        "pilot_env": tuple(
            ResourceSpec(
                f"infra://{e}", f"infrastructure definition {e}", "mcp:pilot_env:read", reader(e)
            )
            for e in environments.INFRA_ENVIRONMENTS
        )
    }


def servers_for(
    registry: Registry,
    handlers: Mapping[str, Handler],
    extra: Mapping[str, tuple[ResourceSpec, ...]],
) -> dict[str, ServerTools]:
    servers: dict[str, ServerTools] = {}
    for server in registry.on_host(HOST):
        tools = CATALOGUE.for_server(server.id)
        if not all(t.full_name in handlers for t in tools):
            log.warning("bridge server %s has tools without handlers; not served", server.id)
            continue
        servers[server.id] = ServerTools(tools, handlers, extra.get(server.id, ()))
    return servers


def build_bridge(settings: BridgeSettings, pilot: Pilot | None = None) -> Starlette:
    registry = Registry.load(settings.spec_dir)
    registry.check()
    pilot = pilot or pilot_from(settings)
    records = Records(Path(settings.bridge_data_dir) / "records")
    handlers = all_handlers(pilot, settings, records)
    hosts = [h.strip() for h in settings.bridge_allowed_hosts.split(",") if h.strip()]
    app = build_app(
        "adlc-pilot-bridge",
        servers_for(registry, handlers, resources(pilot)),
        settings.tools_token_key.get_secret_value(),
        hosts,
        audit=records.audit,
    )
    app.state.records = records
    return app
