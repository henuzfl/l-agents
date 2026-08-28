from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.db_models import RefreshTokenRecord, UserRecord


class AuthenticationError(Exception):
    pass


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID
    username: str


class AuthService:
    _ALGORITHM = "HS256"

    def __init__(
        self,
        settings: Settings,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        if settings.jwt_secret_key is None:
            raise ConfigurationError("缺少认证配置：JWT_SECRET_KEY")
        self._settings = settings
        self._session_maker = session_maker
        self._secret = settings.jwt_secret_key.get_secret_value()
        if len(self._secret) < 32:
            raise ConfigurationError("JWT_SECRET_KEY 至少需要 32 个字符。")
        self._passwords = PasswordHash.recommended()

    @property
    def access_token_seconds(self) -> int:
        return self._settings.access_token_minutes * 60

    @property
    def refresh_token_seconds(self) -> int:
        return self._settings.refresh_token_days * 24 * 60 * 60

    @property
    def secure_cookie(self) -> bool:
        return self._settings.refresh_cookie_secure

    def _encode(self, *, user: UserRecord, token_type: str, jti: UUID, expires: datetime,
                family_id: UUID | None = None) -> str:
        now = datetime.now(UTC)
        payload: dict[str, object] = {
            "sub": str(user.id), "username": user.username, "type": token_type,
            "jti": str(jti), "iss": self._settings.jwt_issuer,
            "aud": self._settings.jwt_audience, "iat": now, "exp": expires,
        }
        if family_id is not None:
            payload["family"] = str(family_id)
        return jwt.encode(payload, self._secret, algorithm=self._ALGORITHM)

    def _decode(self, token: str, expected_type: str) -> dict[str, object]:
        try:
            payload = jwt.decode(
                token, self._secret, algorithms=[self._ALGORITHM],
                issuer=self._settings.jwt_issuer, audience=self._settings.jwt_audience,
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("认证凭据无效或已过期。") from exc
        if payload.get("type") != expected_type:
            raise AuthenticationError("认证凭据类型无效。")
        return payload

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def _expired(value: datetime) -> bool:
        comparable = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return comparable <= datetime.now(UTC)

    async def login(self, username: str, password: str) -> tuple[str, str]:
        async with self._session_maker() as session:
            user = await session.scalar(select(UserRecord).where(UserRecord.username == username))
            password_valid = user is not None and self._passwords.verify(
                password, user.password_hash
            )
            if user is None or not user.is_active or not password_valid:
                raise AuthenticationError("用户名或密码错误。")
            tokens = await self._issue_pair(session, user)
            await session.commit()
            return tokens

    async def _issue_pair(
        self, session: AsyncSession, user: UserRecord, *, family_id: UUID | None = None
    ) -> tuple[str, str]:
        now = datetime.now(UTC)
        access = self._encode(
            user=user, token_type="access", jti=uuid4(),
            expires=now + timedelta(minutes=self._settings.access_token_minutes),
        )
        refresh_jti = uuid4()
        family = family_id or uuid4()
        refresh_expires = now + timedelta(days=self._settings.refresh_token_days)
        refresh = self._encode(
            user=user, token_type="refresh", jti=refresh_jti,
            expires=refresh_expires, family_id=family,
        )
        session.add(RefreshTokenRecord(
            jti=refresh_jti, user_id=user.id, family_id=family,
            token_hash=self._token_hash(refresh), expires_at=refresh_expires,
        ))
        return access, refresh

    async def current_user(self, access_token: str) -> AuthenticatedUser:
        payload = self._decode(access_token, "access")
        try:
            user_id = UUID(str(payload["sub"]))
        except (KeyError, ValueError) as exc:
            raise AuthenticationError("认证凭据无效。") from exc
        async with self._session_maker() as session:
            user = await session.get(UserRecord, user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("用户不存在或已停用。")
        return AuthenticatedUser(user.id, user.username)

    async def refresh(self, token: str) -> tuple[str, str]:
        payload = self._decode(token, "refresh")
        try:
            jti = UUID(str(payload["jti"]))
            family = UUID(str(payload["family"]))
            user_id = UUID(str(payload["sub"]))
        except (KeyError, ValueError) as exc:
            raise AuthenticationError("刷新凭据无效。") from exc
        async with self._session_maker() as session:
            record = await session.get(RefreshTokenRecord, jti, with_for_update=True)
            if record is None or record.token_hash != self._token_hash(token):
                raise AuthenticationError("刷新凭据无效。")
            if record.revoked_at is not None:
                await session.execute(
                    update(RefreshTokenRecord).where(
                        RefreshTokenRecord.family_id == family,
                        RefreshTokenRecord.revoked_at.is_(None),
                    ).values(revoked_at=datetime.now(UTC))
                )
                await session.commit()
                raise AuthenticationError("检测到刷新凭据重复使用，请重新登录。")
            user = await session.get(UserRecord, user_id)
            if user is None or not user.is_active or self._expired(record.expires_at):
                raise AuthenticationError("刷新凭据无效或已过期。")
            record.revoked_at = datetime.now(UTC)
            new_access, new_refresh = await self._issue_pair(session, user, family_id=family)
            new_payload = self._decode(new_refresh, "refresh")
            record.replaced_by = UUID(str(new_payload["jti"]))
            await session.commit()
            return new_access, new_refresh

    async def validate_refresh(self, token: str) -> AuthenticatedUser:
        payload = self._decode(token, "refresh")
        try:
            jti = UUID(str(payload["jti"]))
            user_id = UUID(str(payload["sub"]))
        except (KeyError, ValueError) as exc:
            raise AuthenticationError("刷新凭据无效。") from exc
        async with self._session_maker() as session:
            record = await session.get(RefreshTokenRecord, jti)
            user = await session.get(UserRecord, user_id)
        if (
            record is None
            or record.token_hash != self._token_hash(token)
            or record.revoked_at is not None
            or self._expired(record.expires_at)
            or user is None
            or not user.is_active
        ):
            raise AuthenticationError("刷新凭据无效或已过期。")
        return AuthenticatedUser(user.id, user.username)

    async def logout(self, token: str | None) -> None:
        if not token:
            return
        try:
            payload = self._decode(token, "refresh")
            jti = UUID(str(payload["jti"]))
        except (AuthenticationError, KeyError, ValueError):
            return
        async with self._session_maker() as session:
            await session.execute(
                update(RefreshTokenRecord).where(
                    RefreshTokenRecord.jti == jti,
                    RefreshTokenRecord.revoked_at.is_(None),
                ).values(revoked_at=datetime.now(UTC))
            )
            await session.commit()

    async def seed_demo_users(self) -> None:
        if not self._settings.seed_demo_users:
            return
        credentials = (
            ("demo1", self._settings.demo1_password),
            ("demo2", self._settings.demo2_password),
            ("demo3", self._settings.demo3_password),
        )
        async with self._session_maker() as session:
            for username, secret in credentials:
                assert secret is not None
                user = await session.scalar(
                    select(UserRecord).where(UserRecord.username == username)
                )
                password_hash = self._passwords.hash(secret.get_secret_value())
                if user is None:
                    session.add(UserRecord(
                        id=uuid4(), username=username, password_hash=password_hash, is_active=True
                    ))
                else:
                    user.password_hash = password_hash
                    user.is_active = True
            await session.commit()
