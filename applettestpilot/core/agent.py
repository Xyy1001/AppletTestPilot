"""
MiniTestAgent — the top-level autonomous GUI testing agent.

Integrates: Environment, Planner, Executor, Oracle, Memory, Analyzer.
Implements the canonical Agent loop:

    observe → plan → execute → observe → verify → memorize → repeat
"""

from __future__ import annotations

import logging
import time
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from openai import OpenAI

from .env import MiniProgramEnv, EnvConfig
from .state import GUIState
from .action import Action, ActionType
from .memory import AgentMemory
from .planner import Planner
from .oracle import Oracle, OracleResult
from .analyzer import FailureAnalyzer, FailureReport
from .world_model import WorldModel, load_world_model

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for a MiniTestAgent session."""
    max_steps: int = 50
    max_step_retries: int = 1
    assertion_enabled: bool = True
    vlm_enabled: bool = True
    goal: str = "Explore all features of the mini program"
    screenshot_dir: str = ""
    world_model: "WorldModel | None" = None  # app knowledge for Planner


@dataclass
class StepRecord:
    """Complete record of one Agent step."""
    step_index: int
    action: Action
    before_state: GUIState | None = None
    after_state: GUIState | None = None
    oracle_result: OracleResult | None = None
    failure: FailureReport | None = None
    duration_s: float = 0.0
    tokens_used: int = 0


@dataclass
class AgentResult:
    """Result of a complete Agent session."""
    task_completed: bool
    total_steps: int
    successful_steps: int
    failed_steps: int
    steps: list[StepRecord] = field(default_factory=list)
    memory: AgentMemory | None = None
    total_duration_s: float = 0.0
    total_tokens: int = 0
    bug_count: int = 0
    coverage: dict = field(default_factory=dict)


class MiniTestAgent:
    """Autonomous GUI testing agent for WeChat Mini Programs.

    Usage
    -----
    >>> env = MiniProgramEnv()
    >>> env.connect()
    >>> agent = MiniTestAgent(env)
    >>> result = agent.run(goal="Test merchant creation flow")
    >>> print(f"Success: {result.task_completed}, Steps: {result.total_steps}")
    """

    def __init__(self, env: MiniProgramEnv, config: AgentConfig | None = None):
        self._env = env
        self._config = config or AgentConfig()

        # ── LLM clients ──
        self._llm = OpenAI(
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com"),
            api_key=os.getenv("OPENAI_API_KEY", ""),
        )
        self._model = os.getenv("OPENAI_MODEL_NAME", "deepseek-v4-flash")

        # ── modules ──
        wm = self._config.world_model
        self._planner = Planner(self._llm, self._model, world_model=wm)
        self._oracle = Oracle(self._llm, self._model)
        self._analyzer = FailureAnalyzer()
        self._memory = AgentMemory()
        self._world_model = wm

    # ── public API ─────────────────────────────────────────────────────

    def run(self, goal: str | None = None,
            setup_function: str = "launch_home") -> AgentResult:
        """Execute the full Agent loop until task completion or max_steps.

        Args:
            goal: Natural-language task description.
            setup_function: Name of a setup function to pre-seed data.

        Returns:
            AgentResult with full step history and metrics.
        """
        goal = goal or self._config.goal
        steps: list[StepRecord] = []
        t_start = time.perf_counter()
        total_tokens = 0

        # ── setup ──
        self._run_setup(setup_function)

        # ── initial observation ──
        obs = self._env.observe()
        current_state = GUIState.from_env_observation(obs, step_index=0)
        if self._config.vlm_enabled:
            current_state.vlm_description = self._describe_screenshot(current_state)
        self._memory.record_page(
            current_state.page.route, current_state.page.semantic_role,
            current_state.page.business_function, current_state.page.risk_level,
            current_state.state_id,
        )

        logger.info("Agent starting. Goal: %s", goal)
        logger.info("Initial page: %s [%s]", current_state.page.route, current_state.page.semantic_role)

        # ── agent loop ──
        for step_idx in range(1, self._config.max_steps + 1):
            step_start = time.perf_counter()

            # --- plan ---
            action = self._planner.plan(current_state, self._memory, goal)
            logger.info("Step %d | PLAN: %s (%s)", step_idx, action.to_nl(), action.reasoning)

            if action.action_type == ActionType.DONE:
                logger.info("Agent signaled DONE after %d steps", step_idx - 1)
                break

            # --- execute + retry ---
            before_state = current_state
            ok = False
            last_error = ""
            for retry in range(self._config.max_step_retries + 1):
                result = self._env.execute(action.to_dict())
                ok = result["ok"]
                if ok:
                    break
                last_error = result.get("error", "unknown")
                if retry < self._config.max_step_retries:
                    logger.info("  Retry %d/%d: %s", retry + 1, self._config.max_step_retries, last_error[:80])
                    time.sleep(1.0)

            # --- stability wait (input actions need DOM update) ---
            if action.action_type == ActionType.INPUT:
                time.sleep(0.3)

            # --- observe ---
            obs = self._env.observe()
            after_state = GUIState.from_env_observation(
                obs, step_index=step_idx,
                prev_action=action.to_nl(), prev_state_id=before_state.state_id,
            )
            if self._config.vlm_enabled:
                after_state.vlm_description = self._describe_screenshot(after_state)

            # --- verify ---
            oracle_result = None
            failure = None
            if self._config.assertion_enabled:
                oracle_result = self._oracle.verify(
                    before_state, after_state, action, action.expected_outcome
                )
                total_tokens += oracle_result.tokens_used
                if not oracle_result.passed:
                    failure = self._analyzer.analyze(
                        after_state, action, oracle_result.message, self._memory
                    )
                    logger.warning("  ORACLE FAIL [%s]: %s", failure.category.value, failure.root_cause_hypothesis[:120])

            # --- memorize ---
            self._memory.record_step(after_state.state_id, action.to_nl(),
                                     ok and (oracle_result is None or oracle_result.passed),
                                     after_state.page.route,
                                     error=oracle_result.message if oracle_result and not oracle_result.passed else "")
            self._memory.record_page(
                after_state.page.route, after_state.page.semantic_role,
                after_state.page.business_function, after_state.page.risk_level,
                after_state.state_id,
            )
            self._memory.record_transition(
                before_state.page.route, after_state.page.route, action.to_nl(),
                success=ok,
            )

            # --- record step ---
            duration = time.perf_counter() - step_start
            steps.append(StepRecord(
                step_index=step_idx,
                action=action,
                before_state=before_state,
                after_state=after_state,
                oracle_result=oracle_result,
                failure=failure,
                duration_s=duration,
                tokens_used=oracle_result.tokens_used if oracle_result else 0,
            ))

            current_state = after_state

        # ── finalize ──
        total_time = time.perf_counter() - t_start
        bugs = [s for s in steps if s.failure is not None]
        task_ok = all(s.oracle_result is None or s.oracle_result.passed for s in steps)

        result = AgentResult(
            task_completed=task_ok,
            total_steps=len(steps),
            successful_steps=sum(1 for s in steps if s.failure is None),
            failed_steps=len(bugs),
            steps=steps,
            memory=self._memory,
            total_duration_s=total_time,
            total_tokens=total_tokens + self._oracle.total_tokens,
            bug_count=len(bugs),
            coverage=self._memory.get_exploration_progress(),
        )

        logger.info("Agent finished. %d steps, %d bugs, %.1fs",
                    result.total_steps, result.bug_count, total_time)
        return result

    # ── memory access ──────────────────────────────────────────────────

    @property
    def memory(self) -> AgentMemory:
        return self._memory

    # ── internal ───────────────────────────────────────────────────────

    def _run_setup(self, name: str) -> None:
        """Execute a named setup function to seed data."""
        if not name or name == "launch_home":
            return
        import sys
        bench_dir = Path(__file__).parent.parent.parent / "benchmark"
        sys.path.insert(0, str(bench_dir))
        try:
            from setup_functions import (
                launch_home_with_merchant,
                launch_home_with_merchant_and_product,
                launch_home_with_merchant_and_product_in_cart,
            )
            funcs = {
                "launch_home_with_merchant": launch_home_with_merchant,
                "launch_home_with_merchant_and_product": launch_home_with_merchant_and_product,
                "launch_home_with_merchant_and_product_in_cart": launch_home_with_merchant_and_product_in_cart,
            }
            fn = funcs.get(name)
            if fn:
                logger.info("Setup: %s", name)
                fn(self._env.mini)
        except ImportError:
            pass

    def _describe_screenshot(self, state: GUIState) -> str:
        """Get a VLM description of the current screenshot."""
        if not state.screenshot_bytes:
            return ""
        try:
            from ..clients.vision import vision_client
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(state.screenshot_bytes))
            desc = vision_client.call_vision(img, (
                "Describe this WeChat Mini Program screenshot (mobile app): "
                "page title, visible text, buttons, form fields, tab bar state, "
                "dialogs/modals if any. Be specific about text content."
            ))
            return desc.strip() if desc else ""
        except Exception as e:
            logger.warning("VLM description failed: %s", e)
            return ""
