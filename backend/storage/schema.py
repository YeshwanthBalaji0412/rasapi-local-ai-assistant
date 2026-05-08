"""
SQL schema for the RasaPi local store (Phase 3).

CREATE TABLE statements are idempotent (IF NOT EXISTS), so init_db() can run
on every startup without migration tooling. Phase 3 has no schema migrations;
later phases will introduce a versioning column when needed.
"""

NOTES_TABLE = """
CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    content     TEXT    NOT NULL,
    tags        TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT,
    archived    INTEGER NOT NULL DEFAULT 0
)
"""

TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'open',
    priority      TEXT    NOT NULL DEFAULT 'normal',
    due_date      TEXT,
    created_at    TEXT    NOT NULL,
    completed_at  TEXT
)
"""

MEMORY_TABLE = """
CREATE TABLE IF NOT EXISTS memory_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT,
    value       TEXT    NOT NULL,
    category    TEXT    NOT NULL DEFAULT 'general',
    created_at  TEXT    NOT NULL,
    updated_at  TEXT,
    archived    INTEGER NOT NULL DEFAULT 0
)
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)",
    "CREATE INDEX IF NOT EXISTS idx_memory_archived ON memory_items(archived)",
    "CREATE INDEX IF NOT EXISTS idx_notes_archived ON notes(archived)",
]

ALL_STATEMENTS = [NOTES_TABLE, TASKS_TABLE, MEMORY_TABLE, *INDEXES]
