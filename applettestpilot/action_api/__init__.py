"""
Action execution layer for WeChat Mini Programs.
Dispatches natural language actions to appropriate handlers.
"""

import logging
from typing import Any

from .navigation import _switch_to_tab, _navigate_back
from .click import _execute_click
from .input import _execute_type
from .scroll import _execute_scroll
from .locators import _extract_quoted_targets

logger = logging.getLogger(__name__)


def execute_action(session: Any, action: str) -> None:
    """
    Execute a natural language action on the WeChat Mini Program.
    """
    action_lower = action.lower()
    targets = _extract_quoted_targets(action)

    # Re-sync page to avoid stale connection issues
    try:
        current_page = session._get_current_page()
        if current_page is not None:
            session._page = current_page
            session.page._page = current_page
    except Exception:
        pass

    # No-op actions: just capture state for assertion verification
    if any(kw in action_lower for kw in ("wait", "verify", "check", "assert", "observe")):
        session.capture_state(prev_action=action)
        return

    # Back navigation
    if any(kw in action_lower for kw in ("go back", "navigate back", "swipe back", "return")):
        _navigate_back(session, action)
        return

    # Tab switching
    if any(kw in action_lower for kw in ("switch to", "switch tab", "go to tab", "goto", "go to",
                                          "navigate to tab")):
        target = targets[0] if targets else None
        if target:
            _switch_to_tab(session, target, action)
            return

    # Click / tap
    if "click" in action_lower or "tap" in action_lower:
        _execute_click(session, action)
        return

    # Type / input
    if any(kw in action_lower for kw in ("type", "input", "输入", "填入", "填写")):
        _execute_type(session, action)
        return

    # Scroll / swipe
    if any(kw in action_lower for kw in ("scroll", "swipe", "滑动", "滚动", "翻页")):
        _execute_scroll(session, action)
        return

    raise RuntimeError(f"Action failed or not implemented: {action}")
