"""Report delivery: record a generated report, list it, download it (tenancy + path-safe)."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-please-change-0123456789abcdef")

from conftest import requires_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _client():
    from rep_engine.api.main import app
    return TestClient(app)


def _admin(conn, email="admin@example.com"):
    from rep_engine.api import auth
    conn.execute("INSERT INTO users (email, password_hash, role) VALUES (%s,%s,'admin')",
                 (email, auth.hash_password("pw12345678")))
    conn.commit()


@requires_db
def test_record_list_download(fresh_schema, tmp_path, monkeypatch):
    conn = fresh_schema
    from rep_engine import report_generator as rg
    monkeypatch.setattr(rg, "OUTPUT_DIR", str(tmp_path))
    bid = conn.execute("INSERT INTO businesses (name, domain) VALUES ('Acme','a.com') RETURNING id").fetchone()["id"]
    conn.commit()

    f = tmp_path / "Acme_report.docx"
    f.write_bytes(b"PK-fake-docx")
    rg._record_report(bid, "Acme_report.docx", str(f))

    _admin(conn)
    c = _client()
    c.post("/auth/login", json={"email": "admin@example.com", "password": "pw12345678"})

    reps = c.get(f"/businesses/{bid}/reports").json()
    assert len(reps) == 1 and reps[0]["filename"] == "Acme_report.docx"
    rid = reps[0]["id"]

    d = c.get(f"/businesses/{bid}/reports/{rid}/download")
    assert d.status_code == 200 and d.content == b"PK-fake-docx"

    # the report is bound to its business: requesting it under another business id 404s
    other = conn.execute("INSERT INTO businesses (name) VALUES ('Other') RETURNING id").fetchone()["id"]
    conn.commit()
    assert c.get(f"/businesses/{other}/reports/{rid}/download").status_code == 404


@requires_db
def test_download_never_serves_a_file_outside_output_dir(fresh_schema, tmp_path, monkeypatch):
    conn = fresh_schema
    from rep_engine import report_generator as rg
    monkeypatch.setattr(rg, "OUTPUT_DIR", str(tmp_path / "out"))
    os.makedirs(tmp_path / "out", exist_ok=True)
    bid = conn.execute("INSERT INTO businesses (name) VALUES ('Acme') RETURNING id").fetchone()["id"]
    # a malicious row whose filename carries traversal + a path pointing OUTSIDE the dir: we
    # only ever serve OUTPUT_DIR/<basename>, so the outside file is never returned.
    outside = tmp_path / "secret.docx"
    outside.write_bytes(b"SECRET")
    conn.execute("INSERT INTO reports (business_id, filename, path, kind) VALUES (%s,'../secret.docx',%s,'monthly')",
                 (bid, str(outside)))
    conn.commit()
    rid = conn.execute("SELECT id FROM reports WHERE business_id=%s", (bid,)).fetchone()["id"]

    _admin(conn)
    c = _client()
    c.post("/auth/login", json={"email": "admin@example.com", "password": "pw12345678"})
    r = c.get(f"/businesses/{bid}/reports/{rid}/download")
    assert r.status_code == 410           # basename anchored to OUTPUT_DIR, no such file there
    assert b"SECRET" not in r.content     # the outside file is never served


@requires_db
def test_client_tenancy(fresh_schema, tmp_path, monkeypatch):
    conn = fresh_schema
    from rep_engine import report_generator as rg
    from rep_engine.api import auth
    monkeypatch.setattr(rg, "OUTPUT_DIR", str(tmp_path))
    # two businesses; the client is granted access to only one
    granted = conn.execute("INSERT INTO businesses (name) VALUES ('Granted') RETURNING id").fetchone()["id"]
    forbidden = conn.execute("INSERT INTO businesses (name) VALUES ('Forbidden') RETURNING id").fetchone()["id"]
    uid = conn.execute("INSERT INTO users (email, password_hash, role) VALUES ('c@example.com',%s,'client') RETURNING id",
                       (auth.hash_password("pw12345678"),)).fetchone()["id"]
    conn.execute("INSERT INTO business_access (user_id, business_id, access_role) VALUES (%s,%s,'viewer')",
                 (uid, granted))
    conn.commit()
    f = tmp_path / "G.docx"; f.write_bytes(b"PK-g")
    rg._record_report(granted, "G.docx", str(f))
    rg._record_report(forbidden, "F.docx", str(tmp_path / "F.docx"))
    gid = conn.execute("SELECT id FROM reports WHERE business_id=%s", (granted,)).fetchone()["id"]

    c = _client()
    c.post("/auth/login", json={"email": "c@example.com", "password": "pw12345678"})
    assert c.get(f"/businesses/{granted}/reports").status_code == 200
    assert c.get(f"/businesses/{granted}/reports/{gid}/download").status_code == 200
    # no grant to the other business -> 403 from authorize_business
    assert c.get(f"/businesses/{forbidden}/reports").status_code == 403


@requires_db
def test_download_missing_file_is_gone(fresh_schema, tmp_path, monkeypatch):
    conn = fresh_schema
    from rep_engine import report_generator as rg
    monkeypatch.setattr(rg, "OUTPUT_DIR", str(tmp_path))
    bid = conn.execute("INSERT INTO businesses (name) VALUES ('Acme') RETURNING id").fetchone()["id"]
    conn.commit()  # commit so _record_report's own connection can see the business (FK)
    rg._record_report(bid, "gone.docx", str(tmp_path / "gone.docx"))  # file never written
    rid = conn.execute("SELECT id FROM reports WHERE business_id=%s", (bid,)).fetchone()["id"]

    _admin(conn)
    c = _client()
    c.post("/auth/login", json={"email": "admin@example.com", "password": "pw12345678"})
    assert c.get(f"/businesses/{bid}/reports/{rid}/download").status_code == 410
