"""
AppletTestPilot Core — AI-Native Autonomous GUI Testing Agent.

Modules
-------
env       : MiniProgramEnv — clean Minium abstraction
state     : GUIState — unified page snapshot
action    : Action / ActionType / ActionSpace
memory    : AgentMemory — navigation graph + failure patterns
planner   : Planner — LLM-based action proposal
oracle    : Oracle — multi-layer semantic verification
agent     : MiniTestAgent — top-level agent loop
analyzer  : FailureAnalyzer — multi-signal root-cause attribution
"""

from .env import MiniProgramEnv, EnvConfig
from .state import GUIState, PageInfo, UIElement
from .action import Action, ActionType, PAGE_ACTION_MAP
from .memory import AgentMemory, PageNode, TransitionEdge, FailureRecord
from .planner import Planner
from .oracle import Oracle, OracleResult
from .agent import MiniTestAgent, AgentConfig, AgentResult, StepRecord
from .analyzer import FailureAnalyzer, FailureReport, BugCategory
from .world_model import WorldModel, load_world_model

__all__ = [
    # Environment
    "MiniProgramEnv", "EnvConfig",
    # State
    "GUIState", "PageInfo", "UIElement",
    # Action
    "Action", "ActionType", "PAGE_ACTION_MAP",
    # Memory
    "AgentMemory", "PageNode", "TransitionEdge", "FailureRecord",
    # Reasoning
    "Planner", "Oracle", "OracleResult",
    # Agent
    "MiniTestAgent", "AgentConfig", "AgentResult", "StepRecord",
    # Analysis
    "FailureAnalyzer", "FailureReport", "BugCategory",
    # World Model
    "WorldModel", "load_world_model",
]
