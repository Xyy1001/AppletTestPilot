"""
Agent integration hooks — connect the MiniTestAgent loop to the web UI event stream.

Call ``install_hooks(agent)`` before ``agent.run()`` to enable live UI updates.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Callable

from .events import AgentEvent, EventType, get_event_stream
from ..core.agent import MiniTestAgent, StepRecord
from ..core.action import Action, ActionType

logger = logging.getLogger(__name__)

# Store original methods so we can restore them
_originals: dict[str, Callable] = {}


def install_hooks(agent: MiniTestAgent) -> None:
    """Monkey-patch the Agent to emit UI events after each loop phase."""
    stream = get_event_stream()
    logger.info("install_hooks: stream=%s, goal=%s", id(stream), agent._config.goal)

    # ── session start ──
    stream.emit(AgentEvent(
        event_type=EventType.SESSION_START,
        message=f"Agent starting. Goal: {agent._config.goal}",
        detail={"goal": agent._config.goal, "max_steps": str(agent._config.max_steps)},
    ))
    logger.info("install_hooks: SESSION_START emitted")

    # ── patch run() to wrap the inner loop ──
    orig_run = agent.run

    def hooked_run(goal=None, setup_function="launch_home"):
        # Override _describe_screenshot to emit observe events
        orig_describe = agent._describe_screenshot

        def hooked_describe(state):
            desc = orig_describe(state)
            if state.screenshot_bytes:
                b64 = base64.b64encode(state.screenshot_bytes).decode("utf-8")
            else:
                b64 = ""
            stream.emit(AgentEvent(
                event_type=EventType.OBSERVE,
                step_index=state.step_index,
                message=f"Page: {state.page.route} [{state.page.semantic_role}], {len(state.elements)} elements, {len(state.text_on_screen)} text tokens",
                detail={
                    "route": state.page.route,
                    "role": state.page.semantic_role,
                    "business": state.page.business_function,
                    "element_count": str(len(state.elements)),
                    "text_count": str(len(state.text_on_screen)),
                    "vlm": desc[:120] if desc else "(none)",
                },
                screenshot_b64=b64,
            ))
            return desc

        agent._describe_screenshot = hooked_describe
        return orig_run(goal=goal, setup_function=setup_function)

    agent.run = hooked_run

    # ── patch planner.plan() to emit plan events ──
    orig_plan = agent._planner.plan

    def hooked_plan(state, memory, goal="Explore all features"):
        action = orig_plan(state, memory, goal)
        logger.info("hooked_plan: action=%s", action.to_nl())
        stream.emit(AgentEvent(
            event_type=EventType.PLAN,
            step_index=state.step_index + 1,
            message=f"Next: {action.to_nl()}",
            detail={
                "action": action.to_nl(),
                "type": action.action_type.value,
                "target": action.target,
                "input": action.input_text,
                "reasoning": action.reasoning,
                "expected": action.expected_outcome,
                "confidence": f"{action.confidence:.2f}",
            },
        ))
        return action

    agent._planner.plan = hooked_plan

    # ── patch _env.execute to emit execute events ──
    orig_execute = agent._env.execute

    def hooked_execute(action_dict):
        result = orig_execute(action_dict)
        stream.emit(AgentEvent(
            event_type=EventType.EXECUTE,
            step_index=getattr(agent._memory, 'total_steps', 0) + 1,
            message=f"{'OK' if result['ok'] else 'FAIL'}: {action_dict.get('type','')} {action_dict.get('target','')}",
            detail={
                "ok": str(result["ok"]),
                "type": action_dict.get("type", ""),
                "target": action_dict.get("target", ""),
                "error": result.get("error") or "",
                "route_after": result.get("new_route") or "",
            },
        ))
        return result

    agent._env.execute = hooked_execute

    # ── patch oracle.verify to emit oracle events ──
    orig_verify = agent._oracle.verify

    def hooked_verify(before, after, action, expectation=""):
        result = orig_verify(before, after, action, expectation)
        stream.emit(AgentEvent(
            event_type=EventType.ORACLE,
            step_index=after.step_index,
            message=f"{'PASS' if result.passed else 'FAIL'} [{result.layer}] {result.message}",
            detail={
                "passed": str(result.passed),
                "layer": result.layer,
                "evidence": result.evidence[:200] if result.evidence else "",
                "attempts": str(result.attempts),
            },
        ))
        return result

    agent._oracle.verify = hooked_verify

    # ── patch run inner loop for step_start + result events ──
    # We do this by wrapping the agent's run with our own loop that emits events.
    # Since we already hooked run(), we add the step_start emission in the
    # hooked_describe (when step_index increments) and result via a post-hoc hook.

    # Use the memory's record_step as a result hook
    orig_record_step = agent._memory.record_step

    def hooked_record_step(state_id, action_str, success, page_route="", error=""):
        orig_record_step(state_id, action_str, success, page_route, error)
        step_idx = agent._memory.total_steps
        stream.emit(AgentEvent(
            event_type=EventType.RESULT,
            step_index=step_idx,
            message=f"{'PASS' if success else 'FAIL'} | Step {step_idx}/{agent._config.max_steps} | {action_str[:80]}",
            detail={
                "step": str(step_idx),
                "success": str(success),
                "action": action_str[:100],
                "page": page_route,
                "error": error[:150] if error else "",
            },
        ))
        # Also emit step_start for the *next* step (except on last)
        if success and step_idx < agent._config.max_steps:
            stream.emit(AgentEvent(
                event_type=EventType.STEP_START,
                step_index=step_idx + 1,
            ))

    agent._memory.record_step = hooked_record_step

    # ── emit initial step_start ──
    stream.emit(AgentEvent(event_type=EventType.STEP_START, step_index=1))

    logger.info("Web UI hooks installed on Agent")


def uninstall_hooks(agent: MiniTestAgent) -> None:
    """Restore original methods (for cleanup)."""
    stream = get_event_stream()
    stream.emit(AgentEvent(
        event_type=EventType.SESSION_END,
        message=f"Session complete. {agent._memory.total_steps} steps, "
                f"{agent._memory.successful_steps} OK, {agent._memory.failed_steps} failed.",
        detail=agent._memory.get_exploration_progress(),
    ))
    stream.close()
