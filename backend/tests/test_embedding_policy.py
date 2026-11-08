"""Embedding policy and storage rules that need no database (G5)."""

from __future__ import annotations

import math

import pytest

from app.model_registry.runtime import EndpointPolicy, RegistryRuntime
from app.schemas import ModelParams
from app.storage.embeddings import EmbeddingIndexError, vector_type, vectors_valid


def test_vector_storage_follows_model_size() -> None:
    assert vector_type(1) == vector_type(2000) == "vector"
    assert vector_type(2001) == vector_type(4000) == "halfvec"
    for size in (0, 4001):
        with pytest.raises(EmbeddingIndexError):
            vector_type(size)


def test_vectors_must_be_finite_sized_and_non_zero() -> None:
    assert vectors_valid([[0.1, 0.2], [0.3, -0.4]], 2)
    assert not vectors_valid([[0.1, 0.2, 0.3]], 2)
    assert not vectors_valid([[0.0, 0.0]], 2)
    assert not vectors_valid([[math.nan, 1.0]], 2)


def test_requested_dimensions_are_stored_for_the_adapter() -> None:
    assert ModelParams(embedding_dimensions=256).to_stored() == {"dimensions": 256}
    assert ModelParams().to_stored() == {}


def test_remote_embedding_flag_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EVIDENCE_REMOTE_EMBEDDING_ALLOWED", raising=False)
    assert EndpointPolicy.from_env().remote_embedding_allowed is False
    monkeypatch.setenv("EVIDENCE_REMOTE_EMBEDDING_ALLOWED", "true")
    assert EndpointPolicy.from_env().remote_embedding_allowed is True


async def test_public_embedding_profile_needs_api_mode_and_both_flags() -> None:
    allowed = EndpointPolicy(remote_processing_allowed=True, remote_embedding_allowed=True)
    local = RegistryRuntime(object(), mode="LOCAL", attempt_limit=1, policy=allowed)
    assert await local._remote_embedding_denied(None, "index") == "REMOTE_EMBEDDING_DENIED"
    only_processing = RegistryRuntime(
        object(), mode="API", attempt_limit=1,
        policy=EndpointPolicy(remote_processing_allowed=True),
    )
    assert await only_processing._remote_embedding_denied(None, "index") \
        == "REMOTE_EMBEDDING_DENIED"
    api = RegistryRuntime(object(), mode="API", attempt_limit=1, policy=allowed)
    assert await api._remote_embedding_denied(None, "index") is None
    # A search query from an unknown principal never leaves the network.
    assert await api._remote_embedding_denied("not-a-user", "query") \
        == "REMOTE_EMBEDDING_DENIED"
