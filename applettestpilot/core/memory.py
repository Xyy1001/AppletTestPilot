"""
Agent Memory — navigation graph, transition history, and failure patterns.

The memory is the Agent's "world model" of the mini program under test.
It grows over time and guides future planning decisions.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PageNode:
    """A node in the navigation graph — one logical page."""
    route: str
    semantic_role: str = ""
    business_function: str = ""
    risk_level: str = "low"
    visit_count: int = 0
    first_seen_step: int = 0
    last_seen_step: int = 0
    screenshot_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "route": self.route,
            "semantic_role": self.semantic_role,
            "business_function": self.business_function,
            "risk_level": self.risk_level,
            "visit_count": self.visit_count,
            "first_seen_step": self.first_seen_step,
            "last_seen_step": self.last_seen_step,
        }


@dataclass
class TransitionEdge:
    """A directed edge: src_page → action → dst_page."""
    src_route: str
    dst_route: str
    action: str                          # NL action that caused the transition
    semantic_type: str = ""              # "navigate", "submit", "tab_switch", "back"
    success_count: int = 0
    failure_count: int = 0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "src": self.src_route,
            "dst": self.dst_route,
            "action": self.action,
            "semantic_type": self.semantic_type,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": round(self.success_rate, 3),
        }


@dataclass
class FailureRecord:
    """A single failure event recorded during testing."""
    step_index: int
    page_route: str
    action: str
    error_type: str                     # "assertion", "navigation", "timeout", "crash", "ui_missing"
    error_message: str
    screenshot_id: str = ""

    def to_dict(self) -> dict:
        return {
            "step": self.step_index,
            "route": self.page_route,
            "action": self.action,
            "type": self.error_type,
            "message": self.error_message[:200],
        }


class AgentMemory:
    """Accumulated knowledge across a single Agent session.

    Stores the navigation graph, transition history, failure records,
    and exploration statistics.
    """

    def __init__(self):
        # ── graph ──
        self.pages: dict[str, PageNode] = {}          # route → PageNode
        self.edges: list[TransitionEdge] = []

        # ── history ──
        self.state_sequence: list[str] = []            # ordered state_ids
        self.action_sequence: list[str] = []           # ordered NL actions
        self.visited_routes: list[str] = []            # deduped route sequence

        # ── failures ──
        self.failures: list[FailureRecord] = []
        self.failure_patterns: dict[str, int] = defaultdict(int)  # error_type → count

        # ── statistics ──
        self.total_steps: int = 0
        self.successful_steps: int = 0
        self.failed_steps: int = 0
        self.unique_pages_visited: int = 0

    # ── recording ──────────────────────────────────────────────────────

    def record_step(self, state_id: str, action: str, success: bool,
                    page_route: str = "", error: str = ""):
        """Record a completed step."""
        self.total_steps += 1
        self.state_sequence.append(state_id)
        self.action_sequence.append(action)
        if success:
            self.successful_steps += 1
        else:
            self.failed_steps += 1
            self._record_failure(action, page_route, error)

    def record_page(self, route: str, semantic_role: str = "",
                    business_function: str = "", risk_level: str = "low",
                    screenshot_id: str = ""):
        """Register a page visit."""
        if route not in self.pages:
            self.pages[route] = PageNode(
                route=route,
                semantic_role=semantic_role,
                business_function=business_function,
                risk_level=risk_level,
                first_seen_step=self.total_steps,
            )
            self.unique_pages_visited += 1
        node = self.pages[route]
        node.visit_count += 1
        node.last_seen_step = self.total_steps
        if screenshot_id:
            node.screenshot_ids.append(screenshot_id)
        if route not in self.visited_routes:
            self.visited_routes.append(route)

    def record_transition(self, src_route: str, dst_route: str, action: str,
                          success: bool = True):
        """Record a page transition (or same-page action)."""
        edge = self._find_edge(src_route, dst_route, action)
        if edge is None:
            edge = TransitionEdge(
                src_route=src_route, dst_route=dst_route, action=action,
                semantic_type=_classify_transition(action, src_route, dst_route),
            )
            self.edges.append(edge)
        if success:
            edge.success_count += 1
        else:
            edge.failure_count += 1

    # ── queries ────────────────────────────────────────────────────────

    def get_unvisited_pages(self) -> list[str]:
        """Return routes that exist as edges but haven't been visited."""
        known = set(self.pages.keys())
        targets = {e.dst_route for e in self.edges}
        return sorted(targets - known)

    def get_high_risk_pages(self) -> list[PageNode]:
        """Pages tagged as high-risk."""
        return [p for p in self.pages.values() if p.risk_level == "high"]

    def get_frequent_failures(self, min_count: int = 1) -> list[tuple[str, int]]:
        """Error types sorted by occurrence count."""
        return sorted(self.failure_patterns.items(), key=lambda x: -x[1])

    def get_exploration_progress(self) -> dict:
        """Summary of exploration coverage."""
        return {
            "total_steps": self.total_steps,
            "successful": self.successful_steps,
            "failed": self.failed_steps,
            "unique_pages": self.unique_pages_visited,
            "total_pages_known": len(self.pages),
            "total_edges": len(self.edges),
            "failure_patterns": dict(self.failure_patterns),
        }

    # ── export ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "pages": {k: v.to_dict() for k, v in self.pages.items()},
            "edges": [e.to_dict() for e in self.edges],
            "failures": [f.to_dict() for f in self.failures],
            "stats": {
                "total_steps": self.total_steps,
                "successful": self.successful_steps,
                "failed": self.failed_steps,
                "unique_pages": self.unique_pages_visited,
                "total_edges": len(self.edges),
            },
        }

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                        encoding="utf-8")

    # ── internal ───────────────────────────────────────────────────────

    def _record_failure(self, action: str, page_route: str, error: str):
        error_type = _classify_error(error)
        self.failures.append(FailureRecord(
            step_index=self.total_steps,
            page_route=page_route,
            action=action,
            error_type=error_type,
            error_message=error,
        ))
        self.failure_patterns[error_type] += 1

    def _find_edge(self, src: str, dst: str, action: str) -> TransitionEdge | None:
        for e in self.edges:
            if e.src_route == src and e.dst_route == dst and e.action == action:
                return e
        return None


# ── helpers ────────────────────────────────────────────────────────────

def _classify_transition(action: str, src: str, dst: str) -> str:
    """Categorize the semantic type of a page transition."""
    al = action.lower()
    if "back" in al:
        return "back"
    if "switch to" in al or "tab" in al:
        return "tab_switch"
    if "保存" in al or "save" in al or "提交" in al or "submit" in al:
        return "submit"
    if "删除" in al or "delete" in al or "清空" in al or "clear" in al or "remove" in al:
        return "delete"
    if src != dst:
        return "navigate"
    return "interact"


def _classify_error(error_msg: str) -> str:
    """Categorize an error message into a failure type."""
    msg = error_msg.lower()
    if any(k in msg for k in ("assertion", "assert", "expected", "expect")):
        return "assertion"
    if any(k in msg for k in ("navigate", "navigation", "page id")):
        return "navigation"
    if any(k in msg for k in ("timeout", "timed out")):
        return "timeout"
    if any(k in msg for k in ("crash", "exception", "not found")):
        return "crash"
    if any(k in msg for k in ("element", "找不到", "not visible", "clickable")):
        return "ui_missing"
    if any(k in msg for k in ("connection", "fetch", "network")):
        return "connection"
    return "unknown"
