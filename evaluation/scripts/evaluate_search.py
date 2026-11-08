"""Đo các chỉ số Search v1 (mục 9-B kế hoạch) trên bộ case JSON.

Mặc định script chạy bộ case HƯ CẤU (số hiệu/định danh văn bản hư cấu,
`approved_by = null`) để kiểm tra công thức và đường gọi API. Case chỉ được
tính vào `official_metrics` khi `approved_by` khác null; nếu không có case nào
được duyệt, report ghi `quality_status = "not_evaluated"` và tuyệt đối không
được dùng để tuyên bố chất lượng tìm kiếm trên văn bản thật.

Script chỉ đọc HTTP API và ghi report; không sửa backend hay cơ sở dữ liệu,
không tự duyệt đáp án.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUERIES_PATH = PROJECT_ROOT / "evaluation" / "search_eval" / "queries_hucau.json"
DEFAULT_FIXTURES_PATH = PROJECT_ROOT / "evaluation" / "search_eval" / "fixtures" / "sample_responses.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "search_eval" / "reports"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TOKEN_ENV = "EVIDENCE_ACCESS_TOKEN"
SEARCH_PATH = "/api/v1/search"

SCHEMA_VERSION = 1
CORPUS_LABEL = "HU_CAU"
DISPLAY_LABEL = "HƯ CẤU"
VALID_MODES = ("auto", "phrase", "keywords")
VALID_GROUP_BY = ("document",)
VALID_EMPTY_REASONS = frozenset({"NO_AUTHORIZED_DOCUMENTS", "NO_RESULTS", "PHRASE_NOT_FOUND"})
FILTER_KEYS = ("category_id", "doc_type", "issuing_body", "as_of_date", "only_active", "group_by")
REQUIRED_CASE_FIELDS = (
    "id",
    "query",
    "mode",
    "filters",
    "expected_documents",
    "expected_nodes",
    "expected_no_result",
    "notes",
    "approved_by",
    "corpus",
)
DISCLAIMER = (
    "HƯ CẤU: bộ case hiện tại dùng số hiệu/định danh văn bản hư cấu và "
    "approved_by = null; số liệu chỉ kiểm tra công thức và đường gọi API, "
    "KHÔNG phải chất lượng tìm kiếm trên văn bản pháp luật thật."
)


class SearchRequestError(Exception):
    """Lỗi một lượt gọi API search, đủ thông tin để ghi report."""

    def __init__(self, kind: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def percentile(values: list[float], fraction: float) -> float | None:
    """Percentile theo nearest-rank (dùng cho p95)."""

    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = math.ceil(fraction * len(ordered))
    return ordered[min(max(rank, 1), len(ordered)) - 1]


def latency_stats(values: list[float]) -> dict[str, float | int | None]:
    """p50 = trung vị; p95 = nearest-rank. Đơn vị mili-giây."""

    if not values:
        return {"count": 0, "p50": None, "p95": None, "min": None, "max": None}
    return {
        "count": len(values),
        "p50": float(statistics.median(values)),
        "p95": percentile(values, 0.95),
        "min": float(min(values)),
        "max": float(max(values)),
    }


def _document_number(document: dict) -> str | None:
    number = document.get("document_number")
    return None if number is None else str(number)


def _is_expected_document(document: dict, expected_documents: set[str]) -> bool:
    number = _document_number(document)
    return number is not None and number in expected_documents


def _is_expected_clause(
    document: dict, clause: dict, expected_documents: set[str], expected_nodes: set[str]
) -> bool:
    """Clause thuộc kỳ vọng nếu khớp node_id/nhãn node, hoặc thuộc văn bản kỳ vọng.

    `expected_nodes` chấp nhận cả `node_id` lẫn cách ghi nhãn (label) vì Gold
    thật có thể chưa có UUID; điều này được ghi rõ trong README.
    """

    if _is_expected_document(document, expected_documents):
        return True
    node_id = clause.get("node_id")
    label = clause.get("label")
    return (node_id is not None and str(node_id) in expected_nodes) or (
        label is not None and str(label) in expected_nodes
    )


def normalize_phrase_tokens(text: str) -> list[str]:
    """Chuẩn hóa để so cụm từ: NFC + lowercase, mọi ký tự không phải chữ/số là phân tách."""

    normalized = unicodedata.normalize("NFC", text or "").lower()
    tokens: list[str] = []
    current: list[str] = []
    for char in normalized:
        if char.isalnum():
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def quote_contains_phrase(quote: str, phrase: str) -> bool:
    """Tự xác minh `quote` có chứa `phrase` dưới dạng các từ liền nhau hay không.

    Không tin nhãn `match_type` của backend: so khớp trên token đã chuẩn hóa
    (NFC + lowercase + gom khoảng trắng + dấu câu là phân tách).
    """

    phrase_tokens = normalize_phrase_tokens(phrase)
    if not phrase_tokens:
        return False
    quote_tokens = normalize_phrase_tokens(quote)
    window = len(phrase_tokens)
    for start in range(0, len(quote_tokens) - window + 1):
        if quote_tokens[start : start + window] == phrase_tokens:
            return True
    return False


def _expected_phrase(case: dict, response: dict) -> str:
    """Cụm từ kỳ vọng: ưu tiên `query.phrase` của API, không có thì dùng query của case."""

    query = response.get("query")
    if isinstance(query, dict):
        phrase = query.get("phrase")
        if isinstance(phrase, str) and phrase.strip():
            return phrase
    return str(case.get("query") or "")


def case_metrics(case: dict, response: dict, k: int) -> dict:
    """Tính chỉ số của một case trên một response search.

    - recall@k (document): |expected_documents ∩ documents[:k]| / |expected_documents|.
    - precision@k (clause): clause thuộc expected_documents hoặc expected_nodes / tổng clause trả về.
    - exact_phrase_precision (owner chốt): số clause được gắn `match_type = exact_phrase`
      mà `quote_exact` **tự xác minh** thực sự chứa cụm từ / tổng số clause được gắn
      `exact_phrase`. Ca âm (`expected_no_result`) luôn = 0.0; case dương không có clause
      exact_phrase nào = null (không coi là 1.0).
    - wrong_doc_rate: văn bản trả về không nằm trong expected_documents / tổng văn bản trả về.
    - wrong_node_rate: 1 - precision@k (clause không khớp cả văn bản lẫn node kỳ vọng).
    - no_result_correct: chỉ cho case expected_no_result.
    """

    results = response.get("results") or []
    if not isinstance(results, list):
        results = []
    top_documents = [document for document in results[:k] if isinstance(document, dict)]
    expected_documents = [str(item) for item in case.get("expected_documents") or []]
    expected_document_set = set(expected_documents)
    expected_nodes = {str(item) for item in case.get("expected_nodes") or []}

    returned_document_numbers = [
        number
        for number in (_document_number(document) for document in top_documents)
        if number is not None
    ]
    recall_at_k: float | None = None
    if expected_documents:
        hits = len(expected_document_set.intersection(returned_document_numbers))
        recall_at_k = round(hits / len(expected_documents), 6)
    wrong_doc_rate = 0.0
    if returned_document_numbers:
        wrong_doc_rate = round(
            sum(number not in expected_document_set for number in returned_document_numbers)
            / len(returned_document_numbers),
            6,
        )

    returned_clauses: list[tuple[dict, dict]] = []
    for document in top_documents:
        for clause in document.get("clauses") or []:
            if isinstance(clause, dict):
                returned_clauses.append((document, clause))
    matched_clauses = sum(
        _is_expected_clause(document, clause, expected_document_set, expected_nodes)
        for document, clause in returned_clauses
    )
    precision_at_k: float | None = None
    if returned_clauses:
        precision_at_k = round(matched_clauses / len(returned_clauses), 6)
    wrong_node_rate = 0.0
    if returned_clauses:
        wrong_node_rate = round((len(returned_clauses) - matched_clauses) / len(returned_clauses), 6)

    expected_phrase = _expected_phrase(case, response)
    exact_clauses = [
        (document, clause)
        for document, clause in returned_clauses
        if clause.get("match_type") == "exact_phrase"
    ]
    exact_labeled = len(exact_clauses)
    exact_verified = sum(
        1
        for _, clause in exact_clauses
        if quote_contains_phrase(clause.get("quote_exact") or "", expected_phrase)
    )
    exact_phrase_precision: float | None
    if case.get("expected_no_result"):
        exact_phrase_precision = 0.0
    elif exact_labeled == 0:
        exact_phrase_precision = None
    else:
        exact_phrase_precision = round(exact_verified / exact_labeled, 6)

    no_result_correct: bool | None = None
    if case.get("expected_no_result"):
        no_result_correct = (not results) and response.get("empty_reason") in VALID_EMPTY_REASONS

    notes: list[str] = []
    if case.get("expected_no_result"):
        notes.append("Ca âm (expected_no_result) → exact_phrase_precision = 0.0 (không coi là 1.0).")
    elif exact_labeled == 0:
        notes.append(
            "Không có clause exact_phrase trong response → exact_phrase_precision = null "
            "(case dương, mẫu số 0; không tính vào trung bình)."
        )
    elif exact_verified < exact_labeled:
        notes.append(
            f"{exact_labeled - exact_verified}/{exact_labeled} clause gắn exact_phrase nhưng "
            "quote_exact không chứa cụm từ kỳ vọng sau khi tự xác minh → tử số không tăng."
        )
    if case.get("expected_no_result") and results:
        notes.append("Case kỳ vọng 0 kết quả nhưng API trả về kết quả.")
    if case.get("expected_no_result") and not results and not no_result_correct:
        notes.append("Không có kết quả nhưng empty_reason không thuộc tập hợp lệ.")

    return {
        "recall_at_k": recall_at_k,
        "precision_at_k": precision_at_k,
        "exact_phrase_precision": exact_phrase_precision,
        "exact_phrase_returned": exact_labeled,
        "exact_phrase_verified": exact_verified,
        "exact_phrase_phrase": expected_phrase,
        "exact_phrase_negative_case": bool(case.get("expected_no_result")),
        "returned_document_count": len(returned_document_numbers),
        "returned_clause_count": len(returned_clauses),
        "wrong_doc_rate": wrong_doc_rate,
        "wrong_node_rate": wrong_node_rate,
        "no_result_correct": no_result_correct,
        "notes": notes,
    }


def aggregate(rows: list[dict]) -> dict:
    """Tổng hợp chỉ số (trung bình theo case, trừ p50/p95 theo request thành công)."""

    measured = [row["metrics"] for row in rows if row.get("metrics")]
    latencies = [
        float(row["latency_ms"])
        for row in rows
        if row.get("latency_ms") is not None and row.get("status") == "ok"
    ]
    no_result_values = [
        (1.0 if metrics["no_result_correct"] else 0.0)
        for metrics in measured
        if metrics["no_result_correct"] is not None
    ]
    exact_values = [
        metrics["exact_phrase_precision"]
        for metrics in measured
        if metrics["exact_phrase_precision"] is not None
    ]
    return {
        "cases": len(rows),
        "cases_ok": len(measured),
        "cases_error": sum(1 for row in rows if row.get("status") != "ok"),
        "recall_at_k": _mean(
            [metrics["recall_at_k"] for metrics in measured if metrics["recall_at_k"] is not None]
        ),
        "precision_at_k": _mean(
            [
                metrics["precision_at_k"]
                for metrics in measured
                if metrics["precision_at_k"] is not None
            ]
        ),
        "exact_phrase_precision": _mean(exact_values),
        "exact_phrase_cases_scored": len(exact_values),
        "exact_phrase_cases_null": len(measured) - len(exact_values),
        "exact_phrase_negative_cases": sum(
            1 for metrics in measured if metrics["exact_phrase_negative_case"]
        ),
        "exact_phrase_total_labeled": sum(
            metrics["exact_phrase_returned"] for metrics in measured
        ),
        "exact_phrase_total_verified": sum(
            metrics["exact_phrase_verified"] for metrics in measured
        ),
        "wrong_doc_rate": _mean([metrics["wrong_doc_rate"] for metrics in measured]),
        "wrong_node_rate": _mean([metrics["wrong_node_rate"] for metrics in measured]),
        "no_result_accuracy": _mean(no_result_values),
        "no_result_cases": len(no_result_values),
        "latency_ms": latency_stats(latencies),
        "metric_notes": [
            "recall_at_k/precision_at_k/nhóm wrong rate/no_result_accuracy là trung bình theo từng case.",
            "exact_phrase_precision (owner chốt): tử số = clause gắn exact_phrase mà quote_exact tự xác minh chứa cụm từ; mẫu số = tổng clause gắn exact_phrase.",
            "Ca âm (expected_no_result) luôn = 0.0; case dương không có clause exact_phrase nào = null và bị loại khỏi trung bình (không coi là 1.0).",
            "Tự xác minh quote: NFC + lowercase + mọi ký tự không phải chữ/số là phân tách; so khớp các từ liền nhau.",
            "p50/p95 chỉ tính trên request thành công (HTTP 200, JSON hợp lệ); p50 = trung vị, p95 = nearest-rank.",
        ],
    }


def build_search_url(base_url: str, case: dict, page_size: int) -> str:
    params: list[tuple[str, str]] = [
        ("q", str(case["query"])),
        ("mode", str(case.get("mode") or "auto")),
        ("page", "1"),
        ("page_size", str(page_size)),
    ]
    filters = case.get("filters") or {}
    for key in ("doc_type", "issuing_body", "as_of_date", "group_by"):
        value = filters.get(key)
        if value not in (None, ""):
            params.append((key, str(value)))
    if filters.get("only_active") is not None:
        params.append(("only_active", "true" if filters["only_active"] else "false"))
    for category_id in filters.get("category_id") or []:
        params.append(("category_id", str(category_id)))
    return base_url.rstrip("/") + SEARCH_PATH + "?" + urllib.parse.urlencode(params)


def fetch_search(
    base_url: str, case: dict, page_size: int, token: str, timeout: float
) -> tuple[dict, float]:
    """Gọi API và trả (payload, latency_ms). Ném SearchRequestError khi lỗi."""

    url = build_search_url(base_url, case, page_size)
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300].strip()
        raise SearchRequestError("http", f"HTTP {exc.code}: {detail}", status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise SearchRequestError("unreachable", f"Không kết nối được API: {exc.reason}") from exc
    except TimeoutError as exc:
        raise SearchRequestError("timeout", f"Timeout sau {timeout} giây") from exc
    latency_ms = (time.perf_counter() - started) * 1000.0
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SearchRequestError("invalid_json", f"Response không phải JSON hợp lệ: {exc}") from exc
    if not isinstance(payload, dict):
        raise SearchRequestError("invalid_json", "Response JSON không phải object.")
    return payload, latency_ms


def validate_queries(payload: dict) -> list[dict]:
    """Kiểm tra tối thiểu theo schema; ném ValueError nếu không hợp lệ."""

    errors: list[str] = []
    if not isinstance(payload, dict):
        raise ValueError("File queries phải là JSON object.")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version phải bằng {SCHEMA_VERSION}.")
    if payload.get("label") != CORPUS_LABEL:
        errors.append(f"label phải bằng {CORPUS_LABEL!r} (bộ case hư cấu).")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("File queries phải có danh sách 'cases' không rỗng.")

    seen_ids: set[str] = set()
    for index, case in enumerate(cases):
        where = f"cases[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{where} không phải object.")
            continue
        missing = [field for field in REQUIRED_CASE_FIELDS if field not in case]
        if missing:
            errors.append(f"{where} thiếu trường {missing}.")
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            errors.append(f"{where}.id không hợp lệ.")
        elif case_id in seen_ids:
            errors.append(f"id trùng: {case_id}.")
        else:
            seen_ids.add(case_id)
        if not isinstance(case.get("query"), str) or not case["query"].strip():
            errors.append(f"{where}.query không hợp lệ.")
        if case.get("mode") not in VALID_MODES:
            errors.append(f"{where}.mode phải thuộc {list(VALID_MODES)}.")
        filters = case.get("filters")
        if not isinstance(filters, dict):
            errors.append(f"{where}.filters phải là object.")
        else:
            unknown = sorted(set(filters) - set(FILTER_KEYS))
            if unknown:
                errors.append(f"{where}.filters có khóa lạ {unknown}.")
            category_ids = filters.get("category_id")
            if category_ids is not None and (
                not isinstance(category_ids, list)
                or any(not isinstance(item, str) or not item.strip() for item in category_ids)
            ):
                errors.append(f"{where}.filters.category_id phải là mảng chuỗi.")
            for key in ("doc_type", "issuing_body"):
                value = filters.get(key)
                if value is not None and (not isinstance(value, str) or not value.strip()):
                    errors.append(f"{where}.filters.{key} phải là chuỗi không rỗng.")
            as_of_date = filters.get("as_of_date")
            if as_of_date is not None:
                try:
                    datetime.strptime(str(as_of_date), "%Y-%m-%d")
                except ValueError:
                    errors.append(f"{where}.filters.as_of_date phải có dạng YYYY-MM-DD.")
            only_active = filters.get("only_active")
            if only_active is not None and not isinstance(only_active, bool):
                errors.append(f"{where}.filters.only_active phải là boolean.")
            group_by = filters.get("group_by")
            if group_by is not None and group_by not in VALID_GROUP_BY:
                errors.append(f"{where}.filters.group_by phải thuộc {list(VALID_GROUP_BY)}.")

        expected_documents = case.get("expected_documents")
        if not isinstance(expected_documents, list) or any(
            not isinstance(item, str) or not item.strip() for item in expected_documents
        ):
            errors.append(f"{where}.expected_documents phải là mảng chuỗi.")
            expected_documents = []
        expected_nodes = case.get("expected_nodes")
        if not isinstance(expected_nodes, list) or any(
            not isinstance(item, str) or not item.strip() for item in expected_nodes
        ):
            errors.append(f"{where}.expected_nodes phải là mảng chuỗi.")
        expected_no_result = case.get("expected_no_result")
        if not isinstance(expected_no_result, bool):
            errors.append(f"{where}.expected_no_result phải là boolean.")
        elif expected_no_result != (not expected_documents):
            errors.append(
                f"{where}: expected_no_result phải bằng (expected_documents rỗng)."
            )
        if not isinstance(case.get("notes"), str) or not case["notes"].strip():
            errors.append(f"{where}.notes phải là chuỗi không rỗng.")
        approved_by = case.get("approved_by")
        if approved_by is not None and (
            not isinstance(approved_by, str) or not approved_by.strip()
        ):
            errors.append(f"{where}.approved_by phải là null hoặc chuỗi không rỗng.")
        if case.get("corpus") != CORPUS_LABEL:
            errors.append(f"{where}.corpus phải bằng {CORPUS_LABEL!r}.")
    if errors:
        raise ValueError("Queries không hợp lệ: " + " | ".join(errors[:20]))
    return cases


def load_queries(path: Path) -> list[dict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return validate_queries(payload)


def run_self_test(fixtures_path: Path = DEFAULT_FIXTURES_PATH) -> int:
    """Kiểm tra công thức trên response giả lập; không cần API/token."""

    _configure_stdout()
    failures: list[dict] = []
    checked = 0
    try:
        data = json.loads(Path(fixtures_path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"self_test": "fail", "error": f"Không đọc được fixtures: {exc}"}, ensure_ascii=False))
        return 1
    if data.get("label") != CORPUS_LABEL:
        failures.append({"check": "fixture_label", "expected": CORPUS_LABEL, "actual": data.get("label")})
    fixture_cases = data.get("cases") or []
    for index, item in enumerate(fixture_cases):
        case = item.get("case") or {}
        response = item.get("response") or {}
        metrics = case_metrics(case, response, int(item.get("k", data.get("k", 10))))
        for key, expected in (item.get("expected") or {}).items():
            checked += 1
            actual = metrics.get(key)
            if isinstance(expected, (int, float)) and not isinstance(expected, bool):
                passed = (
                    isinstance(actual, (int, float))
                    and not isinstance(actual, bool)
                    and abs(float(actual) - float(expected)) <= 1e-9
                )
            else:
                passed = actual == expected
            if not passed:
                failures.append(
                    {
                        "check": f"cases[{index}].{key}",
                        "expected": expected,
                        "actual": actual,
                    }
                )
    latency_checks = data.get("latency_checks") or []
    for index, check in enumerate(latency_checks):
        values = [float(value) for value in check.get("values") or []]
        stats = latency_stats(values)
        for key in ("p50", "p95"):
            if key not in check:
                continue
            checked += 1
            expected = float(check[key])
            actual = stats[key]
            if actual is None or abs(float(actual) - expected) > 1e-9:
                failures.append(
                    {"check": f"latency_checks[{index}].{key}", "expected": expected, "actual": actual}
                )
    result = {
        "self_test": "pass" if not failures else "fail",
        "label": data.get("label"),
        "cases_checked": len(fixture_cases),
        "value_checks": checked,
        "latency_checks": len(latency_checks),
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


def _format_metric(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "đúng" if value else "sai"
    if isinstance(value, (int, float)):
        return f"{float(value):.3f}"
    return str(value)


def _format_exact(value: object) -> str:
    """Riêng exact_phrase_precision: null phải hiện rõ là null, không gộp với N/A."""

    if value is None:
        return "null"
    return _format_metric(value)


def _exact_detail(metrics: dict) -> str:
    """Chuỗi truy vết tử số/mẫu số của exact_phrase_precision."""

    return f"{metrics.get('exact_phrase_verified', 0)}/{metrics.get('exact_phrase_returned', 0)}"


def render_markdown(report: dict) -> str:
    hucau = report["hucau_metrics"]
    official = report["official_metrics"]
    lines = [
        "# Báo cáo đánh giá Search v1 — HƯ CẤU",
        "",
        f"> ⚠️ **CẢNH BÁO** — {report['disclaimer']}",
        "",
        "## Môi trường",
        "",
        "| Trường | Giá trị |",
        "|---|---|",
        f"| Thời điểm (UTC) | {report['generated_at_utc']} |",
        f"| Hệ điều hành | {report['environment']['os']} |",
        f"| Python | {report['environment']['python_version']} ({report['environment']['python_implementation']}) |",
        f"| base_url | {report['run']['base_url']} |",
        f"| k / page_size | {report['run']['k']} / {report['run']['page_size']} |",
        f"| Bộ case | {report['run']['queries_file']} |",
        f"| Số case / đã duyệt | {report['run']['case_count']} / {report['run']['approved_case_count']} |",
        "",
        "## Trạng thái chất lượng",
        "",
        f"`quality_status = {report['quality_status']}`",
        "",
        report["quality_status_reason"],
        "",
        "## Chỉ số trên bộ HƯ CẤU (`hucau_metrics`)",
        "",
        "| Chỉ số | Giá trị |",
        "|---|---:|",
        f"| Case chạy được / lỗi | {hucau['cases_ok']} / {hucau['cases_error']} |",
        f"| recall@k (document) | {_format_metric(hucau['recall_at_k'])} |",
        f"| precision@k (clause) | {_format_metric(hucau['precision_at_k'])} |",
        f"| exact_phrase_precision | {_format_exact(hucau['exact_phrase_precision'])} |",
        f"| exact_phrase verified/labeled | {hucau['exact_phrase_total_verified']}/{hucau['exact_phrase_total_labeled']} |",
        f"| exact_phrase case null / ca âm | {hucau['exact_phrase_cases_null']} / {hucau['exact_phrase_negative_cases']} |",
        f"| wrong_doc_rate | {_format_metric(hucau['wrong_doc_rate'])} |",
        f"| wrong_node_rate | {_format_metric(hucau['wrong_node_rate'])} |",
        f"| no-result accuracy | {_format_metric(hucau['no_result_accuracy'])} ({hucau['no_result_cases']} case) |",
        f"| latency p50 / p95 (ms) | {_format_metric(hucau['latency_ms']['p50'])} / {_format_metric(hucau['latency_ms']['p95'])} |",
        f"| latency min / max (ms) | {_format_metric(hucau['latency_ms']['min'])} / {_format_metric(hucau['latency_ms']['max'])} |",
        "",
        "## Chỉ số chính thức (`official_metrics`)",
        "",
    ]
    if official is None:
        lines.append(
            "Không có case nào có `approved_by != null` → **chưa đánh giá chất lượng trên Gold thật**."
        )
    else:
        lines.extend(
            [
                "| Chỉ số | Giá trị |",
                "|---|---:|",
                f"| Case chạy được / lỗi | {official['cases_ok']} / {official['cases_error']} |",
                f"| recall@k (document) | {_format_metric(official['recall_at_k'])} |",
                f"| precision@k (clause) | {_format_metric(official['precision_at_k'])} |",
                f"| exact_phrase_precision | {_format_exact(official['exact_phrase_precision'])} |",
                f"| exact_phrase verified/labeled | {official['exact_phrase_total_verified']}/{official['exact_phrase_total_labeled']} |",
                f"| exact_phrase case null / ca âm | {official['exact_phrase_cases_null']} / {official['exact_phrase_negative_cases']} |",
                f"| wrong_doc_rate | {_format_metric(official['wrong_doc_rate'])} |",
                f"| wrong_node_rate | {_format_metric(official['wrong_node_rate'])} |",
                f"| no-result accuracy | {_format_metric(official['no_result_accuracy'])} ({official['no_result_cases']} case) |",
                f"| latency p50 / p95 (ms) | {_format_metric(official['latency_ms']['p50'])} / {_format_metric(official['latency_ms']['p95'])} |",
            ]
        )
    lines.extend(
        [
            "",
            "## Chi tiết từng case",
            "",
            "| id | query | mode | trạng thái | recall | precision | exact_phrase (verified/labeled) | wrong_doc | wrong_node | no-result | latency (ms) |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---|---:|",
        ]
    )
    for row in report["cases"]:
        metrics = row.get("metrics") or {}
        lines.append(
            "| {case_id} | {query} | {mode} | {status} | {recall} | {precision} | {exact} | "
            "{wrong_doc} | {wrong_node} | {no_result} | {latency} |".format(
                case_id=row["case_id"],
                query=row["query"].replace("|", "\\|"),
                mode=row.get("mode") or "—",
                status=row.get("status"),
                recall=_format_metric(metrics.get("recall_at_k")),
                precision=_format_metric(metrics.get("precision_at_k")),
                exact=(
                    f"{_format_exact(metrics.get('exact_phrase_precision'))} "
                    f"({_exact_detail(metrics)})"
                    if metrics
                    else "—"
                ),
                wrong_doc=_format_metric(metrics.get("wrong_doc_rate")),
                wrong_node=_format_metric(metrics.get("wrong_node_rate")),
                no_result=_format_metric(metrics.get("no_result_correct")),
                latency=_format_metric(row.get("latency_ms")),
            )
        )
    lines.extend(["", "## Ghi chú", ""])
    lines.extend(f"- {note}" for note in report["notes"])
    lines.append("")
    return "\n".join(lines)


def build_report(
    rows: list[dict],
    cases: list[dict],
    args: argparse.Namespace,
    queries_path: Path,
    queries_sha256: str,
) -> dict:
    approved_rows = [row for row in rows if row.get("approved_by") not in (None, "")]
    hucau_rows = [row for row in rows if row.get("approved_by") in (None, "")]
    approved_case_count = len([case for case in cases if case.get("approved_by") not in (None, "")])
    quality_status = "not_evaluated" if approved_case_count == 0 else "measured_on_approved_cases"
    if approved_case_count == 0:
        quality_status_reason = (
            "Không có case nào có approved_by != null. Chỉ báo hucau_metrics; "
            "KHÔNG dùng số liệu này để kết luận chất lượng tìm kiếm."
        )
    else:
        quality_status_reason = (
            f"Có {approved_case_count} case được duyệt; official_metrics chỉ tính trên các case đó."
        )
    notes = [
        DISCLAIMER,
        "Case hư cấu không phải văn bản pháp luật; không dùng làm Gold hay bằng chứng nội dung.",
        "Quy ước exact_phrase_precision (owner chốt): tử số = clause gắn exact_phrase mà quote_exact tự xác minh chứa cụm từ (NFC + lowercase + dấu câu là phân tách, các từ liền nhau); mẫu số = tổng clause gắn exact_phrase.",
        "Ca âm (expected_no_result) luôn cho exact_phrase_precision = 0.0; case dương không có clause exact_phrase nào cho null và bị loại khỏi trung bình (không coi là 1.0).",
        "p50 = trung vị; p95 = nearest-rank trên các request thành công.",
        "Report do evaluate_search.py tạo; không sửa tay số liệu.",
    ]
    if args.base_url.rstrip("/") != DEFAULT_BASE_URL:
        notes.append(f"base_url khác mặc định: {args.base_url.rstrip('/')}.")
    return {
        "schema_version": SCHEMA_VERSION,
        "label": CORPUS_LABEL,
        "disclaimer": DISCLAIMER,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "os": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
        },
        "run": {
            "base_url": args.base_url.rstrip("/"),
            "search_path": SEARCH_PATH,
            "k": args.k,
            "page_size": args.page_size,
            "timeout_s": args.timeout,
            "queries_file": str(queries_path),
            "queries_sha256": queries_sha256,
            "case_count": len(cases),
            "approved_case_count": approved_case_count,
            "hucau_case_count": len(hucau_rows),
        },
        "quality_status": quality_status,
        "quality_status_reason": quality_status_reason,
        "official_metrics": aggregate(approved_rows) if approved_rows else None,
        "hucau_metrics": aggregate(hucau_rows),
        "cases": rows,
        "notes": notes,
    }


def _write_report(report: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token", default=None, help="Access token (không khuyến nghị trên CLI).")
    parser.add_argument(
        "--token-env",
        default=DEFAULT_TOKEN_ENV,
        help=f"Tên biến môi trường chứa token; mặc định {DEFAULT_TOKEN_ENV}.",
    )
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES_PATH)
    parser.add_argument("--k", type=int, default=10, help="Số văn bản đầu dùng cho recall/precision.")
    parser.add_argument("--page-size", type=int, default=50, help="page_size gửi API (tối đa 50).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Chạy công thức trên fixtures giả lập, không cần API/token.",
    )
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES_PATH)
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test(args.fixtures)

    if args.k < 1:
        print("--k phải >= 1.", file=sys.stderr)
        return 2
    if not 1 <= args.page_size <= 50:
        print("--page-size phải trong khoảng 1..50.", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("--timeout phải > 0.", file=sys.stderr)
        return 2

    token = args.token or os.environ.get(args.token_env, "")
    if not token:
        print(
            f"Thiếu access token: truyền --token hoặc đặt biến môi trường {args.token_env}.",
            file=sys.stderr,
        )
        return 2

    try:
        queries_bytes = args.queries.read_bytes()
        cases = load_queries(args.queries)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Không đọc/không hợp lệ file queries {args.queries}: {exc}", file=sys.stderr)
        return 2
    queries_sha256 = hashlib.sha256(queries_bytes).hexdigest()

    rows: list[dict] = []
    success_count = 0
    auth_failed = False
    for case in cases:
        row: dict = {
            "case_id": case["id"],
            "query": case["query"],
            "mode": case.get("mode"),
            "corpus": case.get("corpus"),
            "approved_by": case.get("approved_by"),
            "expected_documents": list(case.get("expected_documents") or []),
            "expected_nodes": list(case.get("expected_nodes") or []),
            "expected_no_result": bool(case.get("expected_no_result")),
            "notes": case.get("notes"),
        }
        try:
            payload, latency_ms = fetch_search(
                args.base_url, case, args.page_size, token, args.timeout
            )
        except SearchRequestError as exc:
            row["status"] = "error"
            row["error_type"] = exc.kind
            row["error"] = str(exc)
            row["http_status"] = exc.status
            if exc.status in (401, 403):
                auth_failed = True
            rows.append(row)
            continue
        row["status"] = "ok"
        row["latency_ms"] = round(latency_ms, 3)
        results = payload.get("results") or []
        row["response_summary"] = {
            "phrase_found": payload.get("phrase_found"),
            "totals": payload.get("totals"),
            "page": payload.get("page"),
            "page_size": payload.get("page_size"),
            "has_more": payload.get("has_more"),
            "effectivity_snapshot_status": payload.get("effectivity_snapshot_status"),
            "empty_reason": payload.get("empty_reason"),
            "approximate": payload.get("approximate"),
            "results_count": len(results),
        }
        row["metrics"] = case_metrics(case, payload, args.k)
        rows.append(row)
        success_count += 1

    if auth_failed:
        print(
            "Access token bị API từ chối (HTTP 401/403). Kiểm tra lại token/quyền; "
            "báo cáo không được ghi.",
            file=sys.stderr,
        )
        return 2
    if success_count == 0:
        print(
            "API không chạy hoặc không trả về response hợp lệ nào. "
            "Kiểm tra --base-url, backend và access token; báo cáo không được ghi.",
            file=sys.stderr,
        )
        return 2

    report = build_report(rows, cases, args, args.queries, queries_sha256)
    json_path, markdown_path = _write_report(report, args.output)
    print(
        json.dumps(
            {
                "quality_status": report["quality_status"],
                "label": report["label"],
                "case_count": len(cases),
                "cases_ok": report["hucau_metrics"]["cases_ok"],
                "hucau_metrics": report["hucau_metrics"],
                "report_json": str(json_path),
                "report_markdown": str(markdown_path),
                "disclaimer": DISCLAIMER,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
