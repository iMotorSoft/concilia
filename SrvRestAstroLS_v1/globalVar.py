# -*- coding: utf-8 -*-
# concilia / globalVar.py

from __future__ import annotations
import os
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlsplit, urlunsplit

# =========================
# App / entorno
# =========================
APP_NAME: str = "concilia"
RUN_ENV: Literal["dev", "stg", "prod"] = "dev"

# NO usamos pruebas en este proyecto
ENABLE_PRUEBAS: bool = False
PRUEBA_NIVEL: int = 0

DEBUG: bool = RUN_ENV != "prod"
LOG_LEVEL: str = "DEBUG" if DEBUG else "INFO"

# =========================
# Servidor API
# =========================
HOST: str = "0.0.0.0"
PUERTO: int = 7058  # asegurate que el front apunte a este puerto

# =========================
# Raíces de proyecto / datos
# =========================
# Este archivo vive en: .../concilia/SrvRestAstroLS_v1/globalVar.py
PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
CONCILIA_ROOT: Path = PROJECT_ROOT  # alias

# Storage fuera del proyecto (persistencia de archivos)
STORAGE_PROVIDER: Literal["local", "s3"] = "local"
STORAGE_LOCAL_ROOT: str = (CONCILIA_ROOT / "storage").as_posix()
STORAGE_INCOMING: str = "incoming"
STORAGE_CANONICAL: str = "canonical"
STORAGE_ARCHIVES: str = "archives"

# Data para salidas operativas (reportes)
DATA_ROOT: str = (CONCILIA_ROOT / "data").as_posix()
DATA_REPORTS: str = "reports"

# Particionado sugerido para canónicos
PARTITION_ACCOUNT: str = "account"
PARTITION_PERIOD: str = "period"  # YYYY-MM

# =========================
# Base de datos
# =========================
# Formato SQLAlchemy moderno (recomendado para Alembic/psycopg3)
DB_PG_IP: str = os.environ.get("DB_PG_IP", "localhost")
DB_PG_PORT: str = os.environ.get("DB_PG_PORT", "5432")
DB_PG_USER: str = os.environ.get("DB_PG_USER", "user")
DB_PG_PASS: str = os.environ.get("DB_PG_PASS", "pass")
DB_PG_WORKFLOW_AI: str = os.environ.get("DB_PG_WORKFLOW_AI", "workflow_ai_v1")
# NO usar CONCIAI_DB_URL; canonical = DB_PG_WORKFLOW_AI.
DB_URL: str = (
    f"postgresql+psycopg://{DB_PG_USER}:{DB_PG_PASS}"
    f"@{DB_PG_IP}:{DB_PG_PORT}/{DB_PG_WORKFLOW_AI}"
)
DB_SCHEMA: str = os.environ.get("DB_SCHEMA", "public")
ENABLE_PG_TRGM: bool = True
ENABLE_PG_VECTOR: bool = True

# =========================
# Multitenancy (defaults por proyecto)
# =========================
TENANT_SLUG: str = os.environ.get("CONCIAI_TENANT_SLUG", "fce")
TENANT_NAME: str = os.environ.get("CONCIAI_TENANT_NAME", "FCE")
PROJECT_NAME: str = os.environ.get("CONCIAI_PROJECT_NAME", "concilia")
AUTO_BOOTSTRAP_TENANCY: bool = os.environ.get("CONCIAI_AUTO_BOOTSTRAP", "true").lower() == "true"
WORKSPACE_SLUG: str = os.environ.get("WORKSPACE_SLUG", "fce-concilia")

# =========================
# Telemetria (MVP)
# =========================
ENABLE_TELEMETRY: bool = os.environ.get("CONCIAI_TELEMETRY", "true").lower() == "true"
TELEMETRY_BASIC_ONLY: bool = os.environ.get("CONCIAI_TELEMETRY_BASIC", "true").lower() == "true"

# =========================
# Seguridad / Roles
# =========================
JWT_SECRET: str = os.environ.get("CONCIAI_JWT_SECRET", "change_me_dev_only")
JWT_ISSUER: str = "concilia"
JWT_AUDIENCE: str = "concilia-app"
ROLES: tuple[str, ...] = ("ADMIN", "OPERATOR", "AUDITOR", "VIEWER")

# =========================
# Features / Reglas
# =========================
FEATURE_AI: bool = False
DEFAULT_DATE_WINDOW_DAYS: int = 3
DEFAULT_ROUNDING_DECIMALS: int = 2

RULES_DIR: str = (PROJECT_ROOT / "SrvRestAstroLS_v1" / "rules").as_posix()
RULES_PROFILES_DIR: str = f"{RULES_DIR}/profiles"
RULES_RULESETS_DIR: str = f"{RULES_DIR}/rulesets"

