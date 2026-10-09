from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from threading import Lock
from time import time
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class WizardEvent:
    event_id: str
    type: str
    payload: Dict[str, Any]


@dataclass
class WizardRun:
    run_id: str
    params: Dict[str, Any] = field(default_factory=dict)
    state: Optional[Dict[str, Any]] = None
    events: List[WizardEvent] = field(default_factory=list)
    created_at: float = field(default_factory=time)


_RUNS: dict[str, WizardRun] = {}
_LOCK = Lock()


def create_memory_run(params: Dict[str, Any] | None = None, *, run_id: str | None = None) -> str:
    run_id = run_id or str(uuid4())
    with _LOCK:
        _RUNS[run_id] = WizardRun(run_id=run_id, params=deepcopy(params or {}))
    return run_id


def memory_run_owner(run_id: str) -> str | None:
    with _LOCK:
        run = _RUNS.get(run_id)
        return run.params.get('actor_id') if run else None


def has_memory_run(run_id: str) -> bool:
    with _LOCK:
        return run_id in _RUNS


def get_memory_state(run_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        run = _RUNS.get(run_id)
        return deepcopy(run.state) if run and run.state else None


def list_memory_events(run_id: str) -> List[WizardEvent]:
    with _LOCK:
        run = _RUNS.get(run_id)
        return deepcopy(run.events) if run else []


def append_memory_events(run_id: str, events: List[Dict[str, Any]]) -> None:
    with _LOCK:
        run = _RUNS.get(run_id)
        if not run:
            return
        for event in events:
            payload = deepcopy(event.get("payload") or {})
            evt = WizardEvent(
                event_id=str(uuid4()),
                type=str(event["type"]),
                payload=payload,
            )
            run.events.append(evt)
            if evt.type == "WIZARD_STATE_SET":
                run.state = deepcopy(payload)
