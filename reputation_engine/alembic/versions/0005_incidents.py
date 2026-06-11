"""incidents: reactive-incident records from the Reactive Incident agent (Graph 4)

Each NEW contested mention becomes an incident with a deterministic severity, a
per-incident delay-impact estimate (added weeks + counter levers), a drafted
reply, and an SLA -- pausing at a human gate for approval before anything is sent.

Revision ID: 0005_incidents
Revises: 0004_discovery_targets
Create Date: 2026-06-11
"""
from __future__ import annotations

from alembic import op

revision = "0005_incidents"
down_revision = "0004_discovery_targets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS incidents (
            id             BIGSERIAL PRIMARY KEY,
            business_id    BIGINT REFERENCES businesses(id),
            mention_url    TEXT,
            sentiment      TEXT,
            severity       TEXT,                 -- low | medium | high
            severity_score NUMERIC(4,3),
            delay_impact   JSONB,
            draft_response TEXT,
            sla_hours      INT,
            status         TEXT DEFAULT 'pending_human_review',
            decision       JSONB,
            created_at     TIMESTAMPTZ DEFAULT now(),
            resolved_at    TIMESTAMPTZ
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_incidents_biz ON incidents(business_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS incidents CASCADE")
