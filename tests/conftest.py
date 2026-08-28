import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-long-enough")

from app.api.dependencies import get_current_user  # noqa: E402
from app.auth import AuthenticatedUser  # noqa: E402
from app.core.config import Settings
from app.main import create_app


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        Settings(
            deepseek_api_key=None,
            database_url="postgresql://test:test@localhost/test",
            jwt_secret_key="test-secret-key-that-is-long-enough",
        )
    )
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        UUID("00000000-0000-0000-0000-000000000001"), "test-user"
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
