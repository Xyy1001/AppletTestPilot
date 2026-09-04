"""
Phase 2 — Test execution runner (single + batch).
Loads cases, injects bugs, runs tests, saves results.
"""

import sys
import json
import time
import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import Any

from ..config import Config
from ..models import Step, Session
from ..orchestrator import AppletTestPilot
from ..clients.minium import connect_minium
from ..phase1_generate.case_builder import load_test_case
from ..phase1_generate.bug_generator import generate_bug

logger = logging.getLogger("runner")

PROJECT = Path(__file__).parent.parent.parent


# ═══════════════════════════════════════════════════════════════════════
# Setup functions
# ═══════════════════════════════════════════════════════════════════════

def run_setup(mini: Any, setup_function: str) -> None:
    """Run a setup function to inject seed data into the mini program."""
    if not setup_function:
        return
    try:
        bench_dir = PROJECT / "benchmark"
        sys.path.insert(0, str(bench_dir))
        from setup_functions import (
            launch_home, launch_home_with_merchant,
            launch_home_with_merchant_and_product,
            launch_home_with_merchant_and_product_in_cart,
        )
        funcs = {
            "launch_home": launch_home,
            "launch_home_with_merchant": launch_home_with_merchant,
            "launch_home_with_merchant_and_product": launch_home_with_merchant_and_product,
            "launch_home_with_merchant_and_product_in_cart": launch_home_with_merchant_and_product_in_cart,
        }
        fn = funcs.get(setup_function)
        if fn:
            logger.info("Setup: %s", setup_function)
            fn(mini)
    except ImportError as e:
        logger.warning("Setup import failed: %s", e)


# ═══════════════════════════════════════════════════════════════════════
# Bug injection
# ═══════════════════════════════════════════════════════════════════════

def load_bug_script(js_path: Path) -> str:
    return js_path.read_text(encoding="utf-8")


def inject_bug(session: Session, bug_script: str) -> None:
    """Inject a bug script into the mini program runtime."""
    js = f"""
    (function() {{
        {bug_script}
        if (typeof isConditionMet === 'function' && isConditionMet()) {{
            onConditionMet();
            console.log('[AppletTestPilot] Bug injected');
        }} else {{
            console.log('[AppletTestPilot] Bug condition not met');
        }}
    }})();
    """
    mini = session.mini
    try:
        app = getattr(mini, "app", None)
        if app and hasattr(app, "evaluate_js"):
            app.evaluate_js(js)
        elif hasattr(mini, "evaluate_js"):
            mini.evaluate_js(js)
        logger.info("Bug injected")
    except Exception as e:
        logger.warning("Bug injection failed: %s", e)


# ═══════════════════════════════════════════════════════════════════════
# Single test runner
# ═══════════════════════════════════════════════════════════════════════

