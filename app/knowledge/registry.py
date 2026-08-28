from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db_models import KnowledgeDocumentRecord


class KnowledgeDocumentRegistry:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save(self, payload: dict[str, Any]) -> None:
        statement = insert(KnowledgeDocumentRecord).values(
            task_id=payload["task_id"],
            filename=payload["filename"],
            object_name=payload["object_name"],
            status=payload["status"],
            payload=payload,
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            updated_at=datetime.fromisoformat(str(payload["updated_at"])),
        )
        statement = statement.on_conflict_do_update(
            index_elements=[KnowledgeDocumentRecord.task_id],
            set_={
                "filename": statement.excluded.filename,
                "object_name": statement.excluded.object_name,
                "status": statement.excluded.status,
                "payload": statement.excluded.payload,
                "updated_at": statement.excluded.updated_at,
            },
        )
        with Session(self._engine) as session:
            session.execute(statement)
            session.commit()

    def get(self, task_id: str) -> dict[str, Any] | None:
        with Session(self._engine) as session:
            return session.scalar(
                select(KnowledgeDocumentRecord.payload).where(
                    KnowledgeDocumentRecord.task_id == task_id
                )
            )

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(KnowledgeDocumentRecord.payload)
                .order_by(KnowledgeDocumentRecord.created_at.desc())
                .limit(limit)
            ).all()
        return list(rows)

    def delete(self, task_id: str) -> None:
        with Session(self._engine) as session:
            session.execute(
                delete(KnowledgeDocumentRecord).where(
                    KnowledgeDocumentRecord.task_id == task_id
                )
            )
            session.commit()
