"""SEG-01 primitives; no HTTP bypasses or legacy roles."""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from uuid import UUID

from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError, InvalidHashError

HASHER = PasswordHasher(type=Type.ID)
ROLES = {
    "CONSULTA": frozenset({"view", "export"}),
    "OPERADOR": frozenset({"view", "export", "upload", "reconcile", "manual", "accept_difference", "complement"}),
    "ADMINISTRADOR": frozenset({"view", "export", "upload", "reconcile", "manual", "accept_difference", "complement", "users", "exercise", "reverse", "parameters"}),
}


def password_hash(password: str) -> str:
    if len(password) < 12 or len(password) > 1024:
        raise ValueError("Password must contain between 12 and 1024 characters")
    return HASHER.hash(password)


def verify_password(encoded: str, password: str) -> bool:
    if len(password) > 1024:
        return False
    try:
        return HASHER.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def valid_csrf(expected_hash: bytes, cookie: str, header: str) -> bool:
    return bool(cookie and header and hmac.compare_digest(cookie, header)
                and hmac.compare_digest(expected_hash, token_hash(header)))


@dataclass(frozen=True)
class Principal:
    id: UUID
    email: str
    role: str
    csrf_hash: bytes = field(repr=False)

    def allows(self, capability: str) -> bool:
        return capability in ROLES.get(self.role, frozenset())
