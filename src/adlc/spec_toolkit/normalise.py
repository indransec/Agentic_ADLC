"""Normalised form and content hashes (research R-09; SA Annex A.5 ``sha256:<hex>``).

Formatting-only changes (comments, key order, whitespace) do not change the normalised form,
so they never require a new version (FR-023). Playbooks hash their full text, because their
body is content.
"""

import hashlib
import json
from typing import Any


def normalise(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(data: Any) -> str:
    return _sha256(normalise(data))


def file_hash(text: str) -> str:
    return _sha256(text)
