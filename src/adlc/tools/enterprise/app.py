"""``adlc-tools`` (feature 010, research R-01): the eval store and the enterprise mocks, on the
platform network with the app database role. Servers are those whose registry host is ``tools``."""

from sqlalchemy import Engine
from starlette.applications import Starlette

from adlc.config.settings import ToolsSettings
from adlc.tools.catalogue import CATALOGUE
from adlc.tools.enterprise.records import EnterpriseStore
from adlc.tools.enterprise.servers import handlers
from adlc.tools.mcp_app import ServerTools, build_app
from adlc.tools.registry import Registry

HOST = "tools"


def build_tools(settings: ToolsSettings, engine: Engine) -> Starlette:
    registry = Registry.load(settings.spec_dir)
    registry.check()
    found = handlers(EnterpriseStore(engine), settings.controls_file)
    servers = {s.id: ServerTools(CATALOGUE.for_server(s.id), found) for s in registry.on_host(HOST)}
    hosts = [h.strip() for h in settings.tools_allowed_hosts.split(",") if h.strip()]
    return build_app("adlc-tools", servers, settings.tools_token_key.get_secret_value(), hosts)
