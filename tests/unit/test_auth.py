from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth import AuthenticationError, AuthService
from app.core.config import Settings
from app.db_models import RefreshTokenRecord, UserRecord


async def _service() -> tuple[AuthService, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(UserRecord.__table__.create)
        await connection.run_sync(RefreshTokenRecord.__table__.create)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    settings = Settings(
        database_url="postgresql://test:test@localhost/test",
        jwt_secret_key="test-secret-key-that-is-long-enough",
        seed_demo_users=True,
        demo1_password="password-1",
        demo2_password="password-2",
        demo3_password="password-3",
    )
    service = AuthService(settings, maker)
    await service.seed_demo_users()
    return service, engine


@pytest.mark.asyncio
async def test_login_refresh_rotation_and_replay_detection() -> None:
    service, engine = await _service()
    access, refresh = await service.login("demo1", "password-1")
    user = await service.current_user(access)
    assert user.username == "demo1"

    next_access, _next_refresh = await service.refresh(refresh)
    assert (await service.current_user(next_access)).id == user.id
    with pytest.raises(AuthenticationError, match="重复使用"):
        await service.refresh(refresh)
    await engine.dispose()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_login_rejects_bad_password_and_tampered_access_token() -> None:
    service, engine = await _service()
    with pytest.raises(AuthenticationError, match="用户名或密码错误"):
        await service.login("demo1", "wrong")
    with pytest.raises(AuthenticationError):
        await service.current_user(f"invalid-{uuid4()}")
    await engine.dispose()  # type: ignore[attr-defined]
