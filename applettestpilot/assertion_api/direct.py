"""Fast direct assertion checks — no VLM needed."""

import re
from typing import Any


def _verify_direct(session: Any, assertion: str) -> bool | None:
    """
    Fast path for Page ID assertions only.
    Returns True (pass), False (fail), or None (needs VLM).
    """
    if not assertion or not assertion.strip():
        return True

    a = assertion.strip()

    # Page ID: "Page id is '/pages/xxx'" or "Page id is not '/pages/xxx'"
    m = re.search(r"Page\s+id\s+is\s+(not\s+)?'([^']+)'", a, re.IGNORECASE)
    if m:
        negate = bool(m.group(1))
        expected = m.group(2)
        actual = getattr(session.history[-1].page, "page_id", None)
        if negate:
            return actual != expected
        return actual == expected

    # Everything else needs VLM
    return None
