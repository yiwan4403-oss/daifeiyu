"""SQLite 连接与 schema（v1）。"""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS identity (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    core_persona TEXT DEFAULT '',
    preferences_json TEXT DEFAULT '{}',
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS persona_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL, field TEXT, old_value TEXT, new_value TEXT,
    reason TEXT, approved_by TEXT
);

CREATE TABLE IF NOT EXISTS emotion_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    dims TEXT DEFAULT '{}',
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    type TEXT NOT NULL,
    scope TEXT DEFAULT 'private',
    source TEXT DEFAULT 'user',
    actor TEXT DEFAULT '',
    payload TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT DEFAULT 'self',
    confidence REAL DEFAULT 0.5,
    verified INTEGER DEFAULT 0,
    salience REAL DEFAULT 0.5,
    last_access REAL,
    ts REAL NOT NULL,
    decay_state TEXT DEFAULT 'active',
    links TEXT DEFAULT '[]'
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(content, tokenize='unicode61');

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memory_fts(memory_fts, rowid, content) VALUES ('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
  INSERT INTO memory_fts(memory_fts, rowid, content) VALUES ('delete', old.id, old.content);
  INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    scope TEXT DEFAULT 'private',
    familiarity REAL DEFAULT 0,
    trust REAL DEFAULT 0,
    affinity REAL DEFAULT 0,
    status TEXT DEFAULT '',
    known_json TEXT DEFAULT '[]',
    unverified_json TEXT DEFAULT '[]',
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS desires (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    strength REAL DEFAULT 0.5,
    source TEXT DEFAULT 'self',
    created_at REAL
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    desire_id INTEGER,
    priority INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    created_at REAL,
    parent_id INTEGER
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER,
    text TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    attempts INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL, actor TEXT, action TEXT, resource TEXT, result TEXT, detail TEXT
);

CREATE TABLE IF NOT EXISTS model_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL, task_class TEXT, model TEXT,
    in_tokens INTEGER, out_tokens INTEGER, cost_est REAL, ok INTEGER
);
"""


def open_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
