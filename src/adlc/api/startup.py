"""Startup checks that need the data store (run after ``wait_for_database``).

Role catalogue cross-check (spec 002 FR-025): the identity module reads the role file directly,
so it can work without a data store. At API start, that file must hold exactly the content
of the active registered ``roles`` catalogue; otherwise the API refuses to start.
"""

import logging
from pathlib import Path

from ruamel.yaml import YAML
from sqlalchemy import Engine

from adlc.spec_toolkit.normalise import content_hash
from adlc.spec_toolkit.registry import SqlSpecRegistry

log = logging.getLogger("adlc.startup")


class RoleCatalogueMismatch(RuntimeError):
    """The role file differs from the registered roles catalogue."""


def check_role_catalogue(role_file: Path, engine: Engine) -> None:
    data = YAML(typ="safe").load(role_file.read_text())
    registered = SqlSpecRegistry(engine).catalogue("roles")
    if registered is None:
        log.warning("roles catalogue not registered yet; using %s unchecked", role_file)
        return
    if content_hash(data) != content_hash(registered.content):
        file_version = data.get("version") if isinstance(data, dict) else None
        raise RoleCatalogueMismatch(
            f"role file {role_file} (version {file_version}) differs from registered "
            f"roles {registered.version}; run adlc-spec register or fix ADLC_ROLE_CATALOGUE"
        )
