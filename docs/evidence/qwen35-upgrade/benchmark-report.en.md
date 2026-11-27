**Language / Ngôn ngữ:** [Tiếng Việt](benchmark-report.md) · English

# Gate A1 verification report: `qwen3.5:4b` on Ollama 0.40.15

Verification date: 2026-11-16

## 1. Verification environment and baseline

- **Ollama runtime**: `0.40.15` (the same build packaged in r4; it supports the `qwen35` architecture and the vision projector, so the runtime does not need to be replaced).
- **Test model store**: the project's `models/ollama` directory (separate from the default `<ProgramsRoot>`).
- **Baseline DB (`evidence_rerank_eval`)**:
  - `documents`: `105`
  - `document_versions`: `105`
  - `document_nodes`: `7447`
  - `node_embeddings`: `7447`
  - `embedding_indices`: `1` (`qwen3-embedding:0.6b`, 1,024 dimensions)
  - `source_pages`: `1566`
  - `schema_migrations`: `0015_ocr_page_review.sql`
  - A full backup was taken and restore was verified into the test DB `evidence_qwen35_test` (`105` documents, `7447` vectors).

## 2. Weights and manifest

| Model | Manifest digest | Total blob size | Projector / vision layer | Architecture / quantization |
|---|---|---|---|---|
| `qwen3:1.7b` | `sha256:0f45bae8cd2fec097cf09b400b078cf42388a1f5702f4058d2d6d641a09db46d` | 1,359,294,303 bytes | No (`has_vision_layer=false`) | `qwen3` (2.0B, `Q4_K_M`) |
| `qwen3.5:4b` | `sha256:e0b8c85c75aad2573ff49bec177ebb1013772fba665a53d64c04266439a2222d` | 3,324,175,492 bytes | Yes (`application/vnd.ollama.image.projector`, `sha256:e56a899b1540860385465756dd308c84417410b94dbc1c380adffd20a921ca60`, 675,569,120 bytes) + weights (`sha256:a9d0a3e1d8c91732a3812becd31f8d4a8ff57414903f226306069f0437e2ac50`, 2,648,593,216 bytes) | `qwen35` (4.2B, `Q4_K_M`, capabilities: `completion`, `vision`, `tools`, `thinking`) |

## 3. Same-condition measurements (`scripts/benchmark_qwen35.py`)

| Measurement | `qwen3:1.7b` | `qwen3.5:4b` | Note |
|---|---|---|---|
| Text JSON cold start (`think=false`) | 7,641 ms | 4,938 ms | Valid JSON, no extra reasoning text |
| Text JSON warm median (2 runs) | 320.0 ms (312 / 328 ms) | 812.5 ms (812 / 813 ms) | Within the 30s timeout of the text stage |
| Vision OCR of a synthetic PNG (`think=false`, schema) | Not supported | 20,125 ms (177 tokens) | Read the document number `17/2026` and the date `16/11/2026` correctly |
| Embedding `qwen3-embedding:0.6b` | — | — | Worked normally and returned exactly 1,024 dimensions |

**Gate A1 conclusion:** Passed. Ollama runtime `0.40.15` + `qwen3.5:4b` runs text, JSON schema, `think=false` and vision OCR, and keeps `qwen3-embedding:0.6b` at 1,024 dimensions.

## Cross-check after the 2026-11-17 review

The 2026-11-16 measurements above are unchanged. The manifest-file SHA `e0b8…` differs from the model digest `d8b0…` returned by native `/api/tags`: the store manifest contains nested manifest layers. The runtime was fixed to store the digest from the native API and still keep the configuration fingerprint; see the [review report](REVIEW_FIXES_2026-11-17.en.md). Metadata format source: [Ollama List models](https://docs.ollama.com/api/tags).
