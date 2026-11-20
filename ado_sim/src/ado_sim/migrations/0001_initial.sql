-- ADO simulator schema, version 1 (specs/015-ado-sim-api/data-model.md).
-- Times are ISO 8601 text in UTC with microseconds; JSON columns hold text.

CREATE TABLE organization (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE project (
    id              TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organization (id),
    name            TEXT NOT NULL,
    UNIQUE (organization_id, name)
);

CREATE TABLE area_node (
    id         INTEGER PRIMARY KEY,
    identifier TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL REFERENCES project (id),
    name       TEXT NOT NULL,
    path       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    parent_id  INTEGER REFERENCES area_node (id)
);

CREATE TABLE work_item_type (
    name           TEXT PRIMARY KEY COLLATE NOCASE,
    reference_name TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    color          TEXT NOT NULL DEFAULT '009CCC',
    ordinal        INTEGER NOT NULL
);

CREATE TABLE work_item_type_state (
    type_name TEXT NOT NULL REFERENCES work_item_type (name),
    name      TEXT NOT NULL COLLATE NOCASE,
    category  TEXT NOT NULL
              CHECK (category IN ('Proposed', 'InProgress', 'Resolved', 'Completed', 'Removed')),
    color     TEXT NOT NULL DEFAULT 'b2b2b2',
    ordinal   INTEGER NOT NULL,
    PRIMARY KEY (type_name, name)
);

CREATE TABLE field (
    reference_name TEXT PRIMARY KEY COLLATE NOCASE,
    name           TEXT NOT NULL,
    type           TEXT NOT NULL CHECK (type IN ('string', 'plainText', 'html', 'integer',
                                                 'double', 'dateTime', 'boolean', 'identity',
                                                 'treePath', 'history')),
    read_only      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE work_item_type_field (
    type_name      TEXT NOT NULL REFERENCES work_item_type (name),
    reference_name TEXT NOT NULL REFERENCES field (reference_name),
    allowed_values TEXT,
    PRIMARY KEY (type_name, reference_name)
);

CREATE TABLE identity (
    id           TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    unique_name  TEXT NOT NULL UNIQUE COLLATE NOCASE,
    active       INTEGER NOT NULL DEFAULT 1
);

-- Never holds a token: only its HMAC-SHA256 with ADO_SIM_TOKEN_KEY (FR-017).
CREATE TABLE access_token (
    id          INTEGER PRIMARY KEY,
    identity_id TEXT NOT NULL REFERENCES identity (id),
    token_hash  TEXT NOT NULL UNIQUE,
    label       TEXT NOT NULL DEFAULT '',
    issued_at   TEXT NOT NULL,
    revoked_at  TEXT
);

-- Current state of each work item; ids are allocated from 1 upward and never reused.
CREATE TABLE work_item (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    type_name     TEXT NOT NULL REFERENCES work_item_type (name),
    rev           INTEGER NOT NULL,
    fields        TEXT NOT NULL,
    changed_date  TEXT NOT NULL,
    state         TEXT NOT NULL,
    area_path     TEXT NOT NULL,
    comment_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX work_item_changed_date ON work_item (changed_date);
CREATE INDEX work_item_state ON work_item (state);
CREATE INDEX work_item_area_path ON work_item (area_path);
CREATE INDEX work_item_type_name ON work_item (type_name);

-- One row per revision: the full fields and relations as of that revision. Append-only.
CREATE TABLE revision (
    work_item_id INTEGER NOT NULL REFERENCES work_item (id),
    rev          INTEGER NOT NULL,
    fields       TEXT NOT NULL,
    relations    TEXT NOT NULL,
    PRIMARY KEY (work_item_id, rev)
);

-- One row per change (ADO's "updates"). Append-only. A change that creates a revision has
-- revision_bearing = 1; a link added or removed from the other item records an update on this
-- item with the same rev and no revision (as ADO).
CREATE TABLE work_item_update (
    work_item_id     INTEGER NOT NULL REFERENCES work_item (id),
    id               INTEGER NOT NULL,
    rev              INTEGER NOT NULL,
    revision_bearing INTEGER NOT NULL,
    revised_by       TEXT NOT NULL REFERENCES identity (id),
    change_date      TEXT NOT NULL,
    fields           TEXT NOT NULL,
    relations        TEXT NOT NULL,
    PRIMARY KEY (work_item_id, id)
);

-- Current links, both directions stored explicitly; rowid order is the relation index.
CREATE TABLE relation (
    source_id  INTEGER NOT NULL REFERENCES work_item (id),
    target_id  INTEGER NOT NULL REFERENCES work_item (id),
    rel        TEXT NOT NULL,
    attributes TEXT NOT NULL,
    PRIMARY KEY (source_id, target_id, rel)
);
CREATE INDEX relation_target ON relation (target_id, rel);

CREATE TABLE comment (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    work_item_id  INTEGER NOT NULL REFERENCES work_item (id),
    version       INTEGER NOT NULL DEFAULT 1,
    text          TEXT NOT NULL,
    created_by    TEXT NOT NULL REFERENCES identity (id),
    created_date  TEXT NOT NULL,
    modified_date TEXT NOT NULL
);
CREATE INDEX comment_work_item ON comment (work_item_id, id);

CREATE TRIGGER revision_append_only_update BEFORE UPDATE ON revision
BEGIN SELECT RAISE(ABORT, 'revision rows are append-only'); END;
CREATE TRIGGER revision_append_only_delete BEFORE DELETE ON revision
BEGIN SELECT RAISE(ABORT, 'revision rows are append-only'); END;
CREATE TRIGGER work_item_update_append_only_update BEFORE UPDATE ON work_item_update
BEGIN SELECT RAISE(ABORT, 'work_item_update rows are append-only'); END;
CREATE TRIGGER work_item_update_append_only_delete BEFORE DELETE ON work_item_update
BEGIN SELECT RAISE(ABORT, 'work_item_update rows are append-only'); END;
