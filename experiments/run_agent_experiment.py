#!/usr/bin/env python3
"""
Agent-based Experiment Runner — uses the new MiniTestAgent architecture.

Usage:
  python experiments/run_agent_experiment.py --task create_merchant
  python experiments/run_agent_experiment.py --task full_flow --runs 3
  python experiments/run_agent_experiment.py --benchmark all --output results/agent_v1
"""

import sys
import io
import os
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
_ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(_ENV_PATH)

from applettestpilot.core import (
    MiniProgramEnv, EnvConfig,
    MiniTestAgent, AgentConfig, AgentResult,
)
from applettestpilot.core.benchmark import STANDARD_TASKS, BenchmarkTask
from applettestpilot.core.world_model import load_world_model

PROJECT = Path(__file__).parent.parent.resolve()
_WEB_ENABLED = False
logging.basicConfig(level=logging.WARNING)

# ── Load world model once ──
_SOURCE_PATH = PROJECT / "objects" / "TestApplet"
_WORLD_MODEL = None
if _SOURCE_PATH.exists():
    print("  Loading world model...")
    _WORLD_MODEL = load_world_model(str(_SOURCE_PATH))
    print(f"  World model: {len(_WORLD_MODEL.source_files)} source files, "
          f"{len(_WORLD_MODEL.page_routes)} pages, "
          f"{len(_WORLD_MODEL.storage_keys)} storage keys")
else:
    print(f"  WARNING: Source path not found: {_SOURCE_PATH}")


def run_agent_task(env: MiniProgramEnv, task: BenchmarkTask,
                   world_model=None) -> AgentResult:
    """Run a single benchmark task with the Agent."""
    config = AgentConfig(
        max_steps=task.max_steps,
        assertion_enabled=True,
        vlm_enabled=True,
        goal=task.description,
        world_model=world_model,
    )
    agent = MiniTestAgent(env, config)
    if _WEB_ENABLED:
        from applettestpilot.web_ui.hooks import install_hooks
        install_hooks(agent)
    return agent.run(goal=task.description, setup_function=task.setup_function)


