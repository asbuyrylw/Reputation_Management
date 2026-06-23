"""Onboarding (Phase 2d): teammate invites + password reset.

Self-serve account creation for a pilot is admin/owner-driven: an org owner/admin (or platform
admin) invites a user, who receives an email with a single-use link to set their password and
activate. Password reset is the same pattern. Email is sent via email_service (Zoho SMTP), which
logs the link in dev when SMTP isn't configured -- so a pilot can be set up before email creds
are added. The raw token is emailed; only its hash is stored.
"""

from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from .. import auth, ratelimit
from ..deps import get_conn, require_org_manager
from ..schemas import AcceptInviteRequest, ForgotPasswordRequest, InviteRequest, ResetPasswordRequest

try:
    from ... import email_service as _email
except ImportError:  # pragma: no cover
    import email_service as _email  # type: ignore

router = APIRouter(tags=["onboarding"])

INVITE_TTL_HOURS = 168   # 7 days
RESET_TTL_HOURS = 2


def _app_base() -> str:
    return os.getenv("APP_BASE_URL", "http://localhost:3000").rstrip("/")


def _check_password(pw: str) -> None:
    if not pw or len(pw) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password must be at least 8 characters")


@router.post("/auth/invite", status_code=status.HTTP_201_CREATED)
def invite_user(body: InviteRequest, user: dict = Depends(require_org_manager),
                conn=Depends(get_conn)):
    """Invite a teammate into an organization. Platform admin may target any org via org_id;
    an org owner/admin invites into their own org."""
    if body.org_role not in ("owner", "admin", "member"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "org_role must be owner|admin|member")
    org_id = body.org_id if user["role"] == "admin" else user.get("org_id")
    if not org_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no target organization")
    if not conn.execute("SELECT 1 FROM organizations WHERE id=%s", (org_id,)).fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "organization not found")
    if auth.get_user_by_email(conn, body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "a user with that email already exists")
    # create an INACTIVE user with an unusable random password; they set a real one on accept
    row = conn.execute(
        "INSERT INTO users (email, password_hash, full_name, role, is_active, org_id, org_role) "
        "VALUES (%s,%s,%s,'client',FALSE,%s,%s) RETURNING id",
        (body.email, auth.hash_password(secrets.token_urlsafe(16)), body.full_name,
         org_id, body.org_role),
    ).fetchone()
    raw = auth.issue_action_token(conn, row["id"], "invite", INVITE_TTL_HOURS)
    conn.commit()
    link = f"{_app_base()}/accept-invite?token={raw}"
    _email.send_email(
        body.email, "You're invited to the Reputation Console",
        f"You've been invited to join an organization on the Reputation Console.\n\n"
        f"Set your password and activate your account here (valid 7 days):\n{link}\n")
    # return the link only when email isn't configured, so an admin can still deliver it
    return {"ok": True, "user_id": row["id"],
            "invite_link": None if _email.enabled() else link}


@router.post("/auth/accept-invite")
def accept_invite(body: AcceptInviteRequest, conn=Depends(get_conn)):
    _check_password(body.password)
    user_id = auth.consume_action_token(conn, "invite", body.token)
    if not user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired invite token")
    auth.set_password(conn, user_id, body.password)
    conn.commit()
    return {"ok": True}


@router.post("/auth/forgot-password")
def forgot_password(body: ForgotPasswordRequest, request: Request, conn=Depends(get_conn)):
    """Email a password-reset link. Always returns ok (never reveals whether the email
    exists). Rate-limited per IP."""
    client = request.client.host if request.client else "?"
    if ratelimit.enabled() and not ratelimit.rate_check(f"forgot:{client}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests; try again shortly.")
    u = auth.get_user_by_email(conn, body.email)
    if u:
        raw = auth.issue_action_token(conn, u["id"], "reset", RESET_TTL_HOURS)
        conn.commit()
        link = f"{_app_base()}/reset-password?token={raw}"
        _email.send_email(
            body.email, "Reset your Reputation Console password",
            f"Use this link to reset your password (valid 2 hours):\n{link}\n\n"
            f"If you didn't request this, you can ignore this email.\n")
    return {"ok": True}


@router.post("/auth/reset-password")
def reset_password(body: ResetPasswordRequest, conn=Depends(get_conn)):
    _check_password(body.password)
    user_id = auth.consume_action_token(conn, "reset", body.token)
    if not user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired reset token")
    auth.set_password(conn, user_id, body.password)
    conn.commit()
    return {"ok": True}


# --------------------------------------------------------------------------------------
# Guided first-run setup: capture a business profile (name, site, goals, competitors,
# locations, keywords) in one call and kick off the full pipeline, so a new org goes from
# nothing to a populated dashboard without manually visiting every page + every "run" button.
# --------------------------------------------------------------------------------------
class CompetitorIn(BaseModel):
    name: str
    domain: str = ""


