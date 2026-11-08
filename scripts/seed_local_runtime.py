"""Explicit local bootstrap and test-corpus drafts; never approve sources or invent models."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'backend'))

from app.admin_services import create_category, create_or_update_user  # noqa: E402
from app.documents.draft import persist_draft, prepare_draft  # noqa: E402
from app.documents.provenance import sha256_bytes  # noqa: E402
from app.migrations.runner import apply_migrations  # noqa: E402
from app.storage.postgres import create_pool  # noqa: E402


async def seed() -> dict[str, int]:
    dsn = os.environ.get('DATABASE_URL')
    store_value = os.environ.get('EVIDENCE_DOCUMENT_STORE_ROOT')
    if not dsn or not store_value or not Path(store_value).is_absolute():
        raise RuntimeError('DATABASE_URL and absolute EVIDENCE_DOCUMENT_STORE_ROOT required')
    store_root = Path(store_value)
    store_root.mkdir(parents=True, exist_ok=True)
    pool = await create_pool(dsn)
    created_users = imported = 0
    try:
        async with pool.acquire() as conn:
            await apply_migrations(conn)
            user_count = await conn.fetchval('SELECT count(*) FROM users')
        if not user_count:
            password = os.environ.get('EVIDENCE_BOOTSTRAP_PASSWORD')
            if not password:
                raise RuntimeError('EVIDENCE_BOOTSTRAP_PASSWORD required for first bootstrap')
            actor = uuid4()
            category = await create_category(
                pool, actor_id=actor, code='PUBLIC_PDF_TEST', name='Tài liệu thử chưa duyệt'
            )
            for name, roles in [('admin', ['SYS_ADMIN', 'AUDITOR']),
                                ('curator', ['CURATOR']), ('reviewer', ['REVIEWER']),
                                ('chuyenvien', ['USER'])]:
                await create_or_update_user(
                    pool, actor_id=actor, username=name, display_name=name,
                    password=password, roles=roles,
                    category_ids=[UUID(category['id'])] if name == 'chuyenvien' else [],
                    must_change_password=True,
                )
                created_users += 1
        # Re-running startup never resets passwords, roles, ACL or approval state.
        corpus_value = os.environ.get('EVIDENCE_CORPUS_DIR')
        async with pool.acquire() as conn:
            curator = await conn.fetchval(
                "SELECT u.id FROM users u JOIN user_roles r ON r.user_id=u.id "
                "WHERE r.role_code='CURATOR' AND u.disabled_at IS NULL ORDER BY u.id LIMIT 1"
            )
        if corpus_value and curator:
            corpus_root = Path(corpus_value).resolve()
            manifest = json.loads((corpus_root / 'manifest.json').read_text(encoding='utf-8'))
            for entry in manifest['documents']:
                if entry.get('review_status') != 'test_only_unreviewed':
                    raise RuntimeError('TEST_CORPUS_STATUS_REQUIRED')
                path = (corpus_root / entry['local_file']).resolve()
                if not path.is_relative_to(corpus_root):
                    raise RuntimeError('UNSAFE_CORPUS_PATH')
                content = path.read_bytes()
                if sha256_bytes(content) != entry['sha256'] or len(content) != entry['size_bytes']:
                    raise RuntimeError('CORPUS_INTEGRITY_MISMATCH')
                async with pool.acquire() as conn:
                    exists = await conn.fetchval(
                        'SELECT 1 FROM document_versions WHERE original_file_sha256=$1',
                        entry['sha256'],
                    )
                if exists:
                    continue
                prepared = await asyncio.to_thread(
                    prepare_draft, content, max_pages=200, temporary_root=store_root,
                    isolate=True,
                )
                await persist_draft(
                    prepared, pool=pool, store_root=store_root,
                    title=entry['title'], doc_type='decree', original_filename=path.name,
                    document_number=entry['document_number'], official_url=entry['pdf_url'],
                    submitted_by=curator,
                )
                imported += 1
        return {'users_created': created_users, 'drafts_imported': imported,
                'auto_approved': 0, 'model_profiles_created': 0}
    finally:
        await pool.close()


if __name__ == '__main__':
    print(json.dumps(asyncio.run(seed()), ensure_ascii=False))
