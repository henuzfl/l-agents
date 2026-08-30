from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import UserAccount
from app.db.models import UserRecord


def _account(record: UserRecord | None) -> UserAccount | None:
    if record is None:
        return None
    return UserAccount(record.id, record.username, record.password_hash, record.is_active)


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID) -> UserAccount | None:
        return _account(await self._session.get(UserRecord, user_id))

    async def get_by_username(self, username: str) -> UserAccount | None:
        record = await self._session.scalar(
            select(UserRecord).where(UserRecord.username == username)
        )
        return _account(record)

    async def upsert_demo_user(
        self, user_id: UUID, username: str, password_hash: str
    ) -> None:
        record = await self._session.scalar(
            select(UserRecord).where(UserRecord.username == username)
        )
        if record is None:
            self._session.add(
                UserRecord(
                    id=user_id,
                    username=username,
                    password_hash=password_hash,
                    is_active=True,
                )
            )
            return
        record.password_hash = password_hash
        record.is_active = True