class OnboardingSetupRequest(BaseModel):
    name: str
    domain: str = ""
    services: str = ""           # comma-joined service keywords (edited as tags in the UI)
    industry: str = ""           # the vertical, distinct from the specific services
    goal: str = ""               # the positioning goal AI should reflect
    contested_terms: str = ""    # narratives/terms working against them
    geo: str = ""                # areas served (city/region) for local rankings
    competitors: list[CompetitorIn] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    run_pipeline: bool = True


# Full first-run pipeline so a new customer gets EVERY section populated, run once. The worker
# is strictly FIFO + one-at-a-time (pump() = "WHERE status='queued' ORDER BY id LIMIT 1"), so
# listing these in dependency order is sufficient: each completes before the next starts. The
# downstream steps that need the audit/gap (gap_model, plan, citation) therefore always run
# after it, and `report` runs LAST so the client report reflects everything above.
# NOTE: this is a one-time onboarding cost (audit ~$4 + benchmark + discovery, etc. -> ~$8-12)
# and takes ~30-50 min; progress shows live on the dashboard/audits banner.
_SETUP_PIPELINE = [
    "audit",             # AI-state audit -> scored answers (everything downstream needs this)
    "site_crawl",        # technical / on-page SEO crawl
    "gap_model",         # the gap analysis (needs the audit)
    "plan",              # strategy -> improvement tasks (needs the gap model)
    "sync_plan",         # materialize the plan into trackable work orders
    "citation_analyze",  # AI-citation share-of-voice / who AI quotes (needs the audit)
    "benchmark",         # competitor AI share-of-voice
    "local_rank",        # local Google rankings (needs SERPER_API_KEY)
    "suggest_prompts",   # AI-suggested tracking prompts
    "mentions_scan",     # web mentions + drafted (human-gated) replies
    "discovery",         # outreach targets (journalists / outlets / communities)
    "production_briefs", # content-to-produce briefs
    "report",            # client report LAST, so it reflects audit + gaps + plan + rankings
]

# Explicit prerequisites (job_type -> the job_types that must complete first). The worker
# enforces these via api_jobs.depends_on, so ordering is correct with ANY number of workers
# (not just a single FIFO consumer). Centralized in job_deps so the ad-hoc trigger path and
# the onboarding pipeline share one source of truth. Jobs not listed have no prerequisites.
from .. import job_deps as _job_deps

_SETUP_DEPS = _job_deps.SETUP_PREREQS


@router.post("/onboarding/setup", status_code=status.HTTP_201_CREATED)
def onboarding_setup(body: OnboardingSetupRequest, user: dict = Depends(require_org_manager),
                     conn=Depends(get_conn)):
    """Create a business under the caller's org from the setup wizard, register its
    competitors + keywords, and enqueue the full pipeline. Returns the new business id
    and the queued jobs so the UI can poll progress."""
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Business name is required")
    org_id = user.get("org_id")

    row = conn.execute(
        "INSERT INTO businesses (name, domain, services, industry, goal, contested_terms, geo, org_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (name, (body.domain or "").strip(), (body.services or "").strip(),
         (body.industry or "").strip(), (body.goal or "").strip(),
         (body.contested_terms or "").strip(), (body.geo or "").strip(), org_id),
    ).fetchone()
    business_id = row["id"]
    conn.commit()

    from ... import competitor as _c, mention_monitor as _mm

    competitors_added = 0
    for c in body.competitors:
        cn = (c.name or "").strip()
        if cn:
            _c.register_competitor(business_id, cn, (c.domain or "").strip())
            competitors_added += 1

    keywords_added = 0
    for k in body.keywords:
        kw = (k or "").strip()
        if kw:
            _mm.add_keyword(business_id, kw)
            keywords_added += 1

    jobs_enqueued = []
    if body.run_pipeline:
        from .. import jobs as _jobs
        id_by_type: dict = {}   # job_type -> enqueued job id, to wire dependencies
        for jt in _SETUP_PIPELINE:
            try:
                dep_ids = [id_by_type[d] for d in _SETUP_DEPS.get(jt, []) if d in id_by_type]
                job_id, active = _jobs.enqueue(business_id, jt, requested_by=user["id"],
                                               depends_on=dep_ids or None)
                if job_id:
                    id_by_type[jt] = job_id
                jobs_enqueued.append({
                    "job_type": jt,
                    "job_id": job_id or active,
                    "already_running": job_id is None,
                })
            except Exception as e:  # a single bad job type must not abort the whole setup
                jobs_enqueued.append({"job_type": jt, "job_id": None, "error": str(e)[:120]})

    return {
        "business_id": business_id,
        "name": name,
        "competitors_added": competitors_added,
        "keywords_added": keywords_added,
        "jobs": jobs_enqueued,
    }
