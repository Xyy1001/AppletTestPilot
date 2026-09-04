#!/usr/bin/env python3
"""
AppletTestPilot — End-to-End Experiment Runner.

Runs test cases with and without bug injection, then computes evaluation metrics.

Modes:
  --mode task_completion  : Run all cases WITHOUT bugs (measure pass rate)
  --mode bug_detection    : Run all cases WITH bugs (measure precision/recall/F1)
  --mode full             : Run both task_completion and bug_detection (default)

Usage:
  python experiments/run_experiment.py --cases input/cases
  python experiments/run_experiment.py --cases input/cases --bugs input/bugs
  python experiments/run_experiment.py --cases input/cases --mode bug_detection
  python experiments/run_experiment.py --cases input/cases --runs 3
  python experiments/run_experiment.py --cases input/cases --output experiments/results
"""

import sys
import io
import time
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from applettestpilot.config import Config
from applettestpilot.clients.minium import connect_minium
from applettestpilot.phase2_execute import run_one_test, run_batch

from experiments.metrics import (
    load_results_from_dir,
    generate_report,
    print_report,
)

PROJECT = Path(__file__).parent.parent

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("experiment")


def run_experiment(
    cases_dir: Path,
    bugs_dir: Path | None,
    output_dir: Path,
    mode: str,
    num_runs: int,
) -> Path:
    """Run the experiment and return the output directory with results.

    Args:
        cases_dir: Directory with case_*/case.yaml files.
        bugs_dir: Directory with case_*/bug.js files (required for bug_detection mode).
        output_dir: Root output directory.
        mode: "task_completion", "bug_detection", or "full".
        num_runs: Number of repeat runs for stability measurement.

    Returns:
        The output directory containing all run results.
    """
    config = Config.load(PROJECT / "config.yaml")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    exp_dir = output_dir / f"experiment_{timestamp}"
    exp_dir.mkdir(parents=True, exist_ok=True)

    # Save experiment config
    exp_config = {
        "mode": mode,
        "num_runs": num_runs,
        "cases_dir": str(cases_dir),
        "bugs_dir": str(bugs_dir) if bugs_dir else None,
        "timestamp": timestamp,
    }
    (exp_dir / "experiment_config.json").write_text(
        json.dumps(exp_config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    modes_to_run = []
    if mode == "full":
        modes_to_run = ["task_completion", "bug_detection"]
    else:
        modes_to_run = [mode]

    all_outputs: list[Path] = []

    for current_mode in modes_to_run:
        inject_bugs = (current_mode == "bug_detection")

        if inject_bugs and not bugs_dir:
            print("  WARNING: No bugs directory provided, skipping bug_detection mode")
            continue

        print(f"\n{'=' * 60}")
        print(f"  MODE: {current_mode}")
        print(f"  Runs: {num_runs}  |  Bugs: {inject_bugs}")
        print(f"{'=' * 60}")

        mode_dir = exp_dir / current_mode
        mode_dir.mkdir(parents=True, exist_ok=True)

        for run_idx in range(num_runs):
            run_label = f"run_{run_idx + 1}"
            run_dir = mode_dir / run_label
            run_dir.mkdir(parents=True, exist_ok=True)

            print(f"\n  [{current_mode}] {run_label}...")

            use_bugs = bugs_dir if inject_bugs else None
            try:
                passed, failed, summary = run_batch(cases_dir, use_bugs, run_dir)
                all_outputs.append(run_dir)
                print(f"    -> {passed} passed, {failed} failed")
            except Exception as e:
                print(f"    -> ERROR: {e}")
                import traceback
                traceback.print_exc()

            if run_idx < num_runs - 1:
                time.sleep(1)

    # Generate evaluation report
    print(f"\n{'=' * 60}")
    print(f"  GENERATING EVALUATION REPORT")
    print(f"{'=' * 60}")

    df = load_results_from_dir(exp_dir)
    if not df.empty:
        report = generate_report(df, exp_dir)
        print_report(report)

    return exp_dir


def main():
    parser = argparse.ArgumentParser(
        description="AppletTestPilot — End-to-End Experiment Runner"
    )
    parser.add_argument(
        "--cases", type=Path, required=True,
        help="Directory with case_*/case.yaml test cases"
    )
    parser.add_argument(
        "--bugs", type=Path, default=None,
        help="Directory with case_*/bug.js bug scripts"
    )
    parser.add_argument(
        "--output", type=Path, default=PROJECT / "experiments" / "results",
        help="Root output directory for experiment results"
    )
    parser.add_argument(
        "--mode", type=str, default="full",
        choices=["task_completion", "bug_detection", "full"],
        help="Experiment mode (default: full = both)"
    )
    parser.add_argument(
        "--runs", type=int, default=1,
        help="Number of repeat runs for stability measurement (default: 1)"
    )
    args = parser.parse_args()

    if not args.cases.exists():
        print(f"ERROR: Cases directory not found: {args.cases}")
        sys.exit(1)

    if args.mode in ("bug_detection", "full") and not args.bugs:
        print(f"NOTE: No --bugs directory specified. Bug detection will be skipped.")
        if args.mode == "bug_detection":
            print("ERROR: --bugs is required for bug_detection mode")
            sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  APPLETTESTPILOT — EXPERIMENT RUNNER")
    print(f"  Cases : {args.cases}")
    print(f"  Bugs  : {args.bugs or '(none)'}")
    print(f"  Mode  : {args.mode}")
    print(f"  Runs  : {args.runs}")
    print(f"  Output: {args.output}")
    print(f"{'=' * 60}")

    result_dir = run_experiment(
        cases_dir=args.cases,
        bugs_dir=args.bugs,
        output_dir=args.output,
        mode=args.mode,
        num_runs=args.runs,
    )

    print(f"\n  Experiment complete!")
    print(f"  Results: {result_dir}")
    print(f"  Report : {result_dir / 'evaluation_report.json'}")


if __name__ == "__main__":
    main()
