# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/services/wizard_engine.py

from __future__ import annotations

from datetime import datetime, date
from typing import Any, Dict, List, Tuple

STEP_ORDER = ["SCOPE", "MONTHS", "WINDOW", "SUMMARY"]
STEP_TITLES = {
    "SCOPE": "Alcance",
    "MONTHS": "Meses",
    "WINDOW": "Ventana",
    "SUMMARY": "Resumen",
}

WINDOW_DAYS_MIN = 1
WINDOW_DAYS_MAX = 365
DEFAULT_WINDOW_DAYS = 5


def normalize_window_days(value: Any, fallback: int | None = None) -> int:
    if fallback is None:
        fallback = DEFAULT_WINDOW_DAYS
    try:
        window_days = int(value)
    except Exception:
        window_days = fallback
    if window_days < WINDOW_DAYS_MIN:
        return WINDOW_DAYS_MIN
    if window_days > WINDOW_DAYS_MAX:
        return WINDOW_DAYS_MAX
    return window_days


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _add_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _months_in_range(date_range: List[str]) -> List[str]:
    if not date_range or len(date_range) < 2:
        return []
    start = _month_start(_parse_date(date_range[0]))
    end = _month_start(_parse_date(date_range[1]))
    out: List[str] = []
    cur = start
    while cur <= end:
        out.append(f"{cur.year:04d}-{cur.month:02d}")
        cur = _add_month(cur)
    return out


def _month_items(preview: Dict[str, Any], selected: List[str]) -> List[Dict[str, Any]]:
    missing = set(preview.get("missing_months") or [])
    partial_list = preview.get("partial_months") or []
    partial = {item.get("month"): item for item in partial_list if item.get("month")}
    items = []
    for month in _months_in_range(preview.get("range") or []):
        if month in missing:
            items.append({
                "id": month,
                "month": month,
                "status": "missing",
                "selectable": False,
                "selected": False,
            })
            continue
        if month in partial:
            items.append({
                "id": month,
                "month": month,
                "status": "partial",
                "selectable": True,
                "selected": month in selected,
                "missing_days": partial[month].get("missing_days") or [],
            })
            continue
        items.append({
            "id": month,
            "month": month,
            "status": "ok",
            "selectable": True,
            "selected": month in selected,
        })
    return items


def _available_months(preview: Dict[str, Any]) -> List[str]:
    return [item["month"] for item in _month_items(preview, []) if item["selectable"]]


def _ok_months(preview: Dict[str, Any]) -> List[str]:
    return [item["month"] for item in _month_items(preview, []) if item["status"] == "ok"]


def _partial_months(preview: Dict[str, Any]) -> List[str]:
    return [item.get("month") for item in preview.get("partial_months") or [] if item.get("month")]


