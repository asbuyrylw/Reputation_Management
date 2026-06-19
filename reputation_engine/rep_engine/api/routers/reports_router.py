"""Report delivery: list the generated monthly reports for a business and download one.
Generation itself is the background `report` job (LLM/render work out of the request path);
this router only serves the resulting files, tenancy-checked and path-validated."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr

from ..deps import authorize_business, get_conn, require_business_editor

router = APIRouter(prefix="/businesses/{business_id}", tags=["reports"])

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _resolve_report_file(conn, report_id: int, business_id: int) -> tuple[str, str]:
    """(name, path) for a tenant's report, or raise 404/403/410. The served path is rebuilt
    from OUTPUT_DIR + the stored BASENAME so it's CWD-independent and can never escape the dir."""
    row = conn.execute(
        "SELECT filename FROM reports WHERE id=%s AND business_id=%s",
        (report_id, business_id),
    ).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    from ...report_generator import OUTPUT_DIR
    base = os.path.realpath(OUTPUT_DIR)
    name = os.path.basename(row["filename"] or "")
    path = os.path.realpath(os.path.join(base, name))
    if not name or not path.startswith(base + os.sep):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid report path")
    if not os.path.isfile(path):
        raise HTTPException(status.HTTP_410_GONE, "Report file is no longer available")
    return name, path


@router.get("/reports")
def list_reports(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, filename, kind, created_at FROM reports WHERE business_id=%s ORDER BY id DESC",
        (business_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/reports/{report_id}/download")
def download_report(report_id: int, business_id: int = Depends(authorize_business),
                    conn=Depends(get_conn)):
    name, path = _resolve_report_file(conn, report_id, business_id)
    return FileResponse(path, media_type=_DOCX_MIME, filename=name)


class ReportEmail(BaseModel):
    to: EmailStr


@router.post("/reports/{report_id}/email")
def email_report(report_id: int, payload: ReportEmail,
                 business_id: int = Depends(require_business_editor), conn=Depends(get_conn)):
    """Email a report to a recipient as a .docx attachment. Returns {sent} -- False (not an
    error) when SMTP isn't configured, so the UI can say 'email isn't set up' rather than fail."""
    name, path = _resolve_report_file(conn, report_id, business_id)
    biz = conn.execute("SELECT name FROM businesses WHERE id=%s", (business_id,)).fetchone()
    biz_name = (biz or {}).get("name") or "your business"
    with open(path, "rb") as f:
        content = f.read()
    from ... import email_service
    subject = f"AI Visibility Report — {biz_name}"
    body = (f"Attached is the latest AI-visibility report for {biz_name}.\n\n"
            "It summarizes where you stand with AI assistants and the progress since last month.")
    sent = email_service.send_email(str(payload.to), subject, body,
                                    attachments=[(name, content, _DOCX_MIME)])
    return {"sent": sent, "to": str(payload.to)}
