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


def _bearer(c, email="admin@example.com", pw="pw12345678"):
    tok = c.post("/auth/login", json={"email": email, "password": pw}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_send_email_attaches_file(monkeypatch):
    import smtplib
    from rep_engine import email_service as es
    monkeypatch.setenv("SMTP_HOST", "h"); monkeypatch.setenv("SMTP_USER", "u"); monkeypatch.setenv("SMTP_PASSWORD", "p")
    captured = {}

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, *a): pass
        def send_message(self, msg): captured["msg"] = msg
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    sent = es.send_email("x@y.com", "Subj", "body",
                         attachments=[("r.docx", b"PKDATA", _DOCX)])
    assert sent is True
    assert [p.get_filename() for p in captured["msg"].iter_attachments()] == ["r.docx"]


def test_send_email_bad_header_returns_false(monkeypatch):
    import smtplib
    from rep_engine import email_service as es
    monkeypatch.setenv("SMTP_HOST", "h"); monkeypatch.setenv("SMTP_USER", "u"); monkeypatch.setenv("SMTP_PASSWORD", "p")
    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not reach SMTP")))
    # a CR/LF in a header value makes EmailMessage raise; send_email must CATCH it and return
    # False (never raise) -- so the email endpoint returns {sent:false}, not a 500.
    assert es.send_email("x@y.com", "Subject\nBcc: evil@example.com", "body") is False


_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


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


def test_docx_to_pdf_no_libreoffice_returns_none(monkeypatch):
    import shutil
    from rep_engine import report_generator as rg
    monkeypatch.setattr(shutil, "which", lambda name: None)   # no soffice/libreoffice on PATH
    assert rg._docx_to_pdf("/whatever.docx") is None


