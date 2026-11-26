"""Tests for A1 benchmark manifest inspection and vision readiness gating."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import benchmark_qwen35 as bench  # noqa: E402


def _write_blob(models_dir: Path, payload: bytes) -> tuple[str, int]:
    digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    blob_path = models_dir / "blobs" / digest.replace(":", "-")
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(payload)
    return digest, len(payload)


def _write_manifest(
    models_dir: Path,
    model_id: str,
    *,
    include_projector: bool = True,
    drop_projector_blob: bool = False,
) -> None:
    repo_name, tag = bench.parse_model_ref(model_id)
    manifest_file = models_dir / "manifests" / "registry.ollama.ai" / repo_name / tag
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_digest, cfg_size = _write_blob(models_dir, b'{"model_format":"gguf"}')
    mdl_digest, mdl_size = _write_blob(models_dir, b"weights-bytes")
    layers: list[dict[str, Any]] = [
        {"mediaType": "application/vnd.ollama.image.model", "digest": mdl_digest, "size": mdl_size}
    ]
    if include_projector:
        proj_digest, proj_size = _write_blob(models_dir, b"projector-bytes")
        layers.append(
            {
                "mediaType": "application/vnd.ollama.image.projector",
                "digest": proj_digest,
                "size": proj_size,
            }
        )
        if drop_projector_blob:
            (models_dir / "blobs" / proj_digest.replace(":", "-")).unlink()
    manifest = {
        "schemaVersion": 2,
        "config": {"mediaType": "application/vnd.docker.container.image.v1+json",
                   "digest": cfg_digest, "size": cfg_size},
        "layers": layers,
    }
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")


def test_missing_vision_layers_cannot_be_ready(tmp_path: Path) -> None:
    # Case 1: manifest has no projector/vision layer
    text_only_dir = tmp_path / "text-only"
    _write_manifest(text_only_dir, "qwen3.5:4b", include_projector=False)
    check_no_layer = bench.inspect_model_manifest(text_only_dir, "qwen3.5:4b", require_vision=True)
    assert check_no_layer["ok"] is False
    assert check_no_layer["error_code"] == "VISION_LAYER_MISSING"
    verdict_no_layer = bench.evaluate_readiness(
        check_no_layer,
        {"capabilities": ["completion", "vision"]},
        text_probe_ok=True,
        vision_probe_ok=True,
        require_vision=True,
    )
    assert verdict_no_layer["ready"] is False

    # Case 2: manifest lists projector layer, but its blob is missing on disk
    missing_blob_dir = tmp_path / "missing-blob"
    _write_manifest(
        missing_blob_dir, "qwen3.5:4b", include_projector=True, drop_projector_blob=True
    )
    check_missing_blob = bench.inspect_model_manifest(
        missing_blob_dir, "qwen3.5:4b", require_vision=True
    )
    assert check_missing_blob["ok"] is False
    assert check_missing_blob["error_code"] == "LAYER_BLOB_MISSING"
    verdict_missing_blob = bench.evaluate_readiness(
        check_missing_blob,
        {"capabilities": ["completion", "vision"]},
        text_probe_ok=True,
        vision_probe_ok=True,
        require_vision=True,
    )
    assert verdict_missing_blob["ready"] is False

    # Case 3: manifest is complete, /api/show says vision, but image probe fails -> ready=False
    full_dir = tmp_path / "full"
    _write_manifest(full_dir, "qwen3.5:4b", include_projector=True)
    check_full = bench.inspect_model_manifest(full_dir, "qwen3.5:4b", require_vision=True)
    assert check_full["ok"] is True and check_full["has_vision_layer"] is True
    verdict_probe_fail = bench.evaluate_readiness(
        check_full,
        {"capabilities": ["completion", "vision"]},
        text_probe_ok=True,
        vision_probe_ok=False,
        require_vision=True,
    )
    assert verdict_probe_fail == {"ready": False, "error_code": "VISION_PROBE_FAILED"}

    # Case 4: /api/show lacks vision capability -> ready=False
    verdict_no_cap = bench.evaluate_readiness(
        check_full,
        {"capabilities": ["completion"]},
        text_probe_ok=True,
        vision_probe_ok=True,
        require_vision=True,
    )
    assert verdict_no_cap == {"ready": False, "error_code": "VISION_CAPABILITY_MISSING"}

    # Case 5: everything passes -> ready=True
    verdict_ok = bench.evaluate_readiness(
        check_full,
        {"capabilities": ["completion", "vision"]},
        text_probe_ok=True,
        vision_probe_ok=True,
        require_vision=True,
    )
    assert verdict_ok == {"ready": True, "error_code": None}


def test_synthetic_ocr_png_creates_valid_png() -> None:
    png = bench.make_synthetic_ocr_png(["Điều 1. Nội dung thử nghiệm"])
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 100
