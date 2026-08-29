"""
Tiny SQLite-backed state store. Every alert-worthy item gets a stable,
source-prefixed unique ID before it's checked here — that's what makes
the bot idempotent across restarts and poll cycles.

ID conventions used elsewhere in this project:
  yc:<company-slug>
  speedrun:<company-slug>
  x:<tweet-id>
  linkedin:<post-or-page-id>
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from config import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_items (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    company_name TEXT,
    detected_at TEXT NOT NULL
);
"""


@contextmanager
def _connect():
    conn = sqlite3.connect(config.DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.execute(SCHEMA)
        conn.commit()


def is_seen(item_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM seen_items WHERE id = ?", (item_id,)
        ).fetchone()
        return row is not None


def mark_seen(item_id: str, source: str, company_name: str = "") -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen_items (id, source, company_name, detected_at) "
            "VALUES (?, ?, ?, ?)",
            (item_id, source, company_name, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
