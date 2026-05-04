from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

APP_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = APP_ROOT / "decksweep.db"
DB_LOCK = threading.RLock()


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def read_conn() -> Iterator[sqlite3.Connection]:
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def write_conn() -> Iterator[sqlite3.Connection]:
    with DB_LOCK:
        connection = get_connection()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def init_db() -> None:
    with write_conn() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                root_path TEXT NOT NULL,
                include_hidden INTEGER NOT NULL DEFAULT 0,
                order_mode TEXT NOT NULL DEFAULT 'random',
                status TEXT NOT NULL DEFAULT 'scanning',
                score INTEGER NOT NULL DEFAULT 0,
                streak INTEGER NOT NULL DEFAULT 0,
                max_streak INTEGER NOT NULL DEFAULT 0,
                root_size_bytes INTEGER NOT NULL DEFAULT 0,
                indexed_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                applied_at TEXT
            );

            CREATE TABLE IF NOT EXISTS decks (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                parent_folder_item_id TEXT,
                name TEXT NOT NULL,
                total_cards INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                path TEXT NOT NULL,
                name TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('file', 'folder')),
                deck_id TEXT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
                parent_id TEXT,
                depth INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                percent_of_root REAL NOT NULL DEFAULT 0,
                mime TEXT,
                modified_at TEXT,
                created_at TEXT,
                accessed_at TEXT,
                is_hidden INTEGER NOT NULL DEFAULT 0,
                is_system INTEGER NOT NULL DEFAULT 0,
                random_rank REAL NOT NULL DEFAULT 0,
                UNIQUE(session_id, path)
            );

            CREATE TABLE IF NOT EXISTS decisions (
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                action TEXT NOT NULL CHECK(action IN ('keep', 'delete')),
                decided_at TEXT NOT NULL,
                PRIMARY KEY (session_id, item_id)
            );

            CREATE TABLE IF NOT EXISTS skipped_folders (
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                skipped_at TEXT NOT NULL,
                PRIMARY KEY (session_id, item_id)
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
            CREATE INDEX IF NOT EXISTS idx_decks_session ON decks(session_id);
            CREATE INDEX IF NOT EXISTS idx_items_session_deck ON items(session_id, deck_id);
            CREATE INDEX IF NOT EXISTS idx_items_session_parent ON items(session_id, parent_id);
            CREATE INDEX IF NOT EXISTS idx_items_session_depth ON items(session_id, depth DESC);
            CREATE INDEX IF NOT EXISTS idx_decisions_session_action ON decisions(session_id, action);
            """
        )
