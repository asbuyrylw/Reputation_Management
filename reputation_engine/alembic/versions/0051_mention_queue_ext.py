"""mentions / mention_replies surface + connection + auto-policy columns (Integrations Phase 4)

Extends the existing Module-13 tables (created by mention_monitor._ensure()) so the unified
approval queue can route every item to a surface (owned vs third_party) and an auto-policy. Defaults
are the SAFE values (surface='third_party', auto_policy='manual') so legacy rows can never auto-post.
mention_monitor._ensure() is updated with the same ADD COLUMN set for fresh-DB parity.

Asymmetric downgrade: drops only the added columns, never the pre-existing _ensure() tables.

Revision ID: 0051_mention_queue_ext
Revises: 0050_review_replies
Create Date: 2026-06-25
"""
from __future__ import annotations

from alembic import op

revision = "0051_mention_queue_ext"
down_revision = "0050_review_replies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # mentions: surface routing + connection + PII/retention
    for ddl in (
        "ALTER TABLE mentions ADD COLUMN IF NOT EXISTS surface TEXT DEFAULT 'third_party'",
        "ALTER TABLE mentions ADD COLUMN IF NOT EXISTS target_connection_id BIGINT",
        "ALTER TABLE mentions ADD COLUMN IF NOT EXISTS external_url TEXT",
        "ALTER TABLE mentions ADD COLUMN IF NOT EXISTS author_pii_redacted BOOLEAN DEFAULT FALSE",
        "ALTER TABLE mentions ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ DEFAULT now()",
        # mention_replies: surface + auto-policy + posting audit
        "ALTER TABLE mention_replies ADD COLUMN IF NOT EXISTS surface TEXT DEFAULT 'third_party'",
        "ALTER TABLE mention_replies ADD COLUMN IF NOT EXISTS target_connection_id BIGINT",
        "ALTER TABLE mention_replies ADD COLUMN IF NOT EXISTS auto_policy TEXT DEFAULT 'manual'",
        "ALTER TABLE mention_replies ADD COLUMN IF NOT EXISTS posted_at TIMESTAMPTZ",
        "ALTER TABLE mention_replies ADD COLUMN IF NOT EXISTS external_url TEXT",
        "ALTER TABLE mention_replies ADD COLUMN IF NOT EXISTS external_post_id TEXT",
        "ALTER TABLE mention_replies ADD COLUMN IF NOT EXISTS posted_by TEXT",
        "ALTER TABLE mention_replies ADD COLUMN IF NOT EXISTS last_error TEXT",
        "ALTER TABLE mention_replies ADD COLUMN IF NOT EXISTS job_id BIGINT",
    ):
        op.execute(ddl)
    # FK on the connection columns (wrapped: tables may differ on fresh test DBs).
    op.execute("""DO $$ BEGIN
        ALTER TABLE mentions ADD CONSTRAINT fk_mentions_target_conn
            FOREIGN KEY (target_connection_id) REFERENCES platform_connections(id) ON DELETE SET NULL;
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN undefined_table THEN NULL; WHEN undefined_column THEN NULL; END $$;""")
    op.execute("""DO $$ BEGIN
        ALTER TABLE mention_replies ADD CONSTRAINT fk_mention_replies_target_conn
            FOREIGN KEY (target_connection_id) REFERENCES platform_connections(id) ON DELETE SET NULL;
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN undefined_table THEN NULL; WHEN undefined_column THEN NULL; END $$;""")


def downgrade() -> None:
    op.execute("ALTER TABLE mentions DROP CONSTRAINT IF EXISTS fk_mentions_target_conn")
    op.execute("ALTER TABLE mention_replies DROP CONSTRAINT IF EXISTS fk_mention_replies_target_conn")
    for col in ("surface", "target_connection_id", "external_url", "author_pii_redacted", "last_seen_at"):
        op.execute(f"ALTER TABLE mentions DROP COLUMN IF EXISTS {col}")
    for col in ("surface", "target_connection_id", "auto_policy", "posted_at", "external_url",
                "external_post_id", "posted_by", "last_error", "job_id"):
        op.execute(f"ALTER TABLE mention_replies DROP COLUMN IF EXISTS {col}")
