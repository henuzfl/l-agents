from __future__ import annotations

from types import TracebackType
from typing import Protocol
from uuid import UUID

from app.auth.models import StoredRefreshToken, UserAccount


class UserRepository(Protocol):
    async def get_by_id(self, user_id: UUID) -> UserAccount | None: ...

    async def get_by_username(self, username: str) -> UserAccount | None: ...

    async def upsert_demo_user(
        self, user_id: UUID, username: str, password_hash: str
    ) -> None: ...


class RefreshTokenRepository(Protocol):
    async def add(self, token: StoredRefreshToken) -> None: ...

    async def get_for_update(self, jti: UUID) -> StoredRefreshToken | None: ...

    async def get(self, jti: UUID) -> StoredRefreshToken | None: ...

    async def revoke_family(self, family_id: UUID) -> None: ...

    async def rotate(self, jti: UUID, replaced_by: UUID) -> None: ...

    async def revoke(self, jti: UUID) -> None: ...


class AuthUnitOfWork(Protocol):
    users: UserRepository
    refresh_tokens: RefreshTokenRepository

    async def __aenter__(self) -> AuthUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class AuthUnitOfWorkFactory(Protocol):
    def __call__(self) -> AuthUnitOfWork: ...
