# ── v2 Agent (primary) ─────────────────────────────────────────────────
from .core import (
    MiniProgramEnv, EnvConfig,
    GUIState, PageInfo, UIElement,
    Action, ActionType, PAGE_ACTION_MAP,
    AgentMemory, PageNode, TransitionEdge, FailureRecord,
    Planner, Oracle, OracleResult,
    MiniTestAgent, AgentConfig, AgentResult, StepRecord,
    FailureAnalyzer, FailureReport, BugCategory,
)

# ── v1 Orchestrator (legacy compatibility) ────────────────────────────
from .orchestrator import AppletTestPilot
from .config import Config
from .models import (
    Step, Session, State, Page, Element,
    TestCase, TestStep, StepResult, TestResult, BugReport,
)

__all__ = [
    # v2 Agent
    "MiniProgramEnv", "EnvConfig",
    "GUIState", "PageInfo", "UIElement",
    "Action", "ActionType", "PAGE_ACTION_MAP",
    "AgentMemory", "PageNode", "TransitionEdge", "FailureRecord",
    "Planner", "Oracle", "OracleResult",
    "MiniTestAgent", "AgentConfig", "AgentResult", "StepRecord",
    "FailureAnalyzer", "FailureReport", "BugCategory",
    # v1 Legacy
    "AppletTestPilot", "Config",
    "Step", "Session", "State", "Page", "Element",
    "TestCase", "TestStep", "StepResult", "TestResult", "BugReport",
]
