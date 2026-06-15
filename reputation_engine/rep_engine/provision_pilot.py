"""
Provision the Team Unstoppable pilot (free / unmetered)
=======================================================
Creates the organization + business + an invited owner login -- no subscription, so the
quota gate treats it as unmetered (free). Idempotent: re-running won't duplicate the org or
business. The owner gets an invite link (emailed if SMTP is configured, otherwise printed so
you can hand it over). Run:

    python -m rep_engine.provision_pilot --owner-email owner@teamunstoppable.com --owner-name "Jane Doe"
"""

from __future__ import annotations

import argparse
import os
import secrets
from typing import Optional

try:
    from .db import db
    from .api import auth
    from . import email_service
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    from api import auth  # type: ignore
    import email_service  # type: ignore

PILOT_ORG = "Team Unstoppable"
PILOT_BUSINESS = {
    "name": "Team Unstoppable",
    "domain": "teamunstoppable.com",
    "services": ("financial services, term life insurance, financial education and training, "
                 "recruitment of licensed financial professionals"),
    "goal": ("Be seen as a legitimate, reputable financial-services career opportunity and "
             "life-insurance provider -- ensure AI assistants surface accurate, positive "
             "information and that MLM/pyramid/scam narratives do not dominate the answer."),
    "contested_terms": "MLM, pyramid scheme, scam, income disclosure, recruitment",
    "geo": "United States",
}


def provision(owner_email: str, owner_name: Optional[str] = None,
              org_name: Optional[str] = None, base_url: Optional[str] = None) -> dict:
    org_name = org_name or PILOT_ORG
    invite_link = None
    with db() as conn:
        org = conn.execute("SELECT id FROM organizations WHERE name=%s", (org_name,)).fetchone()
        if not org:
            org = conn.execute("INSERT INTO organizations (name) VALUES (%s) RETURNING id",
                               (org_name,)).fetchone()
        org_id = org["id"]

        b = PILOT_BUSINESS
        biz = conn.execute("SELECT id FROM businesses WHERE domain=%s AND org_id=%s",
                           (b["domain"], org_id)).fetchone()
        if not biz:
            biz = conn.execute(
                "INSERT INTO businesses (name, domain, services, goal, contested_terms, geo, org_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (b["name"], b["domain"], b["services"], b["goal"], b["contested_terms"],
                 b["geo"], org_id),
            ).fetchone()
        business_id = biz["id"]

        existing = auth.get_user_by_email(conn, owner_email)
        if existing:
            owner_id = existing["id"]
            conn.execute("UPDATE users SET org_id=%s, org_role='owner' WHERE id=%s",
                         (org_id, owner_id))
        else:
            owner_id = conn.execute(
                "INSERT INTO users (email, password_hash, full_name, role, is_active, org_id, org_role) "
                "VALUES (%s,%s,%s,'client',FALSE,%s,'owner') RETURNING id",
                (owner_email, auth.hash_password(secrets.token_urlsafe(16)), owner_name, org_id),
            ).fetchone()["id"]
            raw = auth.issue_action_token(conn, owner_id, "invite", 168)
            base = (base_url or os.getenv("APP_BASE_URL", "http://localhost:3000")).rstrip("/")
            invite_link = f"{base}/accept-invite?token={raw}"
        conn.commit()

    if invite_link:
        email_service.send_email(
            owner_email, "Your Team Unstoppable reputation console is ready",
            f"Welcome! Your Team Unstoppable reputation console is set up.\n\n"
            f"Set your password and sign in here (valid 7 days):\n{invite_link}\n")
    return {"org_id": org_id, "business_id": business_id, "owner_user_id": owner_id,
            "invite_link": invite_link}


def main() -> None:  # pragma: no cover -- CLI entrypoint
    ap = argparse.ArgumentParser(description="Provision the Team Unstoppable pilot")
    ap.add_argument("--owner-email", required=True)
    ap.add_argument("--owner-name")
    ap.add_argument("--org-name")
    ap.add_argument("--base-url")
    args = ap.parse_args()
    out = provision(args.owner_email, args.owner_name, args.org_name, args.base_url)
    print(f"Pilot provisioned: org={out['org_id']} business={out['business_id']} "
          f"owner_user={out['owner_user_id']}")
    if out["invite_link"]:
        print("Invite link (emailed if SMTP is configured; share it with the owner otherwise):")
        print("  " + out["invite_link"])
    else:
        print("Owner already existed; attached to the org as owner (no new invite issued).")


if __name__ == "__main__":  # pragma: no cover
    main()
