#!/usr/bin/env python3
"""
AppletTestPilot — Evaluation CLI.

Computes metrics from result.json files produced by Phase 2 test runs.

Usage:
  python experiments/evaluate.py --results outputs/
  python experiments/evaluate.py --results outputs/ --output metrics/
  python experiments/evaluate.py --results outputs/ --csv metrics/results.csv
"""

import sys
import io
import argparse
from pathlib import Path

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.metrics import (
    load_results_from_dir,
    load_batch_summaries,
    compute_task_completion,
    compute_correct_trace,
    compute_bug_detection,
    compute_duration_stats,
    compute_token_stats,
    compute_stability,
    generate_report,
    print_report,
)


def main():
    parser = argparse.ArgumentParser(
        description="AppletTestPilot — Evaluate test results"
    )
    parser.add_argument(
        "--results", type=Path, required=True,
        help="Directory containing run output (with result.json files)"
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output directory for evaluation report (JSON + CSV)"
    )
    parser.add_argument(
        "--csv", type=Path, default=None,
        help="Export raw results as CSV to this path"
    )
    args = parser.parse_args()

    results_dir = Path(args.results)
    if not results_dir.exists():
        print(f"ERROR: Results directory not found: {results_dir}")
        sys.exit(1)

    print(f"Loading results from: {results_dir}")

    # Load all result.json files
    df = load_results_from_dir(results_dir)

    if df.empty:
        print("ERROR: No result.json files found in the results directory.")
        print("Expected structure: results/run_*/case_*/result.json")
        sys.exit(1)

    print(f"  Loaded {len(df)} step results from {df['case_name'].nunique()} cases "
          f"across {df['run_id'].nunique()} runs")

    # Also try loading batch summaries
    summaries = load_batch_summaries(results_dir)
    if summaries:
        total_cases = sum(s.get("total", 0) for s in summaries)
        total_passed = sum(s.get("passed", 0) for s in summaries)
        print(f"  Batch summaries: {len(summaries)} runs, {total_passed}/{total_cases} passed")

    # Generate full report
    output_dir = args.output or (results_dir / "evaluation")
    report = generate_report(df, output_dir)

    # Print report
    print_report(report)

    # Export CSV if requested
    if args.csv:
        csv_path = Path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv_path, index=False)
        print(f"  CSV exported: {csv_path}")

    print(f"  Report saved: {output_dir / 'evaluation_report.json'}")


if __name__ == "__main__":
    main()
