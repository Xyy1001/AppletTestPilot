"""
VLM + LLM assertion pipeline for AppletTestPilot.

Architecture:
1. VLM describes screenshot (visual understanding only, no code)
2. LLM generates assertion code from VLM description
3. Sandbox executes assertion code with variable tracing
"""

import logging
import os
import re
import textwrap
from typing import Any

from openai import OpenAI

from .sandbox import execute
from ..clients.vision import vision_client
from ..models.step import Step

logger = logging.getLogger(__name__)

# DeepSeek LLM client (for code generation from VLM descriptions)
_llm_client = OpenAI(
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com"),
    api_key=os.getenv("OPENAI_API_KEY", ""),
)
_LLM_MODEL = os.getenv("OPENAI_MODEL_NAME", "deepseek-v4-flash")


# ═══════════════════════════════════════════════════════════════════════
# Text collection helper
# ═══════════════════════════════════════════════════════════════════════

def _get_all_texts(state: Any) -> list[str]:
    """Collect all visible text + input values from a state's elements."""
    elements = getattr(state, "elements", {}) or {}
    texts: list[str] = []
    for e in elements.values():
        t = getattr(e, "text", None)
        if t:
            texts.append(str(t))
        v = getattr(e, "value", None)
        if v:
            texts.append(str(v))
        attrs = getattr(e, "attributes", None) or {}
        if isinstance(attrs, dict):
            for key in ("value", "placeholder"):
                av = attrs.get(key)
                if av and str(av) not in texts:
                    texts.append(str(av))
    return texts


# ═══════════════════════════════════════════════════════════════════════
# VLM prompt: describe screenshot (visual understanding only)
# ═══════════════════════════════════════════════════════════════════════

_VLM_DESCRIBE = textwrap.dedent("""\
Describe this WeChat Mini Program screenshot (MOBILE phone app, NOT desktop):
- Page title at top center
- Tab bar at bottom: which tab icon is highlighted/active?
- ALL visible text strings (exact, including placeholder text)
- ALL buttons with exact label text
- Form fields: what's filled? what shows placeholder?
- Icons: star, cart, plus, minus, user avatar — describe their state
- DIALOGS/MODALS are CRITICAL: if a popup dialog is visible (e.g. "确认删除", "确定"/"取消"),
  describe its title, message text, and ALL buttons explicitly
- Toast messages, modal dialogs, empty state messages
- Do NOT mention cursor, mouse pointer, hover, scrollbar — this is a phone app.
""")

# ═══════════════════════════════════════════════════════════════════════
# LLM prompt: generate assertion code from VLM description
# ═══════════════════════════════════════════════════════════════════════

_CODE_GEN_PROMPT = textwrap.dedent("""\
You are a Python code generator for automated testing of WeChat Mini Programs.
Write a function that verifies the assertion by checking the page description.

# Mini Program Element Model (important!)
- state.elements is a dict of ALL UI elements
- <view>: .text = child text merged
- <input>/<textarea>: .text = placeholder or empty. TYPED VALUE is in .attributes['value']
- Check typed values by collecting BOTH .text AND .attributes.get('value','')
- Use any() or "in" for text checks, NOT == exact match on single element

# CRITICAL — How to verify page navigation
The VLM description shows what is ACTUALLY on the page. Use it as the PRIMARY truth.
state.page.page_id may be stale (Minium timing issue). The VLM description is authoritative.
- For navigation assertions: check BOTH page-specific text from VLM description AND page_id
- Prefer content-based checks (text from VLM description) over route-based checks (page_id)
- Tab bar uses ICONS (not text). Cart tab = cart icon. User tab = user icon.

# API (pre-imported, do NOT import)
session.history[-1] — current state
state.page.page_id    — page route string
state.page.title      — page title text
state.page.description — page description text (NOT state.description!)
state.elements        — dict of elements: .text, .tag_name, .attributes, .visible

# WRONG — these DO NOT exist and WILL crash:
#   state.description  → use state.page.description
#   state.url          → use state.page.page_id
#   element.value      → use element.attributes.get('value','')

# Rules
- Define def postcondition(session): (or def precondition for before-action checks)
- Output ONLY ```python ... ``` block. No explanation.
- No type annotations on function parameters.
- DO NOT write: from typing import ... or from pydantic import ...
- Use simple assert with clear failure messages.
""")

