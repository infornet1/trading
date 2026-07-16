from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import models so Base.metadata is populated for autogenerate.
# Alembic runs synchronously, so we import the synchronous metadata only.
from api.database import Base
from api import models  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata


def _get_database_url():
    """Read DB_URL from the environment and coerce aiomysql -> pymysql for sync Alembic."""
    url = os.getenv(
        "DB_URL",
        "mysql+pymysql://viznago:90GSxYu0GdSe6fzGowBA4hNOlsBK@localhost/viznago_dev",
    )
    # Support both sync and async URL variants so the same env var works everywhere.
    url = url.replace("mysql+aiomysql://", "mysql+pymysql://")
    if url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+pymysql://", 1)
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Override the ini URL with the environment-derived sync URL.
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _get_database_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
