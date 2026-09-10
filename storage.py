"""Хранилище сообщений для восстановления веток диалога (SQLite, без внешних зависимостей)."""
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StoredMessage:
    chat_id: int
    message_id: int
    role: str  # "user" | "assistant"
    author: str
    text: str
    reply_to: int | None
    created_at: float


class MessageStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    chat_id    INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    role       TEXT    NOT NULL,
                    author     TEXT    NOT NULL,
                    text       TEXT    NOT NULL,
                    reply_to   INTEGER,
                    created_at REAL    NOT NULL,
                    PRIMARY KEY (chat_id, message_id)
                )
                """
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_time ON messages(chat_id, created_at)")
            self._conn.commit()

    def save(self, chat_id: int, message_id: int, role: str, author: str, text: str, reply_to: int | None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO messages VALUES (?, ?, ?, ?, ?, ?, ?)",
                (chat_id, message_id, role, author, text, reply_to, time.time()),
            )
            self._conn.commit()

    def get(self, chat_id: int, message_id: int) -> StoredMessage | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM messages WHERE chat_id = ? AND message_id = ?", (chat_id, message_id)
            ).fetchone()
        return StoredMessage(*row) if row else None

    def thread(self, chat_id: int, last_message_id: int, limit: int) -> list[StoredMessage]:
        """Идём по цепочке ответов вверх от последнего сообщения. Возвращаем в хронологическом порядке."""
        chain: list[StoredMessage] = []
        seen: set[int] = set()
        current: int | None = last_message_id
        while current is not None and current not in seen and len(chain) < limit:
            seen.add(current)
            msg = self.get(chat_id, current)
            if msg is None:
                break
            chain.append(msg)
            current = msg.reply_to
        return list(reversed(chain))

    def recent(self, chat_id: int, limit: int) -> list[StoredMessage]:
        """Последние сообщения чата (для лички, где никто не жмёт «ответить»)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?", (chat_id, limit)
            ).fetchall()
        return [StoredMessage(*r) for r in reversed(rows)]

    def clear_chat(self, chat_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            self._conn.commit()

    def cleanup(self, ttl_days: int) -> int:
        cutoff = time.time() - ttl_days * 86400
        with self._lock:
            cur = self._conn.execute("DELETE FROM messages WHERE created_at < ?", (cutoff,))
            self._conn.commit()
            return cur.rowcount
