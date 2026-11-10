"""T006: file store and file checks (contracts/storage.md)."""

import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from adlc.config.settings import DEFAULT_ATTACHMENT_TYPES
from adlc.ledger.storage import AttachmentRefused, FileStore, structured_hash

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _office(*names: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        for name in names:
            z.writestr(name, "x")
    return buffer.getvalue()


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return FileStore(tmp_path / "files", max_bytes=1000, allowed_types=DEFAULT_ATTACHMENT_TYPES)


def test_store_read_and_dedupe(store: FileStore) -> None:
    data = b"hello ledger"
    ref = store.put(data, "text/plain")
    digest = hashlib.sha256(data).hexdigest()
    assert ref.content_hash == f"sha256:{digest}" and ref.size == len(data)
    path = store.root / digest[0:2] / digest[2:4] / digest
    assert path.read_bytes() == data
    assert store.put(data, "text/plain") == ref
    assert len(list(store.root.rglob("*"))) == 3  # two folders and one file
    assert store.open(ref.content_hash) == data
    assert store.open("sha256:" + "0" * 64) is None


@pytest.mark.parametrize(
    ("data", "media_type", "reason"),
    [
        (b"x" * 1001, "text/plain", "larger than"),
        (b"x", "application/x-msdownload", "not an allowed type"),
        (b"not a zip", DOCX, "not a valid Office file"),
        (_office("xl/vbaProject.bin"), XLSX, "macros"),
        (b"%PDX-1.4", "application/pdf", "not a PDF"),
        (b"PNG?", "image/png", "not a PNG"),
        (b"\xff\xfe<svg>", "image/svg+xml", "not UTF-8"),
        (b"plain text no svg", "image/svg+xml", "not an SVG"),
        (b"\xff\xfe\xfd", "text/plain", "not UTF-8"),
    ],
)
def test_refusals(store: FileStore, data: bytes, media_type: str, reason: str) -> None:
    with pytest.raises(AttachmentRefused, match=reason):
        store.put(data, media_type)


@pytest.mark.parametrize(
    ("data", "media_type"),
    [
        (_office("xl/workbook.xml"), XLSX),
        (_office("word/document.xml"), DOCX),
        (b"%PDF-1.7 rest", "application/pdf"),
        (PNG, "image/png"),
        (b"<?xml version='1.0'?><svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml"),
        ("# notes ✓".encode(), "text/markdown"),
    ],
)
def test_accepted(store: FileStore, data: bytes, media_type: str) -> None:
    assert store.put(data, media_type).media_type == media_type


def test_unwritable_root(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    store = FileStore(blocker / "files", max_bytes=100, allowed_types=frozenset({"text/plain"}))
    with pytest.raises(AttachmentRefused, match="file store"):
        store.put(b"x", "text/plain")


def test_structured_hash_ignores_key_order() -> None:
    assert structured_hash([{"a": 1, "b": 2}]) == structured_hash([{"b": 2, "a": 1}])
    assert structured_hash([{"a": 1}, {"a": 2}]) != structured_hash([{"a": 2}, {"a": 1}])
