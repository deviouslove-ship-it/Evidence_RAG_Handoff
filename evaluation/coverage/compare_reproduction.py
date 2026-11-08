"""Does the rebuilt database reproduce an earlier benchmark run?

    python evaluation/coverage/compare_reproduction.py --old bench-rrf.json --new bench-rrf-rebuilt-24.json \
        --out-json reproduction.json --out-md reproduction.md

The database was rebuilt (new node ids, new vectors), so results are matched on what a reader
sees: document number and clause label, in order.  Per query it reports the pool size, how many
of the first 10 / 50 positions hold the same clause, and the rank of every required citation;
then the summary metrics of both runs side by side.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from compare_rerank import metrics


def key(item: dict) -> tuple[str, str]:
    return (item["document_number"], item["label"] or "")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--old", required=True)
    parser.add_argument("--new", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()
    old = {(r["topic"], r["query"]): r for r in json.loads(Path(args.old).read_text("utf-8"))["rows"]}
    new = {(r["topic"], r["query"]): r for r in json.loads(Path(args.new).read_text("utf-8"))["rows"]}
    common = [k for k in old if k in new]
    rows = []
    for k in common:
        a, b = old[k], new[k]
        seq_a, seq_b = [key(i) for i in a["top50"]], [key(i) for i in b["top50"]]
        same10 = sum(1 for x, y in zip(seq_a[:10], seq_b[:10]) if x == y)
        same50 = sum(1 for x, y in zip(seq_a, seq_b) if x == y)
        ranks_a = [c["best_rank"] for c in a["citations"]]
        ranks_b = [c["best_rank"] for c in b["citations"]]
        rows.append({
            "topic": k[0], "query": k[1], "pool_old": a["total"], "pool_new": b["total"],
            "same_position_top10": same10, "same_position_top50": same50,
            "top50_overlap": len(set(seq_a) & set(seq_b)), "citation_ranks_old": ranks_a,
            "citation_ranks_new": ranks_b, "citation_ranks_equal": ranks_a == ranks_b})
    summary = {
        "queries": len(rows),
        "pool_size_equal": sum(1 for r in rows if r["pool_old"] == r["pool_new"]),
        "top10_identical": sum(1 for r in rows if r["same_position_top10"] == 10),
        "top50_identical": sum(1 for r in rows if r["same_position_top50"] == 50),
        "citation_ranks_equal": sum(1 for r in rows if r["citation_ranks_equal"]),
        "metrics_old": metrics([old[k] for k in common]),
        "metrics_new": metrics([new[k] for k in common]),
    }
    Path(args.out_json).write_text(json.dumps({"summary": summary, "rows": rows},
                                              ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# Đối chiếu kết quả sau khi dựng lại dữ liệu", "",
             f"{summary['queries']} câu hỏi của bộ gốc, so theo (số hiệu, nhãn khoản) theo thứ tự.", "",
             f"- Kích thước nhóm ứng viên bằng nhau: {summary['pool_size_equal']}/{summary['queries']}",
             f"- 10 kết quả đầu giống hệt: {summary['top10_identical']}/{summary['queries']}",
             f"- 50 kết quả đầu giống hệt: {summary['top50_identical']}/{summary['queries']}",
             f"- Hạng của mọi căn cứ bắt buộc bằng nhau: {summary['citation_ranks_equal']}/{summary['queries']}", "",
             "| Chỉ số | Lần chạy trước (DB đã xóa) | Sau khi dựng lại |", "|---|---|---|"]
    for name in ("recall@10", "recall@20", "recall@50", "recall@all", "mrr@10", "ndcg@10", "p@10"):
        lines.append(f"| {name} | {summary['metrics_old'][name]} | {summary['metrics_new'][name]} |")
    different = [r for r in rows if not r["citation_ranks_equal"] or r["pool_old"] != r["pool_new"]]
    if different:
        lines += ["", "Câu hỏi có khác biệt:", "", "| Câu hỏi | Nhóm trước / sau | Hạng căn cứ trước | Hạng căn cứ sau |", "|---|---|---|---|"]
        for r in different:
            lines.append(f"| {r['query'][:70]} | {r['pool_old']} / {r['pool_new']} | {r['citation_ranks_old']} | {r['citation_ranks_new']} |")
    Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
