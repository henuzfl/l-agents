from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import KnowledgeDocumentRecord


class KnowledgeDocumentRepository:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker

    async def save(self, payload: dict[str, Any]) -> None:
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
        async with self._session_maker() as session:
            await session.execute(statement)
            await session.commit()

    async def get(self, task_id: str) -> dict[str, Any] | None:
        async with self._session_maker() as session:
            return await session.scalar(
                select(KnowledgeDocumentRecord.payload).where(
                    KnowledgeDocumentRecord.task_id == task_id
                )
            )

    async def list(self, limit: int = 100) -> list[dict[str, Any]]:
        async with self._session_maker() as session:
            rows = await session.scalars(
                select(KnowledgeDocumentRecord.payload)
                .order_by(KnowledgeDocumentRecord.created_at.desc())
                .limit(limit)
            )
            return list(rows.all())

    async def delete(self, task_id: str) -> None:
        async with self._session_maker() as session:
            await session.execute(
                delete(KnowledgeDocumentRecord).where(
                    KnowledgeDocumentRecord.task_id == task_id
                )
            )
            await session.commit()
