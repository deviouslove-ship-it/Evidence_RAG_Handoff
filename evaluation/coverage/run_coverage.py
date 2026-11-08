"""D15/G5 coverage check: required citations found per topic, per channel, over HTTP.

    python evaluation/coverage/run_coverage.py --base-url <api> --out <report.json>

Credentials come from EVIDENCE_EVAL_USERNAME / EVIDENCE_EVAL_PASSWORD (a USER account);
nothing is stored.  For every query the comprehensive search is run once with all
channels and once per single channel; a required citation counts as found when any
returned clause of that document belongs to the required Điều (or any clause when no
Điều is given).  The whole result set is read through paging, never only page 1.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
CHANNELS = ("exact", "semantic", "concept", "relation")
_ARTICLE = re.compile(r"\bĐiều\s+(\d+)", re.IGNORECASE)


def _items(client: httpx.Client, base: str, token: str, body: dict) -> tuple[list[dict], dict]:
    headers = {"Authorization": f"Bearer {token}"}
    first = client.post(f"{base}/api/v1/search/comprehensive", headers=headers,
                        json={**body, "page_size": 50})
    first.raise_for_status()
    page = first.json()
    items = list(page["items"])
    number = 1
    while page["has_more"]:
        number += 1
        page = client.get(f"{base}/api/v1/search/comprehensive/{page['result_set_id']}",
                          headers=headers, params={"page": number, "page_size": 50}).json()
        items += page["items"]
    return items, first.json()


def _found(items: list[dict], required: dict) -> bool:
    for item in items:
        if item["document_number"] != required["document_number"]:
            continue
        if required.get("article") is None:
            return True
        match = _ARTICLE.search(item["label"] or "")
        if match and int(match.group(1)) == int(required["article"]):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--rerank", action="store_true")
    args = parser.parse_args()
    topics = json.loads((HERE / "topics.json").read_text(encoding="utf-8"))["topics"]
    with httpx.Client(timeout=600) as client:
        login = client.post(f"{args.base_url}/api/v1/auth/login", json={
            "username": os.environ["EVIDENCE_EVAL_USERNAME"],
            "password": os.environ["EVIDENCE_EVAL_PASSWORD"]})
        login.raise_for_status()
        token = login.json()["access_token"]
        rows = []
        for topic in topics:
            for query in topic["queries"]:
                started = time.perf_counter()
                items, head = _items(client, args.base_url, token,
                                     {"q": query, "rerank": args.rerank, "display": "all"})
                row = {"topic": topic["id"], "query": query, "total": len(items),
                       "seconds": round(time.perf_counter() - started, 2),
                       "all": [_found(items, need) for need in topic["required"]],
                       "semantic_available": head["channels"]["semantic"].get("available")}
                for channel in CHANNELS:
                    only, _ = _items(client, args.base_url, token, {
                        "q": query, "rerank": False, "display": "all", "channels": [channel]})
                    row[channel] = [_found(only, need) for need in topic["required"]]
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
    required = sum(len(row["all"]) for row in rows)
    summary = {"queries": len(rows), "required_citations": required,
               "found_all_channels": sum(sum(row["all"]) for row in rows)}
    for channel in CHANNELS:
        summary[f"found_{channel}_only"] = sum(sum(row[channel]) for row in rows)
    summary["recall_all_channels"] = round(summary["found_all_channels"] / required, 3)
    for channel in CHANNELS:
        summary[f"recall_{channel}_only"] = round(summary[f"found_{channel}_only"] / required, 3)
    topics_full = {}
    for row in rows:
        topics_full.setdefault(row["topic"], []).append(all(row["all"]))
    summary["topics_all_queries_complete"] = sum(all(v) for v in topics_full.values())
    summary["topics"] = len(topics_full)
    Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows},
                                         ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
