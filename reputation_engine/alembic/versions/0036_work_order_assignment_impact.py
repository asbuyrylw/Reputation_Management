"""work_orders: start date + predicted impact (assignment & ROI)

- start_date: planned start (target_date already serves as the due/end date) so the owner can
  see who's doing what, by when.
- predicted_ai_points / predicted_seo_impact / predicted_basis: a per-task estimate of how much
  it moves the AI-reputation score (points, from learned-or-baseline lever weights) and the SEO
  impact (qualitative), so tasks can be ranked by ROI. Snapshotted at plan time so we can later
  compare predicted vs. measured.

Revision ID: 0036_work_order_assignment_impact
Revises: 0035_work_order_revision
Create Date: 2026-06-24
"""
from __future__ import annotations

from alembic import op

revision = "0036_wo_assign_impact"
down_revision = "0035_work_order_revision"
branch_labels = None
depends_on = None

_COLS = [
    "start_date DATE",
    "predicted_ai_points NUMERIC(5,2)",
    "predicted_seo_impact TEXT",
    "predicted_basis TEXT",
]


def upgrade() -> None:
    for col in _COLS:
        op.execute(f"ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS {col}")


def downgrade() -> None:
    for col in _COLS:
        op.execute(f"ALTER TABLE work_orders DROP COLUMN IF EXISTS {col.split()[0]}")
