from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings
from app.core.exceptions import ConfigurationError

APP_SCHEMA = "app"


def require_database_url(settings: Settings) -> str:
    if settings.database_url is None:
        raise ConfigurationError("缺少数据库配置：DATABASE_URL")
    return settings.database_url.get_secret_value()


def async_database_url(settings: Settings) -> str:
    return make_url(require_database_url(settings)).set(
        drivername="postgresql+asyncpg"
    ).render_as_string(hide_password=False)


def sync_database_url(settings: Settings) -> str:
    return make_url(require_database_url(settings)).set(
        drivername="postgresql+psycopg2"
    ).render_as_string(hide_password=False)


def create_app_async_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        async_database_url(settings),
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": APP_SCHEMA}},
    )


def create_app_sync_engine(settings: Settings) -> Engine:
    return create_engine(
        sync_database_url(settings),
        pool_pre_ping=True,
        connect_args={"options": f"-csearch_path={APP_SCHEMA}"},
    )
