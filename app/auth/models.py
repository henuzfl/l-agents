from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


class AuthenticationError(Exception):
    pass


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID
    username: str


@dataclass(frozen=True)
class UserAccount:
    id: UUID
    username: str
    password_hash: str
    is_active: bool


@dataclass(frozen=True)
class StoredRefreshToken:
    jti: UUID
    user_id: UUID
    family_id: UUID
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None