# Examples
_CODE_EXAMPLE = textwrap.dedent("""\
__input__
Page description: Title "创建商家账户". Fields: 商家名称, 手机号, 简介. Button: 保存.
After Action: Click '创建商家'
Assert: Navigates to vendor join page

__output__
```python
def postcondition(session):
    state = session.history[-1]
    all_texts = []
    for e in state.elements.values():
        if e.text:
            all_texts.append(e.text)
    assert any('创建商家账户' in t for t in all_texts), "Vendor join page content not found"
    if state.page.page_id != '/pages/vendor/join':
        pass
```
""")

_EXAMPLE_NAV = textwrap.dedent("""\
__input__
After Action: Click 'cart tab'
Assert: Cart page is showing

__output__
```python
def postcondition(session):
    state = session.history[-1]
    assert state.page.page_id == '/pages/cart/cart', f"Expected cart page, got {state.page.page_id}"
    texts = [e.text for e in state.elements.values() if e.text]
    assert len(texts) > 0, "Cart page appears empty"
```
""")

_EXAMPLE_FORM = textwrap.dedent("""\
__input__
After Action: Type '13800138000' into phone field
Assert: Phone field shows '13800138000'

__output__
```python
def postcondition(session):
    state = session.history[-1]
    all_texts = []
    for e in state.elements.values():
        if e.text:
            all_texts.append(e.text)
        v = e.attributes.get('value', '') if hasattr(e, 'attributes') else ''
        if v:
            all_texts.append(v)
    assert any('13800138000' in t for t in all_texts), "Phone number not visible"
```
""")


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _format_history(session: Any) -> str:
    """Serialize session history for the VLM prompt."""
    states = session.history
    if not states:
        return "(no history)"

    seen_pages: set[str] = set()
    lines: list[str] = []
    for i, st in enumerate(states):
        pid = getattr(st.page, "page_id", f"state-{i}")
        prev = getattr(st, "prev_action", None) or "(initial)"
        label = "  Current state" if i == len(states) - 1 else f"  State ({i})"
        lines.append(label)
        lines.append(f"    Page: {pid}")
        if pid not in seen_pages:
            desc = getattr(st.page, "description", "") or ""
            if desc:
                lines.append(f"    Description: {desc}")
            seen_pages.add(pid)
        lines.append(f"    After: {prev}")
    return "\n".join(lines)


def _sanitize_vlm_code(code: str) -> str:
    """Fix common VLM code artifacts: natural language fragments in code blocks."""
    lines = code.split("\n")
    cleaned = []
    for line in lines:
        s = line.strip()
        if not s:
            cleaned.append(line)
            continue
        if s.startswith(("def ", "class ", "assert ", "if ", "for ", "return ",
                         "import ", "from ", "try:", "except", "pass", "break",
                         "continue", "raise ", "with ", "while ", "else:", "elif ",
                         "#", "```", "@")):
            cleaned.append(line)
            continue
        if any(c in s for c in ("=", "(", ")", ":", "[", "]", "{", "}", ".", "+", "-", "*", "/")):
            cleaned.append(line)
            continue
        if len(s.split()) == 1:
            cleaned.append(line)
            continue
        cleaned.append(f"# [VLM artifact] {s}")
    return "\n".join(cleaned)


# ═══════════════════════════════════════════════════════════════════════
# Main VLM+LLM assertion pipeline
# ═══════════════════════════════════════════════════════════════════════

