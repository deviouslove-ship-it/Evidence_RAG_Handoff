"""Real HTTP smoke in a disposable schema with explicitly synthetic approved data."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import httpx

from benchmark_search import AS_OF, PHRASE, ROOT, _seed

from app.auth_acl.passwords import hash_password
from app.documents.provenance import save_immutable_pdf
from app.migrations.runner import apply_migrations


async def run(output: Path, soak_turns: int) -> None:
    dsn = os.environ["EVIDENCE_TEST_DATABASE_URL"]
    schema = "audit_http_" + uuid4().hex
    connection = await asyncpg.connect(dsn)
    process = None
    result: dict[str, object] = {"label": "HU_CAU_HTTP_RUNTIME", "failures": []}
    output.mkdir(parents=True, exist_ok=True)
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f'SET search_path TO "{schema}", public')
        await apply_migrations(connection)
        await _seed(connection, 3, 2)
        password = secrets.token_urlsafe(24)
        await connection.execute(
            "UPDATE users SET password_hash=$1, must_change_password=FALSE WHERE username='bench'",
            hash_password(password),
        )
        await connection.execute("INSERT INTO user_roles SELECT id, 'USER' FROM users")
        parsed = urlsplit(dsn)
        isolated_dsn = urlunsplit(parsed._replace(query=urlencode([
            *parse_qsl(parsed.query), ("search_path", schema + ",public"),
        ])))
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        with TemporaryDirectory(prefix="evidence-audit-http-") as temporary:
            # Byte/hash sentinel fixtures only; this smoke does not claim to
            # validate PDF rendering or extract real legal text from these bytes.
            for version in await connection.fetch("SELECT id FROM document_versions"):
                content = (
                    b"%PDF-1.4\n1 0 obj<<>>endobj\n% HU CAU "
                    + str(version["id"]).encode() + b"\n%%EOF\n"
                )
                source = save_immutable_pdf(content, Path(temporary) / "originals")
                await connection.execute(
                    "UPDATE document_versions SET original_file_path=$2, "
                    "original_file_sha256=$3 WHERE id=$1",
                    version["id"], f"originals/{source.sha256}.pdf", source.sha256,
                )
            environment = {
                **os.environ, "DATABASE_URL": isolated_dsn, "AI_OPERATING_MODE": "LOCAL",
                "DEV_ALLOW_IN_MEMORY_STORE": "false", "EVIDENCE_DOCUMENT_STORE_ROOT": temporary,
                "EVIDENCE_SEARCH_RATE_PER_MINUTE": "600", "EVIDENCE_QUERY_TIMEOUT_SECONDS": "3",
            }
            with (output / "http-server.log").open("w", encoding="utf-8") as server_log:
                process = subprocess.Popen(
                    [sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory",
                     "--host", "127.0.0.1", "--port", str(port)],
                    cwd=ROOT / "backend", env=environment, stdout=server_log,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                async with httpx.AsyncClient(base_url=origin, timeout=10) as client:
                    for _ in range(100):
                        if process.poll() is not None:
                            raise RuntimeError("HTTP server exited during startup")
                        try:
                            health = await client.get("/health")
                            if health.status_code == 200:
                                break
                        except httpx.ConnectError:
                            pass
                        await asyncio.sleep(0.05)
                    else:
                        raise RuntimeError("HTTP server startup deadline exceeded")
                    login = await client.post("/api/v1/auth/login", json={
                        "username": "bench", "password": password, "client": "web",
                    })
                    login.raise_for_status()
                    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
                    tick = time.perf_counter()
                    search = await client.get("/api/v1/search", headers=headers, params={
                        "q": f'"{PHRASE}"', "as_of_date": AS_OF.isoformat(),
                    })
                    search.raise_for_status()
                    found = search.json()
                    assert found["totals"]["documents"] == 3
                    assert all(PHRASE in clause["quote_exact"] for doc in found["results"]
                               for clause in doc["clauses"])
                    result["search_ms"] = round((time.perf_counter() - tick) * 1000, 2)
                    result["search_documents"] = found["totals"]["documents"]
                    unauthorized = await client.get("/api/v1/search", params={"q": PHRASE})
                    assert unauthorized.status_code == 401
                    session = await client.post("/api/v1/agent/sessions", headers=headers, json={})
                    session.raise_for_status()
                    session_id = session.json()["session_id"]
                    tick = time.perf_counter()
                    stream = await client.post(
                        f"/api/v1/agent/sessions/{session_id}/turns",
                        headers={**headers, "Idempotency-Key": uuid4().hex},
                        json={"question": "báo cáo định kỳ", "scope": {
                            "scope_mode": "ALL_AUTHORIZED", "as_of_date": AS_OF.isoformat(),
                        }, "facts": []},
                    )
                    stream.raise_for_status()
                    assert "event: answer_complete" in stream.text, stream.text
                    assert "event: evidence_verified" in stream.text
                    result["chat_sse_ms"] = round((time.perf_counter() - tick) * 1000, 2)
                    timings = []
                    turn_payload = json.loads(stream.request.content)
                    for _ in range(soak_turns):
                        tick = time.perf_counter()
                        repeated = await client.post(
                            f"/api/v1/agent/sessions/{session_id}/turns",
                            headers={**headers, "Idempotency-Key": uuid4().hex},
                            json=turn_payload,
                        )
                        repeated.raise_for_status()
                        assert "event: answer_complete" in repeated.text, repeated.text
                        timings.append((time.perf_counter() - tick) * 1000)
                    result["repeated_turns"] = {
                        "completed": len(timings), "max_ms": round(max(timings, default=0), 2),
                    }

                    async def health_probe() -> float:
                        tick = time.perf_counter()
                        response = await client.get("/health")
                        response.raise_for_status()
                        return (time.perf_counter() - tick) * 1000

                    probes = await asyncio.gather(*(health_probe() for _ in range(20)))
                    result["health_concurrent_20_max_ms"] = round(max(probes), 2)
                    logout = await client.post("/api/v1/auth/logout", headers=headers)
                    assert logout.status_code == 204
                    revoked = await client.get("/api/v1/categories", headers=headers)
                    assert revoked.status_code == 401
                    result["logout_revokes_token"] = True
                    result["server_alive_after"] = process.poll() is None
    except BaseException as exc:
        result["failures"] = [type(exc).__name__ + ": " + str(exc)]
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            await asyncio.to_thread(process.wait, 5)
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()
        (output / "http-smoke.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--soak-turns", type=int, choices=range(0, 101), default=35)
    arguments = parser.parse_args()
    asyncio.run(run(arguments.output, arguments.soak_turns))
