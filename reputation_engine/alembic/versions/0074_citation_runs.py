"""citation_runs + directory_credentials: the computer-use citation/directory-listing builder

Human-supervised directory-listing submissions (Apple Maps, Bing Places, Nextdoor Business, etc.)
driven by a headless browser under Gemini Computer Use. `citation_runs` is the step-by-step audit
trail (screenshots + actions); the run always pauses before any submit-like action for an explicit
human confirm, never runs as a background job. `directory_credentials` stores the login for each
directory account, Fernet-encrypted the same way platform_connections tokens are (rep_engine.crypto).

Revision ID: 0074_citation_runs
Revises: 0073_extension_tokens
Create Date: 2026-07-06
"""
from __future__ import annotations

from alembic import op

revision = "0074_citation_runs"
down_revision = "0073_extension_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS directory_credentials ("
        "id SERIAL PRIMARY KEY, "
        "business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE, "
        "directory_key TEXT NOT NULL, "
        "username TEXT NOT NULL, "
        "password_enc TEXT NOT NULL, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "UNIQUE (business_id, directory_key)"
        ")"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS citation_runs ("
        "id SERIAL PRIMARY KEY, "
        "business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE, "
        "work_order_id INTEGER REFERENCES work_orders(id) ON DELETE SET NULL, "
        "directory_key TEXT NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'running', "  # running | awaiting_confirmation | done | failed | cancelled
        "steps JSONB NOT NULL DEFAULT '[]'::jsonb, "
        "pending_action JSONB, "
        "error TEXT, "
        "created_by INTEGER, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_citation_runs_business ON citation_runs (business_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS citation_runs")
    op.execute("DROP TABLE IF EXISTS directory_credentials")
