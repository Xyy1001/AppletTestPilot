"""
Action Space — formal definitions of every action the Agent can take.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ActionType(str, Enum):
    CLICK = "click"
    INPUT = "input"
    SCROLL = "scroll"
    BACK = "back"
    SWITCH_TAB = "switch_tab"
    WAIT = "wait"
    VERIFY = "verify"
    LONG_PRESS = "long_press"
    DONE = "done"               # Agent signals task complete


@dataclass
class Action:
    """A single executable action proposed by the Planner.

    This is the *intent* — the Executor grounds it to Minium calls.
    """
    action_type: ActionType
    target: str = ""             # button text / field label / tab name / scroll direction
    input_text: str = ""         # only for INPUT type
    confidence: float = 1.0      # planner confidence [0, 1]
    reasoning: str = ""          # brief explanation from the planner
    expected_outcome: str = ""   # what the planner expects after execution

    def to_nl(self) -> str:
        """Convert to a natural-language action string (legacy format)."""
        t = self.action_type
        if t == ActionType.CLICK:
            return f"Click '{self.target}'"
        if t == ActionType.INPUT:
            return f"Type '{self.input_text}' into '{self.target}'"
        if t == ActionType.SCROLL:
            return f"Scroll {self.target or 'down'}"
        if t == ActionType.BACK:
            return "Go back"
        if t == ActionType.SWITCH_TAB:
            return f"Switch to '{self.target}'"
        if t == ActionType.WAIT:
            return f"Wait {self.target or '0.5'} seconds"
        if t == ActionType.VERIFY:
            return "Verify page state"
        if t == ActionType.LONG_PRESS:
            return f"Long press '{self.target}'"
        return str(t.value)

    def to_dict(self) -> dict:
        return {
            "type": self.action_type.value,
            "target": self.target,
            "text": self.input_text,
        }


# ── Action Space definitions per page role ─────────────────────────────

# Generic actions available on most pages
BASE_ACTIONS = [
    ActionType.SCROLL,
    ActionType.WAIT,
    ActionType.VERIFY,
    ActionType.BACK,
]

# Page-specific action whitelists (for constraining LLM plans)
PAGE_ACTION_MAP: dict[str, list[ActionType]] = {
    "home":              [ActionType.CLICK, ActionType.SCROLL, ActionType.SWITCH_TAB, ActionType.WAIT, ActionType.VERIFY],
    "form":              [ActionType.CLICK, ActionType.INPUT, ActionType.SCROLL, ActionType.BACK, ActionType.WAIT, ActionType.VERIFY],
    "detail":            [ActionType.CLICK, ActionType.SCROLL, ActionType.BACK, ActionType.LONG_PRESS, ActionType.WAIT, ActionType.VERIFY],
    "cart":              [ActionType.CLICK, ActionType.SCROLL, ActionType.SWITCH_TAB, ActionType.LONG_PRESS, ActionType.WAIT, ActionType.VERIFY],
    "profile":           [ActionType.CLICK, ActionType.SCROLL, ActionType.SWITCH_TAB, ActionType.WAIT, ActionType.VERIFY],
    "modal":             [ActionType.CLICK, ActionType.BACK, ActionType.WAIT, ActionType.VERIFY],
}
