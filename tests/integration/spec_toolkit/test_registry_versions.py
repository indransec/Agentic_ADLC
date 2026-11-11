"""T062: reads use the active version unless a version is named."""

import shutil
from pathlib import Path

from ruamel.yaml import YAML
from sqlalchemy import Engine

from adlc.spec_toolkit.register import register
from adlc.spec_toolkit.registry import SqlSpecRegistry

ROOT = Path(__file__).resolve().parents[3]


def test_active_and_named_versions(
    owner_engine: Engine, app_engine: Engine, tmp_path: Path
) -> None:
    specs = tmp_path / "adlc-specs"
    shutil.copytree(ROOT / "adlc-specs", specs)
    register(specs, owner_engine)

    yaml = YAML()
    path = specs / "terminals" / "T0.yaml"
    data = yaml.load(path.read_text())
    before = str(data["terminal"]["metadata"]["version"])
    after = f"{int(before.split('.')[0]) + 1}.0.0"
    data["terminal"]["timeline"]["max_rework_cycles"] = 4
    data["terminal"]["metadata"]["version"] = after
    with path.open("w") as handle:
        yaml.dump(data, handle)
    register(specs, owner_engine)

    reg = SqlSpecRegistry(app_engine)
    current = reg.timeline("T0", "low")
    old = reg.timeline("T0", "low", version=before)
    assert current is not None and current.max_rework_cycles == 4
    assert old is not None and old.max_rework_cycles == 3
    entry = reg.entry("T0")
    assert entry is not None and (entry.version, entry.status) == (after, "active")
    old_entry = reg.entry("T0", version=before)
    assert old_entry is not None and old_entry.status == "deprecated"
    assert [t.version for t in reg.terminals_opened_by("usecase.submitted")] == [after]
