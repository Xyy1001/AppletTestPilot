"""Scroll/swipe actions for WeChat Mini Programs."""

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
    _find_clickable_by_text,
)

logger = logging.getLogger(__name__)

_SCROLL_DELTA = 300  # px per scroll step (~half a phone screen)


@contextmanager
def _quiet_minium():
    _hold = sys.stderr
    sys.stderr = io.StringIO()
    try:
        yield
    finally:
        sys.stderr = _hold


def _execute_scroll(session: Any, action: str) -> None:
    with _quiet_minium():
        return _execute_scroll_impl(session, action)


def _execute_scroll_impl(session: Any, action: str) -> None:
    action_lower = action.lower()
    targets = _extract_quoted_targets(action)

    scroll_down = any(kw in action_lower for kw in (
        "scroll down", "向下滑动", "向下滚动", "下滑", "向下翻", "向下滚",
    ))
    scroll_up = any(kw in action_lower for kw in (
        "scroll up", "向上滑动", "向上滚动", "上滑", "向上翻", "向上滚", "scroll to top",
    ))
    scroll_to_bottom = any(kw in action_lower for kw in (
        "scroll to bottom", "滑动到底部", "滚动到底部", "滑到底部",
    ))

    # Scroll to a specific element by text
    if targets:
        _scroll_to_element(session, action, targets[0])
        return

    # Directional scroll
    mini = session.mini
    app = getattr(mini, "app", None)

    if scroll_to_bottom:
        js = "wx.pageScrollTo({scrollTop: 99999, duration: 300})"
        logger.info("Scrolling to bottom")
    elif scroll_up:
        js = "wx.pageScrollTo({scrollTop: 0, duration: 300})"
        logger.info("Scrolling to top")
    elif scroll_down:
        js = (
            "wx.createSelectorQuery().selectViewport().scrollOffset(function(res) {"
            f"var target = (res.scrollTop || 0) + {_SCROLL_DELTA};"
            "wx.pageScrollTo({scrollTop: target, duration: 300});"
            "}).exec();"
        )
        logger.info("Scrolling down %dpx", _SCROLL_DELTA)
    else:
        # Generic scroll — default to scroll down
        js = (
            "wx.createSelectorQuery().selectViewport().scrollOffset(function(res) {"
            f"var target = (res.scrollTop || 0) + {_SCROLL_DELTA};"
            "wx.pageScrollTo({scrollTop: target, duration: 300});"
            "}).exec();"
        )
        logger.info("Scrolling")

    if app and hasattr(app, "evaluate_js"):
        try:
            app.evaluate_js(js)
        except Exception as e:
            logger.debug("JS scroll failed, trying call_wx_method: %s", e)
            try:
                offset = 0 if scroll_up else 99999
                app.call_wx_method("pageScrollTo", {"scrollTop": offset, "duration": 300})
            except Exception:
                pass
    elif app and hasattr(app, "call_wx_method"):
        try:
            offset = 0 if scroll_up else 99999
            app.call_wx_method("pageScrollTo", {"scrollTop": offset, "duration": 300})
        except Exception:
            pass

    session.capture_state(prev_action=action)


def _scroll_to_element(session: Any, action: str, target: str) -> None:
    """Scroll until an element containing the target text is visible."""
    page = session.get_current_page()

    # Strategy 1: Element already on screen — scroll it into view
    el = _find_clickable_by_text(page, target)
    if el is not None:
        logger.info("Scrolling to visible element '%s'", target)
        _try_element_scroll(el)
        session.capture_state(prev_action=action)
        return

    # Strategy 2: Find via XPath
    xpath_els = _find_elements_by_xpath_contains_text(page, target)
    if xpath_els:
        logger.info("Scrolling to element '%s' via XPath", target)
        _try_element_scroll(xpath_els[0])
        session.capture_state(prev_action=action)
        return

    # Strategy 3: Element not found — scroll to bottom to reveal it
    logger.info("Scrolling to bottom to find '%s'", target)
    mini = session.mini
    app = getattr(mini, "app", None)
    if app and hasattr(app, "evaluate_js"):
        try:
            app.evaluate_js("wx.pageScrollTo({scrollTop: 99999, duration: 300})")
        except Exception:
            pass

    session.capture_state(prev_action=action)


def _try_element_scroll(el: Any) -> None:
    """Try available scroll-into-view methods on a Minium element."""
    methods = ["scroll_to", "scroll_into_view", "scrollIntoView", "scroll"]
    for method_name in methods:
        method = getattr(el, method_name, None)
        if callable(method):
            try:
                method()
                return
            except Exception:
                continue
    # Last resort: tap to bring into view (Minium auto-scrolls on tap)
    try:
        el.tap()
    except Exception:
        pass
