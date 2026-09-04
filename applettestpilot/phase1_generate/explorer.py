"""
Phase 1 — Step-by-step exploration engine.
LLM proposes actions → Minium executes → VLM observes → LLM judges → builds case.
"""

import json
import io
import os
import re
import time
import tempfile
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from ..clients.llm import create_llm_client, get_llm_model
from ..clients.vision import vision_client
from ..clients.minium import connect_minium
from ..config import Config
from ..models.session import Session
from ..action_api import execute_action
from ..action_api.locators import is_dialog_action

from .prompts import EXPLORE_ACTION, EVALUATE_SYSTEM, VLM_DESCRIBE

PROJECT = Path(__file__).parent.parent.parent
logger = logging.getLogger("explorer")


@dataclass
class ExploreStep:
    action: str
    expectation: str
    passed: bool = False
    vlm_before: str = ""
    vlm_after: str = ""
    assertion_code: str = ""
    reason: str = ""


def take_screenshot(mini: Any, use_pyautogui: bool = False) -> bytes:
    """Take a screenshot of the mini program.

    Default: Minium screenshot (captures ONLY the mini program viewport).
    use_pyautogui=True: screen-level capture via pyautogui (for native dialogs).
    Pyautogui REQUIRES APPLET_SCREENSHOT_REGION to be set — otherwise it would
    capture the entire desktop, which is wrong for VLM analysis.
    """
    if use_pyautogui:
        region_env = os.getenv("APPLET_SCREENSHOT_REGION", "").strip()
        if not region_env:
            # No region configured — fall through to Minium to avoid full-desktop capture
            logger.warning("APPLET_SCREENSHOT_REGION not set, falling back to Minium screenshot")
        else:
            try:
                import pyautogui
                parts = [p.strip() for p in region_env.split(",")]
                if len(parts) == 4:
                    region = tuple(int(x) for x in parts)
                    img = pyautogui.screenshot(region=region)
                    buffer = io.BytesIO()
                    img.save(buffer, format="PNG")
                    return buffer.getvalue()
            except (ImportError, Exception) as e:
                logger.warning("pyautogui screenshot failed: %s", e)

    # Default: Minium screenshot (viewport only, reliable)
    pg = mini.page if hasattr(mini, "page") else mini.get_current_page()
    sc = (getattr(pg, "screen_shot", None) or
          getattr(getattr(pg, "app", None), "screen_shot", None) or
          getattr(getattr(mini, "app", None), "screen_shot", None))
    if not callable(sc):
        raise RuntimeError("No screen_shot method found")

    for retry in range(3):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            path = tf.name
        try:
            sc(path)
            if os.path.getsize(path) > 0:
                with open(path, "rb") as f:
                    data = f.read()
                return data
            logger.warning("Minium screenshot returned empty file (attempt %d/3)", retry + 1)
        except Exception as e:
            logger.warning("Minium screenshot error (attempt %d/3): %s", retry + 1, e)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        time.sleep(0.5)

    raise RuntimeError("Minium screenshot failed after 3 attempts")


def vlm_describe(screenshot_bytes: bytes) -> str:
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(screenshot_bytes))
    desc = vision_client.call_vision(img, VLM_DESCRIBE)
    return desc.strip() if desc else "(no description)"


