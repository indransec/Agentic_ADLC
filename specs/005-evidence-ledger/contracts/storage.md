# Contract: Content store

```text
class ContentStore(Protocol):
    put_structured(conn, value) -> str                                   # content hash; idempotent
    get_structured(conn, content_hash) -> Any | None
    put_file(conn, data: bytes, media_type: str) -> FileRef              # hash, size, media_type
    open_file(content_hash) -> bytes | None
    exists(conn, content_hash) -> bool
```

## Rules

- **Structured content**: stored in `ledger.content_blob` on the caller's connection, so it
  commits with the caller.
- **Files**:
  - **Checks**: the media type must be on `ADLC_ATTACHMENT_TYPES`, and the size at most
    `ADLC_ATTACHMENT_MAX` (bytes; `25MB` means 25,000,000). The content must match the type:
    Office files must be ZIP packages without macros (`vbaProject.bin`), PDF must start with
    `%PDF-`, PNG with its signature, SVG and text must decode as UTF-8. Otherwise the file is
    refused (`AttachmentRefused` with the reason). A file store that cannot be written also
    refuses the file.
  - **Writing**: bytes go to `<ADLC_FILE_STORE_DIR>/<h[7:9]>/<h[9:11]>/<hex>`, through a
    temporary file and an atomic rename. An existing file is left as is. The file is written
    before the `ledger.file_object` row, which goes on the caller's connection.
  - **Reading**: `open_file` re-reads the bytes. Verification re-hashes them.
- **Implementations**:
  - **MVP**: `SqlContentStore` (structured content) plus `FileStore` (files), composed as
    `LedgerContentStore`.
  - **Later**: an S3-compatible implementation of the file half. Callers are unchanged.

## Default allowed media types

| Kind | Media type |
| --- | --- |
| Word | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| Excel | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| PDF | `application/pdf` |
| PNG | `image/png` |
| SVG | `image/svg+xml` |
| Plain text | `text/plain` |
| Markdown | `text/markdown` |
