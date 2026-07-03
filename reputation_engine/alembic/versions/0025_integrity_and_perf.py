"""integrity + perf: cascade deletes, audit_runs.kind, job dedup, hot indexes

Bundles the safe, high-value fixes from the codebase audit:

1. ON DELETE CASCADE on the business_id / run_id FKs that were NO ACTION, so deleting a
   business (admin GDPR erasure) or an audit run no longer FK-fails or orphans rows.
2. `audit_runs.kind` discriminator ('ai_audit' | 'local_rank' | 'competitor') so local-rank
   and competitor-benchmark runs (which reuse audit_runs for a grouping id) stop polluting the
   AI Audits list and the "latest audit" reads.
3. A partial UNIQUE index on api_jobs(business_id, job_type) WHERE status IN ('queued','running')
   so the per-(business,type) job dedup is atomic (the check-then-insert had a race that let two
   concurrent triggers both enqueue -> double LLM spend).
4. Missing business_id indexes on hot, per-tenant tables.

Revision ID: 0025_integrity_and_perf
Revises: 0024_api_jobs_result
Create Date: 2026-06-21
"""
from __future__ import annotations

from alembic import op

revision = "0025_integrity_and_perf"
down_revision = "0024_api_jobs_result"
branch_labels = None
depends_on = None

# (table, constraint, column, referenced_table) for the FKs to flip to ON DELETE CASCADE.
_CASCADE_FKS = [
    ("answers", "answers_business_id_fkey", "business_id", "businesses"),
    ("answers", "answers_run_id_fkey", "run_id", "audit_runs"),
    ("audit_runs", "audit_runs_business_id_fkey", "business_id", "businesses"),
    ("discovery_targets", "discovery_targets_business_id_fkey", "business_id", "businesses"),
    ("gap_models", "gap_models_business_id_fkey", "business_id", "businesses"),
    ("gap_models", "gap_models_run_id_fkey", "run_id", "audit_runs"),
    ("incidents", "incidents_business_id_fkey", "business_id", "businesses"),
    ("production_briefs", "production_briefs_business_id_fkey", "business_id", "businesses"),
    ("root_cause", "root_cause_business_id_fkey", "business_id", "businesses"),
    ("root_cause", "root_cause_run_id_fkey", "run_id", "audit_runs"),
    ("pipeline_steps", "pipeline_steps_pipeline_run_id_fkey", "pipeline_run_id", "pipeline_runs"),
]


def upgrade() -> None:
    # 1. cascade deletes
    for tbl, con, col, ref in _CASCADE_FKS:
        op.execute(f"ALTER TABLE {tbl} DROP CONSTRAINT IF EXISTS {con}")
        op.execute(
            f"ALTER TABLE {tbl} ADD CONSTRAINT {con} "
            f"FOREIGN KEY ({col}) REFERENCES {ref}(id) ON DELETE CASCADE"
        )

    # 2. audit_runs.kind discriminator (existing rows default to 'ai_audit')
    op.execute("ALTER TABLE audit_runs ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'ai_audit'")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_runs_biz_kind ON audit_runs (business_id, kind, id DESC)")

    # 3. atomic job dedup -- first retire any already-existing duplicate active rows, then enforce
    op.execute(
        """
        UPDATE api_jobs SET status='failed', error='superseded (deduped on migration)', finished_at=now()
        WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (PARTITION BY business_id, job_type ORDER BY id DESC) rn
                FROM api_jobs WHERE status IN ('queued','running')
            ) t WHERE rn > 1
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_api_jobs_active "
        "ON api_jobs (business_id, job_type) WHERE status IN ('queued','running')"
    )

    # 4. hot per-tenant indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_mentions_biz ON mentions (business_id, discovered_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_work_orders_biz ON work_orders (business_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_content_drafts_biz ON content_drafts (business_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_assets_biz ON assets (business_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cost_ledger_biz ON cost_ledger (business_id)")


def downgrade() -> None:
    for idx in ("idx_mentions_biz", "idx_work_orders_biz", "idx_content_drafts_biz",
                "idx_assets_biz", "idx_cost_ledger_biz", "uq_api_jobs_active", "idx_audit_runs_biz_kind"):
        op.execute(f"DROP INDEX IF EXISTS {idx}")
    op.execute("ALTER TABLE audit_runs DROP COLUMN IF EXISTS kind")
    # revert FKs to plain NO ACTION
    for tbl, con, col, ref in _CASCADE_FKS:
        op.execute(f"ALTER TABLE {tbl} DROP CONSTRAINT IF EXISTS {con}")
        op.execute(f"ALTER TABLE {tbl} ADD CONSTRAINT {con} FOREIGN KEY ({col}) REFERENCES {ref}(id)")
