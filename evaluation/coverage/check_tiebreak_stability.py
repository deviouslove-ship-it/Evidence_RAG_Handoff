"""Is the order of equal-ranked results the same in two independent imports of the same corpus?

    python evaluation/coverage/check_tiebreak_stability.py --base-a http://127.0.0.1:8765 \
        --base-b http://127.0.0.1:8771 --channels exact relation --out-json s.json --out-md s.md

Two databases built from the same files have the same text but different node UUIDs.  Ties in
a channel (same tier and score) and in the RRF fusion must therefore be broken by the document
and clause position, not by a UUID.  The script runs every query of ``topics.json`` on both
servers with the same channels (no reranking) and compares the complete ordered result lists.
A clause is identified across the two databases by (file SHA-256, label, hash of its text).

Only channels that do not call a model are deterministic (exact, relation); pass
``--channels exact`` for a strict check.  Credentials: EVIDENCE_EVAL_USERNAME and
EVIDENCE_EVAL_PASSWORD (server A) and EVIDENCE_EVAL_PASSWORD_B (server B, default: same).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent


def login(client: httpx.Client, base: str, password: str) -> dict[str, str]:
    response = client.post(f"{base}/api/v1/auth/login", json={
        "username": os.environ["EVIDENCE_EVAL_USERNAME"], "password": password})
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def ordered(client: httpx.Client, base: str, headers: dict, query: str, channels: list[str]
            ) -> list[tuple[str, str, str]]:
    response = client.post(f"{base}/api/v1/search/comprehensive", headers=headers, json={
        "q": query, "display": "all", "rerank": False, "channels": channels, "page_size": 50})
    response.raise_for_status()
    page = response.json()
    items = list(page["items"])
    number = 1
    while page["has_more"]:
        number += 1
        page = client.get(f"{base}/api/v1/search/comprehensive/{page['result_set_id']}",
                          headers=headers, params={"page": number, "page_size": 50}).json()
        items += page["items"]
    return [(item["source_hash"], item["label"] or "",
             hashlib.sha256(item["quote_exact"].encode("utf-8")).hexdigest()[:16]) for item in items]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-a", required=True)
    parser.add_argument("--base-b", required=True)
    parser.add_argument("--channels", nargs="+", default=["exact"],
                        choices=["exact", "semantic", "concept", "relation"])
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()
    topics = json.loads((HERE / "topics.json").read_text(encoding="utf-8"))["topics"]
    queries = [(t["id"], q) for t in topics for q in t["queries"]]
    password_a = os.environ["EVIDENCE_EVAL_PASSWORD"]
    password_b = os.environ.get("EVIDENCE_EVAL_PASSWORD_B", password_a)
    rows = []
    with httpx.Client(timeout=600) as client:
        headers_a = login(client, args.base_a, password_a)
        headers_b = login(client, args.base_b, password_b)
        for topic, query in queries:
            a = ordered(client, args.base_a, headers_a, query, args.channels)
            b = ordered(client, args.base_b, headers_b, query, args.channels)
            first_difference = next((i + 1 for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
            rows.append({"topic": topic, "query": query, "size_a": len(a), "size_b": len(b),
                         "same_set": set(a) == set(b), "identical_order": a == b,
                         "first_difference": first_difference if a != b else None,
                         "positions_equal": sum(1 for x, y in zip(a, b) if x == y)})
    summary = {
        "channels": args.channels, "queries": len(rows),
        "same_result_set": sum(1 for r in rows if r["same_set"]),
        "identical_order": sum(1 for r in rows if r["identical_order"]),
        "empty_results": sum(1 for r in rows if r["size_a"] == 0 and r["size_b"] == 0),
        "queries_with_ties_reordered": sum(1 for r in rows if r["same_set"] and not r["identical_order"]),
        "positions_equal_share": round(sum(r["positions_equal"] for r in rows)
                                       / max(1, sum(max(r["size_a"], r["size_b"]) for r in rows)), 4),
    }
    Path(args.out_json).write_text(json.dumps({"summary": summary, "rows": rows},
                                              ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# Độ ổn định thứ tự khi phá hòa (kênh: {', '.join(args.channels)})", "",
             f"- Số câu hỏi: {summary['queries']} (kết quả rỗng ở cả hai: {summary['empty_results']})",
             f"- Cùng tập kết quả ở hai CSDL: {summary['same_result_set']}/{summary['queries']}",
             f"- Cùng thứ tự đầy đủ: {summary['identical_order']}/{summary['queries']}",
             f"- Cùng tập nhưng khác thứ tự: {summary['queries_with_ties_reordered']}",
             f"- Tỷ lệ vị trí giống nhau: {summary['positions_equal_share']}", ""]
    differing = [r for r in rows if not r["identical_order"]]
    if differing:
        lines += ["| Câu hỏi | Kích thước A / B | Cùng tập | Vị trí khác đầu tiên |", "|---|---|---|---|"]
        for r in differing:
            lines.append(f"| {r['query'][:70]} | {r['size_a']} / {r['size_b']} | {r['same_set']} | {r['first_difference']} |")
    Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