def save_results(result: AgentResult, task: BenchmarkTask, output_dir: Path) -> Path:
    """Persist agent results to disk."""
    run_dir = output_dir / task.id / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "task": {
            "id": task.id, "name": task.name, "difficulty": task.difficulty.value,
            "setup": task.setup_function,
        },
        "result": {
            "task_completed": result.task_completed,
            "total_steps": result.total_steps,
            "successful_steps": result.successful_steps,
            "failed_steps": result.failed_steps,
            "bug_count": result.bug_count,
            "total_duration_s": round(result.total_duration_s, 1),
            "total_tokens": result.total_tokens,
        },
        "coverage": result.coverage,
        "steps": [
            {
                "step": s.step_index,
                "action": s.action.to_nl(),
                "reasoning": s.action.reasoning,
                "passed": s.failure is None,
                "oracle_layer": s.oracle_result.layer if s.oracle_result else "none",
                "duration_s": round(s.duration_s, 1),
                "tokens": s.tokens_used,
            }
            for s in result.steps
        ],
        "failures": [
            {
                "step": s.step_index,
                "category": s.failure.category.value,
                "severity": s.failure.severity,
                "hypothesis": s.failure.root_cause_hypothesis,
            }
            for s in result.steps if s.failure
        ],
    }

    (run_dir / "agent_result.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if result.memory:
        result.memory.save(run_dir / "memory_graph.json")

    return run_dir


def main():
    parser = argparse.ArgumentParser(description="Agent-based Experiment Runner")
    parser.add_argument("--task", type=str, default="create_merchant",
                        help="Task ID from benchmark (or 'all')")
    parser.add_argument("--runs", type=int, default=1,
                        help="Number of repeat runs per task")
    parser.add_argument("--output", type=Path,
                        default=PROJECT / "experiments" / "results" / "agent",
                        help="Output directory")
    parser.add_argument("--web", action="store_true",
                        help="Launch interactive web UI (http://127.0.0.1:9120)")
    parser.add_argument("--web-port", type=int, default=9120,
                        help="Web UI port (default 9120)")
    args = parser.parse_args()

    tasks = STANDARD_TASKS
    if args.task != "all":
        tasks = [t for t in STANDARD_TASKS if t.id == args.task]
        if not tasks:
            print(f"Unknown task: {args.task}")
            print(f"Available: {[t.id for t in STANDARD_TASKS]}")
            sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  AGENT-BASED EXPERIMENT")
    print(f"  Tasks: {len(tasks)} | Runs per task: {args.runs}")
    print(f"  Output: {output_dir}")
    if args.web:
        print(f"  Web UI : http://127.0.0.1:{args.web_port}")
    print(f"{'='*60}")

    # ── start web UI if requested ──
    if args.web:
        global _WEB_ENABLED
        _WEB_ENABLED = True
        from applettestpilot.web_ui import start_server as start_web
        start_web(port=args.web_port)

    # ── connect once ──
    # Resolve paths from environment (set by .env), with sensible defaults.
    _proj = os.getenv("WX_PROJECT_PATH", "") or str(PROJECT / "objects" / "TestApplet")
    _dev  = os.getenv("WX_DEVTOOLS_PATH", "")
    _port = int(os.getenv("WX_TEST_PORT", "37985"))

    print(f"  Project : {_proj}")
    if _dev:
        print(f"  DevTools: {_dev}")
    print(f"  Port    : {_port}")

    env = MiniProgramEnv(EnvConfig(
        project_path=_proj,
        dev_tool_path=_dev,
        test_port=_port,
    ))
    try:
        env.connect()
    except Exception as e:
        print(f"ERROR: Could not connect to DevTools: {e}")
        print(f"  Check: 1) DevTools is installed  2) WX_PROJECT_PATH is correct  3) Port {_port} is open")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    all_results: list[dict] = []

    for task in tasks:
        print(f"\n{'─'*60}")
        print(f"  Task: {task.name} [{task.difficulty.value}]")
        print(f"  Setup: {task.setup_function} | Max steps: {task.max_steps}")
        print(f"{'─'*60}")

        for run_idx in range(args.runs):
            if args.runs > 1:
                print(f"\n  Run {run_idx + 1}/{args.runs}...")

            try:
                result = run_agent_task(env, task, world_model=_WORLD_MODEL)
                run_dir = save_results(result, task, output_dir)
                status = "PASS" if result.task_completed else "FAIL"
                print(f"  -> {status} | {result.total_steps} steps | "
                      f"{result.bug_count} bugs | {result.total_duration_s:.0f}s")

                all_results.append({
                    "task": task.id,
                    "run": run_idx + 1,
                    "completed": result.task_completed,
                    "steps": result.total_steps,
                    "bugs": result.bug_count,
                    "duration_s": round(result.total_duration_s, 1),
                    "tokens": result.total_tokens,
                    "coverage": result.coverage,
                })
            except Exception as e:
                print(f"  -> ERROR: {e}")
                import traceback
                traceback.print_exc()

    # ── summary ──
    print(f"\n{'='*60}")
    print(f"  EXPERIMENT SUMMARY")
    print(f"{'='*60}")
    completed = sum(1 for r in all_results if r["completed"])
    print(f"  Task completion: {completed}/{len(all_results)} ({completed/len(all_results)*100:.0f}%)" if all_results else "  No results")
    if all_results:
        avg_steps = sum(r["steps"] for r in all_results) / len(all_results)
        avg_time = sum(r["duration_s"] for r in all_results) / len(all_results)
        print(f"  Avg steps: {avg_steps:.1f} | Avg time: {avg_time:.0f}s")

    env.disconnect()


if __name__ == "__main__":
    main()
