"""Technical candidate-retrieval smoke test; public PDFs remain unreviewed."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.documents.native_pdf import extract_native_pdf, sha256_file  # noqa: E402
from app.documents.ocr import configured_ocr_engine  # noqa: E402
from app.documents.tree_parser import parse_legal_tree  # noqa: E402
from app.schemas import AmendmentStatus, Scope, ScopeMode  # noqa: E402
from app.storage.authorized_search import (  # noqa: E402
    AuthorizedNode,
    InMemoryAuthorizedNodeSearch,
)
from app.workflow.fixed_pipeline import FixedPipeline  # noqa: E402


async def evaluate(manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = manifest["documents"]
    engine = configured_ocr_engine()
    if engine is None:
        raise ValueError("EVIDENCE_OCR_EXECUTABLE_REQUIRED_FOR_FULL_CORPUS")
    principal = uuid5(NAMESPACE_URL, "public-pdf-technical-evaluation-principal")
    category = uuid5(NAMESPACE_URL, "public-pdf-technical-evaluation-category")
    as_of_date = date.today()
    candidates: list[AuthorizedNode] = []
    for entry in documents:
        if entry["review_status"] != "test_only_unreviewed":
            raise ValueError("TEST_CORPUS_REVIEW_STATUS_CHANGED")
        path = (manifest_path.parent / entry["local_file"]).resolve()
        if not path.is_relative_to(manifest_path.parent.resolve()):
            raise ValueError("UNSAFE_LOCAL_FILE")
        if sha256_file(path) != entry["sha256"]:
            raise ValueError("CORPUS_INTEGRITY_MISMATCH")
        pages, digest = extract_native_pdf(path, ocr_engine=engine)
        if digest != entry["sha256"]:
            raise ValueError("CORPUS_INTEGRITY_MISMATCH")
        document_id = uuid5(NAMESPACE_URL, digest)
        for index, node in enumerate(parse_legal_tree(pages)):
            if not node.text_original.strip():
                continue
            node_id = uuid5(NAMESPACE_URL, f"{digest}:{index}")
            candidates.append(
                AuthorizedNode(
                    evidence_id=f"eval_{node_id.hex}",
                    document_id=document_id,
                    document_version_id=document_id,
                    node_id=node_id,
                    document_number=entry["document_number"],
                    title=entry["title"],
                    label=node.label_original,
                    quote_exact=node.text_original,
                    page=node.page_start,
                    source_hash=digest,
                    as_of_date=as_of_date,
                    amendment_state=AmendmentStatus.UNKNOWN,
                    category_ids=(category,),
                )
            )

    search = InMemoryAuthorizedNodeSearch(candidates, {principal: {category}})
    scope = Scope(scope_mode=ScopeMode.ALL_AUTHORIZED, as_of_date=as_of_date)
    cases = [
        {"query": entry["document_number"], "expected_document": entry["document_number"]}
        for entry in documents
    ]
    cases.extend(
        [
            {
                "query": "Điều 1 Nghị định 351/2026/NĐ-CP",
                "expected_document": "351/2026/NĐ-CP",
                "expected_article": "Điều 1",
            },
            {
                "query": "Điều 3 Nghị định 381/2026/NĐ-CP",
                "expected_document": "381/2026/NĐ-CP",
                "expected_article": "Điều 3",
            },
            {
                "query": "Điều 2 Nghị định 385/2026/NĐ-CP",
                "expected_document": "385/2026/NĐ-CP",
                "expected_article": "Điều 2",
            },
        ]
    )
    results: list[dict[str, object]] = []
    for case in cases:
        found = await search.search(principal_id=principal, scope=scope, query=case["query"])
        reranked = FixedPipeline._rank_evidence(found, case["query"])
        top = reranked[0] if reranked else None
        document_hit = top is not None and top.document_number == case["expected_document"]
        expected_article = case.get("expected_article")
        article_hit = (
            expected_article is None
            or (top is not None and top.label.startswith(expected_article + "."))
        )
        results.append(
            {
                **case,
                "top_document": top.document_number if top else None,
                "top_label": top.label if top else None,
                "candidate_count": len(found),
                "document_hit": document_hit,
                "article_hit": article_hit,
                "passed": document_hit and article_hit,
            }
        )
    return {
        "purpose": "Candidate-retrieval smoke test only; no source approval or verified answers",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "document_count": len(documents),
        "node_count": len(candidates),
        "case_count": len(results),
        "passed": sum(bool(item["passed"]) for item in results),
        "cases": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "evaluation" / "corpus_public_real" / "manifest.json",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(evaluate(args.manifest))
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
