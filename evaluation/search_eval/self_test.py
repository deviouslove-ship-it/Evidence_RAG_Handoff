"""Self-test công thức metric của evaluate_search.py — không cần API, không cần Gold.

Chạy: python evaluation/search_eval/self_test.py
Hoặc: python -m unittest evaluation/search_eval/self_test.py (từ repo root).
Toàn bộ dữ liệu dùng trong test là fixture HƯ CẤU.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import importlib.util
import io
import json
import os
import socket
import sys
import tempfile
import threading
import unicodedata
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SEARCH_EVAL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SEARCH_EVAL_DIR.parents[1]
SCRIPT_PATH = PROJECT_ROOT / "evaluation" / "scripts" / "evaluate_search.py"
QUERIES_PATH = SEARCH_EVAL_DIR / "queries_hucau.json"
SCHEMA_PATH = SEARCH_EVAL_DIR / "schema.json"
FIXTURES_PATH = SEARCH_EVAL_DIR / "fixtures" / "sample_responses.json"


def _load_evaluate_module():
    spec = importlib.util.spec_from_file_location("evaluate_search_under_test", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Không load được {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EVALUATE = _load_evaluate_module()


def make_case(**overrides):
    case = {
        "id": "hc-test",
        "query": "báo cáo định kỳ",
        "mode": "phrase",
        "filters": {},
        "expected_documents": ["HU-CAU/2026/ND-CP"],
        "expected_nodes": ["HC-ND-CP-N01"],
        "expected_no_result": False,
        "notes": "Fixture HƯ CẤU cho self-test.",
        "approved_by": None,
        "corpus": "HU_CAU",
    }
    case.update(overrides)
    return case


def make_response(*documents, phrase="báo cáo định kỳ"):
    """Response giả lập; mỗi clause là (node_id, match_type[, quote_exact])."""

    rendered_documents = []
    for document_number, clauses in documents:
        rendered_clauses = []
        for clause in clauses:
            node_id, match_type = clause[0], clause[1]
            quote = clause[2] if len(clause) > 2 else f"Trích dẫn hư cấu: {phrase}."
            rendered_clauses.append(
                {
                    "node_id": node_id,
                    "label": f"Nhãn {node_id}",
                    "match_type": match_type,
                    "quote_exact": quote,
                }
            )
        rendered_documents.append(
            {"document_number": document_number, "clauses": rendered_clauses}
        )
    return {
        "results": rendered_documents,
        "empty_reason": None,
        "query": {"phrase": phrase},
    }


class MetricFormulaTests(unittest.TestCase):
    def test_recall_precision_exact_phrase(self):
        case = make_case(
            expected_documents=["HU-CAU/2026/ND-CP", "HU-CAU/2026/TT-BTC"],
            expected_nodes=["HC-ND-CP-N01"],
        )
        response = make_response(
            (
                "HU-CAU/2026/ND-CP",
                [("HC-ND-CP-N01", "exact_phrase"), ("HC-ND-CP-N02", "exact_phrase")],
            ),
            ("HU-CAU/2026/TT-BTC", [("HC-TT-BTC-N01", "exact_phrase")]),
            (
                "HU-CAU/2026/QD-UBND",
                [("HC-QD-N01", "exact_phrase", "Báo cáo định kỳ và đột xuất hư cấu.")],
            ),
            phrase="báo cáo định kỳ và thường xuyên",
        )
        metrics = EVALUATE.case_metrics(case, response, k=10)
        self.assertAlmostEqual(metrics["recall_at_k"], 1.0)
        self.assertAlmostEqual(metrics["precision_at_k"], 3 / 4)
        self.assertAlmostEqual(metrics["exact_phrase_precision"], 3 / 4)
        self.assertEqual(metrics["exact_phrase_returned"], 4)
        self.assertEqual(metrics["exact_phrase_verified"], 3)
        self.assertAlmostEqual(metrics["wrong_doc_rate"], 1 / 3, places=6)
        self.assertAlmostEqual(metrics["wrong_node_rate"], 1 / 4)
        self.assertIsNone(metrics["no_result_correct"])

    def test_recall_at_k_truncates_documents(self):
        case = make_case(
            expected_documents=["HU-CAU/2026/ND-CP", "HU-CAU/2026/TT-BTC"],
            expected_nodes=[],
        )
        response = make_response(
            ("HU-CAU/2026/ND-CP", [("HC-ND-CP-N03", "exact_phrase")]),
            ("HU-CAU/2026/TT-BTC", [("HC-TT-BTC-N02", "exact_phrase")]),
        )
        metrics = EVALUATE.case_metrics(case, response, k=1)
        self.assertAlmostEqual(metrics["recall_at_k"], 0.5)
        self.assertAlmostEqual(metrics["precision_at_k"], 1.0)
        self.assertEqual(metrics["returned_document_count"], 1)
        self.assertEqual(metrics["returned_clause_count"], 1)

    def test_node_level_match_beats_wrong_document(self):
        case = make_case(
            expected_documents=["HU-CAU/2026/ND-CP"],
            expected_nodes=["HC-TT-BTC-N09"],
        )
        response = make_response(("HU-CAU/2026/TT-BTC", [("HC-TT-BTC-N09", "exact_phrase")]))
        metrics = EVALUATE.case_metrics(case, response, k=10)
        self.assertAlmostEqual(metrics["recall_at_k"], 0.0)
        self.assertAlmostEqual(metrics["precision_at_k"], 1.0)
        self.assertAlmostEqual(metrics["exact_phrase_precision"], 1.0)
        self.assertAlmostEqual(metrics["wrong_doc_rate"], 1.0)
        self.assertAlmostEqual(metrics["wrong_node_rate"], 0.0)

    def test_exact_phrase_precision_null_when_denominator_zero(self):
        case = make_case(expected_nodes=[])
        response = make_response(("HU-CAU/2026/ND-CP", [("HC-ND-CP-N01", "phrase_folded")]))
        metrics = EVALUATE.case_metrics(case, response, k=10)
        self.assertEqual(metrics["exact_phrase_returned"], 0)
        self.assertIsNone(metrics["exact_phrase_precision"])

    def test_exact_phrase_label_requires_quote_match(self):
        case = make_case(
            query="báo cáo định kỳ và thường xuyên",
            expected_documents=["HU-CAU/2026/ND-CP"],
            expected_nodes=[],
        )
        response = make_response(
            (
                "HU-CAU/2026/ND-CP",
                [
                    ("HC-1", "exact_phrase", "Báo cáo định kỳ và thường xuyên hư cấu."),
                    ("HC-2", "exact_phrase", "Báo cáo định kỳ và đột xuất hư cấu."),
                ],
            ),
            phrase="báo cáo định kỳ và thường xuyên",
        )
        metrics = EVALUATE.case_metrics(case, response, k=10)
        self.assertEqual(metrics["exact_phrase_returned"], 2)
        self.assertEqual(metrics["exact_phrase_verified"], 1)
        self.assertAlmostEqual(metrics["exact_phrase_precision"], 0.5)

    def test_negative_case_exact_phrase_forced_zero(self):
        case = make_case(
            query="thủ tục cấp phép vũ trụ",
            expected_documents=[],
            expected_nodes=[],
            expected_no_result=True,
        )
        response = make_response(
            (
                "HU-CAU/2026/QD-UBND",
                [
                    (
                        "HC-QD-N01",
                        "exact_phrase",
                        "Thủ tục cấp phép vũ trụ là nội dung hư cấu.",
                    )
                ],
            ),
            phrase="thủ tục cấp phép vũ trụ",
        )
        metrics = EVALUATE.case_metrics(case, response, k=10)
        self.assertEqual(metrics["exact_phrase_returned"], 1)
        self.assertEqual(metrics["exact_phrase_verified"], 1)
        self.assertAlmostEqual(metrics["exact_phrase_precision"], 0.0)

    def test_quote_contains_phrase_uses_normalization(self):
        phrase = "báo cáo định kỳ và thường xuyên"
        self.assertTrue(
            EVALUATE.quote_contains_phrase(
                "BÁO CÁO, định kỳ — và  thường xuyên được lập hằng quý!", phrase
            )
        )
        self.assertTrue(
            EVALUATE.quote_contains_phrase(unicodedata.normalize("NFD", phrase), phrase)
        )
        self.assertFalse(
            EVALUATE.quote_contains_phrase("báo cáo định kỳ, thường xuyên và", phrase)
        )
        self.assertFalse(EVALUATE.quote_contains_phrase("", phrase))
        self.assertFalse(EVALUATE.quote_contains_phrase("báo cáo định kỳ", ""))
        self.assertEqual(
            EVALUATE.normalize_phrase_tokens("  Báo-cáo_định  kỳ! "),
            ["báo", "cáo", "định", "kỳ"],
        )

    def test_no_result_correct_and_wrong(self):
        case = make_case(
            expected_documents=[],
            expected_nodes=[],
            expected_no_result=True,
        )
        correct = EVALUATE.case_metrics(
            case, {"results": [], "empty_reason": "NO_RESULTS"}, k=10
        )
        self.assertTrue(correct["no_result_correct"])
        self.assertAlmostEqual(correct["exact_phrase_precision"], 0.0)
        invalid_reason = EVALUATE.case_metrics(
            case, {"results": [], "empty_reason": None}, k=10
        )
        self.assertFalse(invalid_reason["no_result_correct"])
        wrong = EVALUATE.case_metrics(
            case,
            make_response(("HU-CAU/2026/QD-UBND", [("HC-QD-N01", "exact_phrase")])),
            k=10,
        )
        self.assertFalse(wrong["no_result_correct"])
        self.assertAlmostEqual(wrong["wrong_doc_rate"], 1.0)
        self.assertAlmostEqual(wrong["precision_at_k"], 0.0)
        self.assertEqual(wrong["exact_phrase_verified"], 1)
        self.assertAlmostEqual(wrong["exact_phrase_precision"], 0.0)

    def test_pass_through_reason_is_accepted(self):
        case = make_case(expected_documents=[], expected_nodes=[], expected_no_result=True)
        for reason in ("NO_AUTHORIZED_DOCUMENTS", "NO_RESULTS", "PHRASE_NOT_FOUND"):
            metrics = EVALUATE.case_metrics(
                case, {"results": [], "empty_reason": reason}, k=10
            )
            self.assertTrue(metrics["no_result_correct"], reason)

    def test_latency_percentiles(self):
        self.assertEqual(EVALUATE.percentile([10, 20, 30, 40, 50], 0.95), 50.0)
        self.assertEqual(EVALUATE.percentile([5, 15, 25, 35, 45, 55], 0.95), 55.0)
        self.assertEqual(EVALUATE.percentile([7], 0.95), 7.0)
        self.assertIsNone(EVALUATE.percentile([], 0.95))
        stats = EVALUATE.latency_stats([10, 20, 30])
        self.assertEqual(stats["p50"], 20.0)
        self.assertEqual(stats["p95"], 30.0)
        self.assertEqual(EVALUATE.latency_stats([])["count"], 0)

    def test_aggregate_means_and_latency(self):
        case_ok = make_case(expected_nodes=["HC-ND-CP-N01"])
        ok_metrics = EVALUATE.case_metrics(
            case_ok,
            make_response(("HU-CAU/2026/ND-CP", [("HC-ND-CP-N01", "exact_phrase")])),
            k=10,
        )
        case_negative = make_case(
            expected_documents=[], expected_nodes=[], expected_no_result=True
        )
        negative_metrics = EVALUATE.case_metrics(
            case_negative,
            make_response(("HU-CAU/2026/QD-UBND", [("HC-QD-N01", "exact_phrase")])),
            k=10,
        )
        rows = [
            {"status": "ok", "latency_ms": 10.0, "metrics": ok_metrics},
            {"status": "ok", "latency_ms": 30.0, "metrics": negative_metrics},
        ]
        aggregate = EVALUATE.aggregate(rows)
        # Ca âm không có recall (expected_documents rỗng) nên recall chỉ lấy ca dương.
        self.assertAlmostEqual(aggregate["recall_at_k"], 1.0)
        self.assertAlmostEqual(aggregate["precision_at_k"], (1.0 + 0.0) / 2)
        self.assertAlmostEqual(aggregate["exact_phrase_precision"], 0.5)
        self.assertEqual(aggregate["exact_phrase_cases_scored"], 2)
        self.assertEqual(aggregate["exact_phrase_cases_null"], 0)
        self.assertEqual(aggregate["exact_phrase_negative_cases"], 1)
        self.assertEqual(aggregate["exact_phrase_total_labeled"], 2)
        self.assertEqual(aggregate["exact_phrase_total_verified"], 2)
        self.assertAlmostEqual(aggregate["wrong_doc_rate"], 0.5)
        self.assertAlmostEqual(aggregate["wrong_node_rate"], 0.5)
        self.assertAlmostEqual(aggregate["no_result_accuracy"], 0.0)
        self.assertEqual(aggregate["no_result_cases"], 1)
        self.assertEqual(aggregate["latency_ms"]["count"], 2)
        self.assertEqual(aggregate["latency_ms"]["p50"], 20.0)
        self.assertEqual(aggregate["latency_ms"]["p95"], 30.0)
        self.assertEqual(aggregate["cases_error"], 0)

    def test_aggregate_excludes_null_exact_phrase_cases(self):
        case_ok = make_case(expected_nodes=["HC-ND-CP-N01"])
        ok_metrics = EVALUATE.case_metrics(
            case_ok,
            make_response(("HU-CAU/2026/ND-CP", [("HC-ND-CP-N01", "exact_phrase")])),
            k=10,
        )
        case_folded = make_case(expected_nodes=[], query="bao cao dinh ky")
        folded_metrics = EVALUATE.case_metrics(
            case_folded,
            make_response(
                ("HU-CAU/2026/ND-CP", [("HC-ND-CP-N02", "phrase_folded")]),
                phrase="bao cao dinh ky",
            ),
            k=10,
        )
        self.assertIsNone(folded_metrics["exact_phrase_precision"])
        aggregate = EVALUATE.aggregate(
            [
                {"status": "ok", "latency_ms": 10.0, "metrics": ok_metrics},
                {"status": "ok", "latency_ms": 20.0, "metrics": folded_metrics},
            ]
        )
        self.assertAlmostEqual(aggregate["exact_phrase_precision"], 1.0)
        self.assertEqual(aggregate["exact_phrase_cases_scored"], 1)
        self.assertEqual(aggregate["exact_phrase_cases_null"], 1)

    def test_aggregate_ignores_error_rows_for_latency(self):
        rows = [
            {"status": "ok", "latency_ms": 10.0, "metrics": None},
            {"status": "error", "latency_ms": None, "metrics": None},
        ]
        aggregate = EVALUATE.aggregate(rows)
        self.assertEqual(aggregate["cases_ok"], 0)
        self.assertEqual(aggregate["cases_error"], 1)
        self.assertEqual(aggregate["latency_ms"]["count"], 1)


class SelfTestFixtureTests(unittest.TestCase):
    def test_fixtures_are_labelled_hucau(self):
        data = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
        self.assertEqual(data["label"], "HU_CAU")

    def test_run_self_test_passes(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = EVALUATE.run_self_test(FIXTURES_PATH)
        result = json.loads(buffer.getvalue())
        self.assertEqual(code, 0, result)
        self.assertEqual(result["self_test"], "pass")
        self.assertGreater(result["value_checks"], 0)
        self.assertGreater(result["latency_checks"], 0)

    def test_run_self_test_detects_wrong_formula(self):
        data = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
        data["cases"][0]["expected"]["recall_at_k"] = 999
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "broken_fixtures.json"
            broken.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                code = EVALUATE.run_self_test(broken)
        self.assertEqual(code, 1)


class QuerySetTests(unittest.TestCase):
    def test_queries_file_valid(self):
        cases = EVALUATE.load_queries(QUERIES_PATH)
        self.assertGreaterEqual(len(cases), 10)
        self.assertLessEqual(len(cases), 14)
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        for case in cases:
            self.assertIsNone(case["approved_by"])
            self.assertEqual(case["corpus"], "HU_CAU")
            self.assertEqual(case["expected_no_result"], not case["expected_documents"])

    def test_schema_required_fields_match_code(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        required = schema["$defs"]["case"]["required"]
        self.assertEqual(set(required), set(EVALUATE.REQUIRED_CASE_FIELDS))
        EVALUATE.validate_queries(
            {
                "schema_version": 1,
                "label": "HU_CAU",
                "description": "test",
                "corpus": "HU_CAU",
                "cases": [make_case()],
            }
        )

    def test_invalid_queries_rejected(self):
        base = {
            "schema_version": 1,
            "label": "HU_CAU",
            "description": "test",
            "corpus": "HU_CAU",
            "cases": [make_case()],
        }
        mutations = [
            ("schema_version", 2),
            ("label", "REAL"),
        ]
        for key, value in mutations:
            payload = copy.deepcopy(base)
            payload[key] = value
            with self.assertRaises(ValueError):
                EVALUATE.validate_queries(payload)
        bad_cases = [
            make_case(expected_no_result=True),
            make_case(mode="fuzzy"),
            make_case(approved_by=""),
            make_case(filters={"unknown": "x"}),
            make_case(expected_documents=[]),
        ]
        for bad_case in bad_cases:
            payload = copy.deepcopy(base)
            payload["cases"] = [bad_case]
            with self.assertRaises(ValueError):
                EVALUATE.validate_queries(payload)


class ReportTests(unittest.TestCase):
    def test_approved_cases_split_into_official_metrics(self):
        approved_case = make_case(id="hc-approved", approved_by="reviewer-test")
        hucau_case = make_case(id="hc-null", approved_by=None)
        response = make_response(
            ("HU-CAU/2026/ND-CP", [("HC-ND-CP-N01", "exact_phrase")])
        )
        rows = []
        for case in (approved_case, hucau_case):
            rows.append(
                {
                    "case_id": case["id"],
                    "query": case["query"],
                    "mode": case["mode"],
                    "approved_by": case["approved_by"],
                    "status": "ok",
                    "latency_ms": 5.0,
                    "metrics": EVALUATE.case_metrics(case, response, k=10),
                }
            )
        args = argparse.Namespace(
            base_url="http://127.0.0.1:8000", k=10, page_size=50, timeout=10.0
        )
        report = EVALUATE.build_report(
            rows, [approved_case, hucau_case], args, Path("queries.json"), "0" * 64
        )
        self.assertEqual(report["quality_status"], "measured_on_approved_cases")
        self.assertEqual(report["run"]["approved_case_count"], 1)
        self.assertEqual(report["official_metrics"]["cases"], 1)
        self.assertEqual(report["hucau_metrics"]["cases"], 1)
        self.assertAlmostEqual(report["official_metrics"]["recall_at_k"], 1.0)

    def test_render_markdown_handles_error_row(self):
        case = make_case()
        rows = [
            {
                "case_id": case["id"],
                "query": case["query"],
                "mode": case["mode"],
                "approved_by": None,
                "status": "error",
                "error_type": "unreachable",
                "error": "Không kết nối được API: [Errno 10061]",
                "http_status": None,
            }
        ]
        args = argparse.Namespace(
            base_url="http://127.0.0.1:8000", k=10, page_size=50, timeout=10.0
        )
        report = EVALUATE.build_report(rows, [case], args, Path("queries.json"), "0" * 64)
        markdown = EVALUATE.render_markdown(report)
        self.assertIn("error", markdown)
        self.assertIn("—", markdown)
        self.assertIn("not_evaluated", markdown)


class UrlBuildingTests(unittest.TestCase):
    def test_url_encodes_all_parameters(self):
        case = make_case(
            query="báo cáo định kỳ",
            mode="auto",
            filters={
                "category_id": ["cat-1", "cat-2"],
                "doc_type": "decree",
                "issuing_body": "Bộ Tư pháp hư cấu",
                "as_of_date": "2026-10-31",
                "only_active": True,
                "group_by": "document",
            },
        )
        url = EVALUATE.build_search_url("http://127.0.0.1:8000/", case, 50)
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(parsed.path, "/api/v1/search")
        self.assertEqual(params["q"], ["báo cáo định kỳ"])
        self.assertEqual(params["mode"], ["auto"])
        self.assertEqual(params["page_size"], ["50"])
        self.assertEqual(params["category_id"], ["cat-1", "cat-2"])
        self.assertEqual(params["doc_type"], ["decree"])
        self.assertEqual(params["only_active"], ["true"])
        self.assertEqual(params["group_by"], ["document"])


class _SearchHandler(BaseHTTPRequestHandler):
    response_by_query: dict = {}

    def do_GET(self):  # noqa: N802 - tên do BaseHTTPRequestHandler quy định
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/v1/search":
            self._send(404, {"detail": "not found"})
            return
        if self.headers.get("Authorization") != "Bearer test-token":
            self._send(401, {"detail": "unauthorized"})
            return
        params = urllib.parse.parse_qs(parsed.query)
        query = (params.get("q") or [""])[0]
        payload = self.response_by_query.get(query)
        if payload is None:
            payload = {
                "results": [],
                "empty_reason": "NO_RESULTS",
                "phrase_found": False,
                "totals": {"documents": 0, "clauses": 0, "approximate_matches_hidden": 0},
                "page": 1,
                "page_size": 50,
                "has_more": False,
                "effectivity_snapshot_status": "ok",
            }
        self._send(200, payload)

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: D401 - giữ im lặng khi test
        pass


class ApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _SearchHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def _write_queries(self, directory: Path) -> Path:
        positive = make_case(
            id="hc-integration-positive",
            query="báo cáo định kỳ",
            expected_documents=["HU-CAU/2026/ND-CP"],
            expected_nodes=["HC-ND-CP-N01"],
        )
        negative = make_case(
            id="hc-integration-negative",
            query="không-có-kết-quả",
            expected_documents=[],
            expected_nodes=[],
            expected_no_result=True,
        )
        path = directory / "queries.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "label": "HU_CAU",
                    "description": "fixture cho integration test",
                    "corpus": "HU_CAU",
                    "cases": [positive, negative],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def test_end_to_end_writes_report(self):
        _SearchHandler.response_by_query = {
            "báo cáo định kỳ": {
                "query": {
                    "original": "báo cáo định kỳ",
                    "phrase": "báo cáo định kỳ",
                    "mode": "phrase",
                    "normalization_revision": "fixture",
                },
                "results": [
                    {
                        "document_number": "HU-CAU/2026/ND-CP",
                        "title": "Văn bản hư cấu",
                        "clauses": [
                            {
                                "node_id": "HC-ND-CP-N01",
                                "label": "Khoản 1 Điều 5",
                                "match_type": "exact_phrase",
                                "quote_exact": "Báo cáo định kỳ được lập theo quy định hư cấu.",
                            }
                        ],
                    }
                ],
                "empty_reason": None,
                "phrase_found": True,
                "totals": {"documents": 1, "clauses": 1, "approximate_matches_hidden": 0},
                "page": 1,
                "page_size": 50,
                "has_more": False,
                "effectivity_snapshot_status": "ok",
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            queries_path = self._write_queries(directory)
            output = directory / "out"
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = EVALUATE.main(
                    [
                        "--base-url",
                        self.base_url,
                        "--token",
                        "test-token",
                        "--queries",
                        str(queries_path),
                        "--output",
                        str(output),
                        "--timeout",
                        "5",
                    ]
                )
            self.assertEqual(code, 0, buffer.getvalue())
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            markdown = (output / "report.md").read_text(encoding="utf-8")
            self.assertEqual(report["quality_status"], "not_evaluated")
            self.assertIsNone(report["official_metrics"])
            self.assertEqual(report["run"]["case_count"], 2)
            self.assertEqual(report["run"]["approved_case_count"], 0)
            self.assertEqual(report["hucau_metrics"]["cases_ok"], 2)
            self.assertAlmostEqual(report["hucau_metrics"]["recall_at_k"], 1.0)
            self.assertAlmostEqual(report["hucau_metrics"]["no_result_accuracy"], 1.0)
            self.assertAlmostEqual(report["hucau_metrics"]["exact_phrase_precision"], 0.5)
            self.assertEqual(report["hucau_metrics"]["exact_phrase_total_verified"], 1)
            self.assertEqual(report["hucau_metrics"]["exact_phrase_total_labeled"], 1)
            self.assertEqual(report["hucau_metrics"]["exact_phrase_cases_null"], 0)
            self.assertEqual(report["hucau_metrics"]["exact_phrase_negative_cases"], 1)
            self.assertIn("HƯ CẤU", markdown)
            self.assertIn("not_evaluated", markdown)
            self.assertIn("1/1", markdown)
            self.assertIn("null", markdown)
            report_text = json.dumps(report, ensure_ascii=False)
            self.assertNotIn("test-token", report_text)
            self.assertIn("HƯ CẤU", report["disclaimer"])

    def test_missing_token_returns_config_error(self):
        env_name = "SEARCH_EVAL_DEFINITELY_MISSING_TOKEN"
        self.assertNotIn(env_name, os.environ)
        with tempfile.TemporaryDirectory() as tmp:
            buffer = io.StringIO()
            with contextlib.redirect_stderr(buffer):
                code = EVALUATE.main(["--token-env", env_name, "--output", str(Path(tmp) / "out")])
        self.assertEqual(code, 2)
        self.assertIn("token", buffer.getvalue().lower())

    def test_invalid_page_size_returns_config_error(self):
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            code = EVALUATE.main(["--page-size", "99", "--token", "test-token"])
        self.assertEqual(code, 2)

    def test_unreachable_api_returns_two(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
        probe.close()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            queries_path = self._write_queries(directory)
            buffer = io.StringIO()
            with contextlib.redirect_stderr(buffer):
                code = EVALUATE.main(
                    [
                        "--base-url",
                        f"http://127.0.0.1:{closed_port}",
                        "--token",
                        "test-token",
                        "--queries",
                        str(queries_path),
                        "--output",
                        str(directory / "out"),
                        "--timeout",
                        "0.5",
                    ]
                )
        self.assertEqual(code, 2)
        self.assertIn("không chạy", buffer.getvalue().lower())

    def test_rejected_token_returns_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            queries_path = self._write_queries(directory)
            buffer = io.StringIO()
            with contextlib.redirect_stderr(buffer):
                code = EVALUATE.main(
                    [
                        "--base-url",
                        self.base_url,
                        "--token",
                        "wrong-token",
                        "--queries",
                        str(queries_path),
                        "--output",
                        str(directory / "out"),
                        "--timeout",
                        "5",
                    ]
                )
        self.assertEqual(code, 2)
        self.assertIn("401", buffer.getvalue())


if __name__ == "__main__":
    sys.exit(unittest.main(verbosity=2))
