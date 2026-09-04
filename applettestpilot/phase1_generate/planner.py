"""
Phase 1 — Test Plan generation from FRAMEWORK.md analysis.
"""

import json
import re
import time
import logging

from ..clients.llm import create_llm_client, get_llm_model
from .prompts import PLAN_SYSTEM

logger = logging.getLogger(__name__)


def _default_plan() -> list[dict]:
    """Fallback plan when LLM fails."""
    return [
        {"feature": "Create merchant", "goal": "full create+verify",
         "setup": "launch_home", "depends_on": "",
         "must_include": "Click create→fill name/phone/intro→Click save→verify home→Switch to 我的→verify"},
        {"feature": "Upload product", "goal": "full upload+verify",
         "setup": "launch_home_with_merchant", "depends_on": "merchant",
         "must_include": "Click upload→fill title/price/desc→Click save product→verify home→verify card→Switch to 我的→verify list"},
        {"feature": "Add to cart", "goal": "add+verify",
         "setup": "launch_home_with_merchant_and_product", "depends_on": "product",
         "must_include": "Click product→Click add to cart→Switch to 购物车→verify item"},
        {"feature": "Delete product", "goal": "delete+verify",
         "setup": "launch_home_with_merchant_and_product", "depends_on": "product",
         "must_include": "Switch to 我的→Scroll down if needed→Click delete→Click confirm→verify gone"},
        {"feature": "Toggle favorite", "goal": "favorite+verify",
         "setup": "launch_home_with_merchant_and_product", "depends_on": "product",
         "must_include": "Click product→Click star→verify filled→Go back"},
        {"feature": "Submit comment", "goal": "comment+verify",
         "setup": "launch_home_with_merchant_and_product", "depends_on": "product",
         "must_include": "Click product→Type comment→Click submit→verify in list"},
    ]


def build_test_plan(framework: str, existing_cases: list[dict] | None = None) -> list[dict]:
    """LLM analyzes FRAMEWORK.md, returns a test plan as a JSON array.

    Args:
        framework: FRAMEWORK.md content describing the mini program.
        existing_cases: List of dicts with 'name' and 'summary' (first few steps)
            from already-generated case.yaml files. LLM uses these to skip
            covered features instead of guessing from directory names.
    """
    client = create_llm_client()
    model = get_llm_model()

    # Build a meaningful "already covered" section from real case content
    if existing_cases:
        covered_lines = []
        for c in existing_cases:
            name = c.get("name", "?")
            summary = c.get("summary", "")
            covered_lines.append(f"- {name}")
            if summary:
                for line in summary.strip().split("\n")[:6]:
                    covered_lines.append(f"    {line}")
        covered_text = "\n".join(covered_lines)
    else:
        covered_text = "(none yet)"

    prompt = f"""# FRAMEWORK.md
{framework[:5000]}

# Already covered test cases (DO NOT regenerate these features):
{covered_text}

Analyze the framework. Count how many features this mini program has.
Generate a test plan for UNCOVERED features ONLY. Skip any feature that is
already covered by the existing cases above.
Output a JSON array with ONE test plan item for EACH uncovered feature.
"""

    text = None
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": PLAN_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4 + attempt * 0.1,
                max_tokens=2048,
            )
            text = resp.choices[0].message.content
            if text and text.strip():
                break
            time.sleep(1)
        except Exception as e:
            logger.warning("  Plan LLM error: %s", e)
            time.sleep(2)

    logger.info("  LLM plan (%d chars)\n%s", len(text) if text else 0, text if text else "(empty)")
    if not text:
        return _default_plan()

    for strategy in [
        lambda t: json.loads(re.search(r'\[.*\]', t, re.DOTALL).group(0)),
        lambda t: json.loads(t.strip()),
    ]:
        try:
            plan = strategy(text)
            if isinstance(plan, list) and len(plan) > 0:
                return plan
        except Exception:
            continue

    return _default_plan()
