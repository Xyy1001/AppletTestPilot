#!/usr/bin/env python3
"""
Phase 1 — Exploration-based Test Case Generation.

LLM explores the mini program step by step:
  1. Analyze FRAMEWORK.md → create feature-level test plan
  2. For each feature: propose actions → Minium executes → VLM observes → LLM judges
  3. Build complete test case → validate 100% PASS → save case + generate bug

Usage:
  python explore_and_test.py
  python explore_and_test.py --source TestApplet --output input --max-cases 20
  python explore_and_test.py --source TestApplet --output input --log output.log
"""

import sys
import io
import logging
from pathlib import Path

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from applettestpilot.phase1_generate import (
    build_test_plan, explore_one_case, generate_bug, save_bug,
)

PROJECT = Path(__file__).parent


def setup_logging(log_path: Path | None = None):
    """Configure logging: console + optional UTF-8 file (avoids PowerShell
    redirection encoding issues)."""
    _NOISY_PREFIXES = ("minium", "urllib3", "httpx", "httpcore",
                       "zai", "websockets", "asyncio", "PIL")

    # Suppress existing noisy loggers
    for _name in list(logging.root.manager.loggerDict.keys()):
        if any(_name.startswith(p) for p in _NOISY_PREFIXES):
            _lg = logging.getLogger(_name)
            _lg.setLevel(logging.CRITICAL)
            _lg.handlers.clear()
            _lg.propagate = False

    # Intercept future noisy loggers
    _orig_getLogger = logging.getLogger
    def _quiet_getLogger(name):
        _lg = _orig_getLogger(name)
        if any(name.startswith(p) for p in _NOISY_PREFIXES):
            _lg.setLevel(logging.CRITICAL)
            _lg.handlers.clear()
            _lg.propagate = False
        return _lg
    logging.getLogger = _quiet_getLogger

    fmt = logging.Formatter("%(message)s")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(logging.INFO)

    for name in ("applettestpilot", "explorer", "planner", "runner"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        lg.handlers.clear()
        lg.addHandler(console)

    if log_path:
        # Treat paths without a file extension as directories (append output.log).
        # Otherwise a bare path like "results/run1" gets created as a regular file,
        # which then blocks --output from creating subdirectories there (WinError 183).
        if log_path.is_dir() or not log_path.suffix:
            log_path = log_path / "output.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(str(log_path), encoding="utf-8", mode="w")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
        fh.setLevel(logging.DEBUG)
        for name in ("applettestpilot", "explorer", "planner", "runner"):
            logging.getLogger(name).addHandler(fh)
        print(f"  Log: {log_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Exploration-based test case generation")
    parser.add_argument("--source", type=Path, default=PROJECT / "TestApplet")
    parser.add_argument("--output", type=Path, default=PROJECT / "input")
    parser.add_argument("--max-cases", type=int, default=99,
                        help="Safety cap (plan determines actual count)")
    parser.add_argument("--log", type=Path, default=None,
                        help="Write structured log to file (UTF-8, avoids PowerShell encoding issues)")
    args = parser.parse_args()

    setup_logging(args.log)

    framework_path = args.source / "FRAMEWORK.md"
    if not framework_path.exists():
        print(f"ERROR: {framework_path} not found")
        sys.exit(1)
    framework = framework_path.read_text(encoding="utf-8")

    cases_dir = args.output / "cases"
    bugs_dir = args.output / "bugs"

    print(f"\n{'='*60}")
    print(f"  EXPLORATION-BASED GENERATION")
    print(f"  Source: {args.source}")
    print(f"  Safety cap: {args.max_cases} cases")
    print(f"{'='*60}")

    # Scan existing cases ONCE — subsequent iterations reuse plan, not re-scan
    existing_cases: list[dict] = []
    if (args.output / "cases").exists():
        import yaml
        for d in sorted((args.output / "cases").iterdir()):
            if not d.is_dir():
                continue
            case_yaml = d / "case.yaml"
            if not case_yaml.exists():
                continue
            try:
                data = yaml.safe_load(case_yaml.read_text(encoding="utf-8"))
                steps = data.get("steps", [])
                summary = "\n".join(
                    f"  - {s.get('action','?')} -> {s.get('expectation','?')}"
                    for s in steps[:6]
                )
                existing_cases.append({
                    "name": data.get("name", d.name),
                    "summary": summary,
                })
            except Exception:
                existing_cases.append({"name": d.name, "summary": ""})

    plan = build_test_plan(framework, existing_cases)
    if not plan:
        print("ERROR: Could not create test plan")
        sys.exit(1)

    print(f"\n  LLM analyzed framework -> {len(plan)} feature(s) to test")
    for i, f in enumerate(plan):
        print(f"     {i+1}. {f.get('feature','?')} [{f.get('depends_on','?')}]")

    # Sort plan by dependency order: features with no deps first, then
    # features whose deps have already been sorted. This ensures
    # "Create merchant" always runs before "Upload product", etc.
    sorted_plan = []
    remaining = list(plan)
    while remaining:
        ready = []
        for item in remaining:
            dep = (item.get("depends_on") or "").strip().lower()
            if not dep:
                ready.append(item)
            else:
                for s in sorted_plan:
                    sf = (s.get("feature") or "").lower()
                    if dep in sf or sf in dep:
                        ready.append(item)
                        break
        if not ready:
            sorted_plan.extend(remaining)
            break
        for item in ready:
            if item in remaining:
                remaining.remove(item)
                sorted_plan.append(item)
    plan = sorted_plan

    next_index = len(existing_cases)  # 0-based, so case_01 = index 0
    generated = 0
    while generated < args.max_cases and generated < len(plan):
        feature = plan[generated]
        case_name = f"case_{next_index + 1:02d}"

        print(f"\n{'─'*60}")
        print(f"  [{generated+1}/{min(len(plan), args.max_cases)}] {feature.get('feature','?')}")
        print(f"  Goal: {feature.get('goal','?')}")
        print(f"{'─'*60}")

        # Up to 3 attempts per feature
        ok = False
        for attempt in range(3):
            if attempt > 0:
                print(f"\n  Retry {attempt+1}/3 for '{feature.get('feature','?')}'...")
            try:
                ok = explore_one_case(framework, case_name, cases_dir, bugs_dir, feature)
                if ok:
                    break
            except Exception as e:
                print(f"  CRASH in explore_one_case: {e}")
                import traceback
                traceback.print_exc()
                # If a case.yaml was saved before the crash, keep it
                case_yaml_path = cases_dir / case_name / "case.yaml"
                if case_yaml_path.exists():
                    print(f"  Case already saved before crash, keeping it")
                    ok = True
                    break
            print(f"  Attempt {attempt+1} failed")

        if ok:
            # Generate bug script for this case
            case_yaml_path = cases_dir / case_name / "case.yaml"
            if case_yaml_path.exists():
                case_yaml = case_yaml_path.read_text(encoding="utf-8")
                bug_code = generate_bug(framework, case_yaml, case_name)
                if bug_code:
                    save_bug(bug_code, bugs_dir / case_name)
                    print(f"  Bug generated: {bugs_dir / case_name / 'bug.js'}")

            generated += 1
            next_index += 1
            print(f"\n  {generated}/{len(plan)} features done")
        else:
            print(f"  Failed '{feature.get('feature','?')}' after 3 attempts, skipping")
            generated += 1   # move to next feature in plan
            next_index += 1  # consume the case number slot

    print(f"\n{'='*60}")
    print(f"  DONE: {generated} case(s) generated")
    print(f"  Cases: {cases_dir}")
    print(f"  Bugs : {bugs_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
