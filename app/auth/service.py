from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.models import (
    AuthenticatedUser,
    AuthenticationError,
    StoredRefreshToken,
    UserAccount,
)
from app.auth.password import PasswordService
from app.auth.repository import AuthUnitOfWorkFactory, RefreshTokenRepository
from app.auth.tokens import TokenCodec
from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.repositories.auth import SqlAlchemyAuthUnitOfWork


class AuthService:
    def __init__(
        self,
        settings: Settings,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        *,
        unit_of_work: AuthUnitOfWorkFactory | None = None,
        passwords: PasswordService | None = None,
    ) -> None:
        if settings.jwt_secret_key is None:
            raise ConfigurationError("缺少认证配置：JWT_SECRET_KEY")
        secret = settings.jwt_secret_key.get_secret_value()
        if len(secret) < 32:
            raise ConfigurationError("JWT_SECRET_KEY 至少需要 32 个字符。")
        if unit_of_work is None and session_maker is None:
            raise ValueError("session_maker or unit_of_work is required")
        self._settings = settings
        self._unit_of_work = unit_of_work or (
            lambda: SqlAlchemyAuthUnitOfWork(session_maker)  # type: ignore[arg-type]
        )
        self._passwords = passwords or PasswordService()
        self._tokens = TokenCodec(secret, settings.jwt_issuer, settings.jwt_audience)

    @property
    def access_token_seconds(self) -> int:
        return self._settings.access_token_minutes * 60

    @property
    def refresh_token_seconds(self) -> int:
        return self._settings.refresh_token_days * 24 * 60 * 60

    @property
    def secure_cookie(self) -> bool:
        return self._settings.refresh_cookie_secure

    @staticmethod
    def _expired(value: datetime) -> bool:
        comparable = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return comparable <= datetime.now(UTC)

    async def login(self, username: str, password: str) -> tuple[str, str]:
        async with self._unit_of_work() as unit:
            user = await unit.users.get_by_username(username)
            password_valid = user is not None and self._passwords.verify(
                password, user.password_hash
            )
            if user is None or not user.is_active or not password_valid:
                raise AuthenticationError("用户名或密码错误。")
            pair = await self._issue_pair(unit.refresh_tokens, user)
            await unit.commit()
            return pair

    async def _issue_pair(
        self,
        refresh_tokens: RefreshTokenRepository,
        user: UserAccount,
        *,
        family_id: UUID | None = None,
    ) -> tuple[str, str]:
        now = datetime.now(UTC)
        access = self._tokens.encode(
            user=user,
            token_type="access",
            jti=uuid4(),
            expires=now + timedelta(minutes=self._settings.access_token_minutes),
        )
        refresh_jti = uuid4()
        family = family_id or uuid4()
        refresh_expires = now + timedelta(days=self._settings.refresh_token_days)
        refresh = self._tokens.encode(
            user=user,
            token_type="refresh",
            jti=refresh_jti,
            expires=refresh_expires,
            family_id=family,
        )
        await refresh_tokens.add(
            StoredRefreshToken(
                jti=refresh_jti,
                user_id=user.id,
                family_id=family,
                token_hash=self._tokens.hash(refresh),
                expires_at=refresh_expires,
                revoked_at=None,
            )
        )
        return access, refresh

    async def current_user(self, access_token: str) -> AuthenticatedUser:
        payload = self._tokens.decode(access_token, "access")
        try:
            user_id = UUID(str(payload["sub"]))
        except (KeyError, ValueError) as exc:
            raise AuthenticationError("认证凭据无效。") from exc
        async with self._unit_of_work() as unit:
            user = await unit.users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("用户不存在或已停用。")
        return AuthenticatedUser(user.id, user.username)

    async def refresh(self, token: str) -> tuple[str, str]:
        payload = self._tokens.decode(token, "refresh")
        try:
            jti = UUID(str(payload["jti"]))
            family = UUID(str(payload["family"]))
            user_id = UUID(str(payload["sub"]))
        except (KeyError, ValueError) as exc:
            raise AuthenticationError("刷新凭据无效。") from exc
        async with self._unit_of_work() as unit:
            record = await unit.refresh_tokens.get_for_update(jti)
            if record is None or record.token_hash != self._tokens.hash(token):
                raise AuthenticationError("刷新凭据无效。")
            if record.revoked_at is not None:
                await unit.refresh_tokens.revoke_family(family)
                await unit.commit()
                raise AuthenticationError("检测到刷新凭据重复使用，请重新登录。")
            user = await unit.users.get_by_id(user_id)
            if user is None or not user.is_active or self._expired(record.expires_at):
                raise AuthenticationError("刷新凭据无效或已过期。")
            new_access, new_refresh = await self._issue_pair(
                unit.refresh_tokens, user, family_id=family
            )
            new_payload = self._tokens.decode(new_refresh, "refresh")
            await unit.refresh_tokens.rotate(jti, UUID(str(new_payload["jti"])))
            await unit.commit()
            return new_access, new_refresh

    async def validate_refresh(self, token: str) -> AuthenticatedUser:
        payload = self._tokens.decode(token, "refresh")
        try:
            jti = UUID(str(payload["jti"]))
            user_id = UUID(str(payload["sub"]))
        except (KeyError, ValueError) as exc:
            raise AuthenticationError("刷新凭据无效。") from exc
        async with self._unit_of_work() as unit:
            record = await unit.refresh_tokens.get(jti)
            user = await unit.users.get_by_id(user_id)
        if (
            record is None
            or record.token_hash != self._tokens.hash(token)
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
            payload = self._tokens.decode(token, "refresh")
            jti = UUID(str(payload["jti"]))
        except (AuthenticationError, KeyError, ValueError):
            return
        async with self._unit_of_work() as unit:
            await unit.refresh_tokens.revoke(jti)
            await unit.commit()

    async def seed_demo_users(self) -> None:
        if not self._settings.seed_demo_users:
            return
        credentials = (
            ("demo1", self._settings.demo1_password),
            ("demo2", self._settings.demo2_password),
            ("demo3", self._settings.demo3_password),
        )
        async with self._unit_of_work() as unit:
            for username, secret in credentials:
                assert secret is not None
                await unit.users.upsert_demo_user(
                    uuid4(),
                    username,
                    self._passwords.hash(secret.get_secret_value()),
                )
            await unit.commit()
