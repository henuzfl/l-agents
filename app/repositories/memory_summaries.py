from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import MemorySummaryRecord


@dataclass(frozen=True)
class MemorySummary:
    summary: str = ""
    summarized_turns: int = 0


class MemorySummaryRepository:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker

    async def get(self, session_id: str) -> MemorySummary:
        async with self._session_maker() as session:
            record = await session.scalar(
                select(MemorySummaryRecord).where(
                    MemorySummaryRecord.session_id == session_id
                )
            )
        if record is None:
            return MemorySummary()
        return MemorySummary(record.summary, record.summarized_turns)

    async def save(self, session_id: str, summary: MemorySummary) -> None:
        statement = insert(MemorySummaryRecord).values(
            session_id=session_id,
            summary=summary.summary,
            summarized_turns=summary.summarized_turns,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[MemorySummaryRecord.session_id],
            set_={
                "summary": summary.summary,
                "summarized_turns": summary.summarized_turns,
            },
        )
        async with self._session_maker() as session:
            await session.execute(statement)
            await session.commit()
