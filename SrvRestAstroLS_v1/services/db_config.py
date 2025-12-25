# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/services/db_config.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from globalVar import DB_SCHEMA as GLOBAL_DB_SCHEMA
from globalVar import DB_URL as GLOBAL_DB_URL

DB_URL = GLOBAL_DB_URL
DB_SCHEMA = GLOBAL_DB_SCHEMA

_LOGGED = False


@dataclass(frozen=True)
class DbUrlInfo:
    host: str | None
    port: str | None
    user: str | None
    dbname: str | None


def _split_userinfo(netloc: str) -> tuple[str | None, str]:
    if "@" in netloc:
        userinfo, hostinfo = netloc.rsplit("@", 1)
        return userinfo, hostinfo
    return None, netloc


def _split_hostinfo(hostinfo: str) -> tuple[str | None, str | None, bool]:
    if not hostinfo:
        return None, None, False
    if hostinfo.startswith("["):
        end = hostinfo.find("]")
        if end != -1:
            host = hostinfo[1:end]
            rest = hostinfo[end + 1 :]
            port = rest[1:] if rest.startswith(":") else None
            return host, port, True
    if ":" in hostinfo:
        host, port = hostinfo.split(":", 1)
        return host, port, False
    return hostinfo, None, False


def _build_hostinfo(host: str | None, port: str | None, is_ipv6: bool) -> str:
    if not host:
        return ""
    host_part = f"[{host}]" if is_ipv6 and ":" in host else host
    if port:
        return f"{host_part}:{port}"
    return host_part


def normalize_db_url(url: str) -> str:
    if not url:
        return url
    if "://" not in url:
        return url.replace("host=localhost", "host=127.0.0.1")
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme.startswith("postgresql+"):
        scheme = "postgresql"
    elif scheme == "postgres":
        scheme = "postgresql"
    netloc = parts.netloc
    if netloc:
        userinfo, hostinfo = _split_userinfo(netloc)
        host, port, is_ipv6 = _split_hostinfo(hostinfo)
        if host == "localhost":
            host = "127.0.0.1"
        hostinfo_new = _build_hostinfo(host, port, is_ipv6)
        if userinfo:
            netloc = f"{userinfo}@{hostinfo_new}"
        else:
            netloc = hostinfo_new
    return urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment))


def _parse_user(userinfo: str | None) -> str | None:
    if not userinfo:
        return None
    if ":" in userinfo:
        user, _password = userinfo.split(":", 1)
        return user
    return userinfo


def parse_db_url(url: str) -> DbUrlInfo:
    if not url or "://" not in url:
        return DbUrlInfo(host=None, port=None, user=None, dbname=None)
    parts = urlsplit(url)
    userinfo, hostinfo = _split_userinfo(parts.netloc)
    host, port, _is_ipv6 = _split_hostinfo(hostinfo)
    dbname = parts.path.lstrip("/") if parts.path else None
    return DbUrlInfo(
        host=host or None,
        port=port or None,
        user=_parse_user(userinfo),
        dbname=dbname or None,
    )


def log_db_config_once(logger: logging.Logger | None = None) -> None:
    global _LOGGED
    if _LOGGED:
        return
    _LOGGED = True
    logger = logger or logging.getLogger(__name__)
    normalized_url = normalize_db_url(DB_URL)
    raw_info = parse_db_url(DB_URL)
    norm_info = parse_db_url(normalized_url)
    logger.info(
        "DB config: host=%s port=%s db=%s user=%s schema=%s db_host_normalized=%s",
        raw_info.host or "",
        raw_info.port or "",
        raw_info.dbname or "",
        raw_info.user or "",
        DB_SCHEMA,
        norm_info.host or "",
    )
