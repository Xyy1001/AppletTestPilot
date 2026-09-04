"""
Thread-safe event stream for the Agent Web UI.

Each Agent step produces a sequence of typed events that the frontend
renders as structured log entries + screenshots.
"""

from __future__ import annotations

import base64
import json
import queue
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EventType(str, Enum):
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    STEP_START = "step_start"
    STEP_PAUSED = "step_paused"
    OBSERVE = "observe"
    PLAN = "plan"
    EXECUTE = "execute"
    ORACLE = "oracle"
    RESULT = "result"
    ERROR = "error"
    ANALYSIS = "analysis"


@dataclass
class AgentEvent:
    """A single event emitted by the Agent loop."""
    event_type: EventType
    step_index: int = 0
    timestamp: float = field(default_factory=time.perf_counter)
    message: str = ""                        # human-readable summary
    detail: dict = field(default_factory=dict)  # structured data
    screenshot_b64: str = ""                 # base64-encoded PNG

    def to_sse(self) -> str:
        data = {
            "type": self.event_type.value,
            "step": self.step_index,
            "ts": self.timestamp,
            "msg": self.message,
            "detail": self.detail,
            "screenshot": self.screenshot_b64,
        }
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


class EventStream:
    """Thread-safe queue-based event stream for SSE delivery."""

    def __init__(self, maxsize: int = 500):
        self._queue: queue.Queue[AgentEvent | None] = queue.Queue(maxsize=maxsize)
        self._lock = threading.Lock()
        self._closed = False

    def emit(self, event: AgentEvent) -> None:
        if not self._closed:
            self._queue.put(event)

    def close(self) -> None:
        with self._lock:
            self._closed = True
        self._queue.put(None)  # sentinel

    def __iter__(self):
        return self

    def __next__(self) -> AgentEvent:
        event = self._queue.get()
        if event is None:
            raise StopIteration
        return event


# ── singleton stream ──
_stream: Optional[EventStream] = None
_stream_lock = threading.Lock()


def get_event_stream() -> EventStream:
    global _stream
    with _stream_lock:
        if _stream is None or _stream._closed:
            _stream = EventStream()
        return _stream
