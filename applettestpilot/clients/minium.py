"""
Minium connection and page wrapper — single location for all Minium logic.
"""

import sys
import os
import time
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MiniumPageWrapper:
    """Wraps a minium.Page to provide a compatible screenshot interface."""

    def __init__(self, page: Any, screenshot_dir: str | None = None,
                 screenshot_backend: str | None = None):
        self._page = page
        base_dir = Path(__file__).resolve().parents[2]
        self._screenshot_dir = screenshot_dir or str(base_dir / "screenshots")
        os.makedirs(self._screenshot_dir, exist_ok=True)
        self._screenshot_counter = 0
        self._screenshot_backend = (
            screenshot_backend or os.getenv("APPLET_SCREENSHOT_BACKEND") or "minium"
        ).lower()
        self._last_screenshot_path: str | None = None

    def screenshot(self, type: str = "png", full_page: bool = False,
                   timeout: int = 0, force_pyautogui: bool = False) -> bytes:
        from datetime import datetime as _dt
        import time as _time
        self._screenshot_counter += 1
        ts = _dt.now().strftime("%Y%m%d_%H%M%S")
        ms = str(_time.perf_counter_ns())[-5:]
        filename = f"{ts}_{self._screenshot_counter:03d}_{ms}.png"
        filepath = os.path.join(self._screenshot_dir, filename)
        backend = "pyautogui" if force_pyautogui else self._screenshot_backend
        try:
            screenshot_taken = False

            # ── pyautogui path (only with configured region, otherwise fall through) ──
            if backend == "pyautogui":
                try:
                    import pyautogui
                except ImportError:
                    if force_pyautogui:
                        logger.warning("pyautogui not installed, falling back to Minium")
                        backend = "minium"
                    else:
                        raise

            if backend == "pyautogui":
                region_env = os.getenv("APPLET_SCREENSHOT_REGION", "").strip()
                if region_env:
                    parts = [p.strip() for p in region_env.split(",")]
                    if len(parts) != 4:
                        raise ValueError("APPLET_SCREENSHOT_REGION must be 'left,top,width,height'")
                    region = tuple(int(x) for x in parts)
                    img = pyautogui.screenshot(region=region)
                    img.save(filepath)
                    screenshot_taken = True
                else:
                    logger.warning(
                        "pyautogui requested but APPLET_SCREENSHOT_REGION not set — "
                        "falling back to Minium (native dialogs may not be visible)"
                    )

            # ── Minium path (default, or fallback from pyautogui) ──
            if not screenshot_taken:
                page_screen = getattr(self._page, "screen_shot", None)
                if callable(page_screen):
                    page_screen(filepath)
                else:
                    app = getattr(self._page, "app", None)
                    app_screen = getattr(app, "screen_shot", None) if app is not None else None
                    if callable(app_screen):
                        result = app_screen(save_path=filepath)
                        if result is None and not os.path.isfile(filepath):
                            raise RuntimeError(
                                "minium App.screen_shot returned None. "
                                "DevTools window may not be in foreground."
                            )
                    else:
                        raise AttributeError(
                            f"{type(self._page).__name__} has no screen_shot method"
                        )

            with open(filepath, "rb") as f:
                data = f.read()
            self._last_screenshot_path = filepath
            return data
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            # Emergency fallback: always use Minium (pyautogui without region
            # would capture the entire desktop)
            region_env = os.getenv("APPLET_SCREENSHOT_REGION", "").strip()
            if backend == "pyautogui" and region_env:
                import pyautogui
                parts = [p.strip() for p in region_env.split(",")]
                if len(parts) == 4:
                    region = tuple(int(x) for x in parts)
                    img = pyautogui.screenshot(region=region)
                    img.save(tmp_path)
                else:
                    backend = "minium"
            if backend != "pyautogui" or not region_env:
                page_screen = getattr(self._page, "screen_shot", None)
                if callable(page_screen):
                    page_screen(tmp_path)
                else:
                    app = getattr(self._page, "app", None)
                    app_screen = getattr(app, "screen_shot", None) if app is not None else None
                    if callable(app_screen):
                        app_screen(save_path=tmp_path)
                    else:
                        raise
            with open(tmp_path, "rb") as f:
                data = f.read()
            self._last_screenshot_path = tmp_path
            return data

    def wait_for_load_state(self, timeout: int = 0):
        pass

    def __getattr__(self, name):
        return getattr(self._page, name)


