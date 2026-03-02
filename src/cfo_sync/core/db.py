from __future__ import annotations

import sqlite3
from pathlib import Path

from cfo_sync.core.models import RawRecord


class LocalDatabase:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS raw_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def save(self, client: str, platform: str, resource: str, payload: RawRecord) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO raw_data (client, platform, resource, payload) VALUES (?, ?, ?, ?)",
                (client, platform, resource, str(payload)),
            )
