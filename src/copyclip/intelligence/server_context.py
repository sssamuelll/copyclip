from dataclasses import dataclass
from typing import Any


@dataclass
class ServerContext:
    root: str
    html: str
    events: list[dict[str, Any]]
    events_lock: Any
    next_event_id: dict[str, int]
    scheduler_state: dict[str, Any]
    analysis_lock: Any
    cancel_lock: Any
    cancel_events: dict[str, Any]
