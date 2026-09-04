"""Click/tap action strategies for WeChat Mini Programs."""

import sys
import io
import logging
from typing import Any
from contextlib import contextmanager

from .locators import (
    _extract_quoted_targets,
    _normalize_text,
    _safe_get_text,
    _find_elements_by_xpath_contains_text,
    _find_clickable_ancestor,
    _find_clickable_by_text,
)

logger = logging.getLogger(__name__)


@contextmanager
def _quiet_minium():
    _hold = sys.stderr
    sys.stderr = io.StringIO()
    try:
        yield
    finally:
        sys.stderr = _hold


def _execute_click(session: Any, action: str) -> None:
    """
    Click on a target element. Multi-level fallback:
    0. Button elements by text match
    1. XPath contains text
    2. Clickable ancestor via XPath
    3. Exhaustive element scan by text
    """
    with _quiet_minium():
        return _execute_click_impl(session, action)


def _execute_click_impl(session: Any, action: str) -> None:
    targets = _extract_quoted_targets(action)
    page = session.get_current_page()

    for target in targets:
        # Strategy 0: Find <button> elements directly
        try:
            buttons = page.get_elements("button")
            for btn in (buttons or []):
                btn_text = _normalize_text(_safe_get_text(btn)).casefold()
                target_norm = _normalize_text(target).casefold()
                if target_norm in btn_text or btn_text == target_norm:
                    logger.info(f"Clicking button '{target}'")
                    btn.click()
                    session.capture_state(prev_action=action)
                    return
        except Exception:
            pass

        # Strategy 1: XPath contains text
        xpath_hits = _find_elements_by_xpath_contains_text(page, target)
        for el in xpath_hits[:5]:
            try:
                logger.info(f"Clicking on '{target}'")
                el.click()
                session.capture_state(prev_action=action)
                return
            except Exception:
                continue

        # Strategy 2: Clickable ancestor
        ancestor = _find_clickable_ancestor(page, target)
        if ancestor is not None:
            try:
                logger.info(f"Clicking on '{target}'")
                ancestor.click()
                session.capture_state(prev_action=action)
                return
            except Exception:
                pass

        # Strategy 3: Exhaustive text match
        el = _find_clickable_by_text(page, target)
        if el is not None:
            logger.info(f"Clicking on '{target}'")
            try:
                el.click()
                session.capture_state(prev_action=action)
                return
            except Exception as e:
                logger.warning(f"Click failed for target '{target}': {e}")
                continue

    if targets:
        raise RuntimeError(f"Could not find a clickable target for action: {action}")