def run_one_test(
    mini: Any,
    config: Config,
    test_path: Path,
    bug_path: Path | None,
    output_dir: Path,
    framework: str | None = None,
) -> tuple[bool, Any, Path]:
    """Run a single test case. Returns (ok, result, run_dir)."""
    from ..models.result import TestResult

    test_case = load_test_case(test_path)
    test_name = test_path.stem

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_dir / f"run_{timestamp}"
    screenshot_dir = run_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    case_dir = run_dir / test_name
    case_dir.mkdir(parents=True, exist_ok=True)

    session = Session(mini, config, screenshot_dir=str(screenshot_dir))
    session._test_name = test_case.name
    session._setup_function = test_case.setup_function

    run_setup(mini, test_case.setup_function)

    if bug_path and bug_path.exists():
        inject_bug(session, load_bug_script(bug_path))

    agent_steps = [Step(action=s.action, expectation=s.expectation)
                   for s in test_case.steps]

    ok = False
    result = None
    for exec_attempt in range(2):
        try:
            result = AppletTestPilot.run(session, agent_steps, assertion=True)
            ok = result.is_task_complete
            break
        except Exception as e:
            msg = str(e)
            if ("connection" in msg.lower() or "timeout" in msg.lower()) and exec_attempt == 0:
                logger.warning("  Connection lost, reconnecting...")
                time.sleep(2)
                new_mini = connect_minium(max_retries=2)
                session = Session(new_mini, config, screenshot_dir=str(screenshot_dir))
                session._test_name = test_case.name
                session._setup_function = test_case.setup_function
                run_setup(new_mini, test_case.setup_function)
                if bug_path and bug_path.exists():
                    inject_bug(session, load_bug_script(bug_path))
                continue
            logger.error("Run failed: %s", e)
            result = TestResult(test_case=test_case, steps=[])
            ok = False
            logger.error("  ERROR: %s", e)
            break

    if result:
        status = "PASS" if ok else "FAIL"
        passed_count = sum(1 for s in result.steps if s.is_action_correct)
        logger.info("=" * 60)
        logger.info("  RESULT : %s", status)
        logger.info("  STEPS  : %d/%d passed (%.1fs)", passed_count, len(result.steps), result.duration)
        for i, sr in enumerate(result.steps):
            s = "PASS" if sr.is_action_correct else "FAIL"
            b = " [BUG]" if sr.is_bug_reported else ""
            logger.info("    Step %d: %s%s  (%.1fs)", i + 1, s, b, sr.duration)
        logger.info("=" * 60)

    # Save outputs
    (case_dir / "result.json").write_text(
        result.model_dump_json(indent=2) if result else "{}",
        encoding="utf-8",
    )
    (case_dir / "trace.json").write_text(
        json.dumps(session.export_trace(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (case_dir / "history.json").write_text(
        json.dumps(session.export_history(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return ok, result, run_dir


# ═══════════════════════════════════════════════════════════════════════
# Validation runner (used by Phase 1 for case validation)
# ═══════════════════════════════════════════════════════════════════════

def validate_case(
    tmp_yaml: Path,
    case_dir: Path,
    max_attempts: int = 3,
    framework: str | None = None,
) -> bool:
    """Validate a generated test case. Used by Phase 1 after exploration."""
    import yaml
    from ..clients.llm import create_llm_client, call_llm, get_llm_model
    from ..phase1_generate.case_builder import extract_yaml
    from ..phase1_generate.prompts import FIX_SYSTEM

    config = Config.load(PROJECT / "config.yaml")
    client = create_llm_client()
    model = get_llm_model()

    for attempt in range(max_attempts):
        try:
            mini = connect_minium()
            ok, result, _ = run_one_test(mini, config, tmp_yaml, None, PROJECT / "outputs")
        except Exception:
            ok = False
            result = None

        if ok:
            return True

        if attempt == max_attempts - 1:
            break

        # Attempt fix
        logger.info("  Fix attempt %d/%d...", attempt + 1, max_attempts - 1)
        yaml_text = tmp_yaml.read_text(encoding="utf-8")
        failures = "Steps failed" if result else "Execution crashed"
        if result:
            for i, sr in enumerate(result.steps):
                if not sr.is_action_correct:
                    failures += f"\n  Step {i+1}: {sr.step.action}"

        fix_prompt = f"""# Framework Documentation
{framework or '(not provided)'}

# Failing Test Case
```yaml
{yaml_text}
```

# Execution Results (FAILURES)
{failures}

# Task
Fix the test case. Output the corrected YAML inside ```yaml ... ```.
"""

        resp = call_llm(client, FIX_SYSTEM, fix_prompt, temperature=0.5, model=model)
        new_content = resp.content if resp else None
        if new_content:
            new_yaml = extract_yaml(new_content)
            if new_yaml:
                tmp_yaml.write_text(new_yaml, encoding="utf-8")
                continue

    return False


# ═══════════════════════════════════════════════════════════════════════
# Batch helpers
# ═══════════════════════════════════════════════════════════════════════

def resolve_cases(cases_dir: Path, only: str | None = None) -> list[Path]:
    """Return sorted YAML paths from cases_dir, optionally filtered."""
    yamls = sorted(cases_dir.rglob("case.yaml"), key=lambda p: str(p))
    if only:
        indices = set()
        for part in only.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-", 1)
                indices.update(range(int(a), int(b) + 1))
            else:
                indices.add(int(part))
        yamls = [y for i, y in enumerate(yamls, 1) if i in indices]
    return yamls


def find_bug(case_name: str, bugs_dir: Path) -> Path | None:
    """Find matching bug script for a case."""
    bug_path = bugs_dir / case_name / "bug.js"
    return bug_path if bug_path.exists() else None


def run_batch(
    cases_dir: Path,
    bugs_dir: Path | None,
    output_dir: Path,
    only: str | None = None,
) -> tuple[int, int, list[dict]]:
    """Run all test cases in batch. Returns (passed, failed, summary_rows)."""
    config = Config.load(PROJECT / "config.yaml")
    cases = resolve_cases(cases_dir, only)

    if not cases:
        logger.warning("No test cases found")
        return 0, 0, []

    logger.info("  Batch: %d case(s)", len(cases))
    passed, failed = 0, 0
    t0 = time.time()
    summary_rows: list[dict] = []

    for case_yaml in cases:
        case_name = case_yaml.parent.name
        n = passed + failed + 1
        logger.info("─" * 60)
        logger.info("  [%d/%d] %s", n, len(cases), case_name)
        logger.info("─" * 60)

        bug_path = None
        has_bug = False
        if bugs_dir:
            bug_path = find_bug(case_name, bugs_dir)
            if bug_path:
                logger.info("  Bug: %s", bug_path)
                has_bug = True

        mini = connect_minium()
        ok, result, _ = run_one_test(mini, config, case_yaml, bug_path, output_dir)
        if ok:
            passed += 1
        else:
            failed += 1

        # Collect summary row
        if result:
            row = {
                "case": case_name,
                "name": result.test_case.name,
                "setup": result.test_case.setup_function,
                "has_bug": has_bug,
                "passed": ok,
                "total_steps": len(result.steps),
                "passed_steps": sum(1 for s in result.steps if s.is_action_correct),
                "bug_reported": any(s.is_bug_reported for s in result.steps),
                "duration": result.duration,
                "tokens": result.tokens,
            }
            if result.steps:
                row["step_details"] = [
                    {
                        "action": sr.step.action,
                        "expectation": sr.step.expectation,
                        "passed": sr.is_action_correct,
                        "bug_reported": sr.is_bug_reported,
                        "duration": sr.duration,
                        "tokens": sr.tokens,
                    }
                    for sr in result.steps
                ]
            summary_rows.append(row)

    total_time = time.time() - t0
    logger.info("=" * 60)
    logger.info("  Done: %d PASS, %d FAIL, %d total", passed, failed, len(cases))
    logger.info("  Time: %.0fs", total_time)
    logger.info("=" * 60)

    # Write batch summary
    summary = {
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "pass_rate": passed / len(cases) if cases else 0,
        "total_time_s": round(total_time, 1),
        "has_bugs": bugs_dir is not None,
        "cases": summary_rows,
    }
    summary_path = output_dir / "batch_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("  Summary: %s", summary_path)

    return passed, failed, summary_rows
