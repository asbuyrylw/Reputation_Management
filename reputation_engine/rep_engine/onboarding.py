"""
Getting-Started status -- a setup checklist derived entirely from EXISTING data (no new
tables). Drives the console's onboarding card so a new owner has an obvious path from an
empty account to a fully-running reputation program.
"""

from __future__ import annotations

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore


# (key, human label, page to act on, SQL that returns a row when the step is done)
_STEPS = [
    # Require a real AI audit (which writes `answers`), not just any finished run -- a
    # competitor benchmark / local-rank run also creates an audit_runs row that init_db()
    # backfills to status='complete', which would otherwise satisfy this step spuriously.
    ("audit", "Run your first AI audit", "/admin/jobs",
     "SELECT 1 FROM answers WHERE business_id=%s AND NOT COALESCE(failed,false) LIMIT 1"),
    ("competitors", "Add competitors to benchmark", "/competitors",
     "SELECT 1 FROM competitors WHERE business_id=%s LIMIT 1"),
    ("prompts", "Add your own tracked prompts", "/prompts",
     "SELECT 1 FROM custom_prompts WHERE business_id=%s LIMIT 1"),
    ("keywords", "Set monitoring keywords", "/sustain/mentions",
     "SELECT 1 FROM monitor_keywords WHERE business_id=%s LIMIT 1"),
    ("content", "Publish your first content asset", "/content/drafts",
     "SELECT 1 FROM assets WHERE business_id=%s LIMIT 1"),
]


def status(business_id: int) -> dict:
    """Which getting-started steps are done for this business. Each step's check is a cheap
    existence query; a missing table is treated as 'not done' so the card never errors."""
    steps = []
    done = 0
    with db() as conn:
        for key, label, href, sql in _STEPS:
            try:
                ok = bool(conn.execute(sql, (business_id,)).fetchone())
            except Exception:  # pragma: no cover -- a not-yet-migrated table => step undone
                conn.rollback()
                ok = False
            done += 1 if ok else 0
            steps.append({"key": key, "label": label, "href": href, "done": ok})
    return {"steps": steps, "done": done, "total": len(steps), "complete": done == len(steps)}
