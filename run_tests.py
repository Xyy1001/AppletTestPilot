#!/usr/bin/env python3
"""
Phase 2 — Test Execution.

Runs test cases with bug injection and structured terminal output.

Usage:
  python run_tests.py --mode single --case input/cases/case_01/case.yaml
  python run_tests.py --mode single --case input/cases/case_01/case.yaml --bug input/bugs/case_01/bug.js
  python run_tests.py --mode batch --cases input/cases
  python run_tests.py --mode batch --cases input/cases --bugs input/bugs
  python run_tests.py --mode batch --cases input/cases --only 1,3,5-7
  python run_tests.py --mode batch --cases input/cases --output results/run1
  python run_tests.py --mode batch --cases input/cases --no-log
"""

import sys
import io
import time
import argparse
import logging
from pathlib import Path

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from applettestpilot.config import Config
from applettestpilot.clients.minium import connect_minium
from applettestpilot.phase2_execute import run_one_test, run_batch

PROJECT = Path(__file__).parent


def setup_logging(log_dir: Path | None = None):
    """Configure agent logging. If log_dir is set, also write output.log."""

    # Brute-force suppress Minium + HTTP noise (Minium creates its own
    # handlers before this script runs; root filters can't catch them).
    _NOISY = ("minium", "urllib3", "httpx", "httpcore",
              "zai", "websockets", "asyncio", "PIL")
    for _name in list(logging.root.manager.loggerDict.keys()):
        if any(_name.startswith(p) for p in _NOISY):
            _lg = logging.getLogger(_name)
            _lg.setLevel(logging.CRITICAL)
            _lg.handlers.clear()
            _lg.propagate = False
    _orig = logging.getLogger
    def _quiet(name):
        _lg = _orig(name)
        if any(name.startswith(p) for p in _NOISY):
            _lg.setLevel(logging.CRITICAL)
            _lg.handlers.clear()
            _lg.propagate = False
        return _lg
    logging.getLogger = _quiet

    fmt = logging.Formatter("%(message)s")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(logging.INFO)

    for name in ("applettestpilot", "runner", "explorer"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        lg.handlers.clear()
        lg.addHandler(console)

    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "output.log"
        fh = logging.FileHandler(log_path, encoding="utf-8", mode="w")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"))
        fh.setLevel(logging.DEBUG)
        for name in ("applettestpilot", "runner", "explorer"):
            logging.getLogger(name).addHandler(fh)
        print(f"  Log: {log_path}")


def main():
    parser = argparse.ArgumentParser(description="Phase 2 — Run Tests")
    parser.add_argument("--mode", type=str, required=True,
                        choices=["single", "batch"],
                        help="Test mode: single case or batch")
    parser.add_argument("--case", type=Path,
                        help="(mode=single) Path to case.yaml")
    parser.add_argument("--bug", type=Path,
                        help="(mode=single) Path to bug.js")
    parser.add_argument("--cases", type=Path,
                        help="(mode=batch) Directory containing case_*/case.yaml")
    parser.add_argument("--bugs", type=Path,
                        help="(mode=batch) Directory containing case_*/bug.js (auto-matched)")
    parser.add_argument("--only", type=str,
                        help="(mode=batch) Filter: 1,3,5-7")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output directory (default: ./outputs)")
    parser.add_argument("--no-log", action="store_true",
                        help="Disable output.log")
    args = parser.parse_args()

    if args.mode == "single" and not args.case:
        parser.error("--case is required for --mode single")
    if args.mode == "batch" and not args.cases:
        parser.error("--cases is required for --mode batch")

    config = Config.load(PROJECT / "config.yaml")
    output_dir = args.output or (PROJECT / "outputs")
    log_dir = output_dir if not args.no_log else None

    setup_logging(log_dir)

    print(f"\n{'='*60}")
    print(f"  PHASE 2 — Test Execution")
    print(f"  Mode  : {args.mode}")
    if args.mode == "single":
        print(f"  Case  : {args.case}")
        if args.bug:
            print(f"  Bug   : {args.bug}")
    else:
        print(f"  Cases : {args.cases}")
        if args.bugs:
            print(f"  Bugs  : {args.bugs}")
    print(f"  Output: {output_dir}")
    print(f"{'='*60}")

    if args.mode == "batch":
        run_batch(args.cases, args.bugs, output_dir, args.only)
        return

    # Single mode
    mini = connect_minium()
    run_one_test(mini, config, args.case, args.bug, output_dir)


if __name__ == "__main__":
    main()
