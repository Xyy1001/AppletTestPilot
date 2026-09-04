"""Element finding utilities for WeChat Mini Program UI."""

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Actions that trigger WeChat native modal dialogs (wx.showModal / wx.showActionSheet).
# These dialogs are rendered OUTSIDE the WebView and do NOT appear in Minium screenshots.
_DIALOG_KEYWORDS = (
    "删除", "确定", "取消", "确认", "移除", "清空", "退出", "注销", "解绑",
    "delete", "remove", "clear", "confirm",
)


def is_dialog_action(action: str) -> bool:
    """Check if an action is likely to trigger a native WeChat modal dialog."""
    if not action:
        return False
    action_lower = action.lower()
    return any(kw in action_lower for kw in _DIALOG_KEYWORDS)


def _extract_quoted_targets(action: str) -> list[str]:
    return [m.strip() for m in re.findall(r"['\"]([^'\"]+)['\"]", action) if m.strip()]


def _safe_get_text(el: Any) -> str:
    try:
        text = getattr(el, "text", "")
        return "" if text is None else str(text)
    except Exception:
        return ""


def _normalize_text(s: str) -> str:
    return " ".join((s or "").split())


def _xpath_literal(s: str) -> str:
    if "'" not in s:
        return f"'{s}'"
    if '"' not in s:
        return f'"{s}"'
    parts = s.split("'")
    expr_parts: list[str] = []
    for i, p in enumerate(parts):
        if p:
            expr_parts.append(f"'{p}'")
        if i != len(parts) - 1:
            expr_parts.append('"\'"')
    return "concat(" + ", ".join(expr_parts) + ")"


def _find_elements_by_xpath_contains_text(page: Any, target: str) -> list[Any]:
    t = _normalize_text(target)
    if not t:
        return []
    lit = _xpath_literal(t)
    xpaths = [
        f"//*[contains(normalize-space(text()), {lit})]",
        f"//*[contains(text(), {lit})]",
        f"//*[contains(@text, {lit})]",
        f"//*[@aria-label and contains(@aria-label, {lit})]",
        f"//*[@value and contains(@value, {lit})]",
    ]
    for xp in xpaths:
        try:
            els = page.get_elements("view", xpath=xp)
            if els:
                return els
        except Exception:
            continue
    return []


def _find_clickable_ancestor(page: Any, target: str) -> Any | None:
    t = _normalize_text(target)
    if not t:
        return None
    lit = _xpath_literal(t)
    xp = (
        f"(//*[contains(normalize-space(text()), {lit})]"
        f" | //*[@text and contains(@text, {lit})])"
        f"/ancestor::*[contains(name(), 'view') or contains(name(), 'button')][1]"
    )
    try:
        els = page.get_elements("view", xpath=xp)
        return els[0] if els else None
    except Exception:
        return None


def _find_clickable_by_text(page: Any, target: str) -> Any | None:
    target_norm = _normalize_text(target).casefold()
    if not target_norm:
        return None

    candidates: list[tuple[int, Any]] = []
    selectors_to_scan = ["view, text, button, image, input", "button", "text", "view", "image", "input"]
    for selector in selectors_to_scan:
        try:
            elements = page.get_elements(selector)
        except Exception:
            continue
        for el in elements or []:
            el_text_norm = _normalize_text(_safe_get_text(el)).casefold()
            if not el_text_norm:
                continue
            if el_text_norm == target_norm:
                candidates.append((0, el))
            elif target_norm in el_text_norm:
                candidates.append((1, el))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _find_input_by_label(page: Any, label_text: str) -> Any | None:
    """
    Find an input/textarea associated with the given label text.
    Strategies:
    0. Placeholder match (label text matches placeholder attribute)
    1. Label elements by text → nearest sibling input/textarea
    2. Parent view containing label text → first input/textarea child
    3. Single input/textarea fallback
    """
    label_norm = _normalize_text(label_text).casefold()
    if not label_norm:
        return None

    # Strategy 0: Direct placeholder match
    for input_selector in ("input", "textarea"):
        try:
            inputs = page.get_elements(input_selector)
            for inp in (inputs or []):
                attrs = getattr(inp, "attributes", None) or {}
                if isinstance(attrs, dict):
                    placeholder = attrs.get("placeholder", "")
                    if placeholder and label_norm in _normalize_text(str(placeholder)).casefold():
                        return inp
                ph = getattr(inp, "placeholder", None)
                if ph and label_norm in _normalize_text(str(ph)).casefold():
                    return inp
        except Exception:
            continue

    # Strategy 1: Find label elements by text, scan for nearest input
    for selector in ("view, text, input, button, image, textarea", "view", "text"):
        try:
            all_els = page.get_elements(selector)
        except Exception:
            continue

        matches: list[tuple[int, int, Any]] = []
        for i, el in enumerate(all_els or []):
            el_text = _normalize_text(_safe_get_text(el))
            el_text_lower = el_text.casefold()
            if label_norm in el_text_lower:
                matches.append((len(el_text), i, el))

        matches.sort(key=lambda x: x[0])

        for _text_len, i, _el in matches:
            for offset in range(1, min(20, len(all_els) - i)):
                for direction in (1, -1):
                    idx = i + offset * direction
                    if 0 <= idx < len(all_els):
                        candidate = all_els[idx]
                        tag = getattr(candidate, "tag_name", None) or getattr(candidate, "tagName", "")
                        if tag and tag.lower() in ("input", "textarea", "wx-input", "wx-textarea"):
                            return candidate
            for offset in range(1, 5):
                idx = i + offset
                if idx < len(all_els):
                    try:
                        view_el = all_els[idx]
                        for input_selector in ("input", "textarea"):
                            try:
                                children = view_el.get_elements(input_selector)
                                if children:
                                    return children[0]
                            except Exception:
                                pass
                    except Exception:
                        pass

    # Strategy 2: Parent view containing label → first input/textarea child
    for input_selector in ("input", "textarea"):
        try:
            inputs = page.get_elements(input_selector)
        except Exception:
            continue
        if not inputs:
            continue
        try:
            parent_els = page.get_elements("view")
        except Exception:
            continue

        best_child = None
        best_text_len = float('inf')
        for parent in (parent_els or []):
            parent_text = _normalize_text(_safe_get_text(parent))
            parent_text_lower = parent_text.casefold()
            if label_norm in parent_text_lower:
                text_len = len(parent_text)
                if text_len < best_text_len:
                    try:
                        children = parent.get_elements(input_selector)
                        if children:
                            best_text_len = text_len
                            best_child = children[0]
                    except Exception:
                        pass
        if best_child is not None:
            return best_child

    # Strategy 3: Single input/textarea fallback
    for input_selector in ("input", "textarea"):
        try:
            inputs = page.get_elements(input_selector)
            if inputs and len(inputs) == 1:
                return inputs[0]
        except Exception:
            continue

    return None
