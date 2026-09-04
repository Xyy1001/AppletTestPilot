"""
Environment Layer — clean abstraction over the WeChat Mini Program runtime.

Encapsulates Minium so the Agent never touches raw SDK calls directly.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class EnvConfig:
    """Immutable snapshot of the environment configuration."""
    project_path: str = ""
    dev_tool_path: str = ""
    test_port: int = 37985
    request_timeout: int = 20
    remote_connect_timeout: int = 20
    auto_relaunch: bool = True
    page_ready_timeout: float = 45.0


class MiniProgramEnv:
    """Thin, testable wrapper around the Minium runtime.

    Responsibilities
    ----------------
    - connect / disconnect lifecycle
    - observe()  → returns raw page + screenshot bytes
    - execute()  → runs a low-level action (click, type, scroll, …)
    - reset()    → clears storage and relaunches
    - page()     → current page proxy (for screenshots, elements, navigation)
    """

    def __init__(self, config: EnvConfig | None = None):
        self._config = config or EnvConfig()
        self._mini: Any = None
        self._session: Any = None          # Session wrapper for action_api compatibility
        self._connected = False

    # ── lifecycle ──────────────────────────────────────────────────────

    def connect(self) -> Any:
        """Connect to WeChat DevTools.  Blocks until the home page is ready."""
        if self._connected:
            return self._mini

        from ..clients.minium import connect_minium

        # Ensure env vars point to our configured paths.
        # Use direct assignment (not setdefault) so explicit config values
        # take precedence over stale environment.
        import os as _os
        _proj = str(self._config.project_path)
        _dev = str(self._config.dev_tool_path)
        if _proj:
            _os.environ["WX_PROJECT_PATH"] = _proj
        if _dev:
            _os.environ["WX_DEVTOOLS_PATH"] = _dev
        _os.environ["WX_TEST_PORT"] = str(self._config.test_port)

        self._mini = connect_minium()

        # Wrap in a Session so the legacy action_api can consume it.
        from ..models.session import Session
        from ..config import Config as AppConfig
        self._session = Session(self._mini, AppConfig(max_tries=3))
        self._connected = True
        return self._mini

    def disconnect(self) -> None:
        """Release the Minium connection."""
        if self._mini is None:
            return
        try:
            if hasattr(self._mini, "release"):
                self._mini.release()
            elif hasattr(self._mini, "shutdown"):
                self._mini.shutdown()
        except Exception:
            pass
        self._mini = None
        self._connected = False

    def reset(self) -> None:
        """Clear all local storage and re-launch to a fresh state."""
        self.disconnect()
        # Give DevTools a moment to fully shut down.
        time.sleep(2)
        self.connect()

    # ── observation ────────────────────────────────────────────────────

    def observe(self) -> dict:
        """Return a raw observation dictionary for the current page.

        Keys
        ----
        - screenshot_bytes : PNG bytes
        - page_route       : current page path (e.g. /pages/index/index)
        - page_title       : navigation bar title
        - elements_raw     : list of element dicts from Minium
        - timestamp        : perf_counter value
        """
        mini = self._mini
        if mini is None:
            return {"screenshot_bytes": b"", "page_route": "/", "page_title": None,
                    "elements_raw": [], "timestamp": time.perf_counter()}

        page = getattr(mini, "page", None) or mini.get_current_page()

        route = getattr(page, "path", "") or getattr(page, "route", "") or "/"
        title = getattr(page, "title", None)

        elements_raw: list[dict] = []
        try:
            # Step 1: text/button/view elements (standard DOM)
            for el in page.get_elements("view, text, button, image"):
                rect = el.rect
                elements_raw.append({
                    "tag": getattr(el, "tag_name", None) or "unknown",
                    "text": el.text or "",
                    "x": rect.get("left", 0), "y": rect.get("top", 0),
                    "w": rect.get("width", 0), "h": rect.get("height", 0),
                    "visible": True,
                    "attrs": _normalize_attrs(getattr(el, "attributes", None)),
                })
            # Step 2: input/textarea (Minium NATIVE components — must be
            #   queried separately; they do NOT appear in mixed selectors)
            for selector in ("input", "textarea"):
                try:
                    for el in page.get_elements(selector):
                        rect = el.rect
                        attrs = _normalize_attrs(getattr(el, "attributes", None))
                        val = attrs.get("value", "") or ""
                        elements_raw.append({
                            "tag": selector,
                            "text": el.text or val or "",
                            "x": rect.get("left", 0), "y": rect.get("top", 0),
                            "w": rect.get("width", 0), "h": rect.get("height", 0),
                            "visible": True,
                            "attrs": attrs,
                        })
                except Exception:
                    pass
            logger.info("observe: %d elements (tags=%s)",
                         len(elements_raw),
                         set(e["tag"] for e in elements_raw))
        except Exception:
            pass

        # Use the Session wrapper's page for screenshots (handles MiniumPageWrapper).
        screenshot_bytes = b""
        if self._session is not None:
            try:
                screenshot_bytes = self._session.page.screenshot(full_page=True)
            except Exception:
                pass

        return {
            "screenshot_bytes": screenshot_bytes,
            "page_route": route,
            "page_title": title,
            "elements_raw": elements_raw,
            "timestamp": time.perf_counter(),
        }

    # ── execution ──────────────────────────────────────────────────────

    def execute(self, action: dict) -> dict:
        """Execute a low-level action through Minium.

        Supported action types
        ----------------------
        - click   : {"type": "click",   "target": "button_text"}
        - input   : {"type": "input",   "target": "field_label", "text": "value"}
        - scroll  : {"type": "scroll",  "direction": "down"|"up"}
        - back    : {"type": "back"}
        - switch  : {"type": "switch_tab", "target": "tab_name"}
        - wait    : {"type": "wait",    "seconds": 0.5}

        Returns a result dict with ``ok``, ``error``, and ``new_route``.
        """
        from ..action_api import execute_action

        action_type = action.get("type", "")
        target = action.get("target", "")
        text = action.get("text", "")

        nl_action = _build_nl_action(action_type, target, text)
        if nl_action is None:
            return {"ok": False, "error": f"Unknown action type: {action_type}"}

        # Use the Session wrapper (not raw mini) so action_api can call
        # session._get_current_page(), session.page, etc.
        session = self._session
        if session is None:
            return {"ok": False, "error": "Not connected — call connect() first"}

        # Re-sync the session's internal page reference before executing.
        try:
            current_page = session._get_current_page()
            if current_page is not None:
                session._page = current_page
                session.page._page = current_page
        except Exception:
            pass

        try:
            execute_action(session, nl_action)
            new_route = self.observe()["page_route"]
            return {"ok": True, "error": None, "new_route": new_route}
        except Exception as e:
            return {"ok": False, "error": str(e), "new_route": None}

    # ── helpers ────────────────────────────────────────────────────────

    @property
    def mini(self) -> Any:
        return self._mini

    @property
    def page(self) -> Any:
        if self._mini is None:
            return None
        return getattr(self._mini, "page", None) or self._mini.get_current_page()


def _normalize_attrs(raw: Any) -> dict:
    """Convert Minium element attributes to a plain dict.

    Minium may return attributes as ``None``, a ``dict``, or a ``list``
    of ``[key, value]`` pairs or ``{{"name": k, "value": v}}`` dicts.
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        result: dict = {}
        for item in raw:
            if isinstance(item, dict):
                name = item.get("name") or item.get("key")
                if name is not None:
                    result[str(name)] = item.get("value")
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                result[str(item[0])] = item[1]
        return result
    return {"value": str(raw)}


def _build_nl_action(action_type: str, target: str, text: str) -> str | None:
    """Convert structured action to natural-language string."""
    _type = action_type.lower()
    if _type == "click":
        return f"Click '{target}'"
    if _type == "input":
        return f"Type '{text}' into '{target}'"
    if _type == "scroll":
        direction = target or "down"
        return f"Scroll {direction}"
    if _type == "back":
        return "Go back"
    if _type == "switch_tab":
        return f"Switch to '{target}'"
    if _type == "wait":
        return f"Wait {target or '0.5'} seconds"
    if _type == "verify":
        return f"Verify page state"
    return None
