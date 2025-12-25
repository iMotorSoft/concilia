# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/services/json_safe.py

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


def json_default(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(to_jsonable(key)): to_jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        return json_default(value)
    except TypeError:
        return str(value)
