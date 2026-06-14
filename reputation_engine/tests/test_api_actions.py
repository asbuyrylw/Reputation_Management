"""Phase-3 API action tests: draft approve/reject (human gate -> assets), work-order
status, and editor-vs-viewer authorization. The actions wrap the verified engine
functions, so the human gate + work-order advance behave exactly as the CLI."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-please-change-0123456789abcdef")

from conftest import requires_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _client():
    from rep_engine.api.main import app
    return TestClient(app)


def _user(conn, email, role):
    from rep_engine.api import auth
    return conn.execute(
        "INSERT INTO users (email, password_hash, role) VALUES (%s,%s,%s) RETURNING id",
        (email, auth.hash_password("pw12345678"), role),
    ).fetchone()["id"]


def _token(c, email):
    return c.post("/auth/login", json={"email": email, "password": "pw12345678"}).json()["access_token"]


def _biz(conn):
    return conn.execute("INSERT INTO businesses (name, domain) VALUES ('Acme','a.com') RETURNING id").fetchone()["id"]


def _draft(conn, bid, wo_id=None, asset_type="faq"):
    return conn.execute(
        "INSERT INTO content_drafts (business_id, work_order_id, asset_type, title, body, status) "
        "VALUES (%s,%s,%s,'A draft','body','pending_review') RETURNING id",
        (bid, wo_id, asset_type),
    ).fetchone()["id"]


@requires_db
def test_approve_reject_and_status(fresh_schema):
    conn = fresh_schema
    bid = _biz(conn)
    _user(conn, "admin@example.com", "admin")
    wo = conn.execute(
        "INSERT INTO work_orders (business_id, wo_code, title, status) "
        "VALUES (%s,'WO-1','Write FAQ','pending') RETURNING id", (bid,)
    ).fetchone()["id"]
    d1 = _draft(conn, bid, wo)
    d2 = _draft(conn, bid, None, "article")
    conn.commit()

    with _client() as c:
        h = {"Authorization": f"Bearer {_token(c, 'admin@example.com')}"}

        # approve d1 -> asset created, draft approved, linked WO advanced to done
        assert c.post(f"/businesses/{bid}/content-drafts/{d1}/approve", headers=h).status_code == 200
        assert conn.execute("SELECT status FROM content_drafts WHERE id=%s", (d1,)).fetchone()["status"] == "approved"
        assert conn.execute("SELECT count(*) n FROM assets WHERE business_id=%s", (bid,)).fetchone()["n"] == 1
        assert conn.execute("SELECT status FROM work_orders WHERE id=%s", (wo,)).fetchone()["status"] == "done"

        # reject d2
        assert c.post(f"/businesses/{bid}/content-drafts/{d2}/reject", headers=h, json={"notes": "off-brand"}).status_code == 200
        assert conn.execute("SELECT status FROM content_drafts WHERE id=%s", (d2,)).fetchone()["status"] == "rejected"

        # set WO status (valid), then reject an invalid status
        assert c.post(f"/businesses/{bid}/work-orders/{wo}/status", headers=h, json={"status": "verified"}).status_code == 200
        assert conn.execute("SELECT status FROM work_orders WHERE id=%s", (wo,)).fetchone()["status"] == "verified"
        assert c.post(f"/businesses/{bid}/work-orders/{wo}/status", headers=h, json={"status": "nope"}).status_code == 400


@requires_db
def test_viewer_cannot_act_editor_can(fresh_schema):
    conn = fresh_schema
    bid = _biz(conn)
    viewer = _user(conn, "viewer@example.com", "client")
    editor = _user(conn, "editor@example.com", "client")
    conn.execute("INSERT INTO business_access (user_id, business_id, access_role) VALUES (%s,%s,'viewer')", (viewer, bid))
    conn.execute("INSERT INTO business_access (user_id, business_id, access_role) VALUES (%s,%s,'editor')", (editor, bid))
    d = _draft(conn, bid)
    conn.commit()

    with _client() as c:
        vh = {"Authorization": f"Bearer {_token(c, 'viewer@example.com')}"}
        eh = {"Authorization": f"Bearer {_token(c, 'editor@example.com')}"}

        assert c.get(f"/businesses/{bid}/content-drafts", headers=vh).status_code == 200    # viewer can read
        assert c.post(f"/businesses/{bid}/content-drafts/{d}/approve", headers=vh).status_code == 403  # but not act
        assert c.post(f"/businesses/{bid}/content-drafts/{d}/approve", headers=eh).status_code == 200  # editor can
        assert c.post(f"/businesses/{bid}/content-drafts/999999/approve", headers=eh).status_code == 404  # missing draft
