from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import AuthService
from app.core.config import Settings


def build_auth_service(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
) -> AuthService:
    return AuthService(settings, sessions)
