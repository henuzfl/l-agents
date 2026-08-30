from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import StoredRefreshToken
from app.db.models import RefreshTokenRecord


def _stored(record: RefreshTokenRecord | None) -> StoredRefreshToken | None:
    if record is None:
        return None
    return StoredRefreshToken(
        record.jti,
        record.user_id,
        record.family_id,
        record.token_hash,
        record.expires_at,
        record.revoked_at,
    )


class SqlAlchemyRefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: StoredRefreshToken) -> None:
        self._session.add(
            RefreshTokenRecord(
                jti=token.jti,
                user_id=token.user_id,
                family_id=token.family_id,
                token_hash=token.token_hash,
                expires_at=token.expires_at,
            )
        )

    async def get_for_update(self, jti: UUID) -> StoredRefreshToken | None:
        return _stored(await self._session.get(RefreshTokenRecord, jti, with_for_update=True))

    async def get(self, jti: UUID) -> StoredRefreshToken | None:
        return _stored(await self._session.get(RefreshTokenRecord, jti))

    async def revoke_family(self, family_id: UUID) -> None:
        await self._session.execute(
            update(RefreshTokenRecord)
            .where(
                RefreshTokenRecord.family_id == family_id,
                RefreshTokenRecord.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )

    async def rotate(self, jti: UUID, replaced_by: UUID) -> None:
        await self._session.execute(
            update(RefreshTokenRecord)
            .where(RefreshTokenRecord.jti == jti)
            .values(revoked_at=datetime.now(UTC), replaced_by=replaced_by)
        )

    async def revoke(self, jti: UUID) -> None:
        await self._session.execute(
            update(RefreshTokenRecord)
            .where(
                RefreshTokenRecord.jti == jti,
                RefreshTokenRecord.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
