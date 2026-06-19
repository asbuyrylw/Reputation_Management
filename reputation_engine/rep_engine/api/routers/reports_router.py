"""Report delivery: list the generated monthly reports for a business and download one.
Generation itself is the background `report` job (LLM/render work out of the request path);
this router only serves the resulting files, tenancy-checked and path-validated."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from ..deps import authorize_business, get_conn

router = APIRouter(prefix="/businesses/{business_id}", tags=["reports"])

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


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
    row = conn.execute(
        "SELECT filename FROM reports WHERE id=%s AND business_id=%s",
        (report_id, business_id),
    ).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")

    # Reconstruct the served path from the configured output dir + the stored BASENAME, so it
    # is always anchored to this API's OUTPUT_DIR (CWD-independent) and can never escape it
    # via a stored absolute/relative path. realpath resolves symlinks; the startswith check is
    # belt-and-suspenders against a filename that somehow carries path separators.
    from ...report_generator import OUTPUT_DIR
    base = os.path.realpath(OUTPUT_DIR)
    name = os.path.basename(row["filename"] or "")
    path = os.path.realpath(os.path.join(base, name))
    if not name or not path.startswith(base + os.sep):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid report path")
    if not os.path.isfile(path):
        raise HTTPException(status.HTTP_410_GONE, "Report file is no longer available")
    return FileResponse(path, media_type=_DOCX_MIME, filename=name)
