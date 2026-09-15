import json
import sqlite3
import time
from contextlib import contextmanager
from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','member')), disabled INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 csrf TEXT NOT NULL, expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS login_attempts (key TEXT PRIMARY KEY, count INTEGER NOT NULL, until REAL NOT NULL);
CREATE TABLE IF NOT EXISTS knowledge_bases (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assistants (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), name TEXT NOT NULL,
 instructions TEXT NOT NULL, kb_id INTEGER REFERENCES knowledge_bases(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS documents (
 id INTEGER PRIMARY KEY, kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
 name TEXT NOT NULL, sha256 TEXT NOT NULL, pdf BLOB NOT NULL, size INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued', progress INTEGER NOT NULL DEFAULT 0,
 error TEXT, pages INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL,
 UNIQUE(kb_id, sha256)
);
CREATE TABLE IF NOT EXISTS chunks (
 id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 page INTEGER NOT NULL, text TEXT NOT NULL, vector BLOB, embedding_id TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, content='chunks', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
 INSERT INTO chunks_fts(rowid,text) VALUES(new.id,new.text); END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
 INSERT INTO chunks_fts(chunks_fts,rowid,text) VALUES('delete',old.id,old.text); END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
 INSERT INTO chunks_fts(chunks_fts,rowid,text) VALUES('delete',old.id,old.text);
 INSERT INTO chunks_fts(rowid,text) VALUES(new.id,new.text); END;
CREATE TABLE IF NOT EXISTS conversations (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), title TEXT NOT NULL,
 assistant_id INTEGER REFERENCES assistants(id) ON DELETE SET NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY, conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 role TEXT NOT NULL, content TEXT NOT NULL, sources TEXT NOT NULL DEFAULT '[]',
 status TEXT NOT NULL DEFAULT 'complete', created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS messages_conversation ON messages(conversation_id,id);
CREATE INDEX IF NOT EXISTS documents_kb ON documents(kb_id);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(settings.db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA synchronous=FULL")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def initialize():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > 2:
            raise RuntimeError("Database belongs to a newer Nelsonict AI release.")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        # Serialize migration across API/worker startup; existing v1 data stays intact.
        conn.execute("BEGIN IMMEDIATE")
        columns = {r[1] for r in conn.execute("PRAGMA table_info(documents)")}
        if "format" not in columns:
            conn.execute("ALTER TABLE documents ADD COLUMN format TEXT NOT NULL DEFAULT 'pdf'")
        columns = {r[1] for r in conn.execute("PRAGMA table_info(chunks)")}
        if "location" not in columns:
            conn.execute("ALTER TABLE chunks ADD COLUMN location TEXT")
        conn.execute("CREATE TABLE IF NOT EXISTS knowledge_members (kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, permission TEXT NOT NULL CHECK(permission IN ('reader','editor')), PRIMARY KEY(kb_id,user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS model_profiles (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, config TEXT NOT NULL)")
        columns = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
        if "knowledge_id" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN knowledge_id INTEGER")
        conn.execute("PRAGMA user_version=2")


def rows(sql, params=()):
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def one(sql, params=()):
    result = rows(sql, params)
    return result[0] if result else None


def execute(sql, params=()):
    with connect() as conn:
        return conn.execute(sql, params).lastrowid


def get_setting(key, default=None):
    row = one("SELECT value FROM settings WHERE key=?", (key,))
    return json.loads(row["value"]) if row else default


def set_setting(key, value):
    execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)))


def audit(action, actor):
    # Administrative metadata only: never log credentials or document text.
    set_setting("last_admin_action", {"action": action, "actor": actor, "at": time.time()})
