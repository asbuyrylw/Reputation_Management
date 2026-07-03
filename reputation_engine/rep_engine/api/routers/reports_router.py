"""Report delivery: list the generated monthly reports for a business, download one (.docx
or, when LibreOffice produced one, .pdf), and email it. Generation itself is the background
`report` job (LLM/render work out of the request path); this router only serves the resulting
files, tenancy-checked and path-validated."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr

from ..deps import authorize_business, get_conn, require_business_editor

router = APIRouter(prefix="/businesses/{business_id}", tags=["reports"])

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PDF_MIME = "application/pdf"


def _resolve_report_file(conn, report_id: int, business_id: int) -> tuple[str, str]:
    """(name, path) for a tenant's report .docx, or raise 404/403/410. The served path is
    rebuilt from OUTPUT_DIR + the stored BASENAME so it's CWD-independent and can't escape."""
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


def _pdf_sibling(docx_path: str) -> str | None:
    """The colocated <basename>.pdf next to a resolved .docx (already anchored to OUTPUT_DIR),
    or None when LibreOffice didn't produce one."""
    pdf = os.path.splitext(docx_path)[0] + ".pdf"
    return pdf if os.path.isfile(pdf) else None


@router.get("/reports")
def list_reports(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, filename, kind, created_at FROM reports WHERE business_id=%s ORDER BY id DESC",
        (business_id,),
    ).fetchall()
    from ...report_generator import OUTPUT_DIR
    base = os.path.realpath(OUTPUT_DIR)
    out = []
    for r in rows:
        name = os.path.basename(r["filename"] or "")
        docx = os.path.realpath(os.path.join(base, name))
        has_pdf = bool(name and docx.startswith(base + os.sep) and _pdf_sibling(docx))
        out.append({**dict(r), "has_pdf": has_pdf})
    return out


@router.get("/reports/{report_id}/download")
def download_report(report_id: int, fmt: str = "docx",
                    business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    name, path = _resolve_report_file(conn, report_id, business_id)
    if fmt == "pdf":
        pdf = _pdf_sibling(path)
        if not pdf:
            raise HTTPException(status.HTTP_410_GONE, "No PDF is available for this report")
        return FileResponse(pdf, media_type=_PDF_MIME, filename=os.path.splitext(name)[0] + ".pdf")
    return FileResponse(path, media_type=_DOCX_MIME, filename=name)


class ReportEmail(BaseModel):
    to: EmailStr


@router.post("/reports/{report_id}/email")
def email_report(report_id: int, payload: ReportEmail,
                 business_id: int = Depends(require_business_editor), conn=Depends(get_conn)):
    """Email a report to a recipient -- the PDF when LibreOffice produced one, else the .docx.
    Returns {sent} -- False (not an error) when SMTP isn't configured, so the UI can say
    'email isn't set up' rather than fail."""
    name, path = _resolve_report_file(conn, report_id, business_id)
    pdf = _pdf_sibling(path)
    if pdf:
        attach_name, attach_path, mime = os.path.splitext(name)[0] + ".pdf", pdf, _PDF_MIME
    else:
        attach_name, attach_path, mime = name, path, _DOCX_MIME
    biz = conn.execute("SELECT name FROM businesses WHERE id=%s", (business_id,)).fetchone()
    biz_name = (biz or {}).get("name") or "your business"
    with open(attach_path, "rb") as f:
        content = f.read()
    from ... import email_service
    subject = f"AI Visibility Report — {biz_name}"
    body = (f"Attached is the latest AI-visibility report for {biz_name}.\n\n"
            "It summarizes where you stand with AI assistants and the progress since last month.")
    sent = email_service.send_email(str(payload.to), subject, body,
                                    attachments=[(attach_name, content, mime)])
    return {"sent": sent, "to": str(payload.to)}
