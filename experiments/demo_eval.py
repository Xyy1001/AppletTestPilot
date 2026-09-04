#!/usr/bin/env python3
"""
Quick demo: run evaluation on existing output data.

Usage:
  D:/anaconda3/envs/applet/python.exe experiments/demo_eval.py
  D:/anaconda3/envs/applet/python.exe experiments/demo_eval.py --results outputs/
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.metrics import load_results_from_dir, generate_report, print_report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Demo: Evaluate existing test results")
    parser.add_argument("--results", type=Path, default=Path(__file__).parent.parent / "outputs",
                        help="Directory with result.json files")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output directory for report")
    args = parser.parse_args()

    results_dir = Path(args.results)
    output_dir = args.output or (results_dir / "evaluation")

    print(f"Scanning: {results_dir}")
    df = load_results_from_dir(results_dir)

    if df.empty:
        print("No result.json files found.")
        print("Expected: results_dir/run_*/case_*/result.json")
        return

    report = generate_report(df, output_dir)
    print_report(report)
    print(f"Report saved to: {output_dir / 'evaluation_report.json'}")


if __name__ == "__main__":
    main()
