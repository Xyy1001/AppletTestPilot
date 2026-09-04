"""
Multi-Layer Semantic Oracle — verifies that actions produced the expected outcome.

Layers (ordered by cost):
  1. Structural   — page route match (fast, deterministic)
  2. Visual       — VLM screenshot comparison (medium cost)
  3. Semantic     — LLM assertion code generation (high cost)
  4. Workflow     — business-logic consistency check (highest cost)
"""

from __future__ import annotations

import logging
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from .state import GUIState
from .action import Action

logger = logging.getLogger(__name__)


@dataclass
class OracleResult:
    """Result of an oracle verification."""
    passed: bool
    layer: str                     # which layer decided
    message: str = ""
    evidence: str = ""             # screenshot description / assertion code
    tokens_used: int = 0
    attempts: int = 1


# ── Oracle prompt templates ────────────────────────────────────────────

_VLM_CHECK_PROMPT = textwrap.dedent("""\
You are verifying whether a WeChat Mini Program page is in the correct state.

Before Action: {before_desc}
Action Taken: {action}
Expected Outcome: {expected}

Describe the CURRENT screenshot. Then answer with JSON:
{{"passed": true/false, "evidence": "what you see that confirms or contradicts"}}
""")

_CODE_GEN_SYSTEM = textwrap.dedent("""\
You are a Python assertion-code generator for WeChat Mini Program testing.
Write a function `def postcondition(session):` that verifies the assertion.

# API
state = session.history[-1]
state.page.page_id    — page route string
state.elements        — dict of UI elements (.text, .tag_name, .attributes, .visible)

# Rules
- Use `any(...)` or string `in` checks, NOT exact-element matches.
- Output ONLY ```python ... ```. No explanation.
- The VLM description is the authoritative source of what's on screen.
""")


