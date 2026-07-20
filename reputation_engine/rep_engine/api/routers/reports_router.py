"""Report delivery: list the generated monthly reports for a business, download one (.docx
or, when LibreOffice produced one, .pdf), and email it. Generation itself is the background
`report` job (LLM/render work out of the request path); this router only serves the resulting
files, tenancy-checked and path-validated."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr

from ..deps import authorize_business, get_conn, require_business_editor

router = APIRouter(prefix="/businesses/{business_id}", tags=["reports"])

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PDF_MIME = "application/pdf"


def _resolve_report(conn, report_id: int, business_id: int) -> dict:
    """Tenant report row -> {name, docx_path (if still on THIS service's disk), storage_key,
    pdf_storage_key}. Path rebuilt from OUTPUT_DIR + stored BASENAME (CWD-independent, can't escape).
    Raises 404 (not the tenant's) / 403 (bad path). Does NOT 410 on a missing file -- the caller
    falls back to durable object storage."""
    row = conn.execute(
        "SELECT filename, storage_key, pdf_storage_key FROM reports WHERE id=%s AND business_id=%s",
        (report_id, business_id),
    ).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    from ...report_generator import OUTPUT_DIR
    base = os.path.realpath(OUTPUT_DIR)
    name = os.path.basename(row["filename"] or "")
    path = os.path.realpath(os.path.join(base, name)) if name else ""
    if name and not path.startswith(base + os.sep):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid report path")
    return {"name": name or "AI_Visibility_Report.docx",
            "docx_path": path if (name and os.path.isfile(path)) else None,
            "storage_key": row.get("storage_key"), "pdf_storage_key": row.get("pdf_storage_key")}


def _pdf_sibling(docx_path: str) -> str | None:
    """The colocated <basename>.pdf next to a resolved .docx (already anchored to OUTPUT_DIR),
    or None when LibreOffice didn't produce one."""
    pdf = os.path.splitext(docx_path)[0] + ".pdf"
    return pdf if os.path.isfile(pdf) else None


def _storage_fetch(key: str) -> bytes | None:
    """Read a report's bytes from durable object storage (the fallback when the local disk file is
    gone after a redeploy). None when storage isn't configured or the object can't be read."""
    if not key:
        return None
    try:
        from ... import storage as _storage
    except ImportError:  # pragma: no cover
        import storage as _storage  # type: ignore
    if not _storage.configured():
        return None
    try:
        return _storage.get_storage().fetch(key)
    except Exception:  # noqa: BLE001
        return None


def _report_content(conn, report_id: int, business_id: int, fmt: str) -> tuple[str, str, bytes]:
    """(download_name, media_type, bytes) for a report in the requested format -- local disk first,
    then durable object storage. Raises 410 when neither has it."""
    r = _resolve_report(conn, report_id, business_id)
    if fmt == "pdf":
        pdf_name = os.path.splitext(r["name"])[0] + ".pdf"
        if r["docx_path"]:
            sib = _pdf_sibling(r["docx_path"])
            if sib:
                with open(sib, "rb") as f:
                    return pdf_name, _PDF_MIME, f.read()
        data = _storage_fetch(r["pdf_storage_key"])
        if data is not None:
            return pdf_name, _PDF_MIME, data
        raise HTTPException(status.HTTP_410_GONE, "No PDF is available for this report")
    # .docx (the source of truth)
    if r["docx_path"]:
        with open(r["docx_path"], "rb") as f:
            return r["name"], _DOCX_MIME, f.read()
    data = _storage_fetch(r["storage_key"])
    if data is not None:
        return r["name"], _DOCX_MIME, data
    raise HTTPException(status.HTTP_410_GONE, "Report file is no longer available")


@router.get("/reports")
def list_reports(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, filename, kind, created_at, storage_key, pdf_storage_key "
        "FROM reports WHERE business_id=%s ORDER BY id DESC",
        (business_id,),
    ).fetchall()
    from ...report_generator import OUTPUT_DIR
    base = os.path.realpath(OUTPUT_DIR)
    out = []
    for r in rows:
        name = os.path.basename(r["filename"] or "")
        docx = os.path.realpath(os.path.join(base, name)) if name else ""
        local_ok = bool(name and docx.startswith(base + os.sep) and os.path.isfile(docx))
        has_pdf = bool((local_ok and _pdf_sibling(docx)) or r.get("pdf_storage_key"))
        # available = servable from disk OR durable storage (else the row is an old, wiped report)
        available = bool(local_ok or r.get("storage_key"))
        out.append({"id": r["id"], "filename": r["filename"], "kind": r["kind"],
                    "created_at": r["created_at"], "has_pdf": has_pdf, "available": available})
    return out


@router.get("/reports/{report_id}/download")
def download_report(report_id: int, fmt: str = "docx",
                    business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    name, media, content = _report_content(conn, report_id, business_id, fmt)
    return Response(content=content, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


class ReportEmail(BaseModel):
    to: EmailStr


@router.post("/reports/{report_id}/email")
def email_report(report_id: int, payload: ReportEmail,
                 business_id: int = Depends(require_business_editor), conn=Depends(get_conn)):
    """Email a report to a recipient -- the PDF when LibreOffice produced one, else the .docx.
    Returns {sent} -- False (not an error) when SMTP isn't configured, so the UI can say
    'email isn't set up' rather than fail."""
    # Prefer the PDF (nicer for a client), fall back to the .docx -- each resolved from disk or storage.
    try:
        attach_name, mime, content = _report_content(conn, report_id, business_id, "pdf")
    except HTTPException:
        attach_name, mime, content = _report_content(conn, report_id, business_id, "docx")
    biz = conn.execute("SELECT name FROM businesses WHERE id=%s", (business_id,)).fetchone()
    biz_name = (biz or {}).get("name") or "your business"
    from ... import email_service
    subject = f"AI Visibility Report — {biz_name}"
    body = (f"Attached is the latest AI-visibility report for {biz_name}.\n\n"
            "It summarizes where you stand with AI assistants and the progress since last month.")
    sent = email_service.send_email(str(payload.to), subject, body,
                                    attachments=[(attach_name, content, mime)])
    return {"sent": sent, "to": str(payload.to)}
