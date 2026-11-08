"""Compare the reports of run_rerank_benchmark.py (pure RRF, RRF + LLM rerank, RRF + cross-encoder).

    python evaluation/coverage/compare_rerank.py --rrf a.json --llm b.json --ce c.json \
        --out-json compare.json --out-md compare.md

Everything printed comes from the three reports; no figure is typed in here.  The
missing-citation section separates a *retrieval* failure (the clause is in no channel's
candidate pool) from a *ranking* failure (it is in the pool but ranked too low, or outside
the head that the reranker re-scores).
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path

HEAD = 40  # EVIDENCE_RERANK_TOP_N default; override with --head when it was changed
LABELS = {"rrf": "RRF thuần", "llm": "RRF + rerank LLM hiện tại (qwen3:1.7b)",
          "ce": "RRF + Qwen3-Reranker-0.6B"}


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def metrics(selected: list[dict]) -> dict:
    """Recall@k over (query, citation) pairs, MRR@10, NDCG@10, P@10 over queries."""
    pairs = [c for row in selected for c in row["citations"]]
    result = {"queries": len(selected), "pairs": len(pairs)}
    for k in (10, 20, 50):
        result[f"recall@{k}"] = round(sum(1 for c in pairs if c["best_rank"]
                                          and c["best_rank"] <= k) / len(pairs), 4)
    result["recall@all"] = round(sum(1 for c in pairs if c["retrieved"]) / len(pairs), 4)
    result["mrr@10"] = round(statistics.fmean(r["mrr10"] for r in selected), 4)
    result["ndcg@10"] = round(statistics.fmean(r["ndcg10"] for r in selected), 4)
    result["p@10"] = round(statistics.fmean(
        sum(1 for item in r["top50"][:10] if item["relevant"]) / 10 for r in selected), 4)
    return result


def separation(selected: list[dict]) -> dict:
    """AUC of the rerank score inside the re-scored head (ties count half), averaged over
    queries that have both relevant and non-relevant clauses there; plus the share of
    head clauses that share their score with another clause (ties fall back to RRF order)."""
    aucs: list[float] = []
    tied = scored = 0
    for row in selected:
        head = [i for i in row["top50"] if i["rerank_score"] is not None]
        scores = [i["rerank_score"] for i in head]
        scored += len(scores)
        tied += sum(1 for s in scores if scores.count(s) > 1)
        positive = [i["rerank_score"] for i in head if i["relevant"]]
        negative = [i["rerank_score"] for i in head if not i["relevant"]]
        if positive and negative:
            wins = sum((p > n) + 0.5 * (p == n) for p in positive for n in negative)
            aucs.append(wins / (len(positive) * len(negative)))
    return {"queries_with_both_classes": len(aucs),
            "mean_auc": round(statistics.fmean(aucs), 4) if aucs else None,
            "share_tied_scores": round(tied / scored, 4) if scored else None,
            "distinct_scores_median": statistics.median(
                len({i["rerank_score"] for i in row["top50"] if i["rerank_score"] is not None})
                for row in selected)}


def bootstrap(differences: list[float], rounds: int = 10000) -> tuple[float, float, float]:
    """Mean paired difference and a 95% percentile interval (fixed seed, deterministic)."""
    generator = random.Random(20261107)
    means = sorted(statistics.fmean(generator.choices(differences, k=len(differences)))
                   for _ in range(rounds))
    return (round(statistics.fmean(differences), 4), round(means[int(0.025 * rounds)], 4),
            round(means[int(0.975 * rounds) - 1], 4))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--rrf", required=True)
    parser.add_argument("--llm", required=True)
    parser.add_argument("--ce", required=True)
    parser.add_argument("--head", type=int, default=HEAD)
    parser.add_argument("--extra", action="append", default=[], metavar="LABEL=REPORT",
                        help="extra run (other threshold, depth, topic subset), shown beside "
                             "the three main variants restricted to the same queries")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()
    reports = {"rrf": load(args.rrf), "llm": load(args.llm), "ce": load(args.ce)}
    rows = {name: {(r["topic"], r["query"]): r for r in rep["rows"]}
            for name, rep in reports.items()}
    keys = list(rows["rrf"])

    out: dict = {"summary": {name: rep["summary"] for name, rep in reports.items()}}
    # Same candidates in every variant? (a precondition for comparing the ranking only)
    same = {key: len({rows[n][key]["candidate_set_sha256"] for n in rows}) == 1 for key in keys}
    out["candidate_sets_identical"] = {"queries_identical": sum(same.values()),
                                       "queries": len(keys),
                                       "different": [k[1] for k, ok in same.items() if not ok]}

    # Paired change of the first relevant position (top 10) against pure RRF.
    paired = {}
    for name in ("llm", "ce"):
        better = worse = equal = 0
        for key in keys:
            a, b = rows["rrf"][key]["mrr10"], rows[name][key]["mrr10"]
            better += b > a
            worse += b < a
            equal += b == a
        paired[name] = {"better_mrr": better, "worse_mrr": worse, "equal_mrr": equal}
    out["paired_vs_rrf"] = paired

    # Same-pool view: only queries whose candidate pool is identical in all three runs.
    matched_keys = [k for k in keys if same[k]]
    out["matched_pool"] = {name: metrics([rows[name][k] for k in matched_keys]) for name in rows}
    out["bootstrap_vs_rrf"] = {}
    for scope, scope_keys in (("all_queries", keys), ("matched_pool", matched_keys)):
        for name in ("llm", "ce"):
            out["bootstrap_vs_rrf"][f"{scope}:{name}"] = {
                metric: dict(zip(("mean_difference", "ci95_low", "ci95_high"), bootstrap(
                    [rows[name][k][field] - rows["rrf"][k][field] for k in scope_keys]),
                    strict=True))
                for metric, field in (("mrr@10", "mrr10"), ("ndcg@10", "ndcg10"))}

    # How well do the reranker's own scores separate relevant from other clauses of the head?
    out["score_separation"] = {name: separation([rows[name][k] for k in keys])
                               for name in ("llm", "ce")}

    out["extra"] = {}
    for item in args.extra:
        label, path = item.split("=", 1)
        extra_rows = {(r["topic"], r["query"]): r for r in load(path)["rows"]}
        common = [k for k in extra_rows if k in rows["rrf"]]
        block = {"extra": metrics([extra_rows[k] for k in common]),
                 "extra_reranked_queries": sum(1 for k in common if extra_rows[k]["reranked"]),
                 "extra_rerank_ms_median": (statistics.median(
                     extra_rows[k]["rerank_ms"] for k in common
                     if extra_rows[k]["rerank_ms"] is not None) if common else None),
                 "extra_pool_sizes": [extra_rows[k]["total"] for k in common]}
        for name in rows:
            block[name] = metrics([rows[name][k] for k in common])
            block[f"{name}_pool_sizes"] = [rows[name][k]["total"] for k in common]
        block["not_retrieved"] = [
            f"{c['document_number']} Điều {c['article']} :: {k[1]}"
            for k in common for c in extra_rows[k]["citations"] if not c["retrieved"]]
        out["extra"][label] = block
    topics = sorted({k[0] for k in keys})
    out["per_topic"] = {
        topic: {name: {
            "mrr@10": round(statistics.fmean(rows[name][k]["mrr10"] for k in keys if k[0] == topic), 3),
            "ndcg@10": round(statistics.fmean(rows[name][k]["ndcg10"] for k in keys if k[0] == topic), 3),
        } for name in rows} for topic in topics
    }

    missing = []
    for key in keys:
        for index, c in enumerate(rows["rrf"][key]["citations"]):
            if c["document_number"] in {"58/2026/TT-BCA", "96/2026/TT-BCA"}:
                entry = {"topic": key[0], "query": key[1],
                         "citation": f"{c['document_number']} Điều {c['article']}"}
                for name in rows:
                    cc = rows[name][key]["citations"][index]
                    entry[name] = {"retrieved": cc["retrieved"], "best_rank": cc["best_rank"],
                                   "channels": cc["channels"], "rerank_score": cc["rerank_score"]}
                base = entry["rrf"]
                if not base["retrieved"]:
                    entry["diagnosis"] = "lỗi truy xuất ứng viên (không nằm trong nhóm ứng viên của kênh nào)"
                elif base["best_rank"] > args.head:
                    entry["diagnosis"] = f"lỗi xếp hạng RRF (hạng {base['best_rank']} > {args.head}, ngoài phần được rerank)"
                elif base["best_rank"] > 10:
                    entry["diagnosis"] = f"lỗi xếp hạng RRF (hạng {base['best_rank']} > 10, trong phần được rerank)"
                else:
                    entry["diagnosis"] = "tìm thấy ở top 10 theo RRF"
                missing.append(entry)
    out["noi_quy_giam_giu"] = missing

    # Citations absent from the pool in the pure RRF run, for every topic.
    out["not_retrieved_pairs"] = [
        {"topic": k[0], "query": k[1], "citation": f"{c['document_number']} Điều {c['article']}"}
        for k in keys for c in rows["rrf"][k]["citations"] if not c["retrieved"]]
    Path(args.out_json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    def fmt(value: object) -> str:
        return "-" if value is None else (f"{value:.3f}" if isinstance(value, float) else str(value))

    lines = ["# So sánh ba phương án xếp hạng (G5)", "",
             f"Số câu hỏi: {reports['rrf']['summary']['queries']}, "
             f"cặp (câu hỏi, căn cứ bắt buộc): {reports['rrf']['summary']['required_citation_pairs']}.", "",
             "| Chỉ số | " + " | ".join(LABELS.values()) + " |", "|---|---|---|---|"]
    for metric in ("recall@10", "recall@20", "recall@50", "recall@all", "mrr@10", "ndcg@10",
                   "seconds_median", "seconds_mean", "seconds_p95", "rerank_ms_median",
                   "queries_reranked"):
        lines.append(f"| {metric} | " + " | ".join(
            fmt(reports[n]["summary"].get(metric)) for n in rows) + " |")
    lines += ["", "Bộ nhớ (MB, đo trong lúc chạy 24 câu hỏi):", ""]
    for name in rows:
        lines.append(f"- {LABELS[name]}: " + ", ".join(
            f"{part} đỉnh {v['peak_mb']} / trung vị {v['median_mb']}"
            for part, v in reports[name]["summary"]["memory"].items()))
    ident = out["candidate_sets_identical"]
    lines += ["", f"Nhóm ứng viên giống nhau giữa ba phương án: {ident['queries_identical']}/{ident['queries']} câu hỏi.", "",
              "So với RRF thuần (MRR@10 theo từng câu hỏi): " + "; ".join(
                  f"{LABELS[n]}: tốt hơn {p['better_mrr']}, kém hơn {p['worse_mrr']}, bằng {p['equal_mrr']}"
                  for n, p in paired.items()), "",
              "## Hai căn cứ nội quy giam giữ", "",
              "| Câu hỏi | Căn cứ | RRF | LLM | Qwen3 | Chẩn đoán |", "|---|---|---|---|---|---|"]
    for e in missing:
        lines.append(f"| {e['query'][:60]} | {e['citation']} | {fmt(e['rrf']['best_rank'])} | "
                     f"{fmt(e['llm']['best_rank'])} | {fmt(e['ce']['best_rank'])} | {e['diagnosis']} |")
    lines += ["", "Khả năng tách căn cứ liên quan khỏi phần còn lại của đầu danh sách bằng điểm rerank "
              "(AUC trung bình theo câu hỏi, 0,5 = ngẫu nhiên; điểm trùng nhau quay về thứ tự RRF):", ""]
    for name, block in out["score_separation"].items():
        lines.append(f"- {LABELS[name]}: AUC {fmt(block['mean_auc'])} trên "
                     f"{block['queries_with_both_classes']} câu hỏi; tỷ lệ kết quả bị trùng điểm "
                     f"{fmt(block['share_tied_scores'])}; số mức điểm khác nhau (trung vị) "
                     f"{block['distinct_scores_median']}")
    lines += ["", f"## Chỉ xét {len(matched_keys)} câu hỏi có nhóm ứng viên giống hệt ở cả ba phương án", "",
              "| Chỉ số | " + " | ".join(LABELS.values()) + " |", "|---|---|---|---|"]
    for metric in ("recall@10", "recall@20", "recall@50", "mrr@10", "ndcg@10", "p@10"):
        lines.append(f"| {metric} | " + " | ".join(
            fmt(out["matched_pool"][n][metric]) for n in rows) + " |")
    lines += ["", "Chênh lệch trung bình so với RRF thuần (khoảng tin cậy 95% bootstrap, 10.000 lần lấy mẫu):", ""]
    for key, value in out["bootstrap_vs_rrf"].items():
        scope, name = key.split(":")
        lines.append(f"- {scope} / {LABELS[name]}: " + "; ".join(
            f"{m} {v['mean_difference']:+.3f} [{v['ci95_low']:+.3f}; {v['ci95_high']:+.3f}]"
            for m, v in value.items()))
    for label, block in out["extra"].items():
        lines += ["", f"## Thí nghiệm bổ sung: {label}", "",
                  f"Số câu hỏi: {block['extra']['queries']}; số lần xếp hạng lại: "
                  f"{block['extra_reranked_queries']}; thời gian rerank trung vị (ms): "
                  f"{fmt(block['extra_rerank_ms_median'])}", "",
                  "| Chỉ số | Thí nghiệm | RRF thuần (chạy chính) | LLM (chạy chính) | Qwen3 (chạy chính) |",
                  "|---|---|---|---|---|"]
        for metric in ("recall@10", "recall@20", "recall@50", "recall@all", "mrr@10", "ndcg@10", "p@10"):
            lines.append(f"| {metric} | {fmt(block['extra'][metric])} | " + " | ".join(
                fmt(block[n][metric]) for n in rows) + " |")
        lines.append("")
        lines.append("Kích thước nhóm ứng viên theo câu hỏi - thí nghiệm: "
                     + ", ".join(map(str, block["extra_pool_sizes"]))
                     + "; RRF chính: " + ", ".join(map(str, block["rrf_pool_sizes"])))
        lines.append("Căn cứ không có trong nhóm ứng viên: "
                     + ("; ".join(block["not_retrieved"]) or "không có"))
    Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