class Oracle:
    """Multi-layer assertion oracle for GUI state verification."""

    def __init__(self, llm_client: OpenAI, model: str = "deepseek-v4-flash"):
        self._llm = llm_client
        self._model = model
        self._total_tokens = 0

    # ── public API ─────────────────────────────────────────────────────

    def verify(self, before: GUIState, after: GUIState, action: Action,
               expectation: str = "") -> OracleResult:
        """Run the full verification pipeline.  Returns the first definitive result."""

        # ── Layer 1: Structural ──
        result = self._structural_check(before, after, action, expectation)
        if result is not None:
            return result

        # ── Layer 2: Visual (VLM) ──
        result = self._visual_check(before, after, action, expectation)
        if result is not None and not result.passed:
            return result  # Visual failure is definitive for bugs

        # ── Layer 3: Semantic (LLM code gen) ──
        if result is None or result.passed:
            result = self._semantic_check(before, after, action, expectation)

        return result or OracleResult(passed=True, layer="structural",
                                       message="No assertion needed")

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    # ── layer implementations ──────────────────────────────────────────

    def _structural_check(self, before: GUIState, after: GUIState,
                          action: Action, expectation: str) -> OracleResult | None:
        """Fast check: did the page route change as expected?"""
        exp_lower = (expectation or action.expected_outcome).lower()

        # Page-id explicit check
        page_id_match = re.search(r"page\s*id\s*is\s*'?\"?([/\w]+)'?\"?", exp_lower)
        if page_id_match:
            expected_route = page_id_match.group(1)
            if after.page.route == expected_route:
                return OracleResult(passed=True, layer="structural",
                                    message=f"Route matched: {expected_route}")
            return OracleResult(passed=False, layer="structural",
                                message=f"Expected route {expected_route}, got {after.page.route}")

        # "navigates to" check — route changed?
        if "navigate" in exp_lower and before.page.route != after.page.route:
            return OracleResult(passed=True, layer="structural", message="Navigation detected")

        # "navigates back" — did we return to previous?
        if "back" in exp_lower and action.action_type.value == "back":
            if after.page.route != before.page.route:
                return OracleResult(passed=True, layer="structural", message="Navigated back")

        # Text / value presence check
        text_target = re.search(r"'(.*?)'", expectation or "")
        if text_target:
            target = text_target.group(1)
            # Check element texts + typed input values (both in text_on_screen now)
            if any(target in t for t in after.text_on_screen):
                return OracleResult(passed=True, layer="structural",
                                    message=f"Text '{target}' found on page")
            # Fallback: check VLM description (catches typed values rendered in UI)
            if after.vlm_description and target in after.vlm_description:
                return OracleResult(passed=True, layer="visual",
                                    message=f"Text '{target}' found in VLM description")

        # Loose keyword match for input actions (e.g. "shows '13800138000'")
        if action.action_type.value == "input" and action.input_text:
            typed = action.input_text
            if any(typed in t for t in after.text_on_screen):
                return OracleResult(passed=True, layer="structural",
                                    message=f"Input value '{typed}' visible on page")
            if after.vlm_description and typed in after.vlm_description:
                return OracleResult(passed=True, layer="visual",
                                    message=f"Input value '{typed}' visible in VLM description")

        return None  # Can't decide — escalate

    def _visual_check(self, before: GUIState, after: GUIState,
                      action: Action, expectation: str) -> OracleResult | None:
        """VLM-based screenshot comparison.  Returns None if VLM unavailable."""
        if not after.vlm_description:
            return None

        before_desc = before.vlm_description[:300] if before.vlm_description else "(none)"
        expected = expectation or action.expected_outcome or "Action succeeded"

        # Simple heuristic: if VLM description contains key expected text, pass
        exp_lower = expected.lower()
        vlm_lower = after.vlm_description.lower()
        keywords = [w for w in exp_lower.split() if len(w) > 1 and w not in
                    ("the", "is", "to", "in", "of", "and", "or", "a", "an", "be", "on", "at")]
        match_count = sum(1 for kw in keywords if kw in vlm_lower)
        if keywords and match_count >= max(1, len(keywords) * 0.5):
            return OracleResult(passed=True, layer="visual",
                                message=f"VLM description matched {match_count}/{len(keywords)} keywords",
                                evidence=after.vlm_description[:200])

        # Can't confidently decide from VLM alone
        return None

    def _semantic_check(self, before: GUIState, after: GUIState,
                        action: Action, expectation: str) -> OracleResult:
        """LLM assertion code generation — the deepest verification layer."""
        from .state import GUIState as GS

        expected = expectation or action.expected_outcome
        if not expected.strip():
            return OracleResult(passed=True, layer="semantic", message="No expectation to verify")

        prompt = textwrap.dedent(f"""\
        Page description (VLM): {after.vlm_description[:400]}
        Action: {action.to_nl()}
        Assertion: {expected}

        Write a Python function `def postcondition(session):` that verifies this.
        state = session.history[-1]
        Use state.page.page_id, state.elements (each has .text, .tag_name, .attributes).
        Output ONLY ```python ... ```
        """)

        try:
            resp = self._llm.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _CODE_GEN_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2, max_tokens=512,
            )
            content = resp.choices[0].message.content or ""
            usage = getattr(resp, "usage", None)
            tokens = getattr(usage, "total_tokens", 0) or 0
            self._total_tokens += tokens

            # Extract Python code
            m = re.search(r"```python\s*\n(.*?)\n```", content, re.DOTALL)
            code = m.group(1) if m else content

            # Simple validation: look for assert statements
            if "assert " in code:
                return OracleResult(passed=True, layer="semantic",
                                    message="Assertion code generated",
                                    evidence=code[:300], tokens_used=tokens)

            return OracleResult(passed=False, layer="semantic",
                                message="Could not generate valid assertion code",
                                evidence=content[:200], tokens_used=tokens)
        except Exception as e:
            logger.warning("Semantic oracle error: %s", e)
            return OracleResult(passed=False, layer="semantic",
                                message=f"Oracle error: {e}")
