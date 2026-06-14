"""External data ingestion (Phase 6): paste/upload a 3rd-party report, list signals.

POST stores RAW content only -- NO LLM in the request. Normalization is a background
job (POST /businesses/{id}/jobs/normalize_signals) that runs through the budget-gated,
fenced agent_tools seam. Ingesting is editor-only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import authorize_business, require_business_editor
from ..schemas import IngestSignalRequest

try:
    from ... import external_signals as _es
except ImportError:  # pragma: no cover
    import external_signals as _es  # type: ignore

router = APIRouter(prefix="/businesses/{business_id}", tags=["integrations"])


@router.post("/external-signals", status_code=201)
def ingest_signal(body: IngestSignalRequest, business_id: int = Depends(require_business_editor)):
    # store_raw makes NO LLM call (safe in a request); normalize via the job.
    return _es.store_raw(business_id, body.source, body.signal_type, body.content)


@router.get("/external-signals")
def list_signals(business_id: int = Depends(authorize_business)):
    return _es.list_signals(business_id)
