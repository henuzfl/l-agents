from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.database import create_app_async_engine


@dataclass(frozen=True)
class DatabaseResources:
    async_engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]


def build_database_resources(settings: Settings) -> DatabaseResources:
    async_engine = create_app_async_engine(settings)
    return DatabaseResources(
        async_engine=async_engine,
        sessions=async_sessionmaker(
            async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        ),
    )
