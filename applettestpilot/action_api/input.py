"""Type/input action strategies for WeChat Mini Programs."""

import sys
import io
import logging
from typing import Any
from contextlib import contextmanager

from .locators import (
    _extract_quoted_targets,
    _normalize_text,
    _safe_get_text,
    _find_input_by_label,
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


def _execute_type(session: Any, action: str) -> None:
    """Type text into an input field identified by label text."""
    with _quiet_minium():
        return _execute_type_impl(session, action)


def _execute_type_impl(session: Any, action: str) -> None:
    targets = _extract_quoted_targets(action)
    if len(targets) < 2:
        raise RuntimeError(f"Type action needs text + field label. Got: {action}")

    text_to_type = targets[0]
    field_label = targets[1]
    page = session.get_current_page()

    # Try finding the input by label
    found = _find_input_by_label(page, field_label)
    if found is not None:
        logger.info("Typing '%s' into field labeled '%s'", text_to_type, field_label)
        tag = (getattr(found, "tag_name", None) or getattr(found, "tagName", "") or "").lower()
        if tag in ("textarea", "wx-textarea"):
            # Minium SDK 3.16.0 dropped textarea.input — use value assignment
            try:
                found.value = text_to_type
            except Exception:
                found.input(text_to_type)  # fallback for older SDK
        else:
            found.input(text_to_type)
        session.capture_state(prev_action=action)
        return

    # Fallback: parent view containing label → first input/textarea child
    label_norm = _normalize_text(field_label).casefold()
    for selector in ("input", "textarea"):
        try:
            els = page.get_elements(selector)
            if not els:
                continue
            try:
                parent_els = page.get_elements("view")
                for parent in (parent_els or []):
                    parent_text = _normalize_text(_safe_get_text(parent)).casefold()
                    if label_norm in parent_text:
                        children = parent.get_elements(selector)
                        if children:
                            logger.info(
                                "Typing '%s' into field labeled '%s' (fallback parent match)",
                                text_to_type, field_label,
                            )
                            children[0].input(text_to_type)
                            session.capture_state(prev_action=action)
                            return
            except Exception:
                pass
            # Last resort: use the first available input/textarea
            logger.warning(
                "Could not find input by label '%s', using first %s as fallback",
                field_label, selector,
            )
            els[0].input(text_to_type)
            session.capture_state(prev_action=action)
            return
        except Exception:
            continue

    raise RuntimeError(
        f"Could not find input field for '{field_label}'. "
        f"No input or textarea elements on the current page."
    )
