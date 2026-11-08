"""Summary of one pure-RRF run over the 50 queries: overall, first 24 (v1), added 26 (v2), per topic.

    python evaluation/coverage/summarize_rrf.py --report bench-rrf-50.json --out-json s.json --out-md s.md

Everything comes from the report written by run_rerank_benchmark.py and topics.json.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from compare_rerank import metrics

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--report", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    topics = {t["id"]: t for t in json.loads((HERE / "topics.json").read_text("utf-8"))["topics"]}
    rows = report["rows"]
    group = {"v1": [r for r in rows if topics[r["topic"]].get("set", "v1") == "v1"],
             "v2": [r for r in rows if topics[r["topic"]].get("set", "v1") == "v2"]}
    out: dict = {"queries": len(rows), "reranked_queries": sum(1 for r in rows if r["reranked"]),
                 "overall": metrics(rows), "v1": metrics(group["v1"]), "v2": metrics(group["v2"]),
                 "seconds": {"median": round(statistics.median(r["seconds"] for r in rows), 3),
                             "mean": round(statistics.fmean(r["seconds"] for r in rows), 3),
                             "max": max(r["seconds"] for r in rows)},
                 "memory": report["summary"]["memory"], "per_topic": {}, "weak_citations": []}
    for topic_id in topics:
        selected = [r for r in rows if r["topic"] == topic_id]
        if selected:
            out["per_topic"][topic_id] = {"set": topics[topic_id].get("set", "v1"),
                                          "queries": len(selected), **metrics(selected)}
    for r in rows:
        for c in r["citations"]:
            if c["best_rank"] is None or c["best_rank"] > 10:
                out["weak_citations"].append({
                    "set": topics[r["topic"]].get("set", "v1"), "topic": r["topic"],
                    "query": r["query"], "citation": f"{c['document_number']} Điều {c['article']}",
                    "pool": r["total"], "best_rank": c["best_rank"], "channels": c["channels"]})
    Path(args.out_json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    def fmt(v: object) -> str:
        return "-" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))

    lines = ["# RRF thuần, 50 câu hỏi", "",
             f"Số câu: {out['queries']}; số câu bị xếp hạng lại: {out['reranked_queries']} (mong đợi 0). "
             f"Thời gian trả lời (giây): trung vị {out['seconds']['median']}, trung bình {out['seconds']['mean']}, lớn nhất {out['seconds']['max']}.", "",
             "| Bộ | Câu | Cặp | R@10 | R@20 | R@50 | R@toàn bộ | MRR@10 | NDCG@10 | P@10 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, label in (("v1", "24 câu gốc"), ("v2", "26 câu bổ sung"), ("overall", "Cả 50 câu")):
        m = out[name]
        lines.append(f"| {label} | {m['queries']} | {m['pairs']} | {fmt(m['recall@10'])} | {fmt(m['recall@20'])} | "
                     f"{fmt(m['recall@50'])} | {fmt(m['recall@all'])} | {fmt(m['mrr@10'])} | {fmt(m['ndcg@10'])} | {fmt(m['p@10'])} |")
    lines += ["", "Theo chủ đề:", "", "| Chủ đề | Bộ | Câu | R@10 | R@20 | R@50 | R@toàn bộ | MRR@10 | NDCG@10 |", "|---|---|---|---|---|---|---|---|---|"]
    for topic_id, m in out["per_topic"].items():
        lines.append(f"| {topic_id} | {m['set']} | {m['queries']} | {fmt(m['recall@10'])} | {fmt(m['recall@20'])} | "
                     f"{fmt(m['recall@50'])} | {fmt(m['recall@all'])} | {fmt(m['mrr@10'])} | {fmt(m['ndcg@10'])} |")
    lines += ["", "Căn cứ không có trong 10 kết quả đầu:", "", "| Bộ | Câu hỏi | Căn cứ | Nhóm ứng viên | Hạng tốt nhất | Kênh |", "|---|---|---|---|---|---|"]
    for w in out["weak_citations"]:
        lines.append(f"| {w['set']} | {w['query'][:70]} | {w['citation']} | {w['pool']} | {fmt(w['best_rank'])} | "
                     f"{'+'.join(w['channels']) if w['channels'] else '-'} |")
    lines += ["", "RAM (MB): " + "; ".join(f"{k} đỉnh {v['peak_mb']} / trung vị {v['median_mb']}"
                                            for k, v in out["memory"].items())]
    Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
