"""platform_connections + oauth_states — the per-tenant credential vault (Integrations Phase 1)

Turns the engine from "draft only" into "draft + publish/reply through OWNED channels" by adding
the credential layer beneath social_presence. Secrets (OAuth tokens, WordPress app-passwords,
Ayrshare profile-keys) are stored as Fernet ciphertext (rep_engine.crypto) in access_token_enc /
refresh_token_enc; the key lives in env (TOKEN_ENC_KEY), never in Postgres. oauth_states is the
short-lived, single-use handshake row that scopes the unprefixed OAuth callback to a business.

Note: the integrations design numbered this 0040; 0040-0047 were taken by the content-intelligence
and NEXT-tier work, so the integrations chain runs 0048->0052.

Revision ID: 0048_platform_connections
Revises: 0047_compliance_signoffs
Create Date: 2026-06-25
"""
from __future__ import annotations

from alembic import op

revision = "0048_platform_connections"
down_revision = "0047_compliance_signoffs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS platform_connections (
        id BIGSERIAL PRIMARY KEY,
        business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        label TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        access_token_enc TEXT,
        refresh_token_enc TEXT,
        token_type TEXT,
        expires_at TIMESTAMPTZ,
        account_ref TEXT,
        profile_ref TEXT,
        external_id TEXT,
        scopes JSONB DEFAULT '[]'::jsonb,
        gbp_access TEXT,
        meta JSONB DEFAULT '{}'::jsonb,
        last_error TEXT,
        last_used_at TIMESTAMPTZ,
        connected_by BIGINT REFERENCES users(id),
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (business_id, kind, account_ref))""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_platform_connections_business ON platform_connections(business_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_platform_connections_kind ON platform_connections(business_id, kind)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_platform_connections_expiry "
               "ON platform_connections(expires_at) WHERE expires_at IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_platform_connections_active "
               "ON platform_connections(business_id) WHERE status='active'")

    op.execute("""CREATE TABLE IF NOT EXISTS oauth_states (
        state TEXT PRIMARY KEY,
        business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
        platform TEXT NOT NULL,
        redirect_uri TEXT,
        created_by BIGINT REFERENCES users(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        expires_at TIMESTAMPTZ NOT NULL)""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_oauth_states_expiry ON oauth_states(expires_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS oauth_states")
    op.execute("DROP TABLE IF EXISTS platform_connections")
