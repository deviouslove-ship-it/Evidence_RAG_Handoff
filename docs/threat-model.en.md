**Language / Ngôn ngữ:** [Tiếng Việt](threat-model.md) · English

English counterpart of `docs/threat-model.md`. The Vietnamese file is the original.

# Threat model (P0 baseline)

## Authentication, headers, and CORS

- Bearer Token authentication is required for every user session and every administrator session.
- The developer identity headers (`X-Principal-Id` and `X-Roles`) may be loaded into the CORS configuration only when the POC flag `DEV_ALLOW_IN_MEMORY_STORE=true` is on. In a standard or production environment, these two headers are removed entirely from the CORS allowlist, so that identity spoofing from the client is prevented absolutely.

## Documents and permissions

- The ACL must be applied in SQL before lexical search, vector search, rerank, cache, and citation.
- `ALL_AUTHORIZED` is resolved again by the server against the current permissions. The client does not send a permission wildcard.
- SYS_ADMIN does not implicitly have `rag.query`, or permission to read content or conversations.

## External sources

- An import URL goes only through a verified domain allowlist. DNS and redirects must be checked again, and private or local networks are blocked.
- An upload is checked for magic bytes, the real MIME type, PDF structure, quota, and SHA-256 before an immutable version is created.

## LLM, runtime, and egress

- A remote route fails closed. Local Mode does not fall back to remote.
- A secret never enters source code, a prompt, a log, or a response.
- An API key entered in the Admin Portal is written once into the encrypted key store (`secret:<tên>` (`secret:<name>`), Windows DPAPI, directory `EVIDENCE_SECRET_STORE_DIR`), bound to the Windows account that runs the server. The key is not returned through the API. It does not enter the database, the audit log, or other logs. The entered key travels to the server over HTTP. On a LAN without TLS, weigh this risk, or use `env:`.
- `secret_ref` allows only the syntax `env:KEY_NAME` or `secret:<tên>` (`secret:<name>`, the key store above). A blacklist blocks system environment variables (`DATABASE_URL`, the database connection password, and internal tokens).
- Model-connection error logs are redacted. They record only the error code or the exception class name. They do not expose the endpoint or authentication headers.
- AI selection of evidence (căn cứ) is protected by its own timeout (70% of the query timeout). On congestion, delay, or a network error, the system degrades gracefully (graceful degradation) and does not crash or block the query flow.
- PDF content is placed in the data region, not in the instructions.

## Memory and deletion

- Incognito is RAM only, with a configured TTL. Content is not written to a durable database, log, or cache.
- When the user logs out or navigates away, the frontend sends a session-cancel signal and clears RAM immediately.
- Deleting one memory item invalidates the older turns, so that context integrity is preserved.
- When the TTL expires or the session is deleted, the SSE stream sends an explicit error event (`turn_error: SESSION_EXPIRED`) instead of disconnecting silently.
- Restore must replay the deletion ledger before the service is opened.

## Not yet closed

- There is not yet an integrated attack test on the target Windows machine, an operative firewall rule, a secret scanner, a production CSP, or evidence of a clean restore.