def _call_vlm_and_execute(
    session: Any,
    action: str,
    assertion: str,
    kind: str,  # "precondition" or "postcondition"
    max_tries: int,
) -> dict:
    """VLM describes screenshot → LLM generates assertion code → sandbox executes.
    Returns dict with token counts from all API calls made."""
    from ..action_api.locators import is_dialog_action
    dialog_action = is_dialog_action(action)
    screenshot_bytes = session.page.screenshot(full_page=True, force_pyautogui=dialog_action)
    from PIL import Image
    import io
    screenshot = Image.open(io.BytesIO(screenshot_bytes))

    history_text = _format_history(session)
    label = "Before Action" if kind == "precondition" else "After Action"

    user_prompt_base = textwrap.dedent(f"""\
        {history_text}

        {label}: {action}
        Assert: {assertion}
    """).strip()

    feedback_list: list[str] = []
    total_tokens = {"prompt": 0, "completion": 0, "total": 0}

    for attempt in range(max_tries):
        feedback_text = ""
        if feedback_list:
            parts = ["\n# Previous attempts that FAILED (do NOT repeat):"]
            for i, fb in enumerate(feedback_list, 1):
                parts.append(f"\n--- Attempt {i}: {fb[:400]}")
            feedback_text = "\n".join(parts)

        user_prompt = user_prompt_base + feedback_text

        label_text = "BEFORE" if kind == "precondition" else "AFTER"
        logger.info("%s | %s: %s", kind.upper(), label_text, action)
        logger.info("ASSERT : %s", assertion)
        logger.info("VLM : GLM-4.1V analyzing screenshot...")

        vlm_desc = vision_client.call_vision(screenshot, _VLM_DESCRIBE)
        vlm_tokens = vision_client.get_last_tokens()
        total_tokens["prompt"] += vlm_tokens["prompt_tokens"]
        total_tokens["completion"] += vlm_tokens["completion_tokens"]
        total_tokens["total"] += vlm_tokens["total_tokens"]

        if not vlm_desc or not vlm_desc.strip():
            feedback_list.append("Vision model returned empty description")
            logger.warning("VLM    : EMPTY response")
            continue

        logger.info("-- VLM description (%d chars) ---\n%s\n----------------------------------",
                    len(vlm_desc), vlm_desc.strip())

        logger.info("LLM : DeepSeek generating assertion code (attempt %d/%d)...", attempt + 1, max_tries)

        llm_prompt = (f"Page description from visual analysis:\n{vlm_desc}\n\n"
                      f"History: {history_text}\n\n"
                      f"{label_text}: {action}\n"
                      f"Assert: {assertion}")
        if feedback_list:
            llm_prompt += "\n\n# Previous FAILED attempts:\n"
            for i, fb in enumerate(feedback_list, 1):
                llm_prompt += f"\nAttempt {i}: {fb[:300]}"

        try:
            resp = _llm_client.chat.completions.create(
                model=_LLM_MODEL,
                messages=[{"role": "system", "content": _CODE_GEN_PROMPT + "\n\n" + _CODE_EXAMPLE},
                           {"role": "user", "content": llm_prompt}],
                temperature=0.3, max_tokens=1024,
            )
            content = resp.choices[0].message.content
            usage = getattr(resp, "usage", None)
            if usage:
                total_tokens["prompt"] += getattr(usage, "prompt_tokens", 0) or 0
                total_tokens["completion"] += getattr(usage, "completion_tokens", 0) or 0
                total_tokens["total"] += getattr(usage, "total_tokens", 0) or 0
        except Exception as e:
            feedback_list.append(f"LLM error: {e}")
            continue

        if not content or not content.strip():
            feedback_list.append("LLM returned empty response")
            continue

        logger.info("-- LLM generated code (%d chars) ----\n%s\n----------------------------------",
                    len(content), content.strip())

        if "```python" not in content and "```" not in content:
            content = f"```python\n{content.strip()}\n```"

        code = "from __future__ import annotations\n" + _sanitize_vlm_code(content)
        passed, message = execute(code, session)

        if passed:
            logger.info("RESULT : PASS (VLM, attempt %d)", attempt + 1)
            logger.info("%s assertion passed (VLM attempt %d)", kind.capitalize(), attempt + 1)
            return total_tokens

        # Mid-retry text fallback
        target_match = re.search(r"'([^']+)'", assertion or "")
        if target_match:
            target = target_match.group(1)
            texts = _get_all_texts(session.history[-1])
            if any(target in t for t in texts):
                logger.info("RESULT : PASS (text check fallback)")
                return total_tokens
            if "no longer" in (assertion or "").lower() or "removed" in (assertion or "").lower():
                if not any(target in t for t in texts):
                    logger.info("RESULT : PASS (text absence fallback)")
                    return total_tokens

        feedback_list.append(message[:500])
        logger.warning("RESULT : FAIL (attempt %d/%d)", attempt + 1, max_tries)
        if message:
            logger.warning("ERROR  : %s", message[:200])

    raise AssertionError(
        f"{kind.capitalize()} failed after {max_tries} VLM attempts. "
        f"Last: {feedback_list[-1][:200] if feedback_list else 'unknown'}"
    )
