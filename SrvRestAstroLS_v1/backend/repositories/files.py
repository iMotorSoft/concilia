"""Permanent SEG-01 file identity and owner authorization (single deployment)."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from uuid import UUID, uuid4

from backend.repositories.security import SecurityRepository

STORAGE_ROOT = Path(__file__).resolve().parents[3] / "storage"


class FileDenied(ValueError):
    """Deliberately does not disclose paths or existence."""


def controlled_path(relative_path: str, root: Path = STORAGE_ROOT) -> Path:
    relative = Path(relative_path)
    if (relative.is_absolute() or ".." in relative.parts or not relative.parts
            or relative.parts[0] not in {"incoming", "canonical"}):
        raise FileDenied("File reference denied")
    path = root / relative
    # Reject symlinks at every level, including storage itself.
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise FileDenied("File reference denied")
    if not path.resolve().is_relative_to(root.resolve()):
        raise FileDenied("File reference denied")
    return path


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class FileRepository:
    def __init__(self, pool, root: Path = STORAGE_ROOT):
        self.pool, self.root = pool, root
        self.audit = SecurityRepository(pool)

    async def register(self, path: Path, source: str, actor: UUID, correlation: UUID,
                       parent_id: UUID | None = None) -> str:
        # Only backend-created files can call this method; no HTTP registration by path.
        try:
            relative = path.relative_to(self.root).as_posix()
        except ValueError:
            raise FileDenied("File reference denied") from None
        checked = controlled_path(relative, self.root)
        digest = await asyncio.to_thread(file_digest, checked)
        file_id = uuid4()
        async with self.pool.connection() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO public.seg_files(id,source,relative_path,uploaded_by,sha256,parent_id) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (file_id, source, relative, actor, digest, parent_id))
            # Catalog visibility and audit are committed together, never best effort.
            await self.audit._audit(conn, actor, "file_derived" if parent_id else "file_upload",
                                    "SUCCESS", correlation, "file", str(file_id))
        return str(file_id)

    async def resolve(self, reference: str, principal) -> str:
        try:
            file_id = UUID(reference)
        except (ValueError, TypeError, AttributeError):
            raise FileDenied("File reference denied") from None
        async with self.pool.connection() as conn, conn.transaction():
            row = await (await conn.execute(
                "SELECT relative_path,sha256 FROM public.seg_files "
                "WHERE id=%s AND status='AVAILABLE' AND (uploaded_by=%s OR %s)",
                (file_id, principal.id, principal.role == "ADMINISTRADOR"))).fetchone()
        if not row:
            raise FileDenied("File reference denied")
        path = controlled_path(row[0], self.root)
        if await asyncio.to_thread(file_digest, path) != row[1]:
            raise FileDenied("File reference denied")
        return path.as_uri()
