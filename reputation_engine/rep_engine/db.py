"""
Single source of database connections for the engine.
=====================================================
Replaces the ~15 byte-identical ``DB_DSN = os.getenv(...)`` + ``def db()`` copies
that used to live in every module. The DSN is sourced from the validated
``config.load_settings()``, so a misconfigured DSN -- the ``USER:PASSWORD``
placeholder, or a non-postgres URL -- fails fast with a clear message at the
first connection instead of a cryptic psycopg error deep inside a run.

Validation happens at CONNECT time, not import time, so importing a module in a
no-DB context (unit tests, ``--help``) never triggers it. Connections are opened
fresh per call (matching the existing ``with db() as conn:`` usage); a pool can
be slotted in here later without touching any caller.
"""

from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row

try:
    from . import config
except ImportError:  # pragma: no cover -- allows running modules as loose scripts
    import config  # type: ignore

# Raw env value, for display only (e.g. preflight shows the connection host).
# db() below uses the *validated* DSN from config, not this constant.
DB_DSN = os.getenv("REP_DB_DSN", "postgresql://USER:PASSWORD@localhost:5432/reputation")


def dsn() -> str:
    """Return the validated Postgres DSN. Raises pydantic.ValidationError (with a
    clear message) on a placeholder / non-postgres DSN."""
    return config.load_settings().rep_db_dsn


def db() -> psycopg.Connection:
    """Open a new dict-row connection to the configured database. The DSN is
    validated via config at call time, so a bad DSN fails fast here."""
    return psycopg.connect(dsn(), row_factory=dict_row)