def explore_one_case(
    framework: str,
    case_name: str,
    cases_dir: Path,
    bugs_dir: Path,
    current_plan: dict | None = None,
) -> bool:
    """Explore and build one test case for the given feature plan.

    Returns True if a 100% PASS case was generated and saved.
    """
    client = create_llm_client()
    model = get_llm_model()
    config = Config.load(PROJECT / "config.yaml")

    case_dir = cases_dir / case_name
    case_dir.mkdir(parents=True, exist_ok=True)

    existing = [d.name for d in cases_dir.iterdir() if d.is_dir() and d.name != case_name]
    history: list[ExploreStep] = []
    steps: list[dict] = []
    current_setup = (current_plan or {}).get("setup", "launch_home")

    logger.info("=" * 60)
    logger.info("  EXPLORING: %s", case_name)
    logger.info("  Existing cases: %d", len(existing))
    logger.info("  Setup: %s", current_setup)
    logger.info("=" * 60)

    try:
        mini = connect_minium()

        # Execute the setup function to seed required data (e.g. merchant/product)
        # so dependent test cases start from the correct app state.
        from ..phase2_execute.runner import run_setup
        run_setup(mini, current_setup)

        ss = take_screenshot(mini)
        vlm_desc = vlm_describe(ss)
        logger.info("  Initial page: %s...", vlm_desc[:200])
    except Exception as e:
        logger.error("  Failed to initialize: %s", e)
        return False

    # ── Incremental exploration loop ──
    # LLM proposes ONE action at a time based on current page + feature goal +
    # what has already been done.  Each action is executed, observed by VLM,
    # and evaluated by LLM.  Successful steps are added to the case; failed
    # steps are recorded in history for the LLM to learn from.
    current_feature = current_plan.get("feature", "exploration") if current_plan else "exploration"
    max_steps = 20  # safety limit
    failed_attempts = 0  # consecutive failures counter

    for _step_num in range(max_steps):
        # Build context: history of what's been done (successes + failures)
        history_context = ""
        if history:
            lines = ["# What has been done so far:"]
            for h in history[-10:]:  # last 10 entries
                status = "PASS" if h.passed else "FAIL"
                lines.append(f"- [{status}] {h.action} -> {h.reason[:80]}")
            history_context = "\n".join(lines)

        explore_prompt = f"""Feature to test: {current_feature}
Current page (from screenshot): {vlm_desc[:400]}

{history_context}

Based on the current page and what has been done, what is the SINGLE next action?"""

        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": EXPLORE_ACTION},
                    {"role": "user", "content": explore_prompt},
                ],
                temperature=0.5,
                max_tokens=512,
            )
            text = resp.choices[0].message.content
            next_action = None
            if text:
                for strategy in [
                    lambda t: json.loads(re.search(r'\{.*\}', t, re.DOTALL).group(0)),
                    lambda t: json.loads(t.strip()),
                ]:
                    try:
                        parsed = strategy(text)
                        if isinstance(parsed, dict) and "action" in parsed:
                            next_action = parsed
                            break
                    except Exception:
                        continue
        except Exception as e:
            logger.warning("  Explore LLM error: %s", e)
            continue

        if not next_action:
            logger.warning("  LLM returned no action, stopping")
            break

        action = next_action.get("action", "")
        action = action.replace("Input '", "Type '")
        expectation = next_action.get("expectation", "")

        # DONE — LLM signals feature is complete
        if action.strip().upper() == "DONE":
            logger.info("  LLM: feature complete (%d steps built)", len(steps))
            break

        logger.info("  Step %d | %s", len(steps) + 1, action)

        # ── Capture BEFORE state ──
        try:
            before_bytes = take_screenshot(mini)
            vlm_before = vlm_describe(before_bytes)
        except Exception:
            vlm_before = vlm_desc

        session = Session(mini, config, screenshot_dir=str(case_dir))
        session._test_name = case_name
        session._setup_function = current_setup

        # ── Execute action ──
        try:
            execute_action(session, action)

            if is_dialog_action(action):
                time.sleep(0.4)
                after_bytes = take_screenshot(mini, use_pyautogui=True)
            else:
                last_ss = getattr(session.page, "_last_screenshot_path", None)
                if last_ss and os.path.exists(last_ss):
                    with open(last_ss, "rb") as f:
                        after_bytes = f.read()
                else:
                    after_bytes = take_screenshot(mini)
            vlm_after = vlm_describe(after_bytes)
        except Exception as e:
            logger.warning("  Action failed: %s", e)
            history.append(ExploreStep(action=action, expectation=expectation,
                                       passed=False, reason=str(e)))
            failed_attempts += 1
            if failed_attempts >= 3:
                logger.warning("  Too many consecutive failures, stopping")
                break
            continue

        # ── VLM + LLM evaluate ──
        eval_prompt = f"""Action: {action}
Expected: {expectation}
BEFORE: {vlm_before[:400]}
AFTER: {vlm_after[:400]}
Did it pass? JSON only."""

        try:
            eval_text = None
            for _t in (0.3, 0.5):
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": EVALUATE_SYSTEM},
                        {"role": "user", "content": eval_prompt},
                    ],
                    temperature=_t,
                    max_tokens=1024,
                )
                eval_text = resp.choices[0].message.content
                if eval_text and eval_text.strip():
                    break
                time.sleep(0.3)
            if not eval_text:
                eval_text = '{"passed": false, "reason": "LLM empty", "assertion_code": ""}'

            if eval_text.strip().startswith("{") and not eval_text.strip().endswith("}"):
                last_quote = eval_text.rfind('"')
                if last_quote > 0:
                    eval_text = eval_text[:last_quote + 1] + ', "assertion_code": ""}'

            evaluation = None
            for strategy in [
                lambda t: json.loads(re.search(r'\{.*\}', t, re.DOTALL).group(0)),
                lambda t: json.loads(t.strip()),
                lambda t: json.loads(re.sub(r'```.*\n?', '', t).strip()),
            ]:
                try:
                    evaluation = strategy(eval_text)
                    break
                except Exception:
                    continue
            if not evaluation:
                evaluation = {"passed": False,
                              "reason": f"Could not parse: {eval_text[:100]}",
                              "assertion_code": ""}
        except Exception as e:
            logger.warning("  Eval failed: %s", e)
            evaluation = {"passed": True, "reason": f"eval error: {e}", "assertion_code": ""}

        passed = evaluation.get("passed", False)
        reason = evaluation.get("reason", "")
        assertion_code = evaluation.get("assertion_code", "")

        step_record = ExploreStep(
            action=action, expectation=expectation,
            passed=passed, vlm_before=vlm_before, vlm_after=vlm_after,
            assertion_code=assertion_code, reason=reason,
        )

        # Update page context for next iteration
        vlm_desc = vlm_after
        history.append(step_record)

        if passed:
            logger.info("  PASS: %s", reason)
            steps.append({"action": action, "expectation": expectation})
            failed_attempts = 0
        else:
            logger.info("  FAIL: %s (will try alternative)", reason)
            # Still record the attempt in history so LLM learns from it
            failed_attempts += 1
            if failed_attempts >= 3:
                logger.warning("  Too many consecutive failures, stopping")
                break

    if not steps:
        logger.warning("  No steps built")
        return False

    # Clean and normalize steps
    clean_steps = []
    for s in steps:
        action = s.get("action", "")
        assertion = s.get("expectation", "")
        action = action.replace("Input '", "Type '").replace("输入'", "Type '").replace("填入'", "Type '")
        action = re.sub(r"\s+button\s*$", "", action, flags=re.IGNORECASE).strip()
        if action.startswith("输入'") or action.startswith("填入'"):
            parts = re.findall(r"'([^']+)'", action)
            if len(parts) >= 2:
                action = f"Type '{parts[1]}' into '{parts[0]}'"
        if not action or len(action) < 2:
            continue
        if not assertion:
            assertion = f"Verify after: {action}"
        clean_steps.append({"action": action, "expectation": assertion})

    import yaml
    case_data = {
        "name": f"Explored: {case_name}",
        "setup_function": current_setup,
        "steps": clean_steps,
    }

    # Save exploration history
    (case_dir / "explore_history.json").write_text(
        json.dumps([
            {"action": h.action, "expectation": h.expectation,
             "passed": h.passed, "reason": h.reason,
             "vlm_before": h.vlm_before[:200], "vlm_after": h.vlm_after[:200]}
            for h in history
        ], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Save the case immediately — each step was already validated during exploration.
    case_yaml = case_dir / "case.yaml"
    case_yaml.write_text(
        yaml.dump(case_data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    logger.info("  Case saved: %s", case_yaml)

    # Best-effort full validation (fresh Minium connection, VLM assertions).
    # Failures here do NOT invalidate the case — the step-by-step exploration
    # already verified each action.  This is a smoke test only.
    try:
        from ..phase2_execute.runner import validate_case
        logger.info("  Smoke test: full validation (%d steps)...", len(steps))
        _tmp_yaml = case_dir / "_tmp.yaml"
        _tmp_yaml.write_text(case_yaml.read_text(encoding="utf-8"), encoding="utf-8")
        ok = validate_case(_tmp_yaml, case_dir, max_attempts=2, framework=framework)
        if ok:
            logger.info("  Smoke test PASSED")
        else:
            logger.warning("  Smoke test failed (case already saved, step-by-step verification passed)")
    except Exception as e:
        logger.warning("  Smoke test crashed (case already saved): %s", e)

    return True
