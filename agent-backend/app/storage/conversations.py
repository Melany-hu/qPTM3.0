"""Persistent conversation storage keyed by client IP (SQLite)."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

DB_PATH = Path(settings.conversations_data_dir) / "agent.db"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                client_ip TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT 'New conversation',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conv_ip_updated
                ON conversations(client_ip, updated_at DESC);

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_msg_conv
                ON messages(conversation_id, id ASC);
        """)


def create_conversation(client_ip: str, title: str = "New conversation") -> dict[str, Any]:
    conv_id = str(uuid.uuid4())
    now = _utcnow()
    title = (title or "New conversation").strip()[:80] or "New conversation"
    with _connect() as conn:
        conn.execute(
            "INSERT INTO conversations (id, client_ip, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (conv_id, client_ip, title, now, now),
        )
    return {"id": conv_id, "title": title, "created_at": now, "updated_at": now}


def list_conversations(client_ip: str, limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, title, created_at, updated_at
               FROM conversations WHERE client_ip = ?
               ORDER BY updated_at DESC LIMIT ?""",
            (client_ip, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_conversation(conversation_id: str, client_ip: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ? AND client_ip = ?",
            (conversation_id, client_ip),
        ).fetchone()
        if not row:
            return None
        messages = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,),
        ).fetchall()
    return {
        **dict(row),
        "messages": [dict(m) for m in messages],
    }


def belongs_to_ip(conversation_id: str, client_ip: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM conversations WHERE id = ? AND client_ip = ?",
            (conversation_id, client_ip),
        ).fetchone()
    return row is not None


def add_message(conversation_id: str, role: str, content: str) -> None:
    now = _utcnow()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, now),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )


def update_title(conversation_id: str, title: str) -> None:
    title = title.strip()[:80] or "New conversation"
    with _connect() as conn:
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, _utcnow(), conversation_id),
        )


def delete_conversation(conversation_id: str, client_ip: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM conversations WHERE id = ? AND client_ip = ?",
            (conversation_id, client_ip),
        )
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    return cur.rowcount > 0
