"""Tab switching and back navigation for WeChat Mini Programs."""

import sys
import io
import time
import logging
from typing import Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@contextmanager
def _quiet_minium():
    """Suppress stderr noise from Minium SDK 3.16.0 internal errors
    (hook_navigation callback signature mismatch, etc.)."""
    _hold = sys.stderr
    sys.stderr = io.StringIO()
    try:
        yield
    finally:
        sys.stderr = _hold

# Tab name → page path mapping (matches app.json tabBar entries)
_TAB_MAP: dict[str, str] = {
    "首页": "pages/index/index",
    "home": "pages/index/index",
    "主页": "pages/index/index",
    "购物车": "pages/cart/cart",
    "cart": "pages/cart/cart",
    "我的": "pages/tabbar/user",
    "user": "pages/tabbar/user",
    "个人中心": "pages/tabbar/user",
}


def _switch_to_tab(session: Any, target: str, action: str) -> None:
    """Navigate between tab bar pages. Tries multiple approaches."""
    with _quiet_minium():
        return _switch_to_tab_impl(session, target, action)


def _switch_to_tab_impl(session: Any, target: str, action: str) -> None:
    target_lower = target.strip().casefold()
    tab_path = None
    for key, path in _TAB_MAP.items():
        if key.casefold() == target_lower or key.casefold() in target_lower or target_lower in key.casefold():
            tab_path = path
            break

    if not tab_path:
        raise RuntimeError(
            f"Cannot find tab page for '{target}'. Known tabs: {list(_TAB_MAP.keys())}"
        )

    mini = session.mini
    switched = False
    last_error = None

    path_variants = [
        tab_path,
        "/" + tab_path,
        tab_path + ".html",
        "/" + tab_path + ".html",
    ]

    # Approach 1: mini.switch_tab with path variants
    for path_variant in path_variants:
        try:
            mini.switch_tab(path_variant)
            time.sleep(1.0)
            current = session._get_current_page()
            current_path = getattr(current, "path", None) or ""
            logger.info("After switch_tab(%s), current page path: %s", path_variant, current_path)
            if tab_path in current_path or current_path in tab_path:
                switched = True
                logger.info("Tab switch succeeded via mini.switch_tab(%s)", path_variant)
                break
        except Exception as e:
            logger.debug("mini.switch_tab(%s) raised: %s", path_variant, e)

    # Approach 2: mini.navigate_to
    if not switched:
        for path_variant in path_variants:
            try:
                if hasattr(mini, "navigate_to"):
                    mini.navigate_to(path_variant)
                    time.sleep(1.0)
                    current = session._get_current_page()
                    current_path = getattr(current, "path", None) or ""
                    if tab_path in current_path or current_path in tab_path:
                        switched = True
                        logger.info("Tab switch succeeded via mini.navigate_to(%s)", path_variant)
                        break
            except Exception:
                pass

    # Approach 3: call wx.switchTab via evaluate
    if not switched:
        try:
            app = getattr(mini, "app", None)
            if app is not None and hasattr(app, "call_wx_method"):
                app.call_wx_method("switchTab", {"url": "/" + tab_path})
                time.sleep(1.0)
                current = session._get_current_page()
                current_path = getattr(current, "path", None) or ""
                if tab_path in current_path or current_path in tab_path:
                    switched = True
                    logger.info("Tab switch succeeded via app.call_wx_method")
        except Exception as e:
            logger.debug("app.call_wx_method switchTab failed: %s", e)

    # Approach 4: tab bar element tap
    if not switched:
        try:
            page = session.get_current_page()
            for method_name in ("get_tab_bar", "getTabBar", "tab_bar", "tabBar"):
                tab_bar = getattr(page, method_name, None)
                if callable(tab_bar):
                    tb = tab_bar()
                    items = getattr(tb, "items", None) or getattr(tb, "list", None) or []
                    for item in items:
                        item_text = getattr(item, "text", None) or ""
                        if target in item_text or item_text in target:
                            if hasattr(item, "tap"):
                                item.tap()
                            elif hasattr(item, "click"):
                                item.click()
                            time.sleep(0.8)
                            current = session._get_current_page()
                            current_path = getattr(current, "path", None) or ""
                            if tab_path in current_path or current_path in tab_path:
                                switched = True
                                logger.info("Tab switch succeeded via tab bar tap")
                            break
                    if switched:
                        break
        except Exception as e:
            logger.debug("Tab bar interaction failed: %s", e)

    if not switched:
        raise RuntimeError(
            f"Failed to switch to tab '{target}' (path={tab_path}). "
            f"Tried {len(path_variants)} path variants + navigate_to + call_wx_method + tab bar tap. "
            f"Last error: {last_error or 'page did not change after all attempts'}"
        )

    # Re-sync session page after successful navigation
    current_page = session._get_current_page()
    session._page = current_page
    session.page._page = current_page
    session.capture_state(prev_action=action)


def _navigate_back(session: Any, action: str) -> None:
    """Navigate back to the previous page."""
    with _quiet_minium():
        return _navigate_back_impl(session, action)


def _navigate_back_impl(session: Any, action: str) -> None:
    mini = session.mini
    try:
        if hasattr(mini, "navigate_back"):
            mini.navigate_back()
        elif hasattr(mini, "navigateBack"):
            mini.navigateBack()
        else:
            mini.app.call_wx_method("navigateBack", {})
    except Exception as e:
        raise RuntimeError(f"Navigate back failed: {e}")
    time.sleep(0.5)
    session.capture_state(prev_action=action)
