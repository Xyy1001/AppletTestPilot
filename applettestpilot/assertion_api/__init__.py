from .direct import _verify_direct
from .oracle import _call_vlm_and_execute
from ..models.step import Step

import logging

logger = logging.getLogger(__name__)


def verify_precondition(session, step: Step) -> int:
    """Verify precondition before an action. Fast direct check, then VLM if needed.
    Returns token count from API calls (0 for direct checks)."""
    action = step.action or ""
    assertion = step.condition or ""

    if not assertion.strip():
        return 0

    result = _verify_direct(session, assertion)
    if result is True:
        logger.info("Precondition PASSED (direct): %s", assertion[:80])
        return 0
    if result is False:
        raise AssertionError(f"Precondition FAILED: {assertion!r}")

    tokens = _call_vlm_and_execute(session, action, assertion, "precondition", max_tries=1)
    return tokens.get("total", 0) if isinstance(tokens, dict) else 0


def verify_postcondition(session, step: Step) -> int:
    """Verify postcondition after an action. Fast direct check, then VLM if needed.
    Returns token count from API calls (0 for direct checks)."""
    action = step.action or ""
    assertion = step.expectation or ""

    if not assertion.strip():
        return 0

    result = _verify_direct(session, assertion)
    if result is True:
        logger.info("Postcondition PASSED (direct): %s", assertion[:80])
        return 0
    if result is False:
        raise AssertionError(f"Postcondition FAILED: {assertion!r}")

    max_tries = getattr(session.config, "max_tries", 3)
    tokens = _call_vlm_and_execute(session, action, assertion, "postcondition", max_tries)
    return tokens.get("total", 0) if isinstance(tokens, dict) else 0
