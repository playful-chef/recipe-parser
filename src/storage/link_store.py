from __future__ import annotations

import sqlite3
import threading
import time
import os
from pathlib import Path
from typing import Iterable

from ..core.logging import get_logger

LOGGER = get_logger(__name__)


class LinkStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._wal_disabled = _env_flag("SCRAPER_DISABLE_WAL")
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._setup()

    def _setup(self) -> None:
        with self._conn:
            if not self._wal_disabled:
                try:
                    self._conn.execute("PRAGMA journal_mode=WAL;")
                except sqlite3.DatabaseError as exc:
                    LOGGER.warning(
                        "Unable to enable SQLite WAL journaling (%s); falling back to default mode",
                        exc,
                    )
                    self._wal_disabled = True
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS urls (
                    url TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    leased_at REAL,
                    first_seen REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    def add_links(self, urls: Iterable[str]) -> int:
        now = time.time()
        unique_urls = list(dict.fromkeys(urls))
        if not unique_urls:
            return 0

        rows = [(url, now, now) for url in unique_urls]
        inserted = 0
        with self._lock, self._conn:
            before = self._conn.total_changes
            self._conn.executemany(
                """
                INSERT INTO urls (url, status, first_seen, updated_at)
                VALUES (?, 'pending', ?, ?)
                ON CONFLICT(url) DO NOTHING
                """,
                rows,
            )
            inserted = self._conn.total_changes - before

            if inserted < len(rows):
                self._conn.executemany(
                    """
                    UPDATE urls
                    SET status = 'pending',
                        attempts = 0,
                        last_error = NULL,
                        leased_at = NULL,
                        updated_at = ?
                    WHERE url = ? AND status != 'processed'
                    """,
                    [(now, url) for url in unique_urls],
                )

        return int(inserted)

    def lease_batch(self, limit: int, lease_seconds: float) -> list[str]:
        now = time.time()
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                SELECT url FROM urls
                WHERE status = 'pending'
                   OR (status = 'leased' AND (? - leased_at) >= ?)
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (now, lease_seconds, limit),
            )
            rows = [row["url"] for row in cur.fetchall()]
            if not rows:
                return []
            self._conn.executemany(
                """
                UPDATE urls
                SET status = 'leased', leased_at = ?, updated_at = ?
                WHERE url = ?
                """,
                [(now, now, url) for url in rows],
            )
        return rows

    def ack_success(self, url: str) -> None:
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE urls
                SET status = 'processed', leased_at = NULL, updated_at = ?, last_error = NULL
                WHERE url = ?
                """,
                (now, url),
            )

    def ack_fail(self, url: str, error: str | None, max_attempts: int) -> None:
        now = time.time()
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT attempts FROM urls WHERE url = ?",
                (url,),
            ).fetchone()
            attempts = row["attempts"] if row else 0
            attempts += 1
            status = "failed" if attempts >= max_attempts else "pending"
            leased_at = None
            self._conn.execute(
                """
                UPDATE urls
                SET status = ?, attempts = ?, last_error = ?, leased_at = ?, updated_at = ?
                WHERE url = ?
                """,
                (status, attempts, error, leased_at, now, url),
            )

    def already_parsed(self, url: str) -> bool:
        cur = self._conn.execute(
            "SELECT status FROM urls WHERE url = ?",
            (url,),
        )
        row = cur.fetchone()
        return bool(row and row["status"] == "processed")

    def stats(self) -> dict[str, int]:
        cur = self._conn.execute(
            """
            SELECT status, COUNT(*) as total
            FROM urls
            GROUP BY status
            """
        )
        return {row["status"]: row["total"] for row in cur.fetchall()}

    def close(self) -> None:
        self._conn.close()


def _env_flag(name: str) -> bool:
    value = os.getenv(name)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


