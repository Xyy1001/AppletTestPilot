"""
Planner — decides the next action given the current GUIState and memory.

Hybrid architecture: LLM reasoning + symbolic constraints + graph guidance.
"""

from __future__ import annotations

import json
import logging
import textwrap
from typing import Optional

from openai import OpenAI

from .state import GUIState
from .action import Action, ActionType, PAGE_ACTION_MAP
from .memory import AgentMemory
from .world_model import WorldModel

logger = logging.getLogger(__name__)

_PLAN_SYSTEM = textwrap.dedent("""\
You control a WeChat Mini Program to complete a testing task. Output ONE action as JSON:
{{
  "action_type": "click|input|scroll|back|switch_tab|wait|verify|done",
  "target": "exact element text",
  "input_text": "text to type (required for input)",
  "reasoning": "brief reason",
  "expected_outcome": "what should happen"
}}

FORM PAGE RULES (highest priority):
- You are on a FORM page. Your ONLY job is to FILL EVERY FIELD then SAVE.
- Fill fields ONE AT A TIME in this exact order:
  Merchant form: 1)Type name  2)Type phone  3)Type intro  4)Click save
  Product form:  1)Type title  2)Type price  3)Type desc  4)Click save
- NEVER click save until ALL fields are filled.
- NEVER do negative testing (no clicking save on empty form).
- If you just navigated to a form, start by typing the FIRST field.
- If recent actions show you typed some fields, type the NEXT unfilled field.
- Only click save AFTER all fields are typed.

GENERAL RULES:
- Complete the task goal as efficiently as possible.
- Never repeat an action that just succeeded.
- If stuck, scroll to find more content.
- Use "done" only when the task goal is fully achieved.
- Use "verify" to check page state without interacting.
""")

_PLAN_USER = textwrap.dedent("""\
Current page: {route} [{role}]
On screen: {texts}
VLM: {vlm_desc}

Goal: {goal}
Step {total_steps} | {successful} OK | {failed} failed
Recent: {visited}
Allowed: {valid_actions}

App info: {planner_ref}

Next action (JSON only):
""")


