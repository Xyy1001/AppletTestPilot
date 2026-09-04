"""
Single Step dataclass — the only definition in the entire project.
"""

from dataclasses import dataclass


@dataclass
class Step:
    """A test step with optional condition, required action, and optional expectation."""
    action: str = ""
    condition: str = ""
    expectation: str = ""
