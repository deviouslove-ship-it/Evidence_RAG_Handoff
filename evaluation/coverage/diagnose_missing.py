"""Why is a required citation missing or ranked low?  Retrieval failure or ranking failure.

    python evaluation/coverage/diagnose_missing.py --base-url <api> --ollama-url <v1 url> \
        --topic noi_quy_giam_giu --out diagnosis.json

Needs DATABASE_URL (read-only queries) and the evaluation account variables used by
run_coverage.py.  For every query of the topic and every required citation it reports:

* the nodes of that citation and their text (so a wrong ground truth is visible);
* per channel (exact / semantic / concept, one channel at a time): was the clause in the
  pool and at which position;
* the true cosine position of the clause among *all* vectors of the active index, the
  similarity of the best vector and the relative threshold the semantic channel applies;
  this separates "the embedding model ranks it low" from "the cap or threshold cut it";
* the share of the query words found in the clause text (exact-channel view).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

import asyncpg
import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "backend"))

from run_rerank_benchmark import fetch_all, relevant_citations  # noqa: E402

from app.vietnamese_nlp.unicode_norm import fold_text  # noqa: E402

_ARTICLE = re.compile(r"\bĐiều\s+(\d+)", re.IGNORECASE)
_WORD = re.compile(r"\w+", re.UNICODE)


def embed(client: httpx.Client, url: str, model: str, text: str) -> list[float]:
    response = client.post(f"{url.rstrip('/')}/embeddings", json={"model": model, "input": [text]})
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]


async def main_async(args: argparse.Namespace) -> dict:
    topics = json.loads((HERE / "topics.json").read_text(encoding="utf-8"))["topics"]
    topic = next(t for t in topics if t["id"] == args.topic)
    connection = await asyncpg.connect(os.environ["DATABASE_URL"])
    index = await connection.fetchrow(
        "SELECT id, model_id, dimensions FROM embedding_indices WHERE is_active AND status='ready'")
    targets: list[dict] = []
    for need in topic["required"]:
        rows = await connection.fetch(
            """SELECT n.id::text AS id, COALESCE(n.citation_label, n.label_original) AS label,
                      n.text_original AS text,
                      EXISTS (SELECT 1 FROM node_embeddings e WHERE e.document_node_id = n.id
                              AND e.embedding_index_id = $2) AS has_vector
               FROM document_nodes n JOIN documents d ON d.id = n.document_id
               WHERE d.document_number = $1 AND n.review_status = 'approved'""",
            need["document_number"], index["id"])
        nodes = [row for row in rows if need.get("article") is None or (
            (m := _ARTICLE.search(row["label"] or "")) and int(m.group(1)) == need["article"])]
        targets.append({"need": need, "nodes": nodes})

    report: dict = {"topic": args.topic, "embedding_model": index["model_id"],
                    "dimensions": index["dimensions"], "targets": [], "queries": []}
    for target in targets:
        report["targets"].append({
            "citation": f"{target['need']['document_number']} Điều {target['need'].get('article')}",
            "nodes": len(target["nodes"]),
            "nodes_with_vector": sum(1 for n in target["nodes"] if n["has_vector"]),
            "labels": [n["label"] for n in target["nodes"]][:12],
            "text_preview": [" ".join(n["text"].split())[:240] for n in target["nodes"]][:4],
        })

    dim = int(index["dimensions"])
    with httpx.Client(timeout=1800) as client:
        login = client.post(f"{args.base_url}/api/v1/auth/login", json={
            "username": os.environ["EVIDENCE_EVAL_USERNAME"],
            "password": os.environ["EVIDENCE_EVAL_PASSWORD"]})
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        for query in topic["queries"]:
            vector = embed(client, args.ollama_url, index["model_id"], query)
            literal = "[" + ",".join(repr(float(v)) for v in vector) + "]"
            top = await connection.fetchrow(
                f"""SELECT 1 - (embedding::vector({dim}) <=> $1::vector({dim})) AS similarity
                    FROM node_embeddings WHERE embedding_index_id = $2
                    ORDER BY embedding::vector({dim}) <=> $1::vector({dim}) LIMIT 1""",
                literal, index["id"])
            entry: dict = {"query": query, "best_similarity": round(float(top["similarity"]), 4),
                           "relative_threshold_0_8": round(float(top["similarity"]) * 0.8, 4),
                           "citations": []}
            query_words = {w for w in _WORD.findall(fold_text(query)) if len(w) > 2}
            channel_items = {}
            for channel in ("exact", "semantic", "concept"):
                channel_items[channel], _, _ = fetch_all(
                    client, args.base_url, headers,
                    {"q": query, "rerank": False, "display": "all", "channels": [channel]})
            all_items, _, _ = fetch_all(client, args.base_url, headers,
                                        {"q": query, "rerank": False, "display": "all"})
            for index_of_need, target in enumerate(targets):
                ids = [n["id"] for n in target["nodes"]]
                ranks = await connection.fetch(
                    f"""WITH ranked AS (
                          SELECT document_node_id::text AS id,
                                 1 - (embedding::vector({dim}) <=> $1::vector({dim})) AS similarity,
                                 row_number() OVER (ORDER BY embedding::vector({dim})
                                                    <=> $1::vector({dim})) AS position
                          FROM node_embeddings WHERE embedding_index_id = $2)
                        SELECT id, similarity, position FROM ranked WHERE id = ANY($3::text[])
                        ORDER BY position LIMIT 3""", literal, index["id"], ids)
                words = [len(query_words & set(_WORD.findall(fold_text(n["text"])))) / max(
                    1, len(query_words)) for n in target["nodes"]]
                def pos(items: list[dict]) -> int | None:
                    hits = [i + 1 for i, item in enumerate(items)
                            if index_of_need in relevant_citations(item, topic["required"])]
                    return hits[0] if hits else None
                entry["citations"].append({
                    "citation": report["targets"][index_of_need]["citation"],
                    "true_cosine_best": [{"position_among_all_vectors": int(r["position"]),
                                          "similarity": round(float(r["similarity"]), 4)}
                                         for r in ranks],
                    "query_word_share_best_node": round(max(words, default=0.0), 3),
                    "position_in_pool": {c: pos(channel_items[c]) for c in channel_items},
                    "pool_size": {c: len(channel_items[c]) for c in channel_items},
                    "position_in_fused_rrf": pos(all_items), "fused_size": len(all_items),
                })
            report["queries"].append(entry)
            print(json.dumps(entry, ensure_ascii=False), flush=True)
    await connection.close()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--ollama-url", required=True, help="OpenAI-compatible base, e.g. .../v1")
    parser.add_argument("--topic", default="noi_quy_giam_giu")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    Path(args.out).write_text(json.dumps(asyncio.run(main_async(args)), ensure_ascii=False,
                                         indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
