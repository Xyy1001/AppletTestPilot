"""
Failure Analyzer — multi-signal root-cause attribution for Agent failures.

Fuses: console logs + screenshot + UI tree + action history + LLM reasoning
to produce a structured ``FailureReport``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from .state import GUIState
from .memory import AgentMemory
from .action import Action

logger = logging.getLogger(__name__)


class BugCategory(str, Enum):
    NAVIGATION_FAILURE = "navigation_failure"
    STATE_INCONSISTENCY = "state_inconsistency"
    UI_MISSING = "ui_missing"
    UNAUTHORIZED_TRANSITION = "unauthorized_transition"
    PAYMENT_ANOMALY = "payment_anomaly"
    DATA_CORRUPTION = "data_corruption"
    TIMEOUT = "timeout"
    CRASH = "crash"
    UNKNOWN = "unknown"


@dataclass
class FailureReport:
    """Structured analysis of a single test failure."""
    step_index: int
    action: str
    page_route: str
    category: BugCategory = BugCategory.UNKNOWN
    severity: str = "medium"          # "low" | "medium" | "high" | "critical"
    signals: dict = field(default_factory=dict)
    root_cause_hypothesis: str = ""
    recommendation: str = ""


class FailureAnalyzer:
    """Multi-signal failure attribution engine."""

    def analyze(self, state: GUIState, action: Action,
                error: str, memory: AgentMemory) -> FailureReport:
        """Fuse all available signals to classify the failure.

        Signals considered:
          1. Error message text (pattern matching)
          2. Page semantic role and risk level
          3. Action type
          4. History of this page/action (from memory)
          5. Console / network logs (if available)
        """
        signals: dict = {
            "error": error[:300],
            "action_type": action.action_type.value,
            "page_role": state.page.semantic_role,
            "page_risk": state.page.risk_level,
            "step_index": state.step_index,
            "has_console_errors": any("error" in l.lower() for l in state.console_logs) if state.console_logs else False,
        }

        category = self._classify(error, state, action, memory)
        severity = self._assess_severity(category, state)
        hypothesis = self._build_hypothesis(category, error, state, action)
        recommendation = self._recommend(category, state, action)

        return FailureReport(
            step_index=state.step_index,
            action=action.to_nl(),
            page_route=state.page.route,
            category=category,
            severity=severity,
            signals=signals,
            root_cause_hypothesis=hypothesis,
            recommendation=recommendation,
        )

    # ── classification ─────────────────────────────────────────────────

    def _classify(self, error: str, state: GUIState, action: Action,
                  memory: AgentMemory) -> BugCategory:
        msg = error.lower()

        if any(k in msg for k in ("timeout", "timed out")):
            return BugCategory.TIMEOUT
        if any(k in msg for k in ("crash", "sys.", "fatal")):
            return BugCategory.CRASH
        if any(k in msg for k in ("navigate", "page id", "route")):
            return BugCategory.NAVIGATION_FAILURE
        if any(k in msg for k in ("assert", "expected", "inconsist")):
            return BugCategory.STATE_INCONSISTENCY
        if any(k in msg for k in ("element", "找不到", "not found", "not visible")):
            return BugCategory.UI_MISSING
        if any(k in msg for k in ("unauthorized", "permission", "login")):
            return BugCategory.UNAUTHORIZED_TRANSITION

        # Page-context heuristics
        if state.page.risk_level == "high" and action.action_type.value in ("click", "long_press"):
            return BugCategory.DATA_CORRUPTION

        return BugCategory.UNKNOWN

    def _assess_severity(self, category: BugCategory, state: GUIState) -> str:
        if category == BugCategory.CRASH:
            return "critical"
        if state.page.risk_level == "high":
            return "high"
        if category in (BugCategory.NAVIGATION_FAILURE, BugCategory.DATA_CORRUPTION):
            return "high"
        if category in (BugCategory.STATE_INCONSISTENCY, BugCategory.TIMEOUT):
            return "medium"
        return "low"

    def _build_hypothesis(self, category: BugCategory, error: str,
                          state: GUIState, action: Action) -> str:
        if category == BugCategory.NAVIGATION_FAILURE:
            return f"Navigation from '{state.page.route}' after '{action.to_nl()}' did not reach expected page"
        if category == BugCategory.STATE_INCONSISTENCY:
            return f"Page state after '{action.to_nl()}' is inconsistent with expectation"
        if category == BugCategory.UI_MISSING:
            return f"Expected UI element for '{action.to_nl()}' is missing or not visible"
        if category == BugCategory.TIMEOUT:
            return f"Operation '{action.to_nl()}' on '{state.page.route}' timed out"
        if category == BugCategory.DATA_CORRUPTION:
            return f"Storage data may have been corrupted during '{action.to_nl()}'"
        return f"Unexpected failure during '{action.to_nl()}': {error[:150]}"

    def _recommend(self, category: BugCategory, state: GUIState, action: Action) -> str:
        if category == BugCategory.NAVIGATION_FAILURE:
            return "Verify page navigation logic and ensure target page exists"
        if category == BugCategory.UI_MISSING:
            return "Check that the element is rendered (not conditionally hidden)"
        if category == BugCategory.STATE_INCONSISTENCY:
            return "Review the action's state mutation — data may not be persisted"
        if category == BugCategory.DATA_CORRUPTION:
            return "Check storage write operations — data may be truncated or malformed"
        if category == BugCategory.TIMEOUT:
            return "Increase timeout or check for blocking operations"
        return "Re-run the step with additional logging"
