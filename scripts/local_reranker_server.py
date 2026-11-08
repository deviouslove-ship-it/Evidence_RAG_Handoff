"""Local cross-encoder reranker service for Qwen3-Reranker (CPU, loopback only).

    python scripts/local_reranker_server.py --model-dir <folder with the model> [--port 8791]

Run it with an interpreter that has ``torch`` and ``transformers``; the application's own
virtual environment does not need them.  The application talks to it over HTTP
(``EVIDENCE_RERANK_BACKEND=cross_encoder`` and ``EVIDENCE_CROSS_ENCODER_URL``).

POST /rerank  {"query": str, "documents": [str, ...], "instruction": str | null}
              -> {"scores": [float, ...], "milliseconds": float}
GET  /health  -> model name, threads, resident memory of this process

The score is the probability of the answer "yes" against "no" (Qwen3-Reranker model card),
in [0, 1].  Nothing leaves the machine: the server binds to a loopback address only and
makes no outbound request.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import psutil
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query "
    "and the Instruct provided. Note that the answer can only be \"yes\" or \"no\"."
    "<|im_end|>\n<|im_start|>user\n"
)
SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
DEFAULT_INSTRUCTION = (
    "Given a Vietnamese legal search query, judge whether the legal provision is a relevant "
    "legal basis for the query"
)
MAX_BODY_BYTES = 4 * 1024 * 1024
MAX_DOCUMENTS = 200


class Scorer:
    def __init__(self, model_dir: Path, *, max_length: int, batch_size: int, threads: int | None):
        if threads:
            torch.set_num_threads(threads)
        self.name = model_dir.name
        self.max_length = max_length
        self.batch_size = batch_size
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_dir), padding_side="left")
        self.model = AutoModelForCausalLM.from_pretrained(
            str(model_dir), torch_dtype=torch.float32).eval()
        self.false_id = self.tokenizer.convert_tokens_to_ids("no")
        self.true_id = self.tokenizer.convert_tokens_to_ids("yes")
        self.prefix = self.tokenizer.encode(PREFIX, add_special_tokens=False)
        self.suffix = self.tokenizer.encode(SUFFIX, add_special_tokens=False)
        self.lock = threading.Lock()  # one forward pass at a time keeps RAM bounded

    def _encode(self, pairs: list[str]) -> Any:
        room = self.max_length - len(self.prefix) - len(self.suffix)
        batch = self.tokenizer(pairs, padding=False, truncation="longest_first",
                               return_attention_mask=False, max_length=room)
        for index, ids in enumerate(batch["input_ids"]):
            batch["input_ids"][index] = self.prefix + ids + self.suffix
        return self.tokenizer.pad(batch, padding=True, return_tensors="pt",
                                  max_length=self.max_length)

    def score(self, query: str, documents: list[str], instruction: str | None) -> list[float]:
        instruction = instruction or DEFAULT_INSTRUCTION
        pairs = [f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}"
                 for doc in documents]
        order = sorted(range(len(pairs)), key=lambda i: len(pairs[i]))  # similar lengths together
        scores = [0.0] * len(pairs)
        with self.lock, torch.inference_mode():
            for start in range(0, len(order), self.batch_size):
                indexes = order[start: start + self.batch_size]
                inputs = self._encode([pairs[i] for i in indexes])
                # Left padding puts the answer position last; only that position is needed,
                # so skip the vocabulary projection of every other token.
                logits = self.model(**inputs, logits_to_keep=1).logits[:, -1, :]
                two = torch.stack([logits[:, self.false_id], logits[:, self.true_id]], dim=1)
                probability = torch.nn.functional.log_softmax(two, dim=1)[:, 1].exp().tolist()
                for position, value in zip(indexes, probability, strict=True):
                    scores[position] = float(value)
        return scores


def handler(scorer: Scorer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:  # no request text in logs
            return

        def _send(self, status: int, body: dict[str, Any]) -> None:
            raw = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/health":
                self._send(404, {"error": "not_found"})
                return
            self._send(200, {
                "status": "ok", "model": scorer.name, "threads": torch.get_num_threads(),
                "dtype": "float32", "max_length": scorer.max_length,
                "rss_mb": round(psutil.Process().memory_info().rss / 1048576, 1),
            })

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/rerank":
                self._send(404, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY_BYTES:
                    raise ValueError("body size")
                body = json.loads(self.rfile.read(length))
                query, documents = body["query"], body["documents"]
                instruction = body.get("instruction")
                if (not isinstance(query, str) or not isinstance(documents, list)
                        or len(documents) > MAX_DOCUMENTS
                        or not all(isinstance(item, str) for item in documents)
                        or not (instruction is None or isinstance(instruction, str))):
                    raise ValueError("shape")
            except (ValueError, KeyError, TypeError):
                self._send(400, {"error": "invalid_request"})
                return
            started = time.perf_counter()
            scores = scorer.score(query, documents, instruction)
            self._send(200, {"scores": scores,
                             "milliseconds": round((time.perf_counter() - started) * 1000, 1)})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--model-dir", default=os.environ.get("EVIDENCE_CROSS_ENCODER_MODEL_DIR"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--threads", type=int, default=None)
    args = parser.parse_args()
    if not args.model_dir or not Path(args.model_dir).is_dir():
        raise SystemExit("--model-dir (or EVIDENCE_CROSS_ENCODER_MODEL_DIR) must name a folder")
    if not ipaddress.ip_address(args.host).is_loopback:
        raise SystemExit("The reranker binds to a loopback address only")
    scorer = Scorer(Path(args.model_dir), max_length=args.max_length,
                    batch_size=args.batch_size, threads=args.threads)
    server = ThreadingHTTPServer((args.host, args.port), handler(scorer))
    print(json.dumps({"listening": f"{args.host}:{args.port}", "model": scorer.name}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
