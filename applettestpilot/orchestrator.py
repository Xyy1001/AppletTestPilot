"""
Test execution orchestrator — the main AppletTestPilot.run() loop.
"""

import logging
import time
import traceback
from typing import Callable, Optional

from .models import Session, Step, TestCase, TestStep, StepResult, TestResult, BugReport
from .action_api import execute_action
from .assertion_api import verify_precondition, verify_postcondition

logger = logging.getLogger(__name__)


class AppletTestPilot:
    """Orchestrates test execution: condition → action → expectation loop."""

    @staticmethod
    def run(
        session: Session,
        test_input: str | list[Step],
        assertion: bool = True,
        hooks: Optional[list[Callable]] = None,
        max_step_retries: int = 0,
    ) -> TestResult:
        """
        Execute a test case on the given Session.

        Args:
            session: The current test session.
            test_input: list of Step objects defining the test.
            assertion: Whether to run precondition/postcondition checks.
            hooks: Optional callbacks invoked on BugReport.
            max_step_retries: Max retries per step on transient failures (0 = no retry).

        Returns:
            TestResult with per-step timing, correctness, and bug-report flags.
        """
        if isinstance(test_input, list):
            steps = test_input
        else:
            raise TypeError("test_input must be a list of Step objects")

        hooks = hooks or []

        test_case = TestCase(
            name=getattr(session, "_test_name", ""),
            setup_function=getattr(session, "_setup_function", ""),
            steps=[TestStep(action=s.action, expectation=s.expectation or "") for s in steps],
        )

        step_results: list[StepResult] = []

        for i, step in enumerate(steps):
            session._step_counter = i + 1
            step_desc = TestStep(
                action=step.action or "",
                expectation=step.expectation or "",
            )

            is_correct = False
            is_bug_reported = False
            step_tokens = 0
            start_time = time.perf_counter()
            end_time = start_time
            last_error = ""

            for retry in range(max_step_retries + 1):
                if retry > 0:
                    logger.info("  Retry %d/%d for step...", retry, max_step_retries)
                    time.sleep(1.0)

                retry_start = time.perf_counter()
                is_bug_reported = False
                is_correct = True
                step_tokens = 0

                logger.info("─" * 60)
                logger.info("  STEP %d/%d | %s%s",
                            i + 1, len(steps), step.action,
                            f" (retry {retry})" if retry > 0 else "")
                logger.info("─" * 60)

                session.record_trace("step_start", action=step.action,
                                     expectation=step.expectation or "")

                try:
                    if assertion and step.condition and step.condition.strip():
                        session.record_trace("precondition", assertion=step.condition)
                        step_tokens += verify_precondition(session, step)

                    execute_action(session, step.action)

                    if assertion and step.expectation and step.expectation.strip():
                        session.record_trace("postcondition", assertion=step.expectation)
                        step_tokens += verify_postcondition(session, step)

                    end_time = time.perf_counter()
                    break  # success

                except BugReport as report:
                    is_correct = False
                    is_bug_reported = True
                    last_error = str(report)[:200]
                    logger.warning("  BUG DETECTED: %s", last_error)
                    session.record_trace("bug_reported", error=last_error)
                    AppletTestPilot._save_error_screenshot(session)
                    for hook in hooks:
                        hook(report)
                    end_time = time.perf_counter()
                    break  # bugs are definitive, don't retry

                except AssertionError as e:
                    is_correct = False
                    is_bug_reported = True
                    last_error = str(e)[:200]
                    logger.warning("  ASSERTION FAILED: %s", last_error)
                    session.record_trace("assertion_failed", error=last_error)
                    AppletTestPilot._save_error_screenshot(session)
                    for hook in hooks:
                        hook(e)
                    end_time = time.perf_counter()
                    break  # assertion failures are definitive, don't retry

                except Exception as e:
                    is_correct = False
                    last_error = str(e)[:200]
                    logger.error("  ERROR: %s", last_error)
                    session.record_trace("exception", error=last_error)
                    AppletTestPilot._save_error_screenshot(session)
                    end_time = time.perf_counter()
                    if retry < max_step_retries:
                        logger.info("  Transient error, will retry...")
                        continue
                    for hook in hooks:
                        hook(e)
                    break

            duration = round(end_time - start_time, 3)
            session.record_trace("step_end", duration=duration, success=is_correct)

            step_results.append(StepResult(
                step=step_desc,
                is_action_correct=is_correct,
                is_bug_reported=is_bug_reported,
                start_time=start_time,
                end_time=end_time,
                tokens=step_tokens,
            ))

        return TestResult(test_case=test_case, steps=step_results)

    @staticmethod
    def _save_error_screenshot(session: Session) -> None:
        try:
            session.page.screenshot(full_page=True)
        except Exception:
            pass
