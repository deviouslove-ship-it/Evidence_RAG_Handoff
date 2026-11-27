"""HTTP smoke & evaluation script for Phase 1 Compare and Phase 2 Conflict Review APIs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str  # PASS | FAIL | SKIP
    detail: str
    elapsed_ms: float


class HttpApiClient:
    """Minimal stdlib HTTP JSON client for smoke evaluation."""

    def __init__(self, base_url: str, *, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token: str | None = None

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any] | list[Any] | None]:
        url = f"{self.base_url}{path}"
        if params:
            encoded = urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None}
            )
            if encoded:
                url = f"{url}?{encoded}"
        headers: dict[str, str] = {"Accept": "application/json"}
        data: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                body = json.loads(raw) if raw else None
                return int(resp.status), body
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                body = {"message": raw}
            return int(exc.code), body


def _record(
    results: list[CheckResult],
    name: str,
    status: str,
    detail: str,
    started_at: float,
) -> None:
    elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 1)
    results.append(CheckResult(name=name, status=status, detail=detail, elapsed_ms=elapsed_ms))


def run_smoke(args: argparse.Namespace) -> list[CheckResult]:
    results: list[CheckResult] = []
    client = HttpApiClient(args.base_url, timeout=args.request_timeout)

    # 1. Authentication
    t0 = time.perf_counter()
    status_code, login_body = client.request(
        "POST",
        "/api/v1/auth/login",
        payload={"username": args.username, "password": args.password, "client": "web"},
    )
    if status_code != 200 or not isinstance(login_body, dict) or not login_body.get("access_token"):
        detail = f"HTTP {status_code}: {login_body}"
        _record(results, "auth_login", "FAIL", detail, t0)
        return results

    client.token = str(login_body["access_token"])
    user_info = login_body.get("user") if isinstance(login_body.get("user"), dict) else {}
    roles = set(user_info.get("roles") or ())
    _record(
        results,
        "auth_login",
        "PASS",
        f"Authenticated as {args.username} (roles={sorted(roles)})",
        t0,
    )

    # 2. Categories
    t0 = time.perf_counter()
    cat_status, cat_body = client.request("GET", "/api/v1/categories")
    categories = cat_body if isinstance(cat_body, list) else []
    if cat_status == 200 and isinstance(cat_body, list):
        _record(results, "categories_list", "PASS", f"{len(categories)} authorized categories", t0)
    else:
        _record(results, "categories_list", "FAIL", f"HTTP {cat_status}: {cat_body}", t0)

    # 3. Discover documents if not passed via CLI
    doc_a = args.doc_a
    doc_b = args.doc_b
    discovered_docs: list[dict[str, Any]] = []
    if not doc_a or not doc_b:
        t0 = time.perf_counter()
        search_status, search_body = client.request(
            "POST",
            "/api/v1/search/comprehensive",
            payload={
                "q": "Điều",
                "mode": "keywords",
                "channels": ["exact"],
                "display": "all",
                "view": "documents",
                "page_size": 10,
                "clauses_per_document": 1,
            },
        )
        if search_status == 200 and isinstance(search_body, dict):
            discovered_docs = list(search_body.get("documents") or ())
            if not doc_a and len(discovered_docs) >= 1:
                doc_a = str(discovered_docs[0]["document_id"])
            if not doc_b and len(discovered_docs) >= 2:
                doc_b = str(discovered_docs[1]["document_id"])
            _record(
                results,
                "document_discovery",
                "PASS",
                f"Discovered {len(discovered_docs)} documents",
                t0,
            )
        else:
            _record(
                results,
                "document_discovery",
                "FAIL",
                f"HTTP {search_status}: {search_body}",
                t0,
            )

    # 4. Version listing + version comparison
    t0 = time.perf_counter()
    if not doc_a:
        _record(results, "compare_versions", "SKIP", "No authorized document available", t0)
    else:
        ver_status, ver_body = client.request("GET", f"/api/v1/documents/{doc_a}/versions")
        if ver_status != 200 or not isinstance(ver_body, dict):
            _record(results, "compare_versions", "FAIL", f"HTTP {ver_status}: {ver_body}", t0)
        else:
            versions = list(ver_body.get("versions") or ())
            if len(versions) >= 2:
                cmp_status, cmp_body = client.request(
                    "POST",
                    "/api/v1/compare/documents",
                    payload={
                        "mode": "versions",
                        "left_document_id": doc_a,
                        "right_document_id": doc_a,
                        "left_version_id": versions[1]["id"],
                        "right_version_id": versions[0]["id"],
                        "as_of_date": args.as_of_date,
                        "only_changes": False,
                    },
                )
                if (
                    cmp_status == 200
                    and isinstance(cmp_body, dict)
                    and "Gợi ý tự động" in str(cmp_body.get("disclaimer", ""))
                ):
                    total_items = (cmp_body.get("summary") or {}).get("total_items", 0)
                    _record(
                        results,
                        "compare_versions",
                        "PASS",
                        f"Compared v{versions[1]['version_number']} vs v{versions[0]['version_number']} ({total_items} items)",
                        t0,
                    )
                else:
                    _record(
                        results,
                        "compare_versions",
                        "FAIL",
                        f"HTTP {cmp_status}: {cmp_body}",
                        t0,
                    )
            else:
                _record(
                    results,
                    "compare_versions",
                    "PASS",
                    f"Versions endpoint OK ({len(versions)} approved version; >=2 needed for diff)",
                    t0,
                )

    # 5. Cross-document comparison
    t0 = time.perf_counter()
    if not doc_a or not doc_b or doc_a == doc_b:
        _record(
            results,
            "compare_cross_document",
            "SKIP",
            "Need 2 distinct authorized documents",
            t0,
        )
    else:
        cmp_status, cmp_body = client.request(
            "POST",
            "/api/v1/compare/documents",
            payload={
                "mode": "cross_document",
                "left_document_id": doc_a,
                "right_document_id": doc_b,
                "as_of_date": args.as_of_date,
                "only_changes": False,
            },
        )
        if (
            cmp_status == 200
            and isinstance(cmp_body, dict)
            and "Gợi ý tự động" in str(cmp_body.get("disclaimer", ""))
        ):
            summary = cmp_body.get("summary") or {}
            _record(
                results,
                "compare_cross_document",
                "PASS",
                f"total_items={summary.get('total_items', 0)}, high_impact={summary.get('high_impact_changes', 0)}",
                t0,
            )
        else:
            _record(
                results,
                "compare_cross_document",
                "FAIL",
                f"HTTP {cmp_status}: {cmp_body}",
                t0,
            )

    # 6. Conflict scan create & poll
    t0 = time.perf_counter()
    scan_payload: dict[str, Any] | None = None
    if doc_a and doc_b and doc_a != doc_b:
        scan_payload = {
            "request_id": f"smoke-{uuid4().hex[:16]}",
            "document_ids": [doc_a, doc_b],
            "as_of_date": args.as_of_date,
            "use_ai": False,
        }
    elif args.category_id or (categories and categories[0].get("id")):
        cat_id = args.category_id or str(categories[0]["id"])
        scan_payload = {
            "request_id": f"smoke-{uuid4().hex[:16]}",
            "category_id": cat_id,
            "as_of_date": args.as_of_date,
            "use_ai": False,
        }

    created_run_id: str | None = None
    if scan_payload is None:
        _record(
            results,
            "conflict_scan_lifecycle",
            "SKIP",
            "No document pair or category available for scan",
            t0,
        )
    else:
        create_status, create_body = client.request(
            "POST", "/api/v1/conflicts/scans", payload=scan_payload
        )
        if create_status != 202 or not isinstance(create_body, dict) or not create_body.get("run_id"):
            _record(
                results,
                "conflict_scan_lifecycle",
                "FAIL",
                f"Create failed HTTP {create_status}: {create_body}",
                t0,
            )
        else:
            created_run_id = str(create_body["run_id"])
            deadline = time.monotonic() + args.poll_timeout
            detail_status = 0
            detail_body: Any = None
            while time.monotonic() <= deadline:
                detail_status, detail_body = client.request(
                    "GET", f"/api/v1/conflicts/scans/{created_run_id}"
                )
                if detail_status == 200 and isinstance(detail_body, dict):
                    run_status = detail_body.get("status")
                    if run_status not in ("queued", "running"):
                        break
                time.sleep(args.poll_interval)

            if (
                detail_status == 200
                and isinstance(detail_body, dict)
                and detail_body.get("status") == "completed"
                and "Gợi ý tự động" in str(detail_body.get("disclaimer", ""))
            ):
                findings = list(detail_body.get("findings") or ())
                by_type: dict[str, int] = {}
                for f in findings:
                    ftype = str(f.get("finding_type", "unknown"))
                    by_type[ftype] = by_type.get(ftype, 0) + 1
                _record(
                    results,
                    "conflict_scan_lifecycle",
                    "PASS",
                    f"run={created_run_id}, total_findings={len(findings)}, by_type={by_type}, hidden_acl={detail_body.get('hidden_due_to_acl', 0)}",
                    t0,
                )
            elif detail_status == 200 and isinstance(detail_body, dict) and detail_body.get("status") in ("queued", "running"):
                _record(
                    results,
                    "conflict_scan_lifecycle",
                    "FAIL",
                    f"Scan {created_run_id} timed out in state {detail_body.get('status')} (is background worker running?)",
                    t0,
                )
            else:
                _record(
                    results,
                    "conflict_scan_lifecycle",
                    "FAIL",
                    f"HTTP {detail_status}: {detail_body}",
                    t0,
                )

    # 7. Conflict scans list
    t0 = time.perf_counter()
    list_status, list_body = client.request("GET", "/api/v1/conflicts/scans", params={"limit": 10})
    if list_status == 200 and isinstance(list_body, dict) and isinstance(list_body.get("items"), list):
        items = list_body["items"]
        has_created = created_run_id is None or any(item.get("run_id") == created_run_id for item in items)
        if has_created:
            _record(results, "conflict_scan_list", "PASS", f"Listed {len(items)} scans", t0)
        else:
            _record(
                results,
                "conflict_scan_list",
                "FAIL",
                f"Created run {created_run_id} missing from list",
                t0,
            )
    else:
        _record(results, "conflict_scan_list", "FAIL", f"HTTP {list_status}: {list_body}", t0)

    # 8. Conflict scan cancel
    t0 = time.perf_counter()
    if scan_payload is None:
        _record(results, "conflict_scan_cancel", "SKIP", "No scope available", t0)
    else:
        cancel_req = {**scan_payload, "request_id": f"smoke-cancel-{uuid4().hex[:12]}"}
        c_status, c_body = client.request("POST", "/api/v1/conflicts/scans", payload=cancel_req)
        if c_status != 202 or not isinstance(c_body, dict):
            _record(results, "conflict_scan_cancel", "FAIL", f"HTTP {c_status}: {c_body}", t0)
        else:
            cancel_run_id = str(c_body["run_id"])
            x_status, x_body = client.request(
                "POST", f"/api/v1/conflicts/scans/{cancel_run_id}/cancel"
            )
            if x_status == 200 and isinstance(x_body, dict) and x_body.get("status") == "cancelled":
                _record(results, "conflict_scan_cancel", "PASS", f"Cancelled run {cancel_run_id}", t0)
            elif (
                x_status == 409
                and isinstance(x_body, dict)
                and x_body.get("code") == "CONFLICT_SCAN_INVALID_STATE"
            ):
                _record(
                    results,
                    "conflict_scan_cancel",
                    "PASS",
                    f"Run {cancel_run_id} completed before cancel arrived (valid 409 state transition)",
                    t0,
                )
            else:
                _record(results, "conflict_scan_cancel", "FAIL", f"HTTP {x_status}: {x_body}", t0)

    # 9. Admin authority rules (SYS_ADMIN)
    t0 = time.perf_counter()
    if "SYS_ADMIN" not in roles:
        _record(results, "admin_authority_rules", "SKIP", "User lacks SYS_ADMIN role", t0)
    else:
        rules_status, rules_body = client.request(
            "GET", "/api/v1/admin/authority-rules", params={"include_inactive": "true"}
        )
        if (
            rules_status == 200
            and isinstance(rules_body, dict)
            and isinstance(rules_body.get("items"), list)
            and len(rules_body["items"]) >= 1
        ):
            _record(
                results,
                "admin_authority_rules",
                "PASS",
                f"Loaded {len(rules_body['items'])} authority rules",
                t0,
            )
        else:
            _record(
                results,
                "admin_authority_rules",
                "FAIL",
                f"HTTP {rules_status}: {rules_body}",
                t0,
            )

    # 10. Admin conflict triage queue (REVIEWER / CURATOR)
    t0 = time.perf_counter()
    if not ({"REVIEWER", "CURATOR"} & roles):
        _record(
            results,
            "admin_conflict_triage_queue",
            "SKIP",
            "User lacks REVIEWER/CURATOR role",
            t0,
        )
    else:
        q_status, q_body = client.request(
            "GET", "/api/v1/admin/conflicts/findings", params={"limit": 20}
        )
        if (
            q_status == 200
            and isinstance(q_body, dict)
            and isinstance(q_body.get("items"), list)
            and "Gợi ý tự động" in str(q_body.get("disclaimer", ""))
        ):
            _record(
                results,
                "admin_conflict_triage_queue",
                "PASS",
                f"Loaded {len(q_body['items'])} triage items (total={q_body.get('total', 0)})",
                t0,
            )
        else:
            _record(
                results,
                "admin_conflict_triage_queue",
                "FAIL",
                f"HTTP {q_status}: {q_body}",
                t0,
            )

    return results


def _print_report(results: list[CheckResult]) -> None:
    passed = sum(1 for item in results if item.status == "PASS")
    failed = sum(1 for item in results if item.status == "FAIL")
    skipped = sum(1 for item in results if item.status == "SKIP")
    print("Compare & Conflict Review HTTP Smoke Report")
    print("=" * 60)
    for item in results:
        print(f"[{item.status}] {item.name} ({item.elapsed_ms:.1f} ms) - {item.detail}")
    print("-" * 60)
    print(f"Summary: PASS={passed} FAIL={failed} SKIP={skipped} TOTAL={len(results)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run HTTP smoke checks for Document Compare & Conflict Review APIs."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("EVIDENCE_BASE_URL", "http://127.0.0.1:8000"),
        help="Backend API base URL (default: EVIDENCE_BASE_URL or http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("EVIDENCE_SMOKE_USER"),
        help="Username for login (or set EVIDENCE_SMOKE_USER)",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("EVIDENCE_SMOKE_PASSWORD"),
        help="Password for login (or set EVIDENCE_SMOKE_PASSWORD)",
    )
    parser.add_argument("--doc-a", default=None, help="Optional first document UUID")
    parser.add_argument("--doc-b", default=None, help="Optional second document UUID")
    parser.add_argument("--category-id", default=None, help="Optional category UUID")
    parser.add_argument("--as-of-date", default=None, help="Optional as-of date YYYY-MM-DD")
    parser.add_argument("--poll-timeout", type=float, default=30.0)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--request-timeout", type=float, default=30.0)
    parser.add_argument("--json-out", default=None, help="Optional path to write JSON report")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.username or not args.password:
        print(
            "Missing credentials: provide --username/--password or set "
            "EVIDENCE_SMOKE_USER and EVIDENCE_SMOKE_PASSWORD.",
            file=sys.stderr,
        )
        return 2

    results = run_smoke(args)
    _print_report(results)
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 1 if any(item.status == "FAIL" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
