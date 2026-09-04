"""
Flask server for the Agent interactive web UI.

Endpoints:
  GET  /             — HTML frontend
  GET  /events       — SSE event stream
  GET  /api/config   — default paths from .env
  POST /api/analyze  — LLM analyzes world model, returns test plan
  POST /api/start    — start Agent (mode: "full" or "step")
  POST /api/next     — continue to next task in step mode
  POST /api/stop     — stop Agent
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from flask import Flask, request, jsonify, send_file

from .events import get_event_stream, AgentEvent, EventType

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_TEMPLATE_DIR = Path(__file__).parent / "templates"
_INDEX_PATH = _TEMPLATE_DIR / "index.html"

app = Flask(__name__)
app.logger.setLevel(logging.WARNING)


def _default_tasks_from_wm(wm) -> list[dict]:
    """Generate fallback test tasks from the world model when LLM fails."""
    tasks = []
    routes = wm.page_routes if wm else []
    has_merchant_page = any("join" in r for r in routes)
    has_product_page = any("product_edit" in r for r in routes)
    has_cart = any("cart" in r for r in routes)
    has_detail = any("detail" in r for r in routes)
    if has_merchant_page:
        tasks.append({"id": "task_1", "name": "创建商家账户", "goal": "从首页点击创建商家,填写商家名称/手机号/简介,点击保存,验证返回首页", "setup": "launch_home"})
    if has_product_page:
        tasks.append({"id": "task_2", "name": "上传产品", "goal": "在有商家的状态下进入产品编辑页,填写产品名称/价格/描述,点击保存产品,验证返回", "setup": "launch_home_with_merchant"})
    if has_detail:
        tasks.append({"id": "task_3", "name": "浏览商品详情", "goal": "点击产品进入详情页,验证标题/价格/描述显示正确", "setup": "launch_home_with_merchant_and_product"})
    if has_cart:
        tasks.append({"id": "task_4", "name": "加入购物车", "goal": "在详情页调整数量,点击加入购物车,切换到购物车Tab验证商品存在", "setup": "launch_home_with_merchant_and_product"})
    tasks.append({"id": "task_5", "name": "提交评论", "goal": "在详情页输入评论内容,点击发布评论,验证评论出现在列表中", "setup": "launch_home_with_merchant_and_product"})
    return tasks


# ── global state ──
_agent_thread: threading.Thread | None = None
_step_event = threading.Event()   # signaled when user clicks "next" in step mode
_step_mode = False


@app.after_request
def _no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/")
def index():
    # send_file bypasses Jinja2 — no {{ }} template conflicts
    return send_file(str(_INDEX_PATH), mimetype="text/html; charset=utf-8")


@app.route("/events")
def events():
    stream = get_event_stream()
    def generate():
        # Heartbeat so frontend immediately knows the connection is alive
        import json as _json
        yield f"data: {_json.dumps({'type':'connected','msg':'SSE connected'})}\n\n"
        for event in stream:
            yield event.to_sse()
        yield f"data: {_json.dumps({'type':'closed'})}\n\n"
    return app.response_class(
        generate(), mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


def _resolve_source_path(source: str) -> Path | None:
    """Resolve a user-supplied source path.  Tries multiple patterns.

    1. If absolute → use as-is.
    2. Relative to project root.
    3. Prefixed with ``objects/`` (common layout).
    4. Basename match inside ``objects/``.
    Returns the first existing path, or None.
    """
    if os.path.isabs(source):
        p = Path(source)
        if p.exists(): return p

    candidates = [
        _PROJECT_ROOT / source,
        _PROJECT_ROOT / "objects" / source,
    ]
    # Also try basename match under objects/
    objs = _PROJECT_ROOT / "objects"
    if objs.exists():
        for d in objs.iterdir():
            if d.is_dir() and d.name == source:
                candidates.append(d)
    for c in candidates:
        if c.exists():
            return c
    return None


@app.route("/api/config", methods=["GET"])
def api_config():
    return jsonify({"source": "objects/TestApplet", "output": "outputs"})


@app.route("/api/projects", methods=["GET"])
def api_projects():
    """List available source directories under objects/."""
    projects = ["objects/TestApplet"]
    objs = _PROJECT_ROOT / "objects"
    if objs.exists():
        projects = []
        for d in sorted(objs.iterdir()):
            if d.is_dir() and (d / "src").exists():
                rel = str(d.relative_to(_PROJECT_ROOT)).replace("\\", "/")
                projects.append(rel)
    if not projects:
        projects = ["objects/TestApplet"]
    return jsonify({"projects": projects, "default": projects[0]})


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Run LLM analysis on the world model, return a test plan."""
    data = request.get_json(silent=True) or {}
    source = data.get("source", "objects/TestApplet")
    src_path = _resolve_source_path(source)

    try:
        import sys; sys.path.insert(0, str(_PROJECT_ROOT))
        from dotenv import load_dotenv; load_dotenv(_PROJECT_ROOT / ".env")
        from applettestpilot.core.world_model import load_world_model
        from openai import OpenAI

        if not src_path:
            return jsonify({"error": f"Source path not found. Tried: '{source}'. Check that the directory exists under AppletTestPilot/ or provide an absolute path."})
        wm = load_world_model(str(src_path))
        if not wm:
            return jsonify({"error": f"Failed to load world model from: {src_path}"})

        logger.info("analyze: src_path=%s, design=%d chars, req=%d chars, framework=%d chars, source_files=%d",
                     src_path, len(wm.design_doc), len(wm.requirements_doc), len(wm.framework_doc), len(wm.source_files))

        llm = OpenAI(
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com"),
            api_key=os.getenv("OPENAI_API_KEY", ""),
        )
        model = os.getenv("OPENAI_MODEL_NAME", "deepseek-v4-flash")

        # Use larger context — DESIGN.md alone is ~8K chars, plus REQUIREMENTS + FRAMEWORK
        wm_ctx = wm.build_context(max_chars=12000)
        logger.info("analyze: context built, %d chars", len(wm_ctx))

        prompt = f"""You are analyzing a WeChat Mini Program to create a testing plan.
Below is the complete design document, requirements, framework overview, and source code summary.

# App Knowledge
{wm_ctx}

# Task
Based on ALL the information above, create a structured testing plan.
Output ONLY a valid JSON object (no markdown, no explanation outside the JSON):

{{
  "plan": "A clear, step-by-step summary of the testing strategy (in Chinese, 2-4 sentences). Include what will be tested, the sequence, and key verifications.",
  "tasks": [
    {{"id": "task_1", "name": "任务名称", "goal": "详细的任务目标描述(含具体操作步骤和验证点)", "setup": "launch_home"}}
  ]
}}

# Rules
- Cover ALL major features: merchant creation (with input validation), product upload/edit, cart add/remove/clear, favorites toggle, comments submit, product delete.
- Order tasks by dependency (merchant first, then products, then cart/favorites/comments/delete).
- Each task goal must include: WHICH page to start from, WHAT to click/type, WHAT to expect (toast messages, page changes, element visibility).
- Use the exact button labels and field names from the design doc (e.g. "创建商家", "商家名称", "保存", "上传产品").
- Use setup functions: launch_home, launch_home_with_merchant, launch_home_with_merchant_and_product, launch_home_with_merchant_and_product_in_cart.
- Include at least 6 tasks.
- Output ONLY the JSON object. No markdown code blocks. No explanations outside the JSON.
"""

        resp = llm.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}], temperature=0.3, max_tokens=4096)
        raw = resp.choices[0].message.content or ""

        # ── Robust JSON extraction ──
        import re
        plan_text = raw
        tasks = []

        # Try extracting JSON from response
        content = raw
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
        if m: content = m.group(1)
        brace = content.find('{')
        if brace >= 0:
            depth = 0; end = brace
            for i, ch in enumerate(content[brace:], brace):
                if ch == '{': depth += 1
                elif ch == '}': depth -= 1
                if depth == 0: end = i + 1; break
            content = content[brace:end]

        try:
            parsed = json.loads(content)
            plan_text = parsed.get("plan", raw[:800])
            tasks = parsed.get("tasks", [])
        except (json.JSONDecodeError, ValueError):
            # LLM returned plain text — use it as the plan and create default tasks
            plan_text = raw.strip() or "(LLM returned empty response — using default plan)"
            logger.warning("LLM returned non-JSON, using raw text as plan")

        # Ensure we always have tasks — fallback based on world model pages
        if not tasks:
            tasks = _default_tasks_from_wm(wm)

        return jsonify({"plan": plan_text, "tasks": tasks})
    except Exception as e:
        logger.exception("analyze failed")
        return jsonify({"error": str(e)})


