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
    links TEXT DEFAULT '[]',
    meta TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS beliefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    source TEXT NOT NULL,          -- user / external / self / llm / hypothesis
    verified INTEGER DEFAULT 0,    -- 模型输出不得自动标 1
    confidence REAL DEFAULT 0.5,
    ts REAL NOT NULL,
    updated_at REAL
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(content, tokenize='unicode61');

-- 本环境 sqlite 对 fts5 'delete' 特令报 SQL logic error：
-- 索引同步改为代码维护（见 memory/manager.py），触发器一律移除。
DROP TRIGGER IF EXISTS memories_ai;
DROP TRIGGER IF EXISTS memories_ad;
DROP TRIGGER IF EXISTS memories_au;

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
    # check_same_thread=False：记忆仲裁经 asyncio.to_thread 在别的线程写库，
    # 单进程顺序使用下安全；并发写保护由 Phase 2 锁机制补。
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    # 迁移：旧库补 meta 列
    try:
        conn.execute("ALTER TABLE memories ADD COLUMN meta TEXT DEFAULT '{}'")
    except sqlite3.OperationalError:
        pass
    conn.commit()
