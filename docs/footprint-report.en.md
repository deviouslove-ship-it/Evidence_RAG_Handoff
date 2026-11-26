**Language / Ngôn ngữ:** [Tiếng Việt](footprint-report.md) · English

English counterpart of `docs/footprint-report.md`. The Vietnamese file is the original.

# Footprint report

There is no measurement on the target machine yet. Do not publish an estimate before measuring.

When an approved install manifest exists, report these separately:

1. Core Pack: frontend, backend, parser, client, dependency runtime;
2. Model Pack: each model id, revision, SHA-256, license, RAM/disk;
3. PostgreSQL and pgvector;
4. Data Pack: PDFs, source pages, vectors, logs, and backups.

`tools/measure-footprint` must run a clean install under the configured root and return an inventory of real paths. Do not use the size of the source tree as evidence of the install package.
