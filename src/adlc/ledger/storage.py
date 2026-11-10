"""Content store (contracts/storage.md; research R-01).

One interface, keyed by SHA-256:

* structured content (table rows, records, references) goes in ``ledger.content_blob`` on the
  caller's connection, so it commits with the run's close;
* files (Word, Excel, PDF, images, text) go in a content-addressed folder, written before the
  database row that refers to them. An S3-compatible store can replace the folder later.
"""

import hashlib
import io
import os
import tempfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import Connection

from adlc.ledger import store
from adlc.orchestration.tracing import span
from adlc.spec_toolkit.normalise import content_hash

PREFIX = "sha256:"
OFFICE = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class AttachmentRefused(Exception):
    """A file that is too large, of a type not allowed, not what it claims, or not storable."""


@dataclass(frozen=True)
class FileRef:
    content_hash: str
    size: int
    media_type: str


def structured_hash(value: Any) -> str:
    """Hash of the normal form (key order ignored, row order kept)."""
    return content_hash(value)


def file_hash(data: bytes) -> str:
    return PREFIX + hashlib.sha256(data).hexdigest()


def check_file(data: bytes, media_type: str, max_bytes: int, allowed: Iterable[str]) -> None:
    if len(data) > max_bytes:
        raise AttachmentRefused(f"file is larger than {max_bytes} bytes ({len(data)})")
    if media_type not in set(allowed):
        raise AttachmentRefused(f"{media_type} is not an allowed type")
    if media_type in OFFICE:
        if not zipfile.is_zipfile(io.BytesIO(data)):
            raise AttachmentRefused("not a valid Office file")
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            names = package.namelist()
        if "[Content_Types].xml" not in names:
            raise AttachmentRefused("not a valid Office file")
        if any(name.lower().endswith("vbaproject.bin") for name in names):
            raise AttachmentRefused("Office files with macros are not accepted")
    elif media_type == "application/pdf" and not data.startswith(b"%PDF-"):
        raise AttachmentRefused("not a PDF")
    elif media_type == "image/png" and not data.startswith(PNG_SIGNATURE):
        raise AttachmentRefused("not a PNG")
    elif media_type.startswith("text/") or media_type == "image/svg+xml":
        try:
            decoded = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AttachmentRefused("not UTF-8 text") from exc
        if media_type == "image/svg+xml" and "<svg" not in decoded:
            raise AttachmentRefused("not an SVG")


class FileStore:
    """Files at ``<root>/<aa>/<bb>/<hex>``; written through a temporary file and a rename."""

    def __init__(self, root: Path, *, max_bytes: int, allowed_types: Iterable[str]) -> None:
        self.root = root
        self.max_bytes = max_bytes
        self.allowed_types = frozenset(allowed_types)

    def path(self, digest: str) -> Path:
        hexdigest = digest.removeprefix(PREFIX)
        return self.root / hexdigest[0:2] / hexdigest[2:4] / hexdigest

    def put(self, data: bytes, media_type: str) -> FileRef:
        check_file(data, media_type, self.max_bytes, self.allowed_types)
        digest = file_hash(data)
        target = self.path(digest)
        with span("ledger", "store_file"):
            try:
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=".upload-")
                    with os.fdopen(handle, "wb") as out:
                        out.write(data)
                    os.replace(temporary, target)
            except OSError as exc:
                raise AttachmentRefused(
                    f"the file store cannot be written ({type(exc).__name__})"
                ) from exc
        return FileRef(digest, len(data), media_type)

    def open(self, digest: str) -> bytes | None:
        target = self.path(digest)
        return target.read_bytes() if target.is_file() else None


class ContentStore(Protocol):
    def put_structured(self, conn: Connection, value: Any) -> str: ...

    def get_structured(self, conn: Connection, digest: str) -> Any | None: ...

    def put_file(self, conn: Connection, data: bytes, media_type: str) -> FileRef: ...

    def open_file(self, digest: str) -> bytes | None: ...


class LedgerContentStore:
    """Structured content in the database, files in a ``FileStore`` (the MVP implementation)."""

    def __init__(self, files: FileStore) -> None:
        self.files = files

    def put_structured(self, conn: Connection, value: Any) -> str:
        digest = structured_hash(value)
        store.insert_blob(conn, digest, value)
        return digest

    def get_structured(self, conn: Connection, digest: str) -> Any | None:
        return store.load_blob(conn, digest)

    def put_file(self, conn: Connection, data: bytes, media_type: str) -> FileRef:
        ref = self.files.put(data, media_type)  # the file exists before its row commits
        store.insert_file_object(conn, ref.content_hash, ref.size, ref.media_type)
        return ref

    def open_file(self, digest: str) -> bytes | None:
        return self.files.open(digest)