@app.route("/api/start", methods=["POST"])
def api_start():
    global _agent_thread
    if _agent_thread is not None and _agent_thread.is_alive():
        return jsonify({"error": "Agent already running"}), 409

    data = request.get_json(silent=True) or {}
    source = data.get("source", "objects/TestApplet")
    screenshots = data.get("screenshots", "outputs/screenshots")
    output = data.get("output", "outputs")
    mode = data.get("mode", "full")
    tasks = data.get("tasks", [])

    src_path = _resolve_source_path(source)
    if not src_path:
        return jsonify({"error": f"Source path not found: '{source}'. Check the directory or use an absolute path."})

    global _step_mode
    _step_mode = (mode == "step" and len(tasks) > 0)

    def _run():
        import sys; sys.path.insert(0, str(_PROJECT_ROOT))
        from dotenv import load_dotenv; load_dotenv(_PROJECT_ROOT / ".env")
        from applettestpilot.core import MiniProgramEnv, EnvConfig, MiniTestAgent, AgentConfig
        from applettestpilot.core.world_model import load_world_model
        from applettestpilot.web_ui.hooks import install_hooks

        try:
            wm = load_world_model(str(src_path))
            env = MiniProgramEnv(EnvConfig(project_path=str(src_path)))
            env.connect()

            stream = get_event_stream()

            if _step_mode:
                # ── step-by-step mode ──
                for idx, task in enumerate(tasks):
                    stream.emit(AgentEvent(event_type=EventType.SESSION_START, step_index=idx + 1,
                        message=f"Task {idx+1}/{len(tasks)}: {task.get('name','')}",
                        detail={"goal": task.get("goal", ""), "setup": task.get("setup", "launch_home")}))

                    agent = MiniTestAgent(env, AgentConfig(
                        max_steps=min(task.get("max_steps", 20), 20), goal=task.get("goal", ""),
                        world_model=wm, screenshot_dir=str(_PROJECT_ROOT / screenshots),
                    ))
                    install_hooks(agent)
                    result = agent.run(goal=task.get("goal", ""), setup_function=task.get("setup", "launch_home"))

                    # Save per-task result
                    _save_result(result, _PROJECT_ROOT / output, task.get("id", f"task_{idx+1}"))

                    if idx < len(tasks) - 1:
                        stream.emit(AgentEvent(event_type=EventType.STEP_PAUSED, step_index=idx + 1,
                            message=f"Task {idx+1}/{len(tasks)} complete. Waiting for user to continue.",
                            detail={"taskIndex": idx + 1, "totalTasks": len(tasks), "taskName": task.get("name", "")}))
                        # Wait for user to click "next"
                        _step_event.clear()
                        _step_event.wait(timeout=600)  # 10 min timeout
                        if not _step_event.is_set():
                            break  # user stopped or timeout

                stream.emit(AgentEvent(event_type=EventType.SESSION_END,
                    message=f"All {len(tasks)} tasks complete."))
            else:
                # ── full-flow mode (single agent run) ──
                agent = MiniTestAgent(env, AgentConfig(
                    max_steps=40, goal=tasks[0].get("goal","") if tasks else "Explore all features",
                    world_model=wm, screenshot_dir=str(_PROJECT_ROOT / screenshots),
                ))
                install_hooks(agent)
                goal = tasks[0].get("goal", "Explore all features") if tasks else "Explore all features"
                setup = tasks[0].get("setup", "launch_home") if tasks else "launch_home"
                result = agent.run(goal=goal, setup_function=setup)
                _save_result(result, _PROJECT_ROOT / output, "full_flow")

            stream.close()
            env.disconnect()
        except Exception as exc:
            logger.exception("Agent crashed")
            stream = get_event_stream()
            stream.emit(AgentEvent(event_type=EventType.ERROR, message=f"Agent crashed: {exc}"))
            stream.close()
        finally:
            global _agent_thread; _agent_thread = None

    _agent_thread = threading.Thread(target=_run, daemon=True)
    _agent_thread.start()
    return jsonify({"status": "started", "mode": mode})