def _wait_for_page(mini: Any, timeout: float = 30.0) -> Any:
    """Poll until the mini program page is accessible and has a valid path.

    After `WXMinium.__init__` returns, the App object exists but the mini program
    may still be loading (especially on Windows where the dev-tool takes ~10 s to
    cold-start).  This function blocks until `mini.page` returns a real page with
    a non-empty path, or raises ``RuntimeError`` on timeout.
    """
    import time as _time
    deadline = _time.perf_counter() + timeout
    last_error = None

    while _time.perf_counter() < deadline:
        try:
            pg = getattr(mini, "page", None)
            if pg is None:
                pg = mini.get_current_page() if hasattr(mini, "get_current_page") else None
            if pg is not None:
                path = getattr(pg, "path", "") or getattr(pg, "route", "") or ""
                if path and path != "/":
                    return pg
        except Exception as e:
            last_error = e
            # App may not be fully initialized yet – keep waiting
        _time.sleep(0.5)

    msg = f"Mini program page not ready after {timeout:.0f}s"
    if last_error:
        msg += f" (last error: {last_error})"
    raise RuntimeError(msg)


def connect_minium(max_retries: int = 5) -> Any:
    """Connect to WeChat DevTools via Minium. Retries on timeout.

    After a successful WebSocket connection this function **blocks** until the
    mini-program home page has loaded so that callers can safely interact with
    ``mini.page``, ``mini.app``, and screenshots immediately.
    """
    try:
        import minium
    except ImportError:
        print("ERROR: minium not installed. Run: pip install minium")
        sys.exit(1)

    project_path = os.getenv("WX_PROJECT_PATH", "").strip()
    dev_tool_path = os.getenv("WX_DEVTOOLS_PATH", "").strip().strip('"')
    test_port = int(os.getenv("WX_TEST_PORT", "37985"))

    for key, val in [("WX_PROJECT_PATH", project_path), ("WX_DEVTOOLS_PATH", dev_tool_path)]:
        if not val:
            print(f"ERROR: {key} not set in .env")
            sys.exit(1)
        p = Path(val)
        if not p.exists():
            print(f"ERROR: {key} does not exist: {p}")
            sys.exit(1)

    pp = Path(project_path).resolve()
    dp = Path(dev_tool_path).resolve()

    last_error = None
    for attempt in range(max_retries):
        try:
            import io as _io
            _stderr_hold = sys.stderr
            sys.stderr = _io.StringIO()
            try:
                mini = minium.Minium({
                    "project_path": str(pp),
                    "dev_tool_path": str(dp),
                    "test_port": test_port,
                    "auto_relaunch": True,   # auto-recover if the runtime restarts
                    "request_timeout": 20,
                    "remote_connect_timeout": 20,
                })
            finally:
                sys.stderr = _stderr_hold

            # Block until the home page is actually loaded and interactable.
            # WXMinium.__init__ already calls launch_weapp(), but on Windows the
            # IDE takes 5–10 s to cold-start and the page may not be ready yet.
            _wait_for_page(mini, timeout=45.0)
            pg_path = getattr(mini.page, "path", "") or getattr(mini.page, "route", "?")
            print(f"  Connected (attempt {attempt+1}, page: {pg_path})")
            return mini
        except Exception as e:
            last_error = e
            ename = type(e).__name__
            emsg = str(e)[:150]
            is_timeout = any(kw in ename.lower() + emsg.lower()
                           for kw in ("timeout", "connection", "connectionbreak"))
            if is_timeout and attempt < max_retries - 1:
                wait = 5 + attempt * 3
                print(f"  DevTools not ready (attempt {attempt+1}/{max_retries}), waiting {wait}s...")
                time.sleep(wait)
                continue
            if not is_timeout:
                raise

    print(f"ERROR: DevTools connection failed after {max_retries} attempts")
    if last_error:
        print(f"  Last error: {type(last_error).__name__}: {last_error}")
    sys.exit(1)
