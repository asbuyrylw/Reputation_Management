"""Request-path connection pool for the API.

The engine opens a fresh `db()` connection per call (fine for the CLI). The API
serves concurrent requests, so inline read handlers borrow from a small pooled set
instead. Handlers that call an existing ENGINE function let the engine open its own
`db()` -- we don't thread the pooled connection into engine code (keeps this layer
additive and lets audit()'s session advisory lock own its own connection lifecycle).
"""

from __future__ import annotations

from typing import Optional

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

try:
    from ..db import dsn
except ImportError:  # pragma: no cover
    from db import dsn  # type: ignore

_POOL: Optional[ConnectionPool] = None


def get_pool() -> ConnectionPool:
    global _POOL
    if _POOL is None:
        # Keep max_size modest: the engine's per-call db() and the langgraph
        # PostgresSaver pool also consume connections -- combined must stay under
        # Postgres max_connections.
        _POOL = ConnectionPool(conninfo=dsn(), min_size=1, max_size=8, open=True,
                               kwargs={"row_factory": dict_row})
    return _POOL


def close_pool() -> None:
    global _POOL
    if _POOL is not None:
        _POOL.close()
        _POOL = None
