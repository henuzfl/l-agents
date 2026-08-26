import json
import sqlite3
from pathlib import Path
from typing import Any


class KnowledgeDocumentRegistry:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    task_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    object_name TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def save(self, payload: dict[str, Any]) -> None:
        serialized = json.dumps(payload, ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_documents (
                    task_id, filename, object_name, status, payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    filename=excluded.filename,
                    object_name=excluded.object_name,
                    status=excluded.status,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["task_id"],
                    payload["filename"],
                    payload["object_name"],
                    payload["status"],
                    serialized,
                    payload["created_at"],
                    payload["updated_at"],
                ),
            )

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM knowledge_documents WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM knowledge_documents
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def delete(self, task_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM knowledge_documents WHERE task_id = ?",
                (task_id,),
            )
