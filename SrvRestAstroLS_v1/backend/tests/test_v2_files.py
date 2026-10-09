"""Synthetic files only. Real PG tests roll back all catalog/users/audit writes."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import AsyncConnection

from backend.core.config import credentials
from backend.core.security import Principal, password_hash
from backend.repositories.files import FileDenied, FileRepository, controlled_path
from backend.scripts.provision_dev import SECRET_PATH


def test_controlled_paths(tmp_path):
    (tmp_path / 'incoming').mkdir()
    file = tmp_path / 'incoming/test.csv'
    file.write_text('synthetic')
    assert controlled_path('incoming/test.csv', tmp_path) == file
    outside = tmp_path / 'outside.csv'
    outside.write_text('synthetic')
    (tmp_path / 'incoming/link.csv').symlink_to(outside)
    for value in ('../outside.csv', '/etc/passwd', 'incoming/../outside.csv',
                  'incoming/link.csv', 'archives/test.csv', 'incoming/missing.csv'):
        with pytest.raises(FileDenied):
            controlled_path(value, tmp_path)


def test_persistent_file_authorization(tmp_path, monkeypatch):
    if not SECRET_PATH.exists():
        pytest.skip('Requires explicitly provisioned DEV database')

    async def check():
        async with await AsyncConnection.connect(**credentials(SECRET_PATH, 'concilia_app').kwargs()) as conn:
            async with conn.transaction(force_rollback=True):
                class Pool:
                    @asynccontextmanager
                    async def connection(self):
                        yield conn
                owner, other, admin = [uuid4() for _ in range(3)]
                encoded = password_hash(str(uuid4()) + str(uuid4()))
                for actor, role in [(owner, 'OPERADOR'), (other, 'OPERADOR'), (admin, 'ADMINISTRADOR')]:
                    await conn.execute('INSERT INTO public.seg_users(id,email,password_hash,role) VALUES (%s,%s,%s,%s)',
                                       (actor, f'{actor}@example.invalid', encoded, role))
                principal = Principal(owner, 'owner@example.invalid', 'OPERADOR', '')
                (tmp_path / 'incoming').mkdir()
                path = tmp_path / 'incoming/synthetic.csv'
                path.write_text('fecha,importe\n2026-01-01,1\n')
                catalog = FileRepository(Pool(), tmp_path)
                correlation = uuid4()
                reference = await catalog.register(path, 'extracto', owner, correlation)
                # New repository reads the same persistent identity, never an in-memory registry.
                rebuilt = FileRepository(Pool(), tmp_path)
                assert await rebuilt.resolve(reference, principal) == path.as_uri()
                assert await rebuilt.resolve(reference, Principal(admin, '', 'ADMINISTRADOR', '')) == path.as_uri()
                for ref, actor in [(reference, Principal(other, '', 'OPERADOR', '')),
                                   (str(uuid4()), principal), (path.as_uri(), principal),
                                   (str(path), principal), ('../synthetic.csv', principal)]:
                    with pytest.raises(FileDenied):
                        await rebuilt.resolve(ref, actor)
                row = await (await conn.execute('SELECT action,result,correlation_id,entity_id FROM public.seg_audit_events WHERE entity_id=%s', (reference,))).fetchone()
                assert row == ('file_upload', 'SUCCESS', correlation, reference)
                # Exercise real canonicalization and opaque SSE references, not a parser mock.
                from openpyxl import Workbook
                from routes.v1 import ingest_confirm as ingest
                workbook = Workbook()
                workbook.active.append(['Fecha', 'Documento', 'Ingresos', 'Egresos'])
                workbook.active.append(['01/01/2026', 'SYNTHETIC-01', 1, 0])
                raw = tmp_path / 'incoming/synthetic.xlsx'
                workbook.save(raw)
                raw_ref = await catalog.register(raw, 'contable', owner, correlation)
                emitted = []
                async def capture(topic, payload):
                    emitted.append(payload)
                monkeypatch.setattr(ingest, 'emit', capture)
                monkeypatch.setattr(ingest.Var, 'resolve_storage_uri',
                    lambda kind, filename: (tmp_path / kind / filename).as_uri())
                topic = str(uuid4())
                ingest._CONFIRMS[topic] = {
                    'extracto': None, 'contable': {'source_file_id': raw_ref}, 'sicom': None,
                    '_catalog': catalog, '_actor': owner, '_correlation': correlation}
                try:
                    await ingest._canonicalize_async(topic, 'contable', raw.as_uri(), None, None, None)
                    ready = next(event for event in emitted if event['type'] == 'INGEST_CANONICAL_READY')
                    canonical_ref = ready['payload']['canonical_uri']
                    assert str(__import__('uuid').UUID(canonical_ref)) == canonical_ref
                    canonical_uri = await rebuilt.resolve(canonical_ref, principal)
                    assert canonical_uri.endswith('.parquet')
                    assert not any('file://' in str(event) for event in emitted)
                finally:
                    ingest._CONFIRMS.pop(topic, None)
                path.write_text('tampered')
                with pytest.raises(FileDenied):
                    await rebuilt.resolve(reference, principal)
                path.unlink()
                outside = tmp_path / 'outside.csv'
                outside.write_text('fecha,importe\n2026-01-01,1\n')
                path.symlink_to(outside)
                with pytest.raises(FileDenied):
                    await rebuilt.resolve(reference, principal)
                # Audit failure rolls catalog insertion back, not a successful financial upload.
                second = tmp_path / 'incoming/second.csv'
                second.write_text('synthetic')
                async def fail_audit(*args, **kwargs):
                    raise RuntimeError('synthetic audit failure')
                catalog.audit._audit = fail_audit
                with pytest.raises(RuntimeError):
                    await catalog.register(second, 'extracto', owner, uuid4())
                count = (await (await conn.execute('SELECT count(*) FROM public.seg_files WHERE relative_path=%s', ('incoming/second.csv',))).fetchone())[0]
                assert count == 0
    asyncio.run(check())