# =========================
# LLM / OpenAI (compat)
# =========================
OpenAI_Key: Optional[str] = (
    os.environ.get("OpenAI_Key_SolFx")  # compat histórico
    or os.environ.get("OPENAI_API_KEY")
)
OpenAI_Model: str = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# =========================
# MLflow (opcional)
# =========================
MLFLOW_TRACKING_URI_DEV: str = os.environ.get(
    "MLFLOW_TRACKING_URI_DEV",
    f"file://{(PROJECT_ROOT / 'SrvRestAstroLS_v1' / 'mlruns_concilia').as_posix()}",
)
MLFLOW_TRACKING_URI_PRO: str = os.environ.get("MLFLOW_TRACKING_URI_PRO", MLFLOW_TRACKING_URI_DEV)
MLFLOW_TRACKING_URI: str = MLFLOW_TRACKING_URI_DEV if RUN_ENV != "prod" else MLFLOW_TRACKING_URI_PRO

# =========================
# Helpers
# =========================
_BOOT_LOG_DONE: bool = False
def resolve_storage_uri(
    kind: Literal["incoming", "canonical", "archives"],
    account_id: str | int | None = None,
    period: str | None = None,
    filename: str | None = None,
) -> str:
    """Construye URI file:// (local) o s3:// (si cambias el provider)."""
    if STORAGE_PROVIDER == "local":
        base = Path(STORAGE_LOCAL_ROOT) / kind
        if kind == "canonical":
            if account_id is not None:
                base = base / f"{PARTITION_ACCOUNT}={account_id}"
            if period is not None:
                base = base / f"{PARTITION_PERIOD}={period}"
        if filename:
            base = base / filename
        return f"file://{base.as_posix()}"

    # S3/MinIO (a futuro)
    bucket = os.environ.get("CONCIAI_S3_BUCKET", "concilia-bucket")
    prefix = os.environ.get("CONCIAI_S3_PREFIX", "storage")
    parts = [prefix, kind]
    if kind == "canonical":
        if account_id is not None:
            parts.append(f"{PARTITION_ACCOUNT}={account_id}")
        if period is not None:
            parts.append(f"{PARTITION_PERIOD}={period}")
    if filename:
        parts.append(filename)
    key = "/".join(parts)
    return f"s3://{bucket}/{key}"

def ensure_local_dirs() -> None:
    """Crea carpetas locales críticas (modo local)."""
    if STORAGE_PROVIDER == "local":
        for sub in (STORAGE_INCOMING, STORAGE_CANONICAL, STORAGE_ARCHIVES):
            Path(STORAGE_LOCAL_ROOT, sub).mkdir(parents=True, exist_ok=True)
    # Asegurar reports (en data/)
    Path(DATA_ROOT, DATA_REPORTS).mkdir(parents=True, exist_ok=True)

def is_prod() -> bool:
    return RUN_ENV == "prod"

def mask(value: Optional[str], visible: int = 4) -> str:
    if not value:
        return ""
    return value[:visible] + "****"

def mask_db_url(url: str) -> str:
    if "://" not in url:
        return url
    parts = urlsplit(url)
    netloc = parts.netloc
    if "@" in netloc:
        userinfo, hostinfo = netloc.rsplit("@", 1)
        if ":" in userinfo:
            user, _password = userinfo.split(":", 1)
            userinfo = f"{user}:****"
        netloc = f"{userinfo}@{hostinfo}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

def db_brief() -> str:
    ssl_mode = os.environ.get("DB_PG_SSLMODE") or os.environ.get("PGSSLMODE")
    base = (
        f"host={DB_PG_IP} port={DB_PG_PORT} "
        f"db={DB_PG_WORKFLOW_AI} schema={DB_SCHEMA} user=***"
    )
    if ssl_mode:
        return f"{base} ssl={ssl_mode}"
    return base

def boot_log() -> None:
    global _BOOT_LOG_DONE
    if _BOOT_LOG_DONE:
        return
    _BOOT_LOG_DONE = True
    print(f"[{APP_NAME}] env={RUN_ENV} debug={DEBUG} log={LOG_LEVEL}")
    print(f"[{APP_NAME}] db={db_brief()}")
    print(f"[{APP_NAME}] workspace_slug={WORKSPACE_SLUG}")
    log_db_full = os.environ.get("CONCIAI_LOG_DB_URL_FULL", "false").lower() == "true"
    if log_db_full:
        print(f"[{APP_NAME}] db_url={mask_db_url(DB_URL)}")
    print(f"[{APP_NAME}] storage_provider={STORAGE_PROVIDER} local_root={STORAGE_LOCAL_ROOT}")
    print(f"[{APP_NAME}] data_root={DATA_ROOT}")
    print(f"[{APP_NAME}] rules_dir={RULES_DIR}")
    print(f"[{APP_NAME}] mlflow={MLFLOW_TRACKING_URI}")
    print(f"[{APP_NAME}] openai_key={mask(OpenAI_Key)} model={OpenAI_Model}")