@requires_db
def test_save_report_drops_stale_pdf_when_conversion_unavailable(fresh_schema, tmp_path, monkeypatch):
    import os as _os
    import shutil
    from datetime import date
    from docx import Document
    from rep_engine import report_generator as rg
    monkeypatch.setattr(rg, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(shutil, "which", lambda name: None)   # no LibreOffice -> conversion returns None
    conn = fresh_schema
    bid = conn.execute("INSERT INTO businesses (name) VALUES ('Acme') RETURNING id").fetchone()["id"]
    conn.commit()
    # a stale PDF from a prior run already sits at today's basename
    fname = f"Acme_AI_Visibility_Report_{date.today().isoformat()}.docx"
    (tmp_path / fname.replace(".docx", ".pdf")).write_bytes(b"%PDF stale")

    doc = Document(); doc.add_paragraph("fresh content")
    path = rg._save_report(doc, {"id": bid, "name": "Acme"})

    # the .docx saved fine (conversion-unavailable didn't break generation) and the stale PDF is gone
    assert _os.path.isfile(path)
    assert not _os.path.exists(_os.path.splitext(path)[0] + ".pdf")


@requires_db
def test_pdf_present_lists_downloads_and_emails(fresh_schema, tmp_path, monkeypatch):
    conn = fresh_schema
    from rep_engine import report_generator as rg
    from rep_engine import email_service as es
    monkeypatch.setattr(rg, "OUTPUT_DIR", str(tmp_path))
    bid = conn.execute("INSERT INTO businesses (name) VALUES ('Acme') RETURNING id").fetchone()["id"]
    conn.commit()
    (tmp_path / "R.docx").write_bytes(b"PK-doc")
    (tmp_path / "R.pdf").write_bytes(b"%PDF-1.4 fake")   # colocated PDF, as if LibreOffice ran
    rg._record_report(bid, "R.docx", str(tmp_path / "R.docx"))
    rid = conn.execute("SELECT id FROM reports WHERE business_id=%s", (bid,)).fetchone()["id"]
    captured = {}
    monkeypatch.setattr(es, "send_email",
                        lambda to, subject, body, **kw: (captured.update(atts=kw.get("attachments")), True)[1])
    _admin(conn)
    c = _client()
    h = _bearer(c)

    # list flags the PDF
    reps = c.get(f"/businesses/{bid}/reports", headers=h).json()
    assert reps[0]["has_pdf"] is True
    # PDF download serves the .pdf
    d = c.get(f"/businesses/{bid}/reports/{rid}/download?fmt=pdf", headers=h)
    assert d.status_code == 200 and d.content == b"%PDF-1.4 fake"
    assert "application/pdf" in d.headers.get("content-type", "")
    # email prefers the PDF attachment
    c.post(f"/businesses/{bid}/reports/{rid}/email", json={"to": "x@example.com"}, headers=h)
    assert captured["atts"][0][0].endswith(".pdf")


@requires_db
def test_pdf_download_410_when_absent(fresh_schema, tmp_path, monkeypatch):
    conn = fresh_schema
    from rep_engine import report_generator as rg
    monkeypatch.setattr(rg, "OUTPUT_DIR", str(tmp_path))
    bid = conn.execute("INSERT INTO businesses (name) VALUES ('Acme') RETURNING id").fetchone()["id"]
    conn.commit()
    (tmp_path / "R.docx").write_bytes(b"PK-doc")   # no .pdf sibling
    rg._record_report(bid, "R.docx", str(tmp_path / "R.docx"))
    rid = conn.execute("SELECT id FROM reports WHERE business_id=%s", (bid,)).fetchone()["id"]
    _admin(conn)
    c = _client()
    h = _bearer(c)
    assert c.get(f"/businesses/{bid}/reports", headers=h).json()[0]["has_pdf"] is False
    assert c.get(f"/businesses/{bid}/reports/{rid}/download?fmt=pdf", headers=h).status_code == 410
    assert c.get(f"/businesses/{bid}/reports/{rid}/download", headers=h).status_code == 200   # docx still works


@requires_db
def test_email_report(fresh_schema, tmp_path, monkeypatch):
    conn = fresh_schema
    from rep_engine import report_generator as rg
    from rep_engine import email_service as es
    monkeypatch.setattr(rg, "OUTPUT_DIR", str(tmp_path))
    bid = conn.execute("INSERT INTO businesses (name) VALUES ('Acme') RETURNING id").fetchone()["id"]
    conn.commit()
    (tmp_path / "R.docx").write_bytes(b"PK-doc")
    rg._record_report(bid, "R.docx", str(tmp_path / "R.docx"))
    rid = conn.execute("SELECT id FROM reports WHERE business_id=%s", (bid,)).fetchone()["id"]

    captured = {}
    monkeypatch.setattr(es, "send_email",
                        lambda to, subject, body, **kw: (captured.update(to=to, atts=kw.get("attachments")), True)[1])
    _admin(conn)
    c = _client()
    h = _bearer(c)
    r = c.post(f"/businesses/{bid}/reports/{rid}/email", json={"to": "client@example.com"}, headers=h)
    assert r.status_code == 200 and r.json()["sent"] is True
    assert captured["to"] == "client@example.com"
    assert captured["atts"][0][0] == "R.docx"   # the report was attached by filename

    # tenancy: the report bound to another business id -> 404
    other = conn.execute("INSERT INTO businesses (name) VALUES ('Other') RETURNING id").fetchone()["id"]
    conn.commit()
    assert c.post(f"/businesses/{other}/reports/{rid}/email", json={"to": "x@y.com"}, headers=h).status_code == 404
    # invalid recipient -> 422 (pydantic EmailStr)
    assert c.post(f"/businesses/{bid}/reports/{rid}/email", json={"to": "not-an-email"}, headers=h).status_code == 422


@requires_db
def test_email_report_unconfigured_smtp_is_sent_false_not_error(fresh_schema, tmp_path, monkeypatch):
    conn = fresh_schema
    from rep_engine import report_generator as rg
    monkeypatch.setattr(rg, "OUTPUT_DIR", str(tmp_path))
    for v in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(v, raising=False)
    bid = conn.execute("INSERT INTO businesses (name) VALUES ('Acme') RETURNING id").fetchone()["id"]
    conn.commit()
    (tmp_path / "R.docx").write_bytes(b"PK")
    rg._record_report(bid, "R.docx", str(tmp_path / "R.docx"))
    rid = conn.execute("SELECT id FROM reports WHERE business_id=%s", (bid,)).fetchone()["id"]
    _admin(conn)
    c = _client()
    h = _bearer(c)
    # real send_email: SMTP unconfigured -> logs + returns False -> endpoint is 200 {sent:false}
    r = c.post(f"/businesses/{bid}/reports/{rid}/email", json={"to": "client@example.com"}, headers=h)
    assert r.status_code == 200 and r.json()["sent"] is False


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
