"""
GDPR / data controls: export everything we hold for a business, and erase it.

Both operate over the set of business-scoped tables DISCOVERED at runtime (every public
table with a `business_id` column) so they stay correct as the schema grows -- no hand-kept
list to drift. Export is a portable JSON dump; delete removes every scoped row plus the
business itself, in an FK-safe order found by a fixpoint (retry tables that are still
referenced until they drain), so it works regardless of inter-table foreign keys.
"""

from __future__ import annotations

import logging

import psycopg

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

log = logging.getLogger("gdpr")


def _scoped_tables(conn) -> list[str]:
    """Every public table with a business_id column = the business-scoped data set."""
    rows = conn.execute(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema='public' AND column_name='business_id' ORDER BY table_name"
    ).fetchall()
    return [r["table_name"] for r in rows]


# Access-control / identity tables that carry OTHER principals' account references (user_ids,
# roles). They are the business's own DATA for ERASURE (drop the grants), but NOT for a
# portability EXPORT handed to a mere editor -- excluded there so the dump can't leak the
# co-tenant membership list.
_EXPORT_EXCLUDE = {"business_access"}


def export_business(business_id: int) -> dict:
    """Portable JSON-able dump of everything we hold for a business: the business row plus
    every scoped table's rows. Returns {} if the business doesn't exist."""
    with db() as conn:
        biz = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not biz:
            return {}
        tables = {}
        for t in _scoped_tables(conn):
            if t in _EXPORT_EXCLUDE:
                continue
            # no ORDER BY: not every scoped table has an `id` column (e.g. business_config).
            rows = conn.execute(f'SELECT * FROM "{t}" WHERE business_id=%s', (business_id,)).fetchall()  # nosec B608
            tables[t] = [dict(r) for r in rows]
    return {"business": dict(biz), "tables": tables}


def delete_business(business_id: int) -> dict:
    """Erase a business and all of its scoped rows. FK-safe: repeatedly delete the scoped
    tables, retrying any that are still referenced, until they all drain (fixpoint), then
    delete the business row. Returns per-table deleted counts."""
    with db() as conn:
        if not conn.execute("SELECT 1 FROM businesses WHERE id=%s", (business_id,)).fetchone():
            return {"deleted_business": None, "rows_deleted": {}}
        remaining = _scoped_tables(conn)
        counts: dict[str, int] = {}
        # at most N passes (each pass must drain >=1 table or we stop) -- a child table's FK
        # blocks its parent until the child is emptied, which the next pass handles.
        for _ in range(len(remaining) + 1):
            if not remaining:
                break
            still = []
            for t in remaining:
                try:
                    with conn.transaction():  # savepoint: a FK violation rolls back just this
                        n = conn.execute(
                            f'DELETE FROM "{t}" WHERE business_id=%s', (business_id,)  # nosec B608
                        ).rowcount
                    counts[t] = counts.get(t, 0) + (n or 0)
                except psycopg.errors.ForeignKeyViolation:
                    still.append(t)
            if len(still) == len(remaining):
                break  # no progress -> a cycle/unknown ref; let the businesses delete surface it
            remaining = still
        conn.execute("DELETE FROM businesses WHERE id=%s", (business_id,))
        conn.commit()
    log.info("Erased business %d (%d scoped tables touched)", business_id, len(counts))
    return {"deleted_business": business_id, "rows_deleted": counts}