@app.route("/api/next", methods=["POST"])
def api_next():
    """Signal the step-mode agent to continue to the next task."""
    _step_event.set()
    return jsonify({"status": "running"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    _step_event.set()  # unblock if waiting
    stream = get_event_stream(); stream.close()
    return jsonify({"status": "stopped"})


def start_server(host: str = "127.0.0.1", port: int = 9120):
    t = threading.Thread(
        target=lambda: app.run(host=host, port=port, debug=False,
                               use_reloader=False, threaded=True),
        daemon=True,
    )
    t.start()
    return f"http://{host}:{port}"


def _save_result(result, out_dir: Path, task_id: str):
    import time as _time
    out_dir = out_dir / task_id; out_dir.mkdir(parents=True, exist_ok=True)
    ts = _time.strftime("%Y%m%d_%H%M%S")
    run_dir = out_dir / f"web_{ts}"; run_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "task": {"id": task_id, "description": result.steps[0].action.to_nl() if result.steps else ""},
        "result": {"task_completed": result.task_completed, "total_steps": result.total_steps, "bug_count": result.bug_count, "total_duration_s": round(result.total_duration_s, 1), "total_tokens": result.total_tokens},
        "coverage": result.coverage,
        "steps": [{"step": s.step_index, "action": s.action.to_nl(), "passed": s.failure is None, "duration_s": round(s.duration_s, 1)} for s in result.steps],
    }
    (run_dir / "agent_result.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if result.memory: result.memory.save(run_dir / "memory_graph.json")
