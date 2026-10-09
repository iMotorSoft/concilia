"""Isolated V2 DEV configuration. Does not import the legacy facade."""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DevDatabase:
    user: str
    password: str = field(repr=False)
    dbname: str = "concilia_fce"
    host: str = "127.0.0.1"
    port: int = 5432

    def kwargs(self) -> dict:
        if self.host != "127.0.0.1" or self.port != 5432:
            raise ValueError("V2 provisioning is restricted to authorized DEV loopback:5432")
        if self.dbname not in ("postgres", "concilia_fce"):
            raise ValueError("Database outside V2 provisioning scope")
        return dict(host=self.host, port=self.port, dbname=self.dbname,
                    user=self.user, password=self.password, connect_timeout=5)


@dataclass(frozen=True)
class HttpSecurity:
    secret_path: Path
    origins: tuple[str, ...]
    secure_cookies: bool


def http_security() -> HttpSecurity:
    # This configuration is DEV-only. HTTP cookies are allowed only on loopback.
    origins = tuple(os.environ.get("CONCILIA_AUTH_ORIGINS",
        "http://127.0.0.1:3058,http://localhost:3058").split(","))
    from urllib.parse import urlparse
    for origin in origins:
        parsed = urlparse(origin)
        if (parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost"}
                or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("SEG-01 HTTP configuration is restricted to DEV loopback origins")
    return HttpSecurity(
        Path(os.environ.get("CONCILIA_AUTH_SECRET_FILE", str(
            Path(__file__).resolve().parents[3] / "storage/v2-dev/technical-credentials.json"))),
        origins, all(origin.startswith("https://") for origin in origins))


def e2e_credentials() -> tuple[str, str] | None:
    email = os.environ.get("CONCILIA_E2E_ADMIN_EMAIL")
    password = os.environ.get("CONCILIA_E2E_ADMIN_PASSWORD")
    if bool(email) != bool(password):
        raise ValueError("Both E2E credentials are required")
    return (email, password) if email and password else None


def administrative_database() -> DevDatabase:
    # Explicitly authorized initial provisioning only, never runtime.
    host = os.environ.get("DB_PG_IP")
    port = os.environ.get("DB_PG_PORT")
    if host not in ("localhost", "127.0.0.1") or port != "5432":
        raise ValueError("Administrative configuration must explicitly target DEV loopback:5432")
    user = os.environ.get("DB_PG_USER")
    password = os.environ.get("DB_PG_PASS")
    if not user or not password:
        raise ValueError("Administrative credentials missing")
    return DevDatabase(user=user, password=password, dbname="postgres")


def runtime_pool(path: Path):
    from psycopg_pool import AsyncConnectionPool
    config = credentials(path, "concilia_app")
    return AsyncConnectionPool(kwargs=config.kwargs(), min_size=2, max_size=10, open=False)


def credentials(path: Path, role: str) -> DevDatabase:
    if role not in ("concilia_owner", "concilia_app"):
        raise ValueError("Unknown V2 technical role")
    if path.is_symlink():
        raise ValueError("Secret file must not be a symlink")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
        raise ValueError("Secret file must be owned by current user with mode 0600")
    data = json.loads(path.read_text())
    if set(data) != {"concilia_owner", "concilia_app"}:
        raise ValueError("Unexpected secret file contents")
    password = data[role]
    if not isinstance(password, str) or len(password) < 32:
        raise ValueError("Invalid technical credential")
    return DevDatabase(user=role, password=password)
