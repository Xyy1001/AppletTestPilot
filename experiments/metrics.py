"""
Evaluation metrics for AppletTestPilot experiments.

Metrics computed:
  - Task Completion Rate (per test case, aggregated)
  - Correct Trace Score (consecutive correct steps from start)
  - Bug Detection: Precision, Recall, F1
  - Duration statistics (per step, per test case)
  - Token usage statistics
  - Stability metrics (variance, Fleiss-Kappa)
"""

import json
from pathlib import Path
from typing import Any
from collections import defaultdict

import pandas as pd


# ═══════════════════════════════════════════════════════════════════════════
# Data loading
# ═══════════════════════════════════════════════════════════════════════════

def load_results_from_dir(results_dir: Path) -> pd.DataFrame:
    """Scan a directory tree for result.json files and load into a DataFrame.

    Expected structure:
        results_dir/
          run_1/
            case_01/result.json
            case_02/result.json
          run_2/
            ...

    Returns DataFrame with columns:
        run_id, case_name, step_id, action, expectation,
        is_action_correct, is_bug_reported, duration, tokens
    """
    rows: list[dict] = []

    for run_dir in sorted(results_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        run_name = run_dir.name

        for result_path in sorted(run_dir.rglob("result.json")):
            try:
                data = json.loads(result_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                continue

            case_name = result_path.parent.name
            test_case = data.get("test_case", {})
            steps: list[dict] = data.get("steps", [])

            for i, step in enumerate(steps, 1):
                step_info = step.get("step", {})
                rows.append({
                    "run_id": run_name,
                    "case_name": case_name,
                    "test_name": test_case.get("name", case_name),
                    "setup_function": test_case.get("setup_function", ""),
                    "step_id": i,
                    "action": step_info.get("action", ""),
                    "expectation": step_info.get("expectation", ""),
                    "is_action_correct": step.get("is_action_correct", False),
                    "is_bug_reported": step.get("is_bug_reported", False),
                    "duration": step.get("end_time", 0) - step.get("start_time", 0),
                    "tokens": step.get("tokens", 0),
                })

    return pd.DataFrame(rows)


def load_batch_summaries(results_dir: Path) -> list[dict]:
    """Load batch_summary.json files from run directories."""
    summaries = []
    for summary_path in sorted(results_dir.rglob("batch_summary.json")):
        try:
            summaries.append(json.loads(summary_path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, IOError):
            pass
    return summaries


# ═══════════════════════════════════════════════════════════════════════════
# Task Completion
# ═══════════════════════════════════════════════════════════════════════════

def compute_task_completion(df: pd.DataFrame) -> pd.DataFrame:
    """Compute task completion rate per case and overall.

    Task completion = all steps in a test case have is_action_correct=True.

    Returns a DataFrame with:
      - Per-case completion rate
      - Overall completion rate
    """
    if df.empty:
        return pd.DataFrame()

    task_completion = (
        df.groupby(["run_id", "case_name", "test_name"])["is_action_correct"]
        .all()
        .astype(int)
        .reset_index(name="task_completed")
    )

    # Per-case rate
    per_case = (
        task_completion.groupby("case_name")["task_completed"]
        .mean()
        .reset_index()
    )
    per_case.columns = ["case_name", "completion_rate"]

    # Overall
    overall = task_completion["task_completed"].mean()

    return per_case, overall


# ═══════════════════════════════════════════════════════════════════════════
# Correct Trace Score
# ═══════════════════════════════════════════════════════════════════════════

def compute_correct_trace(df: pd.DataFrame) -> pd.DataFrame:
    """Compute correct trace score: fraction of consecutive correct steps.

    For each test case, count consecutive correct steps from the start
    until the first failure, divided by total steps.
    """
    if df.empty:
        return pd.DataFrame()

    def progress_score(steps: pd.Series) -> float:
        consecutive = 0
        for correct in steps:
            if correct:
                consecutive += 1
            else:
                break
        return consecutive / len(steps) if len(steps) > 0 else 0.0

    progress = (
        df.groupby(["run_id", "case_name"])["is_action_correct"]
        .apply(progress_score)
        .reset_index(name="trace_score")
    )

    per_case = (
        progress.groupby("case_name")["trace_score"]
        .mean()
        .reset_index()
    )

    overall = progress["trace_score"].mean()
    return per_case, overall


# ═══════════════════════════════════════════════════════════════════════════
# Bug Detection Metrics
# ═══════════════════════════════════════════════════════════════════════════

def compute_bug_detection(df: pd.DataFrame) -> dict:
    """Compute bug detection precision, recall, F1.

    The last step of each test case is the expected bug-triggering step.
    A true positive = bug reported on the last step.
    """
    if df.empty:
        return {"precision": 0, "recall": 0, "f1": 0}

    # Identify last step per test case
    df = df.copy()
    df["is_last_step"] = df.groupby(
        ["run_id", "case_name"]
    )["step_id"].transform("max") == df["step_id"]

    tp = int((df["is_bug_reported"] & df["is_last_step"]).sum())
    fp = int((df["is_bug_reported"] & ~df["is_last_step"]).sum())
    fn = int((~df["is_bug_reported"] & df["is_last_step"]).sum())

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Duration & Token Statistics
# ═══════════════════════════════════════════════════════════════════════════

def compute_duration_stats(df: pd.DataFrame) -> dict:
    """Compute duration statistics per step and per test case."""
    if df.empty:
        return {}

    step_duration = df.groupby("case_name")["duration"].describe().round(3)
    case_duration = (
        df.groupby(["run_id", "case_name"])["duration"]
        .sum()
        .reset_index()
        .groupby("case_name")["duration"]
        .describe()
        .round(3)
    )

    overall_step = df["duration"].describe().round(3)
    overall_case = (
        df.groupby(["run_id", "case_name"])["duration"]
        .sum()
        .describe()
        .round(3)
    )

    return {
        "per_step": step_duration,
        "per_case": case_duration,
        "overall_step_stats": overall_step.to_dict(),
        "overall_case_stats": overall_case.to_dict(),
        "total_duration": df["duration"].sum(),
    }


def compute_token_stats(df: pd.DataFrame) -> dict:
    """Compute token usage statistics."""
    if df.empty:
        return {}

    tokens_per_step = df.groupby("case_name")["tokens"].describe().round(1)
    tokens_per_case = (
        df.groupby(["run_id", "case_name"])["tokens"]
        .sum()
        .reset_index()
        .groupby("case_name")["tokens"]
        .describe()
        .round(1)
    )

    return {
        "per_step": tokens_per_step,
        "per_case": tokens_per_case,
        "total_tokens": int(df["tokens"].sum()),
        "mean_tokens_per_step": round(df["tokens"].mean(), 1),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Stability Metrics
# ═══════════════════════════════════════════════════════════════════════════

def compute_stability(df: pd.DataFrame) -> dict:
    """Compute stability metrics across runs.

    - Correct Trace Variance: variance of per-step correctness rate per test case
    - Task Completion Variance: variance of binary task completion per test case
    - Fleiss-Kappa: inter-run agreement on step correctness
    """
    if df.empty:
        return {}

    num_runs = df["run_id"].nunique()

    # Correct Trace Variance
    frac_correct = (
        df.groupby(["run_id", "case_name"])["is_action_correct"]
        .mean()
    )
    correct_trace_var = float(frac_correct.var(ddof=0)) if len(frac_correct) > 1 else 0.0

    # Task Completion Variance
    task_completed = (
        df.groupby(["run_id", "case_name"])["is_action_correct"]
        .all()
        .astype(int)
    )
    task_completion_var = float(task_completed.var(ddof=0)) if len(task_completed) > 1 else 0.0

    # Fleiss-Kappa (only meaningful with multiple runs)
    # Uses per-step-level agreement across runs.
    # Each unique (case_name, step_id) is a subject; each run is a rater.
    fleiss = None
    if num_runs > 1:
        try:
            from statsmodels.stats.inter_rater import fleiss_kappa

            # Find common (case, step) pairs that appear in ALL runs
            run_ids = sorted(df["run_id"].unique())
            common_pairs = None
            for rid in run_ids:
                run_df = df[df["run_id"] == rid]
                pairs = set(zip(run_df["case_name"], run_df["step_id"]))
                if common_pairs is None:
                    common_pairs = pairs
                else:
                    common_pairs &= pairs

            if common_pairs:
                kappa_matrix = []
                for (case, step_id) in sorted(common_pairs):
                    grp = df[(df["case_name"] == case) & (df["step_id"] == step_id)]
                    n_pass = int(grp["is_action_correct"].sum())
                    n_fail = len(grp) - n_pass
                    kappa_matrix.append([n_fail, n_pass])

                if kappa_matrix and len(kappa_matrix) >= 2:
                    fleiss = round(float(fleiss_kappa(kappa_matrix)), 4)
        except (ImportError, AssertionError, Exception):
            fleiss = None
    else:
        fleiss = 1.0

    return {
        "correct_trace_variance": round(correct_trace_var, 4),
        "task_completion_variance": round(task_completion_var, 4),
        "fleiss_kappa": fleiss,
        "num_runs": num_runs,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Full report generation
# ═══════════════════════════════════════════════════════════════════════════

def generate_report(df: pd.DataFrame, output_dir: Path | None = None) -> dict:
    """Generate a complete evaluation report from result data.

    Returns a dict with all metrics, and optionally writes JSON report.
    """
    per_case_completion, overall_completion = compute_task_completion(df)
    per_case_trace, overall_trace = compute_correct_trace(df)
    bug_metrics = compute_bug_detection(df)
    duration_stats = compute_duration_stats(df)
    token_stats = compute_token_stats(df)
    stability = compute_stability(df)

    report = {
        "summary": {
            "total_runs": int(df["run_id"].nunique()) if not df.empty else 0,
            "total_cases": int(df["case_name"].nunique()) if not df.empty else 0,
            "total_steps": len(df),
            "task_completion_rate": round(float(overall_completion), 4) if not df.empty else 0,
            "correct_trace_score": round(float(overall_trace), 4) if not df.empty else 0,
            "total_duration_s": round(float(df["duration"].sum()), 1) if not df.empty else 0,
            "total_tokens": int(df["tokens"].sum()) if not df.empty else 0,
        },
        "task_completion": {
            "overall": round(float(overall_completion), 4) if not df.empty else 0,
            "per_case": per_case_completion.to_dict("records") if not per_case_completion.empty else [],
        },
        "correct_trace": {
            "overall": round(float(overall_trace), 4) if not df.empty else 0,
            "per_case": per_case_trace.to_dict("records") if not per_case_trace.empty else [],
        },
        "bug_detection": bug_metrics,
        "duration": {
            "overall_step_stats": duration_stats.get("overall_step_stats", {}),
            "overall_case_stats": duration_stats.get("overall_case_stats", {}),
        },
        "tokens": {
            "total": token_stats.get("total_tokens", 0),
            "mean_per_step": token_stats.get("mean_tokens_per_step", 0),
        },
        "stability": stability,
    }

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "evaluation_report.json"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        # Also export CSV
        if not df.empty:
            df.to_csv(output_dir / "raw_results.csv", index=False)

    return report


def print_report(report: dict) -> None:
    """Print a formatted evaluation report to stdout."""
    s = report["summary"]
    bug = report["bug_detection"]
    dur = report["duration"]
    tok = report["tokens"]
    stab = report["stability"]

    print("\n" + "=" * 60)
    print("  APPLETTESTPILOT — EVALUATION REPORT")
    print("=" * 60)

    print(f"\n  Summary")
    print(f"  {'─' * 40}")
    print(f"  Runs: {s['total_runs']}  |  Cases: {s['total_cases']}  |  Steps: {s['total_steps']}")
    print(f"  Task Completion Rate : {s['task_completion_rate']:.2%}")
    print(f"  Correct Trace Score  : {s['correct_trace_score']:.2%}")
    print(f"  Total Duration       : {s['total_duration_s']:.1f}s")
    print(f"  Total Tokens         : {s['total_tokens']:,}")

    print(f"\n  Bug Detection")
    print(f"  {'─' * 40}")
    print(f"  TP={bug.get('tp', 0)}  FP={bug.get('fp', 0)}  FN={bug.get('fn', 0)}")
    print(f"  Precision : {bug.get('precision', 0):.2%}")
    print(f"  Recall    : {bug.get('recall', 0):.2%}")
    print(f"  F1 Score  : {bug.get('f1', 0):.2%}")

    print(f"\n  Duration")
    print(f"  {'─' * 40}")
    os_stats = dur.get("overall_step_stats", {})
    oc_stats = dur.get("overall_case_stats", {})
    print(f"  Per step  — mean: {os_stats.get('mean', 0):.1f}s  |  std: {os_stats.get('std', 0):.1f}s")
    print(f"  Per case  — mean: {oc_stats.get('mean', 0):.1f}s  |  std: {oc_stats.get('std', 0):.1f}s")

    print(f"\n  Tokens")
    print(f"  {'─' * 40}")
    print(f"  Total        : {tok.get('total', 0):,}")
    print(f"  Mean / step  : {tok.get('mean_per_step', 0):.0f}")

    print(f"\n  Stability")
    print(f"  {'─' * 40}")
    print(f"  Correct Trace Var    : {stab.get('correct_trace_variance', 'N/A')}")
    print(f"  Task Completion Var  : {stab.get('task_completion_variance', 'N/A')}")
    print(f"  Fleiss-Kappa         : {stab.get('fleiss_kappa', 'N/A')}")

    print(f"\n  Per-Case Breakdown")
    print(f"  {'─' * 60}")
    tc = report.get("task_completion", {}).get("per_case", [])
    ct = {c["case_name"]: c["trace_score"] for c in report.get("correct_trace", {}).get("per_case", [])}
    for case in tc:
        name = case.get("case_name", "?")
        cr = case.get("completion_rate", 0)
        ts = ct.get(name, 0)
        print(f"  {name:<20s}  completion: {cr:.2%}  trace: {ts:.2%}")

    print(f"\n{'=' * 60}\n")