def _event(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": event_type, "payload": payload}


def _wizard_state_event(state: Dict[str, Any]) -> Dict[str, Any]:
    return _event("WIZARD_STATE_SET", state)


def _alert_events(preview: Dict[str, Any]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    outliers = preview.get("outliers") or []
    partial = preview.get("partial_months") or []
    if outliers or partial:
        events.append(_event("ALERT_ADD", {
            "level": "warning",
            "title": "Datos incompletos",
            "message": "Hay meses parciales u outliers detectados. Revisar antes de continuar.",
        }))
    return events


def _scope_form(state: Dict[str, Any]) -> Dict[str, Any]:
    scope_mode = state["selection"].get("scope_mode")
    return {
        "id": "scope_form",
        "title": "Elegi el alcance",
        "fields": [
            {
                "name": "scope_mode",
                "type": "radio",
                "options": [
                    {"label": "Recomendado", "value": "RECOMMENDED"},
                    {"label": "Manual", "value": "MANUAL"},
                    {"label": "Todo", "value": "ALL"},
                ],
                "value": scope_mode,
            }
        ],
        "actions": {
            "next": {"enabled": scope_mode is not None},
        },
    }


def _window_form(state: Dict[str, Any]) -> Dict[str, Any]:
    window_days = normalize_window_days(state["selection"].get("window_days"))
    return {
        "id": "window_form",
        "title": "Ventana maxima de dias",
        "fields": [
            {
                "name": "window_days",
                "type": "slider",
                "min": WINDOW_DAYS_MIN,
                "max": WINDOW_DAYS_MAX,
                "step": 1,
                "value": window_days,
            }
        ],
        "actions": {
            "next": {"enabled": True},
            "back": {"enabled": True},
        },
    }


def _summary_form(state: Dict[str, Any], preview: Dict[str, Any]) -> Dict[str, Any]:
    warnings = []
    missing = preview.get("missing_months") or []
    partial = preview.get("partial_months") or []
    outliers = preview.get("outliers") or []
    if missing:
        warnings.append(f"Meses faltantes: {', '.join(missing)}")
    if partial:
        warnings.append(f"Meses parciales: {', '.join([p.get('month') for p in partial if p.get('month')])}")
    if outliers:
        warnings.append("Outliers detectados en fechas de archivos.")
    return {
        "id": "summary_form",
        "title": "Resumen",
        "fields": [
            {"name": "months", "type": "list", "value": state["selection"].get("months") or [], "readonly": True},
            {"name": "window_days", "type": "number", "value": state["selection"].get("window_days"), "readonly": True},
            {"name": "window_range", "type": "text", "value": state["selection"].get("window_range"), "readonly": True},
            {"name": "range", "type": "text", "value": preview.get("range") or [], "readonly": True},
            {"name": "files_count", "type": "number", "value": len(preview.get("files") or []), "readonly": True},
            {"name": "warnings", "type": "list", "value": warnings, "readonly": True},
        ],
        "actions": {
            "back": {"enabled": True},
            "execute": {"enabled": True},
        },
    }


def _step_events(state: Dict[str, Any], preview: Dict[str, Any]) -> List[Dict[str, Any]]:
    step = state["step"]
    events: List[Dict[str, Any]] = []
    events.append(_event("STEP_SET", {"step_id": step, "title": STEP_TITLES.get(step, step)}))
    if step == "SCOPE":
        events.append(_event("TEXT_MESSAGE_ADD", {"role": "assistant", "text": "Elegi el alcance para conciliar."}))
        events.extend(_alert_events(preview))
        events.append(_event("FORM_SNAPSHOT", {"step": step, "form": _scope_form(state)}))
    elif step == "MONTHS":
        events.append(_event("TEXT_MESSAGE_ADD", {"role": "assistant", "text": "Selecciona los meses a conciliar."}))
        items = _month_items(preview, state["selection"].get("months") or [])
        events.append(_event("LIST_SNAPSHOT", {"step": step, "items": items}))
    elif step == "WINDOW":
        events.append(_event("TEXT_MESSAGE_ADD", {"role": "assistant", "text": "Ajusta la ventana maxima de dias."}))
        events.append(_event("FORM_SNAPSHOT", {"step": step, "form": _window_form(state)}))
    elif step == "SUMMARY":
        events.append(_event("TEXT_MESSAGE_ADD", {"role": "assistant", "text": "Revisa el resumen antes de confirmar."}))
        events.append(_event("FORM_SNAPSHOT", {"step": step, "form": _summary_form(state, preview)}))
    return events


def build_step_events(state: Dict[str, Any], preview: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _step_events(state, preview)


def build_state_event(state: Dict[str, Any]) -> Dict[str, Any]:
    return _wizard_state_event(state)


def init_state(context: Dict[str, Any], preview: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "step": "SCOPE",
        "context": {
            "bank": context.get("bank"),
            "account": context.get("account"),
            "dataset_ref": context.get("dataset_ref"),
            "preview": preview,
        },
        "selection": {
            "scope_mode": "ALL",
            "months": [],
            "window_days": DEFAULT_WINDOW_DAYS,
            "window_range": None,
            "confirmations": {"all": False, "partial": False},
            "pending_confirmation": None,
        },
    }


def initial_events(run_id: str, state: Dict[str, Any], preview: Dict[str, Any]) -> List[Dict[str, Any]]:
    events = [_event("RUN_STARTED", {"run_id": run_id})]
    events.append(_wizard_state_event(state))
    events.extend(_step_events(state, preview))
    return events


def apply_action(
    state: Dict[str, Any],
    action_type: str,
    payload: Dict[str, Any],
    preview: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    events: List[Dict[str, Any]] = []
    selection = state.get("selection") or {}
    confirmations = selection.setdefault("confirmations", {"all": False, "partial": False})
    pending = selection.get("pending_confirmation")

    def commit_step_events() -> None:
        events.append(_wizard_state_event(state))
        events.extend(_step_events(state, preview))

    if action_type == "FORM_UPDATE":
        if state["step"] == "SCOPE":
            scope_mode = payload.get("scope_mode")
            if scope_mode in {"RECOMMENDED", "MANUAL", "ALL"}:
                selection["scope_mode"] = scope_mode
                events.append(_wizard_state_event(state))
                events.append(_event("FORM_SNAPSHOT", {"step": "SCOPE", "form": _scope_form(state)}))
        elif state["step"] == "WINDOW":
            window_days = normalize_window_days(payload.get("window_days"), selection.get("window_days"))
            selection["window_days"] = window_days
            events.append(_wizard_state_event(state))
            events.append(_event("FORM_SNAPSHOT", {"step": "WINDOW", "form": _window_form(state)}))
        return state, events

    if action_type == "LIST_SELECT":
        if state["step"] == "MONTHS":
            months = payload.get("months") or []
            selectable = set(_available_months(preview))
            selection["months"] = [m for m in months if m in selectable]
            events.append(_wizard_state_event(state))
            items = _month_items(preview, selection.get("months") or [])
            events.append(_event("LIST_SNAPSHOT", {"step": "MONTHS", "items": items}))
        return state, events

    if action_type == "CONFIRM":
        kind = payload.get("kind")
        if pending != kind:
            return state, events
        if kind == "all":
            confirmations["all"] = True
            selection["pending_confirmation"] = None
            selection["months"] = _available_months(preview)
            state["step"] = "MONTHS"
            commit_step_events()
        elif kind == "partial":
            confirmations["partial"] = True
            selection["pending_confirmation"] = None
            state["step"] = "WINDOW"
            commit_step_events()
        return state, events

    if action_type == "CLICK":
        action_id = payload.get("id")
        if action_id == "back":
            idx = STEP_ORDER.index(state["step"])
            if idx > 0:
                state["step"] = STEP_ORDER[idx - 1]
                commit_step_events()
            return state, events
        if action_id == "next":
            if state["step"] == "SCOPE":
                scope_mode = selection.get("scope_mode")
                if scope_mode == "ALL" and not confirmations.get("all"):
                    selection["pending_confirmation"] = "all"
                    events.append(_wizard_state_event(state))
                    events.append(_event("CONFIRMATION_REQUIRED", {
                        "kind": "all",
                        "message": "Vas a incluir meses parciales. Confirmas continuar?",
                    }))
                    return state, events
                if scope_mode == "RECOMMENDED":
                    selection["months"] = _ok_months(preview)
                elif scope_mode == "ALL":
                    selection["months"] = _available_months(preview)
                else:
                    selection["months"] = selection.get("months") or []
                state["step"] = "MONTHS"
                commit_step_events()
                return state, events
            if state["step"] == "MONTHS":
                months = selection.get("months") or []
                if not months:
                    events.append(_event("TEXT_MESSAGE_ADD", {
                        "role": "assistant",
                        "text": "Selecciona al menos un mes para continuar.",
                    }))
                    return state, events
                has_partial = any(m in _partial_months(preview) for m in months)
                if has_partial and not confirmations.get("partial"):
                    selection["pending_confirmation"] = "partial"
                    events.append(_wizard_state_event(state))
                    events.append(_event("CONFIRMATION_REQUIRED", {
                        "kind": "partial",
                        "message": "Seleccionaste meses parciales. Confirmas continuar?",
                    }))
                    return state, events
                state["step"] = "WINDOW"
                commit_step_events()
                return state, events
            if state["step"] == "WINDOW":
                state["step"] = "SUMMARY"
                commit_step_events()
                return state, events
            return state, events
        if action_id == "execute" and state["step"] == "SUMMARY":
            events.append(_event("TEXT_MESSAGE_ADD", {
                "role": "assistant",
                "text": "Plan listo. Podes ejecutar la conciliacion cuando quieras.",
            }))
            events.append(_event("RUN_READY_TO_EXECUTE", {"ready": True}))
        return state, events

    return state, events
