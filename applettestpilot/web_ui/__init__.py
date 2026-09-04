"""
Web UI for real-time Agent monitoring.

Usage:
    from applettestpilot.web_ui import WebAgent
    WebAgent.run(goal="Test merchant creation", port=9120)
"""

from .server import start_server
from .hooks import install_hooks, uninstall_hooks
from .events import EventStream, AgentEvent, EventType, get_event_stream

__all__ = [
    "start_server", "install_hooks", "uninstall_hooks",
    "EventStream", "AgentEvent", "EventType", "get_event_stream",
]
