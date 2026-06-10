"""Alembic environment for the Reputation Engine.

The DB URL is read from REP_DB_DSN (the same env var the app uses) and rewritten
to the psycopg-3 SQLAlchemy dialect, because the project uses psycopg 3, not
psycopg2. Migrations are hand-written SQL (the baseline is the consolidated
schema captured from the live DB), so there are no SQLAlchemy models and
target_metadata is None.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config


def _url() -> str:
    dsn = os.getenv("REP_DB_DSN", "")
    if not dsn:
        raise RuntimeError("REP_DB_DSN is not set; cannot run migrations")
    # SQLAlchemy maps bare postgresql:// to psycopg2; this project ships psycopg 3.
    if dsn.startswith("postgresql://"):
        dsn = "postgresql+psycopg://" + dsn[len("postgresql://"):]
    elif dsn.startswith("postgres://"):
        dsn = "postgresql+psycopg://" + dsn[len("postgres://"):]
    return dsn


config.set_main_option("sqlalchemy.url", _url())
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=_url(), target_metadata=target_metadata,
        literal_binds=True, dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
