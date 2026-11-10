"""L5 version rules (research R-10; V-24, V-25).

``compare`` classifies the change between two versions of a file generically (no terminal
knowledge): descriptive text only → patch; additions only → minor; any removal or changed
value → major. It is reused by registration against the registry baseline.
"""

import enum
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from adlc.spec_toolkit.findings import Finding
from adlc.spec_toolkit.loader import FRONT_MATTER, LoadedFile
from adlc.spec_toolkit.normalise import normalise
from adlc.spec_toolkit.rules import REGISTRY, Context

# Keys whose values are prose: changing them never changes behaviour.
DESCRIPTIVE_KEYS = frozenset(
    {
        "description",
        "text",
        "notes",
        "purpose",
        "name",
        "title",
        "examples",
        "reason",
        "responsibility",
    }
)


class BumpLevel(enum.IntEnum):
    NONE = 0
    PATCH = 1
    MINOR = 2
    MAJOR = 3


def parse_semver(value: Any) -> tuple[int, int, int] | None:
    try:
        major, minor, patch = (int(p) for p in str(value).split("."))
    except ValueError:
        return None
    return major, minor, patch


def _fmt(version: tuple[int, int, int]) -> str:
    return ".".join(map(str, version))


def bump_between(old: tuple[int, int, int], new: tuple[int, int, int]) -> BumpLevel:
    if new[0] > old[0]:
        return BumpLevel.MAJOR
    if new[0] == old[0] and new[1] > old[1]:
        return BumpLevel.MINOR
    if new[:2] == old[:2] and new[2] > old[2]:
        return BumpLevel.PATCH
    return BumpLevel.NONE


def _keyed(items: list[Any]) -> dict[str, Any] | None:
    """Lists of mappings with a unique id/name are compared by key, not position."""
    keys: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict):
            return None
        key = item.get("id", item.get("name", item.get("role")))
        if key is None or str(key) in keys:
            return None
        keys[str(key)] = item
    return keys


def _diff(old: Any, new: Any, key: str | None) -> BumpLevel:
    descriptive = key in DESCRIPTIVE_KEYS
    if isinstance(old, dict) and isinstance(new, dict):
        level = BumpLevel.NONE
        for k in old.keys() - new.keys():
            level = max(level, BumpLevel.PATCH if k in DESCRIPTIVE_KEYS else BumpLevel.MAJOR)
        for k in new.keys() - old.keys():
            level = max(level, BumpLevel.PATCH if k in DESCRIPTIVE_KEYS else BumpLevel.MINOR)
        for k in old.keys() & new.keys():
            level = max(level, _diff(old[k], new[k], k))
        return level
    if isinstance(old, list) and isinstance(new, list):
        old_keyed, new_keyed = _keyed(old), _keyed(new)
        if old_keyed is not None and new_keyed is not None:
            return _diff(old_keyed, new_keyed, key)
        old_set = {normalise(v) for v in old}
        new_set = {normalise(v) for v in new}
        if old_set == new_set:
            return BumpLevel.NONE
        if descriptive:
            return BumpLevel.PATCH
        if old_set <= new_set:
            return BumpLevel.MINOR
        return BumpLevel.MAJOR
    if normalise(old) == normalise(new):
        return BumpLevel.NONE
    return BumpLevel.PATCH if descriptive else BumpLevel.MAJOR


def _without_version(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    copy = dict(data)
    copy.pop("version", None)
    if isinstance(copy.get("terminal"), dict):
        terminal = dict(copy["terminal"])
        meta = dict(terminal.get("metadata") or {})
        meta.pop("version", None)
        terminal["metadata"] = meta
        copy["terminal"] = terminal
    return copy


def compare(baseline: Any, current: Any) -> BumpLevel:
    """Minimum version bump the change from ``baseline`` to ``current`` requires."""
    return _diff(_without_version(baseline), _without_version(current), None)


def version_of(loaded: LoadedFile) -> Any:
    data = loaded.data if isinstance(loaded.data, dict) else {}
    if loaded.kind == "terminal":
        return (data.get("terminal") or {}).get("metadata", {}).get("version")
    return data.get("version")


def version_pointer(loaded: LoadedFile) -> str:
    return "/terminal/metadata/version" if loaded.kind == "terminal" else "/version"


def check_bump(
    ctx: Context,
    loaded: LoadedFile,
    baseline_data: Any,
    baseline_text: str | None,
    baseline_label: str,
) -> Iterator[Finding]:
    old_v, new_v = (
        parse_semver(version_of_data(loaded.kind, baseline_data)),
        parse_semver(version_of(loaded)),
    )
    if old_v is None or new_v is None:
        return
    pointer = version_pointer(loaded)
    if new_v < old_v:
        yield ctx.finding(
            "V-25",
            loaded.rel,
            pointer,
            f"version {_fmt(new_v)} is lower than {baseline_label} {_fmt(old_v)}",
        )
        return
    if loaded.kind == "playbook":
        needed = BumpLevel.PATCH if baseline_text != loaded.text else BumpLevel.NONE
    else:
        needed = compare(baseline_data, loaded.data)
    actual = bump_between(old_v, new_v)
    if needed > actual:
        yield ctx.finding(
            "V-24",
            loaded.rel,
            pointer,
            f"content changed ({needed.name.lower()} change) but version "
            f"{_fmt(old_v)} → {_fmt(new_v)} versus {baseline_label}",
        )


def version_of_data(kind: str, data: Any) -> Any:
    if not isinstance(data, dict):
        return None
    if kind == "terminal":
        return (data.get("terminal") or {}).get("metadata", {}).get("version")
    return data.get("version")


def _git_show(cwd: Path, ref: str, path: str) -> str | None:
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "show", f"{ref}:{path}"],  # noqa: S607 - git from PATH by design
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def _git_toplevel(cwd: Path) -> Path | None:
    result = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--show-toplevel"],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return Path(result.stdout.strip()) if result.returncode == 0 else None


def _ref_exists(cwd: Path, ref: str) -> bool:
    result = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _load_text(kind: str, text: str) -> Any:
    try:
        if kind == "playbook":
            match = FRONT_MATTER.match(text)
            return YAML(typ="safe").load(match.group(1)) if match else None
        return YAML(typ="safe").load(text)
    except YAMLError:
        return None


@REGISTRY.rule("V-24", "L5", "error", "Changed content needs a sufficient version bump")
def v24_bump_against_git(ctx: Context) -> Iterator[Finding]:
    if not ctx.use_git_baseline or not ctx.baseline_ref:
        return
    ref = ctx.baseline_ref
    top = _git_toplevel(ctx.bundle.root)
    if top is None or not _ref_exists(ctx.bundle.root, ref):
        yield ctx.finding(
            "V-24",
            "",
            "",
            f"baseline {ref} unavailable; version-bump checks against git skipped",
            severity="warning",
        )
        return
    for loaded in ctx.bundle.files():
        if loaded.parse_failed or loaded.schema_failed:
            continue
        repo_path = (ctx.bundle.root / loaded.rel).resolve().relative_to(top.resolve()).as_posix()
        text = _git_show(ctx.bundle.root, ref, repo_path)
        if text is None:
            continue  # new file: nothing to compare with
        baseline = _load_text(loaded.kind, text)
        if baseline is None:
            continue
        yield from check_bump(ctx, loaded, baseline, text, ref)


REGISTRY.declare("V-25", "L5", "error", "Version never decreases versus the baseline")
