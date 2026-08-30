from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.schema import CreateSchema

from app.core.config import Settings
from app.database import APP_SCHEMA, sync_database_url
from app.db import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

settings = Settings()
config.set_main_option("sqlalchemy.url", sync_database_url(settings).replace("%", "%%"))
target_metadata = Base.metadata


def include_object(
    _object: object,
    name: str | None,
    type_: str,
    _reflected: bool,
    _compare_to: object | None,
) -> bool:
    return not (type_ == "table" and name == "alembic_version")


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=APP_SCHEMA,
        include_schemas=False,
        include_object=include_object,
    )
    context.execute(f'CREATE SCHEMA IF NOT EXISTS "{APP_SCHEMA}"')
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        connection.execute(CreateSchema(APP_SCHEMA, if_not_exists=True))
        connection.commit()
        connection.exec_driver_sql(f'SET search_path TO "{APP_SCHEMA}"')
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=APP_SCHEMA,
            include_schemas=False,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
