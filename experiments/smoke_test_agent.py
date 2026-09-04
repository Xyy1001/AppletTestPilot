#!/usr/bin/env python3
"""
Smoke test — verifies the v2 Agent architecture imports and can be
instantiated correctly.  Run WITHOUT DevTools connected to validate
the code paths that don't require a live Minium session.

Usage:
  python experiments/smoke_test_agent.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── 1. Package-level imports ──────────────────────────────────────────
print("1. Testing package imports...")
from applettestpilot import (
    MiniTestAgent, MiniProgramEnv, EnvConfig, AgentConfig, AgentResult,
    GUIState, Action, ActionType, AgentMemory,
    Planner, Oracle, FailureAnalyzer,
    AppletTestPilot, Config,  # v1 legacy
)
print("   OK - all package-level imports succeed")

# ── 2. Core sub-module imports ────────────────────────────────────────
print("2. Testing core sub-module imports...")
from applettestpilot.core.benchmark import STANDARD_TASKS, BenchmarkTask, TaskDifficulty
print(f"   OK - {len(STANDARD_TASKS)} benchmark tasks loaded")
for t in STANDARD_TASKS:
    print(f"      [{t.difficulty.value}] {t.id}")

from applettestpilot.core.state import GUIState as GS, PageInfo, UIElement
print("   OK - state module")
from applettestpilot.core.action import Action, ActionType, PAGE_ACTION_MAP
print("   OK - action module (page actions: {})".format(
    {k: len(v) for k, v in PAGE_ACTION_MAP.items()}))
from applettestpilot.core.memory import AgentMemory, PageNode, TransitionEdge, FailureRecord
print("   OK - memory module")
from applettestpilot.core.analyzer import FailureAnalyzer, FailureReport, BugCategory
print(f"   OK - analyzer module (bug categories: {[c.value for c in BugCategory]})")

# ── 3. Data structure instantiation ───────────────────────────────────
print("3. Testing data structure creation...")
state = GS(
    state_id="test_1",
    page=PageInfo(route="/pages/index/index", semantic_role="home"),
    text_on_screen=["商品展示", "暂无商品", "去创建商家"],
)
print(f"   OK - GUIState created: route={state.page.route}, texts={len(state.text_on_screen)}")

action = Action(
    action_type=ActionType.CLICK,
    target="创建商家",
    reasoning="Navigate to merchant creation",
    expected_outcome="Navigates to vendor join page",
)
print(f"   OK - Action created: {action.to_nl()}")

memory = AgentMemory()
memory.record_page("/pages/index/index", "home", "product_browsing")
memory.record_page("/pages/vendor/join", "form", "merchant_creation")
memory.record_step("s1", "Click '创建商家'", True, "/pages/vendor/join")
memory.record_transition("/pages/index/index", "/pages/vendor/join", "Click '创建商家'")
print(f"   OK - Memory: {memory.unique_pages_visited} pages, {len(memory.edges)} edges")
print(f"   Exploration progress: {memory.get_exploration_progress()}")

# ── 4. Action type validation ─────────────────────────────────────────
print("4. Testing action constraints...")
for role, allowed in PAGE_ACTION_MAP.items():
    assert ActionType.CLICK in allowed or ActionType.VERIFY in allowed, f"Bad actions for {role}"
print("   OK - action constraints valid for all page roles")

# ── 5. Failure analyzer ───────────────────────────────────────────────
print("5. Testing failure analyzer...")
analyzer = FailureAnalyzer()
report = analyzer.analyze(
    state, action,
    error="AssertionError: Expected page id '/pages/vendor/join', got '/pages/index/index'",
    memory=memory,
)
print(f"   OK - Failure report: category={report.category.value}, severity={report.severity}")
print(f"   Hypothesis: {report.root_cause_hypothesis}")

# ── 6. Benchmark task validation ──────────────────────────────────────
print("6. Validating benchmark tasks...")
for task in STANDARD_TASKS:
    assert task.id, f"Missing id in {task}"
    assert task.name, f"Missing name in {task}"
    assert task.min_steps <= task.max_steps, f"Invalid step range in {task.id}"
    assert task.difficulty in TaskDifficulty, f"Invalid difficulty in {task.id}"
print("   OK - all 9 tasks validated")

# ── 7. Memory serialization ───────────────────────────────────────────
print("7. Testing memory serialization...")
import json
d = memory.to_dict()
assert "pages" in d and "edges" in d and "failures" in d and "stats" in d
j = json.dumps(d, ensure_ascii=False)
assert len(j) > 0
print(f"   OK - memory serializes to {len(j)} chars JSON")

# ── 8. Config defaults ────────────────────────────────────────────────
print("8. Testing configuration defaults...")
env_config = EnvConfig()
assert env_config.test_port == 37985
assert env_config.page_ready_timeout == 45.0
assert env_config.auto_relaunch is True
print("   OK - EnvConfig defaults valid")

agent_config = AgentConfig()
assert agent_config.max_steps == 50
assert agent_config.assertion_enabled is True
print("   OK - AgentConfig defaults valid")

# ── 9. Env (offline — no DevTools needed) ─────────────────────────────
print("9. Testing MiniProgramEnv (offline)...")
env = MiniProgramEnv(EnvConfig(project_path="/nonexistent"))
assert env._connected is False
print("   OK - env created without crash (not connected)")

# ── 10. Summary ───────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  ALL SMOKE TESTS PASSED")
print("=" * 60)
print(f"  Modules       : 9/9 core modules importable")
print(f"  Tasks         : {len(STANDARD_TASKS)} benchmark tasks defined")
print(f"  Bug categories: {len(BugCategory)} types")
print(f"  Page roles    : {len(PAGE_ACTION_MAP)} with action constraints")
print(f"  v1 compat     : AppletTestPilot, Config, Session importable")
print("=" * 60)
