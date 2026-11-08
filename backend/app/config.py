"""Runtime configuration.

All installation paths and AI routing values are configuration, never code defaults.
The production application requires PostgreSQL; the in-memory store is available only
for unit tests or an explicitly enabled development POC.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    programs_root: str | None
    operating_mode: str
    llm_attempt_budget: int
    session_ttl_seconds: int
    retention_approved: bool
    dev_allow_in_memory_store: bool
    allowed_origins: tuple[str, ...]
    max_upload_bytes: int = 32 * 1024 * 1024
    max_preview_pages: int = 200
    document_store_root: str | None = None
    auth_ttl_seconds: int = 8 * 60 * 60
    query_timeout_seconds: float = 45
    pdf_timeout_seconds: float = 120
    search_statement_timeout_ms: int = 5000
    search_rate_limit_per_minute: int = 30
    search_max_page_depth: int = 1000
    search_count_cap: int = 8000
    # Directory with the built web app (index.html). When set, the backend serves
    # it on the same origin as the API so LAN users need only one URL.
    web_root: str | None = None
    # G2 comprehensive search (design §6): semantic cap N and relative threshold,
    # rerank batch limits, lifetime of a fixed result set, concept threshold.
    semantic_top_n: int = 200
    semantic_relative_threshold: float = 0.8
    rerank_top_n: int = 40
    rerank_batch_size: int = 10
    # Reranking is opt-in: pure RRF is the default of "Tìm toàn diện" (G5 benchmark, 07/11/2026).
    # A request may still ask for it ("rerank": true); this value is used when it does not say.
    rerank_default: bool = False
    result_set_ttl_seconds: int = 1800
    concept_min_terms: int = 1
    # Experimental reranker (G5 benchmark). "llm" is the Registry stage "rerank";
    # "cross_encoder" calls the local Qwen3-Reranker service on a loopback address.
    rerank_backend: str = "llm"
    cross_encoder_url: str | None = None
    cross_encoder_timeout_seconds: float = 120
    cross_encoder_instruction: str | None = None
    # G5: background worker of the API process that runs embedding rebuild jobs
    # queued from the Admin Portal.  Turn off only on extra API processes.
    embedding_worker_enabled: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        origins = tuple(
            item.strip()
            for item in os.getenv(
                "EVIDENCE_ALLOWED_ORIGINS",
                "http://127.0.0.1:1420,http://localhost:1420,http://127.0.0.1:8000,http://tauri.localhost,https://tauri.localhost,tauri://localhost",
            ).split(",")
            if item.strip()
        )
        return cls(
            database_url=os.getenv("DATABASE_URL"),
            programs_root=os.getenv("EVIDENCE_PROGRAMS_ROOT"),
            operating_mode=os.getenv("AI_OPERATING_MODE", "LOCAL").upper(),
            llm_attempt_budget=int(os.getenv("LLM_ATTEMPT_BUDGET", "2")),
            session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "1800")),
            retention_approved=os.getenv("RETENTION_POLICY_APPROVED", "false").lower()
            in {"1", "true", "yes"},
            dev_allow_in_memory_store=os.getenv("DEV_ALLOW_IN_MEMORY_STORE", "false").lower()
            in {"1", "true", "yes"},
            allowed_origins=origins,
            max_upload_bytes=int(os.getenv("EVIDENCE_MAX_UPLOAD_BYTES", str(32 * 1024 * 1024))),
            max_preview_pages=int(os.getenv("EVIDENCE_MAX_PREVIEW_PAGES", "200")),
            document_store_root=os.getenv("EVIDENCE_DOCUMENT_STORE_ROOT"),
            auth_ttl_seconds=int(os.getenv("EVIDENCE_AUTH_TTL_SECONDS", str(8 * 60 * 60))),
            query_timeout_seconds=float(os.getenv("EVIDENCE_QUERY_TIMEOUT_SECONDS", "45")),
            pdf_timeout_seconds=float(os.getenv("EVIDENCE_PDF_TIMEOUT_SECONDS", "120")),
            search_statement_timeout_ms=int(
                os.getenv("EVIDENCE_SEARCH_STATEMENT_TIMEOUT_MS", "5000")
            ),
            search_rate_limit_per_minute=int(
                os.getenv("EVIDENCE_SEARCH_RATE_PER_MINUTE", "30")
            ),
            search_max_page_depth=int(os.getenv("EVIDENCE_SEARCH_MAX_PAGE_DEPTH", "1000")),
            search_count_cap=int(os.getenv("EVIDENCE_SEARCH_COUNT_CAP", "8000")),
            web_root=os.getenv("EVIDENCE_WEB_ROOT") or None,
            semantic_top_n=int(os.getenv("EVIDENCE_SEMANTIC_TOP_N", "200")),
            semantic_relative_threshold=float(
                os.getenv("EVIDENCE_SEMANTIC_RELATIVE_THRESHOLD", "0.8")
            ),
            rerank_top_n=int(os.getenv("EVIDENCE_RERANK_TOP_N", "40")),
            rerank_batch_size=int(os.getenv("EVIDENCE_RERANK_BATCH_SIZE", "10")),
            rerank_default=os.getenv("EVIDENCE_RERANK_DEFAULT", "false").strip().lower()
            in {"1", "true", "yes"},
            result_set_ttl_seconds=int(os.getenv("EVIDENCE_RESULT_SET_TTL_SECONDS", "1800")),
            concept_min_terms=int(os.getenv("EVIDENCE_CONCEPT_MIN_TERMS", "1")),
            rerank_backend=os.getenv("EVIDENCE_RERANK_BACKEND", "llm").strip().lower(),
            cross_encoder_url=os.getenv("EVIDENCE_CROSS_ENCODER_URL") or None,
            cross_encoder_timeout_seconds=float(
                os.getenv("EVIDENCE_CROSS_ENCODER_TIMEOUT_SECONDS", "120")
            ),
            cross_encoder_instruction=os.getenv("EVIDENCE_CROSS_ENCODER_INSTRUCTION") or None,
            embedding_worker_enabled=os.getenv("EVIDENCE_EMBEDDING_WORKER", "true")
            .strip().lower() not in {"0", "false", "no"},
        )

    def validate_runtime(self) -> None:
        if self.operating_mode not in {"API", "LOCAL"}:
            raise ValueError("AI_OPERATING_MODE must be API or LOCAL")
        # Server default for stages without a configured policy (ADR-007).
        if self.llm_attempt_budget < 1 or self.llm_attempt_budget > 10:
            raise ValueError("LLM_ATTEMPT_BUDGET must be between 1 and 10")
        if not 60 <= self.auth_ttl_seconds <= 30 * 24 * 60 * 60:
            raise ValueError("EVIDENCE_AUTH_TTL_SECONDS must be between 60 and 2592000")
        if self.max_upload_bytes < 1 or self.max_preview_pages < 1:
            raise ValueError("PDF preview limits must be positive")
        if not 1 <= self.session_ttl_seconds <= 86400:
            raise ValueError("SESSION_TTL_SECONDS must be between 1 and 86400")
        if not 100 <= self.search_statement_timeout_ms <= 60000:
            raise ValueError("search statement timeout must be 100..60000 ms")
        if not 1 <= self.search_rate_limit_per_minute <= 600:
            raise ValueError("search rate limit must be 1..600 per minute")
        if not 50 <= self.search_max_page_depth <= 10000:
            raise ValueError("search page depth must be 50..10000")
        if not 500 <= self.search_count_cap <= 100000:
            raise ValueError("search count cap must be 500..100000 clauses")
        if not 1 <= self.semantic_top_n <= 2000 or not 0 <= self.semantic_relative_threshold <= 1:
            raise ValueError("semantic search limits are invalid")
        if not 0 <= self.rerank_top_n <= 200 or not 1 <= self.rerank_batch_size <= 50:
            raise ValueError("rerank limits are invalid")
        if self.rerank_backend not in {"llm", "cross_encoder"}:
            raise ValueError("EVIDENCE_RERANK_BACKEND must be llm or cross_encoder")
        if self.rerank_backend == "cross_encoder":
            from .storage.cross_encoder import validate_loopback_url

            if not self.cross_encoder_url:
                raise ValueError("EVIDENCE_CROSS_ENCODER_URL is required for cross_encoder")
            validate_loopback_url(self.cross_encoder_url)
            if not 1 <= self.cross_encoder_timeout_seconds <= 600:
                raise ValueError("cross-encoder timeout must be 1..600 seconds")
        if not 60 <= self.result_set_ttl_seconds <= 86400 or not 0 <= self.concept_min_terms <= 20:
            raise ValueError("result set or concept limits are invalid")
        if not 0 < self.query_timeout_seconds <= 300 or not 0 < self.pdf_timeout_seconds <= 600:
            raise ValueError("Operation timeouts must be positive and bounded")
        if self.document_store_root:
            store = Path(self.document_store_root)
            if not store.is_absolute():
                raise ValueError("EVIDENCE_DOCUMENT_STORE_ROOT must be absolute")
        if self.web_root:
            web = Path(self.web_root)
            if not web.is_absolute() or not (web / "index.html").is_file():
                raise ValueError(
                    "EVIDENCE_WEB_ROOT must be an absolute directory containing index.html"
                )
        if not self.database_url and not self.dev_allow_in_memory_store:
            raise RuntimeError(
                "DATABASE_URL is required; set DEV_ALLOW_IN_MEMORY_STORE=true only for a local POC"
            )
