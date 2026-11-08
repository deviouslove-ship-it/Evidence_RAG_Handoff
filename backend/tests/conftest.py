import os

# CI must exercise the real PostgreSQL integration tests, not silently skip
# them because a DSN was forgotten.  Local runs may omit the DSN.
if os.getenv("CI") and not os.getenv("EVIDENCE_TEST_DATABASE_URL"):
    raise RuntimeError(
        "CI must set EVIDENCE_TEST_DATABASE_URL; PostgreSQL tests may not be skipped."
    )

os.environ.setdefault("DEV_ALLOW_IN_MEMORY_STORE", "true")
os.environ.setdefault("AI_OPERATING_MODE", "LOCAL")
