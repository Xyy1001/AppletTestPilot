import io
import logging
import os
from typing import Any, TYPE_CHECKING, Optional

from ..config import Config
from ..clients.minium import MiniumPageWrapper

if TYPE_CHECKING:
    from .element import Element
    from .state import State

logger = logging.getLogger(__name__)


class Session:
    """Manages a WeChat Mini Program test session using Minium."""

    def __init__(self, mini: Any, config: Config,
                 screenshot_dir: str | None = None,
                 screenshot_backend: str | None = None):
        from .state import State

        self.mini = mini
        self._page = self._get_current_page()
        self.page = MiniumPageWrapper(self._page, screenshot_dir, screenshot_backend)
        self.config = config

        self.trace: list[dict] = []
        self._history: list[State] = []
        self._step_counter: int = 0
        self._test_name: str = ""
        self._setup_function: str = ""
        self._step_tokens: int = 0
        self.capture_state(prev_action=None)

    def _get_current_page(self) -> Any:
        getter = getattr(self.mini, "get_current_page", None)
        if callable(getter):
            return getter()
        page = getattr(self.mini, "page", None)
        if page is not None:
            return page
        app = getattr(self.mini, "app", None)
        if app is not None:
            current_page = getattr(app, "current_page", None)
            if current_page is not None:
                return current_page
            app_getter = getattr(app, "get_current_page", None)
            if callable(app_getter):
                return app_getter()
        raise AttributeError(f"{type(self.mini).__name__} has no current page handle")

    def get_current_page(self) -> Any:
        return self._get_current_page()

    def export_trace(self) -> list[dict]:
        return [
            {k: str(v) if not isinstance(v, (dict, list, str, int, float, bool, type(None))) else v
             for k, v in entry.items()}
            for entry in self.trace
        ]

    def record_trace(self, event_type: str, **kwargs) -> None:
        import time
        entry = {
            "step": self._step_counter,
            "type": event_type,
            "timestamp": time.perf_counter(),
            **kwargs,
        }
        self.trace.append(entry)

    def export_history(self) -> list[dict]:
        result = []
        for st in self._history:
            pid = getattr(st.page, "page_id", "")
            entry = {
                "page_id": pid,
                "prev_action": st.prev_action,
                "element_count": len(st.elements),
                "visible_texts": [
                    e.text[:80] for e in list(st.elements.values())[:20]
                    if e.visible and e.text
                ],
            }
            result.append(entry)
        return result

    @property
    def history(self) -> list["State"]:
        return self._history.copy()

    def capture_state(self, prev_action: str | None):
        from .state import State
        from .page import Page
        from ..action_api.locators import is_dialog_action
        from xml.dom.minidom import getDOMImplementation

        import time as _time
        current_page = self._get_current_page()

        # After navigation actions, poll until DOM updates.
        # Dialog-triggering actions (delete, confirm, etc.) trigger native modals
        # that don't change the underlying DOM — use a short poll but capture a
        # screen-level screenshot (pyautogui) because Minium screenshots cannot
        # see native WeChat dialogs (wx.showModal).
        action_lower = (prev_action or "").lower()
        dialog_action = is_dialog_action(prev_action or "")
        if any(kw in action_lower for kw in ("click", "switch to", "go to", "goto", "tap")):
            poll_rounds = 5 if dialog_action else 15  # 0.5s wait for dialog vs 1.5s for nav
            old_route = getattr(current_page, "path", None) or \
                        getattr(current_page, "route", None) or "/"
            old_text = ""
            try:
                old_els = current_page.get_elements("view, text, button, image, input")
                if old_els:
                    old_text = getattr(old_els[0], "text", "") or ""
            except Exception:
                pass

            import sys
            _stderr_hold = sys.stderr
            sys.stderr = io.StringIO()
            try:
                for _ in range(poll_rounds):
                    _time.sleep(0.1)
                    try:
                        new_page = self._get_current_page()
                        new_route = getattr(new_page, "path", None) or \
                                    getattr(new_page, "route", None) or "/"
                        new_els = new_page.get_elements("view, text, button, image, input")
                        new_text = ""
                        if new_els:
                            new_text = getattr(new_els[0], "text", "") or ""
                        if new_route != old_route or (new_text and new_text != old_text):
                            current_page = new_page
                            break
                    except Exception:
                        pass
            finally:
                sys.stderr = _stderr_hold

        self._page = current_page
        self.page._page = current_page
        route = getattr(current_page, "path", None) or \
                getattr(current_page, "route", None) or "/"
        title = getattr(current_page, "title", None)
        elements = self.capture_elements()

        # Native dialogs (wx.showModal) are rendered outside the WebView —
        # Minium screenshot cannot see them. Use screen-level pyautogui capture.
        try:
            self.page.screenshot(full_page=True, force_pyautogui=dialog_action)
        except Exception as e:
            logger.warning("Screenshot capture failed (continuing): %s", e)

        if prev_action:
            self.record_trace("action_executed",
                              action=prev_action,
                              page_id=route,
                              element_count=len(elements))

        impl = getDOMImplementation()
        doc = impl.createDocument(None, "page", None)

        page = Page(
            page_id=route,
            title=title,
            description=f"Mini program page at {route}",
            layout=doc
        )

        state = State(
            session=self,
            page=page,
            elements=elements,
            prev_action=prev_action
        )
        self._history.append(state)

    def capture_elements(self) -> dict[int, "Element"]:
        from .element import Element

        elements_data = []
        try:
            current_page = self._get_current_page()
            all_elements = current_page.get_elements("view, text, button, image, input")
            for i, el in enumerate(all_elements):
                tag_name = (
                    getattr(el, "tag_name", None)
                    or getattr(el, "tagName", None)
                    or getattr(el, "_tag_name", None)
                    or getattr(el, "_tagName", None)
                )
                if tag_name is None:
                    tag_name = "unknown"
                rect = el.rect
                raw_attrs = getattr(el, "attributes", {})
                attrs: dict[str, Any]
                if raw_attrs is None:
                    attrs = {}
                elif isinstance(raw_attrs, dict):
                    attrs = raw_attrs
                elif isinstance(raw_attrs, list):
                    attrs = {}
                    for item in raw_attrs:
                        if isinstance(item, dict):
                            name = item.get("name") or item.get("key")
                            if name is None:
                                continue
                            attrs[str(name)] = item.get("value")
                        elif isinstance(item, (list, tuple)) and len(item) >= 2:
                            attrs[str(item[0])] = item[1]
                else:
                    attrs = {"value": raw_attrs}

                el_value = getattr(el, "value", None)
                combined_text = el.text or ""
                if el_value and str(el_value) not in str(combined_text):
                    combined_text = f"{combined_text} {el_value}".strip()

                elements_data.append({
                    "id": i + 1,
                    "tagName": str(tag_name),
                    "text": combined_text,
                    "x": rect.get("left", 0),
                    "y": rect.get("top", 0),
                    "width": rect.get("width", 0),
                    "height": rect.get("height", 0),
                    "attributes": attrs,
                    "visible": True,
                })
        except Exception as e:
            logger.error(f"Failed to capture elements: {e}")

        elements: dict[int, Element] = {}
        for data in elements_data:
            elements[data["id"]] = Element(session=self, **data)

        return elements
