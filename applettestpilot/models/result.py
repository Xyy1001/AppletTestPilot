"""
Test result data models and BugReport exception.
"""

from __future__ import annotations
from typing import Optional
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field


class BugReport(Exception):
    """Raised when an assertion detects unexpected behavior (potential bug)."""

    def __init__(self, message: str, screenshots: list | None = None, steps: list | None = None):
        super().__init__(message)
        self.screenshots = screenshots or []
        self.steps = steps or []


class TestStep(BaseModel):
    """A single test step with action and expectation."""
    action: str
    expectation: str
    ground_truth: Optional[str] = None


class TestCase(BaseModel):
    """A complete test case definition."""
    model_config = ConfigDict(extra="allow")

    test_path: Optional[Path] = None
    bug_path: Optional[Path] = None
    name: str = ""
    setup_function: str = ""
    steps: list[TestStep] = Field(default_factory=list)


class StepResult(BaseModel):
    """Result of executing a single test step."""
    step: TestStep
    is_action_correct: bool = False
    is_bug_reported: bool = False
    start_time: float = 0.0
    end_time: float = 0.0
    tokens: int = 0

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class TestResult(BaseModel):
    """Complete result of running a test case."""
    test_case: TestCase
    steps: list[StepResult] = Field(default_factory=list)

    @property
    def is_task_complete(self) -> bool:
        if not self.steps:
            return False
        return all(s.is_action_correct for s in self.steps)

    @property
    def duration(self) -> float:
        return sum(s.duration for s in self.steps)

    @property
    def tokens(self) -> int:
        return sum(s.tokens for s in self.steps)
