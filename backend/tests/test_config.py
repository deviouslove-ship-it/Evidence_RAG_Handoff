import pytest

from app.config import Settings


def test_production_requires_database() -> None:
    settings = Settings(
        database_url=None,
        programs_root=None,
        operating_mode="LOCAL",
        llm_attempt_budget=2,
        session_ttl_seconds=1800,
        retention_approved=False,
        dev_allow_in_memory_store=False,
        allowed_origins=(),
    )
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        settings.validate_runtime()


def test_budget_has_a_hard_cap() -> None:
    settings = Settings(
        database_url="postgresql://example",
        programs_root=None,
        operating_mode="LOCAL",
        llm_attempt_budget=11,
        session_ttl_seconds=1800,
        retention_approved=False,
        dev_allow_in_memory_store=False,
        allowed_origins=(),
    )
    with pytest.raises(ValueError, match="between 1 and 10"):
        settings.validate_runtime()
