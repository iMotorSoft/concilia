# -*- coding: utf-8 -*-
# concilia / globalVar.py

from __future__ import annotations
import os
from pathlib import Path
from typing import Literal, Optional

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
DB_URL: str = os.environ.get("CONCIAI_DB_URL", "postgresql+psycopg://user:pass@localhost:5432/concilia_fce")
DB_SCHEMA: str = os.environ.get("CONCIAI_DB_SCHEMA", "public")
ENABLE_PG_TRGM: bool = True
ENABLE_PG_VECTOR: bool = True

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
    Path(DATA_ROOT, DATA_REPORTS).mkdir(parents=True, exist_ok=True)

def is_prod() -> bool:
    return RUN_ENV == "prod"

def mask(value: Optional[str], visible: int = 4) -> str:
    if not value:
        return ""
    return value[:visible] + "****"

def boot_log() -> None:
    print(f"[{APP_NAME}] env={RUN_ENV} debug={DEBUG} log={LOG_LEVEL}")
    print(f"[{APP_NAME}] db={DB_URL}")
    print(f"[{APP_NAME}] storage_provider={STORAGE_PROVIDER} local_root={STORAGE_LOCAL_ROOT}")
    print(f"[{APP_NAME}] data_root={DATA_ROOT}")
    print(f"[{APP_NAME}] rules_dir={RULES_DIR}")
    print(f"[{APP_NAME}] mlflow={MLFLOW_TRACKING_URI}")
    print(f"[{APP_NAME}] openai_key={mask(OpenAI_Key)} model={OpenAI_Model}")
