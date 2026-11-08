"""G5 reranker benchmark: ranking quality, latency and memory of one ranking variant.

    python evaluation/coverage/run_rerank_benchmark.py --variant <name> --base-url <api> \
        --rerank {on,off} --out <report.json> [--pid-file api=<file>] [--pid reranker=<pid>]

Run once per variant against an API started with the matching ``EVIDENCE_RERANK_BACKEND``,
then compare the reports with ``compare_rerank.py``.  It uses the same ``topics.json``
(queries and required citations) as ``run_coverage.py`` and reads the whole result set of
every query through paging.  Credentials: EVIDENCE_EVAL_USERNAME / EVIDENCE_EVAL_PASSWORD.

A node is *relevant* when it belongs to a required citation: same document number and, when
the citation names an Điều, a label with that Điều.  The required citations were written by
the agent and are not confirmed by a subject-matter officer, so every number is a measure
against that list only.

Memory: resident set size of the processes named with --pid / --pid-file plus every process
whose name contains "ollama", sampled while the queries run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import threading
import time
from pathlib import Path

import httpx

try:  # only the memory sampler needs it; diagnose_missing.py imports this module too
    import psutil
except ModuleNotFoundError:  # pragma: no cover
    psutil = None  # type: ignore[assignment]

HERE = Path(__file__).resolve().parent
KS = (10, 20, 50)
_ARTICLE = re.compile(r"\bĐiều\s+(\d+)", re.IGNORECASE)


def relevant_citations(item: dict, required: list[dict]) -> list[int]:
    """Indexes of the required citations this node belongs to."""
    hits = []
    for index, need in enumerate(required):
        if item["document_number"] != need["document_number"]:
            continue
        if need.get("article") is None:
            hits.append(index)
            continue
        match = _ARTICLE.search(item.get("label") or "")
        if match and int(match.group(1)) == int(need["article"]):
            hits.append(index)
    return hits


def fetch_all(client: httpx.Client, base: str, headers: dict, body: dict
              ) -> tuple[list[dict], dict, float]:
    started = time.perf_counter()
    response = client.post(f"{base}/api/v1/search/comprehensive", headers=headers,
                           json={**body, "page_size": 50})
    response.raise_for_status()
    elapsed = time.perf_counter() - started  # first page = what the user waits for
    page = response.json()
    head = page
    items = list(page["items"])
    number = 1
    while page["has_more"]:
        number += 1
        page = client.get(f"{base}/api/v1/search/comprehensive/{page['result_set_id']}",
                          headers=headers, params={"page": number, "page_size": 50}).json()
        items += page["items"]
    return items, head, elapsed


def dcg(gains: list[int]) -> float:
    return sum(gain / math.log2(position + 2) for position, gain in enumerate(gains))


class MemorySampler:
    def __init__(self, pids: dict[str, int], interval: float = 0.5) -> None:
        if psutil is None:
            raise SystemExit("psutil is required to measure memory")
        self.pids, self.interval = pids, interval
        self.samples: dict[str, list[float]] = {name: [] for name in [*pids, "ollama"]}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _rss(self, process: psutil.Process) -> float:
        """Resident memory of the process and its children (a venv launcher has one)."""
        total = 0.0
        try:
            for item in [process, *process.children(recursive=True)]:
                try:
                    total += item.memory_info().rss
                except psutil.Error:
                    continue
        except psutil.Error:
            return 0.0
        return total / 1048576

    def _run(self) -> None:
        while not self._stop.is_set():
            for name, pid in self.pids.items():
                try:
                    self.samples[name].append(self._rss(psutil.Process(pid)))
                except psutil.Error:
                    self.samples[name].append(0.0)
            total = 0.0
            for process in psutil.process_iter(["name"]):
                if "ollama" in (process.info["name"] or "").lower():
                    total += self._rss(process)
            self.samples["ollama"].append(total)
            self._stop.wait(self.interval)

    def __enter__(self) -> MemorySampler:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join()

    def summary(self) -> dict[str, dict[str, float]]:
        return {name: {"peak_mb": round(max(values), 1),
                       "median_mb": round(statistics.median(values), 1)}
                for name, values in self.samples.items() if values}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--variant", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--rerank", choices=("on", "off", "default"), required=True,
                        help="default = send no 'rerank' field and use the server default")
    parser.add_argument("--out", required=True)
    parser.add_argument("--pid-file", action="append", default=[], metavar="NAME=FILE")
    parser.add_argument("--pid", action="append", default=[], metavar="NAME=PID")
    parser.add_argument("--topic", action="append", help="limit to these topic ids")
    parser.add_argument("--only-set", choices=("v1", "v2"),
                        help="v1 = the first 24 queries, v2 = the 26 added on 07/11/2026")
    parser.add_argument("--warmup", default="đăng ký xe lần đầu trực tuyến toàn trình")
    args = parser.parse_args()
    pids = {item.split("=", 1)[0]: int(item.split("=", 1)[1]) for item in args.pid}
    for item in args.pid_file:
        name, path = item.split("=", 1)
        pids[name] = int(Path(path).read_text(encoding="utf-8-sig").strip())
    topics = [t for t in json.loads((HERE / "topics.json").read_text(encoding="utf-8"))["topics"]
              if (not args.topic or t["id"] in args.topic)
              and (not args.only_set or t.get("set", "v1") == args.only_set)]

    with httpx.Client(timeout=1800) as client:
        login = client.post(f"{args.base_url}/api/v1/auth/login", json={
            "username": os.environ["EVIDENCE_EVAL_USERNAME"],
            "password": os.environ["EVIDENCE_EVAL_PASSWORD"]})
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        base_body: dict = {"display": "all"}
        if args.rerank != "default":
            base_body["rerank"] = args.rerank == "on"
        # Warm-up: loads the models; not part of any figure.
        _, warm_head, warm_seconds = fetch_all(client, args.base_url, headers,
                                               {**base_body, "q": args.warmup})
        rows = []
        with MemorySampler(pids) as sampler:
            for topic in topics:
                required = topic["required"]
                for query in topic["queries"]:
                    items, head, seconds = fetch_all(client, args.base_url, headers,
                                                     {**base_body, "q": query})
                    belongs = [relevant_citations(item, required) for item in items]
                    gains = [1 if hits else 0 for hits in belongs]
                    first = next((i + 1 for i, g in enumerate(gains[:10]) if g), None)
                    per_citation = []
                    for index, need in enumerate(required):
                        ranks = [i + 1 for i, hits in enumerate(belongs) if index in hits]
                        node = items[ranks[0] - 1] if ranks else None
                        per_citation.append({
                            "document_number": need["document_number"],
                            "article": need.get("article"),
                            "retrieved": bool(ranks), "best_rank": ranks[0] if ranks else None,
                            "relevant_nodes": len(ranks),
                            "channels": node["channels"] if node else None,
                            "rrf_score": node["rrf_score"] if node else None,
                            "rerank_score": node["rerank_score"] if node else None,
                        })
                    ideal = dcg(sorted(gains, reverse=True)[:10])
                    row = {
                        "topic": topic["id"], "query": query, "total": len(items),
                        "seconds": round(seconds, 3),
                        "server_ms": head["duration_ms"],
                        "rerank_ms": head["ranking"].get("duration_ms"),
                        "reranked": head["ranking"]["reranked"],
                        "reranked_count": head["ranking"]["reranked_count"],
                        "ranking_note": head["ranking"].get("note"),
                        "relevant_in_pool": sum(gains),
                        "mrr10": 1 / first if first else 0.0,
                        "ndcg10": dcg(gains[:10]) / ideal if ideal else 0.0,
                        "citations": per_citation,
                        "candidate_set_sha256": hashlib.sha256(
                            "\n".join(sorted(item["node_id"] for item in items)).encode()
                        ).hexdigest(),
                        "top50": [{"node_id": item["node_id"],
                                   "document_number": item["document_number"],
                                   "label": item["label"], "relevant": bool(belongs[i]),
                                   "channels": item["channels"],
                                   "rerank_score": item["rerank_score"]}
                                  for i, item in enumerate(items[:50])],
                    }
                    rows.append(row)
                    print(json.dumps({k: row[k] for k in (
                        "topic", "total", "seconds", "rerank_ms", "reranked", "mrr10", "ndcg10")},
                        ensure_ascii=False), flush=True)
            memory = sampler.summary()

    pairs = [(row, c) for row in rows for c in row["citations"]]
    summary = {
        "variant": args.variant, "queries": len(rows), "required_citation_pairs": len(pairs),
        "warmup_seconds": round(warm_seconds, 2), "warmup_reranked": warm_head["ranking"]["reranked"],
        **{f"recall@{k}": round(sum(1 for _, c in pairs
                                    if c["best_rank"] and c["best_rank"] <= k) / len(pairs), 4)
           for k in KS},
        "recall@all": round(sum(1 for _, c in pairs if c["retrieved"]) / len(pairs), 4),
        "mrr@10": round(statistics.fmean(row["mrr10"] for row in rows), 4),
        "ndcg@10": round(statistics.fmean(row["ndcg10"] for row in rows), 4),
        "seconds_median": round(statistics.median(row["seconds"] for row in rows), 3),
        "seconds_mean": round(statistics.fmean(row["seconds"] for row in rows), 3),
        "seconds_p95": round(sorted(row["seconds"] for row in rows)[
            max(0, math.ceil(0.95 * len(rows)) - 1)], 3),
        "rerank_ms_median": (round(statistics.median(
            row["rerank_ms"] for row in rows if row["rerank_ms"] is not None), 1)
            if any(row["rerank_ms"] is not None for row in rows) else None),
        "queries_reranked": sum(1 for row in rows if row["reranked"]),
        "memory": memory,
    }
    Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows},
                                         ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
