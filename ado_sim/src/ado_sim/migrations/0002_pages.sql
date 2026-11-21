-- ADO simulator schema, version 2: pages (specs/017-ado-sim-board/data-model.md).

-- A page password per identity; only its scrypt hash is kept (FR-002).
CREATE TABLE page_password (
    identity_id   TEXT PRIMARY KEY REFERENCES identity (id),
    password_hash TEXT NOT NULL,
    set_at        TEXT NOT NULL
);

-- A page session per sign-in; only the SHA-256 of the cookie's session id is kept (FR-003).
CREATE TABLE page_session (
    session_hash TEXT PRIMARY KEY,
    identity_id  TEXT NOT NULL REFERENCES identity (id),
    csrf_token   TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    revoked_at   TEXT NULL
);
CREATE INDEX page_session_identity ON page_session (identity_id);

-- The seed's board settings (type, card fields, collapsed states, refresh), JSON values.
CREATE TABLE board_setting (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- The platform's service account never signs in to pages (seed `service: true`).
ALTER TABLE identity ADD COLUMN is_service INTEGER NOT NULL DEFAULT 0;
