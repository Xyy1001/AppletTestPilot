"""
Phase 1 — Bug script generation from test cases.
"""

import re
import logging
from pathlib import Path

from ..clients.llm import create_llm_client, call_llm, get_llm_model
from .prompts import BUG_SYSTEM

logger = logging.getLogger(__name__)


def generate_bug(
    framework: str,
    case_yaml: str,
    case_name: str,
    failure_log: list[str] | None = None,
) -> str | None:
    """Generate a JavaScript bug injection script for a test case.

    Args:
        framework: FRAMEWORK.md content.
        case_yaml: The YAML test case content.
        case_name: Name of the test case (for logging).
        failure_log: Optional failure history to target common breakage points.

    Returns:
        JavaScript code string, or None if generation failed.
    """
    client = create_llm_client()
    model = get_llm_model()

    bug_context = case_yaml
    if failure_log:
        bug_context += "\n\n# Failure history during generation:\n" + "\n".join(failure_log)

    prompt = f"""# Framework

{framework[:4000]}

# Test Case
```yaml
{bug_context}
```

# Task
Create a JavaScript bug injection script that subtly breaks ONE step in this test case.
The bug should cause an assertion to fail so the testing agent can detect it.
Focus on: data corruption (truncation, zeroing, wrong value, storage tampering).
If failure history is present above, focus the bug on the most commonly failing step.

Output ONLY JavaScript inside ```javascript ... ```. Must have isConditionMet() and onConditionMet().
"""

    logger.info("  Generating bug for: %s", case_name)
    resp = call_llm(client, BUG_SYSTEM, prompt, temperature=0.6, model=model)
    code = resp.content if resp else None

    m = re.search(r"```(?:javascript|js)\s*\n(.*?)\n```", code, re.DOTALL) if code else None
    return m.group(1).strip() if m else None


def save_bug(bug_code: str, bug_dir: Path) -> Path:
    """Save a bug script to the bug directory."""
    bug_dir.mkdir(parents=True, exist_ok=True)
    bug_path = bug_dir / "bug.js"
    bug_path.write_text(bug_code, encoding="utf-8")
    return bug_path
