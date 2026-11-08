"""Map storage search results into the API evidence contract."""

from __future__ import annotations

from typing import Any

from ..schemas import EvidenceRef


def to_evidence_ref(item: Any) -> EvidenceRef:
    if isinstance(item, EvidenceRef):
        return item
    if hasattr(item, "model_dump"):
        return EvidenceRef.model_validate(item.model_dump())
    if hasattr(item, "dict"):
        return EvidenceRef.model_validate(item.dict())
    if not hasattr(item, "viewer_url"):
        raise TypeError("unsupported evidence result")
    values = {
        "evidence_id": item.evidence_id,
        "document_id": item.document_id,
        "document_version_id": item.document_version_id,
        "node_id": item.node_id,
        "document_number": item.document_number,
        "title": item.title,
        "label": item.label,
        "quote_exact": item.quote_exact,
        "page": item.page,
        "source_hash": item.source_hash,
        "as_of_date": item.as_of_date,
        "amendment_state": item.amendment_state,
        "viewer_url": item.viewer_url,
        "outside_scope": item.outside_scope,
    }
    return EvidenceRef.model_validate(values)