class Planner:
    """LLM-based action planner with world model + symbolic constraints."""

    def __init__(self, llm_client: OpenAI, model: str = "deepseek-v4-flash",
                 temperature: float = 0.4, world_model: "WorldModel | None" = None):
        self._client = llm_client
        self._model = model
        self._temperature = temperature
        self._world_model = world_model
        # System prompt stays short — world model goes into the user message
        # as planner_ref so the LLM gets clear instructions + data separately.
        self._system_prompt = _PLAN_SYSTEM.format()  # convert {{ → {, }} → }
        # Pre-build the planner reference (world model summary) once
        if world_model:
            self._planner_ref = world_model.build_planner_context()
            self._planner_ref = self._planner_ref.replace("{", "{{").replace("}", "}}")
        else:
            self._planner_ref = "(no app reference available)"

    def plan(self, state: GUIState, memory: AgentMemory,
             goal: str = "Explore all features") -> Action:
        """Propose the next action based on current state and history."""
        valid_actions = PAGE_ACTION_MAP.get(
            state.page.semantic_role,
            [ActionType.CLICK, ActionType.SCROLL, ActionType.BACK, ActionType.WAIT, ActionType.VERIFY],
        )
        valid_str = ", ".join(a.value for a in valid_actions)

        # ── Full LLM path (primary) ──
        visited_str = "\n".join(
            f"  - {r} ({memory.pages[r].semantic_role}, visited {memory.pages[r].visit_count}x)"
            for r in memory.visited_routes[-10:]
        ) or "(none)"

        prompt = _PLAN_USER.format(
            goal=goal.replace("{", "{{").replace("}", "}}"),
            route=state.page.route,
            role=state.page.semantic_role,
            texts=", ".join(state.text_on_screen[:30]).replace("{", "{{").replace("}", "}}"),
            vlm_desc=state.vlm_description[:600].replace("{", "{{").replace("}", "}}"),
            planner_ref=self._planner_ref,
            total_steps=memory.total_steps,
            successful=memory.successful_steps,
            failed=memory.failed_steps,
            visited=visited_str.replace("{", "{{").replace("}", "}}"),
            valid_actions=valid_str,
        )

        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2, max_tokens=512,
            )
            content = resp.choices[0].message.content
            if not content:
                return self._fallback_action(state, memory)
            parsed = self._parse_response(content)
            if not parsed:
                return self._fallback_action(state, memory)
            return self._to_action(parsed, valid_actions)
        except Exception as e:
            logger.warning("Planner error: %s", e)
            return self._fallback_action(state, memory)

    def _symbolic_plan(self, state: GUIState, memory: AgentMemory, goal: str) -> Action | None:
        """Pre-compute the next action for form pages without LLM.
        Returns an Action if the situation is clear-cut, or None to fall back to LLM."""
        if state.page.semantic_role != "form":
            return None

        # Collect input fields — check by tag AND by attributes (Minium may use
        # "input", "wx-input", "textarea", "wx-textarea" or even "unknown")
        input_tags = {"input", "textarea", "wx-input", "wx-textarea"}
        inputs = [e for e in state.elements
                  if e.tag.lower() in input_tags or e.semantic_role == "input"]
        # Also detect inputs by placeholder/value attributes (Minium may mis-tag)
        if not inputs:
            for e in state.elements:
                attrs = e.attributes or {}
                if isinstance(attrs, dict):
                    if attrs.get("placeholder") or attrs.get("type") in ("text", "number", "digit"):
                        inputs.append(e)
                        e.semantic_role = "input"
        logger.info("_symbolic_plan: %d inputs among %d elements (tags: %s)",
                     len(inputs), len(state.elements),
                     set(e.tag for e in state.elements))
        for inp in inputs:
            logger.info("  input: tag=%s text=%r attrs.value=%r",
                         inp.tag, inp.text[:30] if inp.text else "",
                         (inp.attributes or {}).get("value", ""))

        if not inputs:
            # Count consecutive waits — after 2, fall back to LLM
            recent_waits = sum(1 for a in memory.action_sequence[-3:] if "wait" in a.lower() or "Wait" in a)
            if recent_waits >= 2:
                logger.warning("_symbolic_plan: %d consecutive waits, falling back to LLM", len(recent))
                return None  # Let LLM handle it
            return Action(action_type=ActionType.WAIT, target="0.5",
                          reasoning="form: waiting for inputs to render",
                          expected_outcome="Page finishes loading")
        # ... rest unchanged

        # Find labels near inputs to determine field names
        labels = [e.text for e in state.elements if e.semantic_role == "label" and e.text]
        label_str = " | ".join(labels[:6]) if labels else "unknown fields"

        # Find first empty input (check BOTH text and attrs.value — Minium
        # stores typed text in .text on some SDK versions, attrs.value on others)
        for inp in inputs:
            val = (inp.attributes or {}).get("value", "") or inp.text or ""
            if not val or val == (inp.attributes or {}).get("placeholder", ""):
                # Determine what to type based on the label text
                label = "field"
                test_text = "test"
                for other in state.elements:
                    if other.semantic_role == "label" and other.text:
                        lt = other.text
                        if "名称" in lt or "name" in lt.lower() or "标题" in lt:
                            test_text = "测试旗舰店" if "商家" in state.page.business_function else "测试商品"
                        elif "手机" in lt or "phone" in lt:
                            test_text = "13800138000"
                        elif "价格" in lt or "price" in lt:
                            test_text = "199.00"
                        elif "简介" in lt or "描述" in lt or "desc" in lt.lower() or "intro" in lt.lower():
                            test_text = "这是一个测试用的描述信息"
                        label = lt
                        break
                return Action(
                    action_type=ActionType.INPUT,
                    target=label,
                    input_text=test_text,
                    reasoning=f"form: fill empty field '{label}' with '{test_text}'",
                    expected_outcome=f"Field '{label}' shows '{test_text}'"
                )

        # All fields filled — click the save BUTTON (not a text label)
        save_btn = None
        for e in state.elements:
            if e.clickable and e.text and "保存" in e.text:
                save_btn = e
                break
        if not save_btn:
            for e in state.elements:
                if e.text and e.text.strip() == "保存":
                    save_btn = e
                    break
        if save_btn:
            return Action(action_type=ActionType.CLICK, target="保存",
                          reasoning="form: all fields filled, clicking save",
                          expected_outcome="Toast '已保存' and navigate back")

        return None

    def _parse_response(self, text: str) -> dict:
        """Extract JSON from LLM response."""
        # Try ```json block
        import re
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        # Try raw JSON
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        # Try brace match
        brace_start = text.find('{')
        if brace_start >= 0:
            depth = 0
            for i, ch in enumerate(text[brace_start:], brace_start):
                if ch == '{': depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[brace_start:i + 1])
                        except json.JSONDecodeError:
                            pass
                        break
        return {}

    def _to_action(self, parsed: dict, valid: list[ActionType]) -> Action:
        """Convert parsed JSON to an Action, with validation."""
        a_type_str = parsed.get("action_type", "verify")
        try:
            a_type = ActionType(a_type_str)
        except ValueError:
            a_type = ActionType.VERIFY

        # Constrain to valid actions for this page
        if a_type not in valid:
            a_type = ActionType.VERIFY

        return Action(
            action_type=a_type,
            target=parsed.get("target", ""),
            input_text=parsed.get("input_text", ""),
            reasoning=parsed.get("reasoning", ""),
            expected_outcome=parsed.get("expected_outcome", ""),
        )

    def _fallback_action(self, state: GUIState, memory: AgentMemory) -> Action:
        """Return a safe fallback action when the planner fails."""
        # On form pages: fill the first empty field
        if state.page.semantic_role == "form":
            input_tags = {"input", "textarea", "wx-input", "wx-textarea"}
            inputs = [e for e in state.elements
                      if e.tag.lower() in input_tags or e.semantic_role == "input"]
            if inputs:
                # Find the first input without a visible value
                for inp in inputs:
                    val = (inp.attributes or {}).get("value", "") or inp.text or ""
                    ph = (inp.attributes or {}).get("placeholder", "")
                    if not val or val == ph:
                        # Determine what to type based on nearby text
                        label = "field"
                        for other in state.elements:
                            if other.semantic_role == "label" and other.text and len(other.text) <= 10:
                                label = other.text
                                break
                        test_text = "test"
                        for other in state.elements:
                            if other.semantic_role == "label" and other.text:
                                lt = other.text
                                if "名称" in lt or "标题" in lt:
                                    test_text = "测试旗舰店" if "商家" in state.page.business_function else "测试商品"
                                elif "手机" in lt:
                                    test_text = "13800138000"
                                elif "价格" in lt:
                                    test_text = "199.00"
                                elif "简介" in lt or "描述" in lt:
                                    test_text = "这是一个测试用的描述信息"
                        return Action(
                            action_type=ActionType.INPUT,
                            target=label,
                            input_text=test_text,
                            reasoning="fallback: fill empty field '"+label+"'",
                            expected_outcome="Field shows typed text"
                        )
            # If all filled, click the save button
            for e in state.elements:
                if e.text and "保存" in e.text:
                    return Action(action_type=ActionType.CLICK, target=e.text,
                                  reasoning="fallback: click save (all fields appear filled)")
        # Otherwise: click first button or scroll
        buttons = [e for e in state.elements if e.clickable and e.text]
        if buttons:
            return Action(action_type=ActionType.CLICK, target=buttons[0].text,
                          reasoning="fallback: first clickable")
        return Action(action_type=ActionType.SCROLL, target="down",
                      reasoning="fallback: scroll for content")
