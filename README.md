# AppletTestPilot

**LLM-based Autonomous GUI Testing Agent for WeChat Mini Programs**

AI-Native 自主 GUI 测试智能体系统。采用 **Hybrid Agent 架构**（符号系统 + LLM 推理 + 图记忆 + 运行时信号），通过 Minium 驱动微信开发者工具，实现对小程序的全自主探索、规划、验证与缺陷发现。

核心能力：自主理解 GUI → 自主规划测试 → 自主探索页面 → 自主生成 Oracle → 自主发现异常 → 学习历史经验 → 长链路任务执行 → 多轮状态推理。

---

## 系统架构（v2.0 — AI-Native Agent）

```
                           ┌──────────────────────┐
                           │   MiniTestAgent       │
                           │   (agent.py)          │
                           │   ┌────────────────┐  │
                           │   │  Agent Loop     │  │
                           │   │  observe→plan   │  │
                           │   │  →execute→      │  │
                           │   │  observe→verify │  │
                           │   │  →memorize      │  │
                           │   └──────┬─────────┘  │
                           └──────────┼────────────┘
                  ┌───────────────────┼───────────────────┐
                  │                   │                   │
          ┌───────┴───────┐  ┌───────┴───────┐  ┌───────┴───────┐
          │   Planner     │  │   Oracle      │  │   Memory      │
          │   (planner.py)│  │   (oracle.py) │  │   (memory.py) │
          │               │  │               │  │               │
          │ LLM-based     │  │ Multi-layer:  │  │ Navigation    │
          │ Graph-guided  │  │ • Structural  │  │ Graph         │
          │ Symbolic      │  │ • Visual(VLM) │  │ Transitions   │
          │ constraints   │  │ • Semantic    │  │ Failures      │
          └───────┬───────┘  └───────┬───────┘  └───────┬───────┘
                  │                   │                   │
          ┌───────┴───────────────────┴───────────────────┴───────┐
          │                    GUIState                           │
          │    screenshot | ui_tree | route | elements | logs     │
          └───────────────────────┬───────────────────────────────┘
                                  │
          ┌───────────────────────┴───────────────────────────────┐
          │               MiniProgramEnv (env.py)                  │
          │         observe() | execute() | reset()                │
          └───────────────────────┬───────────────────────────────┘
                                  │
                          ┌───────┴───────┐
                          │    Minium     │
                          │  (DevTools)   │
                          └───────────────┘
```

### 模块职责

| 模块 | 文件 | 职责 |
|------|------|------|
| **MiniProgramEnv** | `core/env.py` | Minium 环境抽象：连接/断开/观测/执行/重置 |
| **GUIState** | `core/state.py` | 统一页面快照：截图 + UI树 + 路由 + 元素 + 日志 |
| **Action** | `core/action.py` | 形式化动作定义 + 按页面角色的动作白名单 |
| **AgentMemory** | `core/memory.py` | 导航图 + 转换边 + 失败模式 + 探索统计 |
| **Planner** | `core/planner.py` | LLM 决策 + 图引导 + 符号约束的混合规划器 |
| **Oracle** | `core/oracle.py` | 4 层验证：结构化 → 视觉(VLM) → 语义(LLM) → 工作流 |
| **MiniTestAgent** | `core/agent.py` | 顶层 Agent：集成全部模块的主循环 |
| **FailureAnalyzer** | `core/analyzer.py` | 多信号融合的根因归属引擎 |
| **Benchmark** | `core/benchmark.py` | 9 个标准化测试任务 + 难度分级 |

### Agent Loop（核心循环）

```python
# MiniTestAgent.run() 的主循环
for step in range(max_steps):
    action = planner.plan(state, memory, goal)     # LLM 决策
    env.execute(action)                             # Minium 执行
    after = GUIState.from_env_observation(env.observe())  # 观测
    result = oracle.verify(before, after, action)   # 多层验证
    memory.record_step(...)                         # 记忆更新
    memory.record_page(...)                         # 图节点更新
    memory.record_transition(...)                   # 边更新
    if result.failed:
        failure = analyzer.analyze(after, action, result.message, memory)
```

## 项目结构

```
AppletTestPilot/
├── explore_and_test.py              # 阶段一入口：探索式用例生成
├── run_tests.py                     # 阶段二入口：用例执行与缺陷验证
├── generate_test_cases.py           # 独立工具：传统一次性 YAML 生成
├── config.yaml                      # 配置文件
├── .env                             # 环境变量（API Key、路径等）
├── requirements.txt                 # Python 依赖
│
├── applettestpilot/                 # 核心引擎包
│   ├── __init__.py                  # 公共 API 导出
│   ├── config.py                    # 配置数据类
│   ├── orchestrator.py              # 测试编排器：条件→动作→断言循环（v1 兼容）
│   │
│   ├── core/                        # ★ v2.0 AI-Native Agent 架构
│   │   ├── __init__.py              # 全部模块导出
│   │   ├── env.py                   # MiniProgramEnv — 环境抽象层
│   │   ├── state.py                 # GUIState — 统一页面快照
│   │   ├── action.py                # Action / ActionType / ActionSpace
│   │   ├── memory.py                # AgentMemory — 导航图 + 失败模式
│   │   ├── planner.py               # Planner — LLM+图+符号混合规划
│   │   ├── oracle.py                # Oracle — 4 层语义验证
│   │   ├── agent.py                 # MiniTestAgent — 顶层 Agent 主循环
│   │   ├── analyzer.py              # FailureAnalyzer — 多信号根因分析
│   │   ├── benchmark.py             # 9 个标准化测试任务
│   │   └── world_model.py           # WorldModel — 被测应用知识加载
│   │
│   ├── web_ui/                      # ★ Web UI 实时监控面板
│   │   ├── __init__.py              # 包导出
│   │   ├── events.py                # AgentEvent + SSE 事件流
│   │   ├── server.py                # Flask 服务器 + /events 端点
│   │   ├── hooks.py                 # Agent 循环钩子注入
│   │   ├── web_agent.py             # 一键启动入口
│   │   └── templates/
│   │       └── index.html           # 交互前端 (单文件)
│   │
│   ├── models/                      # 数据模型
│   │   ├── step.py                  # Step（单一定义）
│   │   ├── session.py               # Session（Minium 会话管理）
│   │   ├── state.py                 # State（页面状态快照）
│   │   ├── page.py                  # Page（逻辑页面标识）
│   │   ├── element.py               # Element（UI 元素模型）
│   │   └── result.py                # TestCase / TestResult / BugReport
│   │
│   ├── clients/                     # 外部客户端
│   │   ├── minium.py                # Minium 连接 + 页面截图包装器
│   │   ├── vision.py                # GLM-4.1V 视觉模型客户端
│   │   └── llm.py                   # DeepSeek LLM 客户端工厂
│   │
│   ├── action_api/                  # 动作执行层
│   │   ├── click.py                 # 点击策略（4 级回退）
│   │   ├── input.py                 # 输入策略（多级输入框定位）
│   │   ├── scroll.py                # 滚动/滑动策略（scroll down/up、scroll to element）
│   │   ├── navigation.py            # Tab 切换 + 返回导航
│   │   └── locators.py              # 元素查找工具 + 弹窗检测
│   │
│   ├── assertion_api/               # 断言验证层
│   │   ├── direct.py                # 快速直接检查（Page ID）
│   │   ├── oracle.py                # VLM+LLM 断言生成流水线
│   │   └── sandbox.py               # 代码沙箱执行器 + 变量追踪
│   │
│   ├── phase1_generate/             # 阶段一：探索与生成
│   │   ├── planner.py               # 功能分析 → 测试计划
│   │   ├── explorer.py              # 逐步探索引擎
│   │   ├── case_builder.py          # YAML 加载/保存/验证
│   │   ├── bug_generator.py         # Bug 脚本生成
│   │   └── prompts.py               # 阶段一所有 Prompt 模板
│   │
│   └── phase2_execute/              # 阶段二：执行与验证
│       ├── runner.py                # 单例/批量测试执行器
│       └── prompts.py               # 阶段二 Prompt 模板
│
├── TestApplet/                      # 被测小程序（含 FRAMEWORK.md）
├── benchmark/                       # 测试基准 + setup 函数
├── input/                           # 阶段一产物
│   ├── cases/<name>/case.yaml       #   验证通过的测试用例
│   └── bugs/<name>/bug.js           #   对应的缺陷注入脚本
└── outputs/                         # 阶段二产物
    ├── <case>/result.json           #   测试结果
    ├── <case>/trace.json            #   操作轨迹
    └── <case>/history.json          #   页面快照序列
```

## 双模型角色

| 模型 | 用途 | 阶段 |
|------|------|------|
| DeepSeek-v4 (语言) | 理解源码架构、分析 VLM 页面描述、决策下一步动作、生成 YAML 用例、失败修复、Bug 生成、判断测试是否通过 | 阶段一 + 二 |
| GLM-4.1V (视觉) | 观察截图、解析页面元素组成/名称/位置/关系、将视觉理解结果传给语言模型 | 阶段一 + 二 |

## 工作流

```
阶段一：探索 + 生成                         阶段二：执行
LLM 学习源码 → 逐步探索 → 构建用例              加载用例 → 注入 Bug → 执行验证
  │                                              │
  ├── 每步：VLM 观察 → LLM 决策 → Minium 执行      ├── --mode single --case <path>
  ├── 成功 → 加入用例列表                            ├── --mode batch  --cases <dir>
  ├── 失败 → 尝试其他路径                            └── --output <dir>
  ├── 全量验证 100% PASS → 保存 case.yaml
  └── 生成对应 bug.js
```

### 断言流程（双模型协作）

```
verify_postcondition
  │
  ├─ Page ID? → 直接比对（0ms）
  │
  └─ 其他 → 双模型协作
       │
       ├─ Step 1: GLM-4.1V 分析截图
       │   Prompt: "Describe page, CRITICAL: dialogs/modals..."
       │   Output: "Dialog '确认删除' with buttons '确定'/'取消'..."
       │   （弹窗类动作优先用 pyautogui 屏幕截图，可捕获原生对话框）
       │   （等待 0.5s 确保原生弹窗完全渲染）
       │
       ├─ Step 2: DeepSeek-v4 生成断言代码
       │   Input:  VLM 页面描述 + 历史 + 动作 + 断言要求
       │   Output: ```python def postcondition(session): ... ```
       │
       └─ Step 3: sandbox 沙箱执行
            from __future__ import annotations
            exec → 函数查找 → sys.settrace 变量追踪
```

## 配置参数完全参考

### 1. 环境变量（`.env`）

项目根目录 `AppletTestPilot/.env`，所有入口脚本自动加载。

#### 语言模型（DeepSeek）

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `OPENAI_BASE_URL` | 是 | `https://api.deepseek.com` | LLM API 地址（兼容 OpenAI 协议） |
| `OPENAI_API_KEY` | 是 | — | API 密钥 |
| `OPENAI_MODEL_NAME` | 否 | `deepseek-v4-flash` | 模型名称。可选：`deepseek-v4-flash`（推荐）、`deepseek-chat`、`deepseek-reasoner` |

#### 视觉模型（GLM-4.1V / ZhipuAI）

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `GUI_GROUNDING_MODEL_BASE_URL` | 否 | `https://open.bigmodel.cn/api/paas/v4` | 视觉模型 API 地址 |
| `GUI_GROUNDING_MODEL_NAME` | 否 | `glm-4.1v-thinking-flashx` | 视觉模型名称 |
| `GUI_GROUNDING_MODEL_API_KEY` | 是 | — | 智谱 AI API 密钥 |

#### Minium / 微信开发者工具连接

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `WX_PROJECT_PATH` | 是 | — | 小程序项目根目录（含 `project.config.json`）的绝对路径 |
| `WX_DEVTOOLS_PATH` | 是 | — | 微信开发者工具 CLI 路径。Windows 示例：`D:\微信web开发者工具\cli.bat`；macOS 示例：`/Applications/wechatwebdevtools.app/Contents/MacOS/cli` |
| `WX_TEST_PORT` | 否 | `37985` | 开发者工具服务端口。需与 DevTools「设置 → 安全 → 服务端口」一致 |
| `APPLET_USE_REAL_MINIUM` | 否 | — | 设为 `1` 启用真实 Minium 连接 |

#### 截图配置

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `APPLET_SCREENSHOT_REGION` | 否 | (无) | pyautogui 屏幕截图的裁剪区域。格式：`left,top,width,height`（像素）。仅截取模拟器窗口区域，避免全屏截图过大。不设则使用 Minium 视口截图 |
| `APPLET_SCREENSHOT_BACKEND` | 否 | `minium` | 截图后端。`minium`：仅截取小程序视口（无法捕获原生弹窗）；`pyautogui`：屏幕级截图（可捕获 `wx.showModal` 等原生对话框，需配合 `APPLET_SCREENSHOT_REGION`） |

---

### 2. 引擎配置（`config.yaml`）

`AppletTestPilot/config.yaml`，v1 和 v2 共用。

```yaml
# 截图后端: "minium" (默认) 或 "pyautogui" (可捕获原生弹窗)
screenshot_backend: "minium"

executor:
  max_tries: 3           # 断言生成最大重试次数（每次失败后 LLM 重新生成代码）
  max_step_retries: 1    # 步骤级瞬态错误重试次数（0 = 禁用，仅重试连接超时等瞬态错误）

# VLM 视觉模型（GLM-4.1V 截图分析）
vlm:
  model: ""              # 空字符串 = 使用 GUI_GROUNDING_MODEL_NAME 环境变量
  temperature: 0.3       # 生成温度 (0.0-1.0)，越低越确定性
  max_tokens: 1024       # 最大输出 Token 数

# LLM 断言代码生成
llm_assertion:
  model: ""              # 空字符串 = 使用 OPENAI_MODEL_NAME 环境变量
  temperature: 0.3
  max_tokens: 1024
  max_retries: 3         # API 调用空响应重试次数

# LLM 探索动作提议（Phase 1 explore_and_test.py）
llm_explore:
  model: ""
  temperature: 0.5       # 探索阶段需要更高的创造性
  max_tokens: 512
  max_retries: 3

# LLM 测试用例生成（Phase 1 generate_test_cases.py）
llm_generate:
  model: ""
  temperature: 0.7       # 生成阶段需要最高的创造性
  max_tokens: 4096
  max_retries: 3
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `screenshot_backend` | `str` | `"minium"` | 截图后端选择 |
| `executor.max_tries` | `int` | `3` | Oracle 断言代码生成失败后的最大重试次数 |
| `executor.max_step_retries` | `int` | `1` | 每步动作执行失败（连接超时等瞬态错误）的最大重试次数。Bug/断言失败不重试 |
| `vlm.temperature` | `float` | `0.3` | VLM 视觉描述的温度参数 |
| `vlm.max_tokens` | `int` | `1024` | VLM 单次最大输出 Token |
| `llm_assertion.temperature` | `float` | `0.3` | 断言代码生成的温度（低温度保证准确性） |
| `llm_assertion.max_tokens` | `int` | `1024` | 断言代码最大 Token |
| `llm_assertion.max_retries` | `int` | `3` | LLM 空响应重试次数 |
| `llm_explore.temperature` | `float` | `0.5` | 探索阶段温度（适中） |
| `llm_explore.max_tokens` | `int` | `512` | 探索动作提议最大 Token |
| `llm_generate.temperature` | `float` | `0.7` | 用例生成温度（高创造性） |
| `llm_generate.max_tokens` | `int` | `4096` | 用例生成最大 Token |

---

### 3. v2 Agent 配置（`AgentConfig`）

编程调用时通过 `AgentConfig` 数据类传入。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_steps` | `int` | `50` | Agent 最大执行步数。达到此步数后强制终止循环 |
| `max_step_retries` | `int` | `1` | 每步动作执行失败的重试次数 |
| `assertion_enabled` | `bool` | `True` | 是否启用 Oracle 验证。设为 `False` 则跳过所有验证 |
| `vlm_enabled` | `bool` | `True` | 是否启用 VLM 截图描述。设为 `False` 则跳过视觉层 Oracle |
| `goal` | `str` | `"Explore all features..."` | 自然语言任务目标，传递给 Planner 作为探索指引 |
| `screenshot_dir` | `str` | `""` | 截图保存目录。空字符串使用默认临时目录 |
| `world_model` | `WorldModel \| None` | `None` | 被测应用的世界知识。通过 `load_world_model(source_path)` 加载 |

**编程示例：**

```python
from applettestpilot.core import MiniTestAgent, AgentConfig
from applettestpilot.core.world_model import load_world_model

wm = load_world_model("objects/TestApplet")

agent = MiniTestAgent(env, AgentConfig(
    max_steps=20,
    max_step_retries=0,
    assertion_enabled=True,
    vlm_enabled=True,
    goal="Test merchant creation: create merchant, upload product, add to cart",
    world_model=wm,
))
result = agent.run()
```

---

### 4. 环境配置（`EnvConfig`）

通过 `MiniProgramEnv(EnvConfig(...))` 传入。若 `.env` 已配置 `WX_PROJECT_PATH` 等变量，可不传。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `project_path` | `str` | `""` | 小程序项目路径。空字符串 = 使用 `WX_PROJECT_PATH` 环境变量 |
| `dev_tool_path` | `str` | `""` | 开发者工具 CLI 路径。空字符串 = 使用 `WX_DEVTOOLS_PATH` 环境变量 |
| `test_port` | `int` | `37985` | 调试端口。若环境变量 `WX_TEST_PORT` 存在则优先生效 |
| `request_timeout` | `int` | `20` | Minium WebSocket 请求超时（秒） |
| `remote_connect_timeout` | `int` | `20` | 远程调试连接超时（秒） |
| `auto_relaunch` | `bool` | `True` | 小程序运行态重启时是否自动恢复连接 |
| `page_ready_timeout` | `float` | `45.0` | 连接后等待首页就绪的最长时间（秒）。超时抛 `RuntimeError` |

---

### 5. Planner 参数（`Planner.__init__`）

通常由 `MiniTestAgent` 内部创建，也可独立使用。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `llm_client` | `OpenAI` | (必传) | OpenAI 兼容的 LLM 客户端实例 |
| `model` | `str` | `"deepseek-v4-flash"` | 规划用的 LLM 模型 |
| `temperature` | `float` | `0.4` | 规划温度。0.4 在创造性和确定性之间取得平衡 |
| `world_model` | `WorldModel \| None` | `None` | 被测应用知识。非 None 时预构建 system prompt（~6K chars） |

---

### 6. Benchmark Task 参数（`BenchmarkTask`）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `str` | 是 | 任务唯一标识，如 `create_merchant` |
| `name` | `str` | 是 | 任务显示名称 |
| `description` | `str` | 是 | 自然语言任务描述，直接作为 Agent 的 `goal` |
| `setup_function` | `str` | 否 | 预置数据函数。可选：`launch_home`（空启动）、`launch_home_with_merchant`、`launch_home_with_merchant_and_product`、`launch_home_with_merchant_and_product_in_cart` |
| `difficulty` | `TaskDifficulty` | 否 | `easy`（≤4 步）/ `medium`（5-8 步）/ `hard`（≥9 步） |
| `min_steps` | `int` | `3` | 预期最少步数，用于 Agent 的 `max_steps` 下限 |
| `max_steps` | `int` | `15` | 预期最多步数，直接作为 Agent 的 `max_steps` |
| `expected_pages` | `list[str]` | 否 | 预期覆盖的页面路由列表 |
| `expected_actions` | `list[str]` | 否 | 预期使用的动作类型列表 |
| `bug_injection_target` | `str \| None` | 否 | Bug 注入目标步骤的方法名 |

---

### 7. CLI 参数完全参考

#### `explore_and_test.py`（v1 Phase 1 — 探索式用例生成）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--source` | `Path` | `./TestApplet` | 被测小程序源码目录（含 `FRAMEWORK.md`） |
| `--output` | `Path` | `./input` | 产物根目录。其下自动创建 `cases/` 和 `bugs/` 子目录 |
| `--max-cases` | `int` | `99` | 最大生成用例数（安全上限，实际数量由 LLM 根据源码功能数决定） |
| `--log` | `Path` | (无) | 日志输出路径。无后缀时自动追加 `output.log`。替代 PowerShell `>` 重定向（避免 UTF-8 乱码） |

#### `run_tests.py`（v1 Phase 2 — 测试执行）

| 参数 | 模式 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--mode` | **必选** | `str` | — | `single`（单例）或 `batch`（批量） |
| `--case` | single | `Path` | — | case.yaml 文件路径 |
| `--bug` | single | `Path` | — | bug.js 文件路径（可选） |
| `--cases` | batch | `Path` | — | 包含 `case_*/case.yaml` 的目录 |
| `--bugs` | batch | `Path` | — | 包含 `case_*/bug.js` 的目录（可选，自动按 case 名称匹配） |
| `--only` | batch | `str` | — | 筛选用例编号。格式：`"1,3,5-7"` |
| `--output` | 通用 | `Path` | `./outputs` | 结果输出目录 |
| `--no-log` | 通用 | flag | `False` | 禁用 `output.log` 文件输出 |

#### `generate_test_cases.py`（v1 传统 YAML 生成）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--count` | `int` | `3` | 生成用例数量 |
| `--focus` | `str` | (无) | 聚焦领域：`merchant` / `product` / `cart` / `favorite` / `comment` / `edge` |
| `--output-dir` | `Path` | `benchmark/testapplet/test_cases/` | 输出目录 |

#### `run_agent_experiment.py`（v2 Agent 实验运行器）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--task` | `str` | `create_merchant` | 任务 ID。可选：`create_merchant` / `upload_product` / `add_to_cart` / `toggle_favorite` / `submit_comment` / `delete_product` / `edit_product` / `clear_cart` / `full_flow` / `all`（全部 9 个任务） |
| `--runs` | `int` | `1` | 每个任务的重复运行次数。≥2 时可计算稳定性指标（Fleiss-Kappa） |
| `--output` | `Path` | `experiments/results/agent` | 输出目录。任务结果写入 `<output>/<task_id>/<timestamp>/` |
| `--web` | flag | `False` | 启用 Web UI 实时监控面板（`http://127.0.0.1:9120`） |
| `--web-port` | `int` | `9120` | Web UI 端口号 |

#### `evaluate.py`（v1 评测 CLI）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--results` | `Path` | (必传) | 包含 `run_*/case_*/result.json` 的结果目录 |
| `--output` | `Path` | `<results>/evaluation` | 评测报告输出目录。生成 `evaluation_report.json` + `raw_results.csv` |
| `--csv` | `Path` | (无) | 额外导出原始数据 CSV 的路径 |

#### `run_experiment.py`（v1 实验运行器）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--cases` | `Path` | (必传) | 包含 `case_*/case.yaml` 的目录 |
| `--bugs` | `Path` | (无) | 包含 `case_*/bug.js` 的目录（仅 bug_detection/full 模式需要） |
| `--output` | `Path` | `experiments/results` | 实验输出根目录 |
| `--mode` | `str` | `full` | `task_completion`（无 Bug）/ `bug_detection`（有 Bug）/ `full`（两者） |
| `--runs` | `int` | `1` | 每个模式的重复运行次数 |

---

### 8. 配置优先级

当同一参数可从多个来源获取时，优先级为：

```
AgentConfig / EnvConfig (编程传入)
  > config.yaml (文件配置)
    > .env (环境变量)
      > 代码默认值
```

特殊规则：
- `WX_PROJECT_PATH`、`WX_DEVTOOLS_PATH`、`WX_TEST_PORT`：`EnvConfig` 中的显式值会覆盖环境变量
- LLM 模型名称：`config.yaml` 中 `model: ""` 表示回退到 `.env` 的对应变量

---

## 环境准备

```powershell
conda create -n applet python=3.12 -y
conda activate applet
pip install openai pillow pydantic python-dotenv pyyaml minium pyautogui
pip install zai-sdk          # 智谱 AI SDK（视觉模型）
pip install flask            # Web UI 服务器（可选）
pip install pandas statsmodels  # 评测指标（可选）
```

## 配置 .env

```ini
# 语言模型（用例生成/决策/修复）
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL_NAME=deepseek-v4-flash

# 视觉模型（截图断言）
GUI_GROUNDING_MODEL_BASE_URL=https://open.bigmodel.cn/api/paas/v4
GUI_GROUNDING_MODEL_NAME=glm-4.1v-thinking-flashx
GUI_GROUNDING_MODEL_API_KEY=your-key

# 微信开发者工具
WX_PROJECT_PATH=E:\WebTestPilot\AppletTestPilot\TestApplet
WX_DEVTOOLS_PATH=D:\微信web开发者工具\cli.bat
WX_TEST_PORT=37985

# 截图区域 (left,top,width,height) — pyautogui 屏幕截图裁剪区域
# 仅截取微信开发者工具模拟器窗口，避免全屏截图过大
# 不设则截全屏（也能正常捕获原生弹窗）
# APPLET_SCREENSHOT_REGION=300,150,400,720
```

## 运行

### Agent 模式（v2.0 推荐）— 编程调用

```python
from applettestpilot.core import (
    MiniProgramEnv, MiniTestAgent, AgentConfig
)

# 1. 启动环境
env = MiniProgramEnv()
env.connect()

# 2. 创建 Agent
agent = MiniTestAgent(env, AgentConfig(
    max_steps=20,
    goal="Test merchant creation flow: create merchant, upload product, add to cart",
))

# 3. 自主执行
result = agent.run()

# 4. 查看结果
print(f"Completed: {result.task_completed}")
print(f"Steps: {result.total_steps} | Bugs: {result.bug_count}")
print(f"Coverage: {result.coverage}")

# 5. 访问记忆
memory = agent.memory
for route, node in memory.pages.items():
    print(f"  {route}: visited {node.visit_count}x [{node.semantic_role}]")
for edge in memory.edges:
    print(f"  {edge.src_route} --{edge.action}--> {edge.dst_route}")

env.disconnect()
```

### Agent 实验运行

```powershell
# 运行单个任务
python AppletTestPilot\experiments\run_agent_experiment.py --task create_merchant

# 运行全部 benchmark 任务
python AppletTestPilot\experiments\run_agent_experiment.py --task all --runs 3

# 运行长链路任务
python AppletTestPilot\experiments\run_agent_experiment.py --task full_flow --runs 2

# 运行 + Web UI 实时监控
python AppletTestPilot\experiments\run_agent_experiment.py --task all --web --web-port 9120

# 一键启动 WebAgent
D:\anaconda3\envs\applet\python.exe -m applettestpilot.web_ui.web_agent --task create_merchant --port 9120
```

### Web UI — 实时 Agent 交互式测试面板

**核心工作流（唯一正确路径）：**

```
 打开网页 → 初始化 LLM + VLM
    │
    ├─ 用户配置：源码目录 / 截图输出目录 / 结果输出目录
    │
    ├─ 点击 [🔍 分析规划]
    │    └─ 后端：load_world_model() → 源码 + FRAMEWORK.md + REQUIREMENTS.md + DESIGN.md
    │       └─ LLM 生成测试方案 → 返回 {plan, tasks}
    │          └─ 前端弹窗展示方案
    │
    ├─ 用户选择执行模式：
    │    ├─ [全流程端到端自动测试] → Agent 连续执行全部步骤 → 输出完整报告
    │    └─ [逐个交互式测试] → 每完成一个阶段暂停
    │         └─ 显示反馈输入框 → 用户决定：
    │              ├─ 输入反馈 + 点击"发送" → 继续下一个
    │              ├─ 直接点击"下一个" → 跳过继续
    │              └─ 点击"停止" → 结束测试
    │
    └─ 结果自动保存到输出目录
```

**启动方式：**

```powershell
# 推荐：一键启动 Web UI（独立模式，前端控制完整流程）
D:\anaconda3\envs\applet\python.exe -m applettestpilot.web_ui.web_agent --port 9120

# 或者：实验运行器附带的 Web 监控（适合批量实验）
D:\anaconda3\envs\applet\python.exe AppletTestPilot\experiments\run_agent_experiment.py --task all --web
```

打开浏览器访问 `http://127.0.0.1:9120`。

**界面布局：**

```
┌──────────────────────────────────────────────────────────────────────┐
│  控制面板                                                             │
│  源码 [objects/TestApplet] [浏览] 截图 [outputs/screenshots] [浏览]   │
│  输出 [outputs] [浏览]                                               │
│  [🔍 分析规划]  [▶ 逐个测试]  [▶ 全流程]  [⏭ 下一个]  [⏹ 停止]  [↺ 清空]│
│                                            ● 运行中  Step 3  1m23s   │
├──────────────────────────────────────────────┬───────────────────────┤
│  左侧：Agent 思考与行动日志                    │  右侧：实时状态截图      │
│                                              │                       │
│  ANALYSIS  LLM 测试方案已生成 (6 个测试任务)    │  ┌───────────────┐    │
│  ── Step 1 ──                                │  │               │    │
│  20:13:05  OBSERVE                           │  │   PNG 截图     │    │
│  Page: /pages/index/index [home]             │  │   自动更新     │    │
│    route: /pages/index/index                 │  │               │    │
│    role: home  ·  vlm: "Title '商品展示'..." │  └───────────────┘    │
│                                              │                       │
│  20:13:08  PLAN                              │  Step 1               │
│  Next: Click '创建商家'                       │  /pages/index/index   │
│    action: Click '创建商家'  ·  type: click   │  42 elements          │
│    reasoning: Navigate to merchant creation  │                       │
│    expected: Navigates to vendor join page   │                       │
│                                              │                       │
│  20:13:12  EXECUTE  OK: click 创建商家        │                       │
│    ok: True  ·  route_after: /pages/vendor/  │                       │
│                                              │                       │
│  20:13:18  ORACLE  PASS [structural]         │                       │
│    Route matched: /pages/vendor/join          │                       │
│                                              │                       │
│  20:13:18  RESULT  [PASS]                    │                       │
│  PASS | Step 1/10 | Click '创建商家'          │                       │
│                                              │                       │
│  ── Step 2 ──                                │                       │
│  ...                                         │                       │
│                                              │                       │
│  ANALYSIS  测试阶段完成。请在下方输入反馈       │                       │
│  ┌──────────────────────────────────────┐    │                       │
│  │ 输入反馈或新的测试需求…          [发送] │    │                       │
│  └──────────────────────────────────────┘    │                       │
└──────────────────────────────────────────────┴───────────────────────┘
```

**LLM 分析规划弹窗：**

```
┌──────────────────────────────────────────────┐
│  LLM 测试方案分析                               │
│  ┌──────────────────────────────────────────┐ │
│  │ （LLM 根据源码 + 需求文档 + 设计文档生成）    │ │
│  │ 1. 创建商家账户 → 填写表单 → 验证保存       │ │
│  │ 2. 上传产品 → 填写产品信息 → 验证展示       │ │
│  │ 3. 加入购物车 → 调整数量 → 验证             │ │
│  │ ...                                      │ │
│  └──────────────────────────────────────────┘ │
│  识别到 N 个测试任务                            │
│  请选择执行模式：                               │
│  • 全流程端到端自动测试：连续执行，输出完整报告    │
│  • 逐个交互式测试：每完成一个暂停，由你决定继续    │
│          [取消]  [逐个交互式测试]  [全流程端到端]  │
└──────────────────────────────────────────────┘
```

**REST API 端点：**

| 端点 | 方法 | 请求体 | 说明 |
|------|------|--------|------|
| `/api/config` | GET | — | 返回 `.env` 中的默认路径，前端自动预填 |
| `/api/analyze` | POST | `{source}` | LLM 分析 World Model，返回 `{plan, tasks}` |
| `/api/start` | POST | `{source, screenshots, output, mode, tasks}` | 启动 Agent。mode=`"full"` 全流程 / `"step"` 逐步 |
| `/api/next` | POST | — | 逐步模式下触发继续执行下一个测试任务 |
| `/api/stop` | POST | — | 关闭 SSE 事件流，Agent 线程自然结束 |

**事件类型与颜色编码：**

| 事件类型 | 边框色 | 说明 | detail 字段 |
|---------|--------|------|------------|
| `ANALYSIS` | 青色 `#22D3EE` | LLM 分析规划结果 | plan, tasks |
| `SESSION` | 黄色 `#FBBF24` | 会话开始/结束 | goal, max_steps |
| `OBSERVE` | 青色 `#22D3EE` | 页面快照 | route, role, element_count, vlm |
| `PLAN` | 紫色 `#7C3AED` | LLM 决策 | action, type, target, reasoning, expected |
| `EXECUTE` | 橙色 `#F97316` | Minium 执行结果 | ok, type, target, route_after |
| `ORACLE` | 绿色 `#22C55E` | 验证结果 | passed, layer, evidence |
| `RESULT` | 绿色/红色 | 步骤总结 | step, success, action, page |
| `STEP_PAUSED` | 青色 | 逐步模式暂停 | taskIndex, totalTasks, taskName |
| `ERROR` | 红色 `#F43F5E` | 异常事件 | error |

**架构说明：**

```
applettestpilot/web_ui/
├── __init__.py         # 包导出
├── events.py           # AgentEvent (10 种类型) + SSE 事件流
├── server.py           # Flask 服务器 + 5 个 REST 端点 + /events SSE
├── hooks.py            # Agent 循环钩子 — monkey-patch 注入事件
├── web_agent.py        # 一键启动入口
└── templates/
    └── index.html      # 单文件前端 (~22K, 暗色主题, 含弹窗)
```

- **分析规划**：`/api/analyze` → `load_world_model()` → LLM 生成 `{plan, tasks}` JSON → 前端弹窗展示
- **双模式执行**：`full` 模式单 Agent 连续运行；`step` 模式使用 `threading.Event` 在任务间暂停，`/api/next` 信号继续
- **文件夹浏览**：`<input webkitdirectory>` 触发系统原生文件夹选择器，自动填入路径
- **截图传输**：Base64 编码内嵌 SSE，无需额外文件服务

**关键设计决策：**

| 决策 | 原因 |
|------|------|
| `send_file()` 替代 `render_template_string()` | Jinja2 会解析 HTML 中所有 `{{ }}` 模式，与 JS/CSS 冲突导致 `SyntaxError` |
| JS 零模板字面量 | 反引号 `` ` `` 模板字符串中的 `${}` 在复杂嵌套下易导致解析失败；全部改用 `'str'+var+'str'` 拼接 |
| `_resolve_source_path()` 4 级回退 | 用户可能输入 `TestApplet` / `objects/TestApplet` / 绝对路径 / 仅目录名，自动尝试所有模式 |
| `_default_tasks_from_wm()` | LLM 分析返回非 JSON 时的 fallback，从 WorldModel 页面列表自动推导 5 个测试任务 |
| SSE 心跳 `{"type":"connected"}` | 连接建立立即推送，前端确认 SSE 连通后再显示"等待 Agent 事件…" |
| `Flask threaded=True` | 确保 SSE 长连接不阻塞 `/api/start` 等 POST 请求 |
| `Cache-Control: no-store` | 禁止浏览器缓存旧版 HTML，每次刷新拉取最新前端代码 |

### Benchmark 任务列表

| 任务 ID | 名称 | 难度 | 步数 |
|---------|------|------|------|
| `create_merchant` | 创建商家账户 | easy | 4-8 |
| `upload_product` | 上传产品 | easy | 4-10 |
| `add_to_cart` | 加入购物车 | medium | 3-8 |
| `toggle_favorite` | 收藏/取消 | easy | 2-5 |
| `submit_comment` | 提交评论 | medium | 3-8 |
| `delete_product` | 删除产品 | medium | 4-10 |
| `edit_product` | 编辑产品 | medium | 4-10 |
| `clear_cart` | 清空购物车 | easy | 2-5 |
| `full_flow` | 全流程端到端 | hard | 12-30 |

### v2 Agent 输出格式

#### agent_result.json

```json
{
  "task": {"id": "create_merchant", "name": "Create Merchant Account", "difficulty": "easy", "setup": "launch_home"},
  "result": {
    "task_completed": true, "total_steps": 6, "successful_steps": 5,
    "failed_steps": 1, "bug_count": 1, "total_duration_s": 145.3, "total_tokens": 3240
  },
  "coverage": {
    "total_steps": 6, "successful": 5, "failed": 1,
    "unique_pages": 3, "total_pages_known": 3, "total_edges": 5,
    "failure_patterns": {"navigation": 1}
  },
  "steps": [
    {"step": 1, "action": "Click '创建商家'", "reasoning": "...", "passed": true,
     "oracle_layer": "structural", "duration_s": 25.3, "tokens": 520},
    {"step": 2, "action": "Type '测试商家' into '商家名称'", "reasoning": "...",
     "passed": true, "oracle_layer": "visual", "duration_s": 18.1, "tokens": 480}
  ],
  "failures": [
    {"step": 4, "category": "navigation_failure", "severity": "high",
     "hypothesis": "Navigation from '/pages/vendor/join' after 'Click 保存' did not reach expected page"}
  ]
}
```

#### memory_graph.json（导航图）

```json
{
  "pages": {
    "/pages/index/index": {"route": "/pages/index/index", "semantic_role": "home",
      "business_function": "product_browsing", "risk_level": "low", "visit_count": 2,
      "first_seen_step": 0, "last_seen_step": 5},
    "/pages/vendor/join": {"route": "/pages/vendor/join", "semantic_role": "form",
      "business_function": "merchant_creation", "risk_level": "low", "visit_count": 1}
  },
  "edges": [
    {"src": "/pages/index/index", "dst": "/pages/vendor/join",
     "action": "Click '创建商家'", "semantic_type": "navigate",
     "success_count": 1, "failure_count": 0, "success_rate": 1.0}
  ],
  "failures": [...],
  "stats": {"total_steps": 6, "successful": 5, "failed": 1,
            "unique_pages": 3, "total_edges": 5}
}
```

| 字段 | 含义 |
|------|------|
| `task_completed` | 所有步骤的 Oracle 验证均通过 |
| `bug_count` | 被 FailureAnalyzer 分类的异常步数 |
| `coverage.unique_pages` | Agent 探索到的不同页面数 |
| `steps[].oracle_layer` | 该步通过的验证层级 (structural/visual/semantic) |
| `failures[].category` | BugCategory 枚举：navigation_failure / state_inconsistency / ui_missing / timeout / crash / data_corruption / unauthorized_transition |
| `memory_graph` | 完整的导航图 + 转换边 + 失败记录，可用于离线分析和可视化 |

### v1 → v2 对照

| 维度 | v1 (`run_tests.py`) | v2 (`run_agent_experiment.py`) |
|------|---------------------|-------------------------------|
| 输入 | YAML 用例 (`case.yaml`) | 自然语言任务描述 (`BenchmarkTask`) |
| 规划 | 固定步骤顺序 | LLM 自主决策每步动作 |
| 验证 | 单层断言 (direct + VLM) | 4 层 Oracle (structural → visual → semantic → workflow) |
| 记忆 | 无 | 导航图 + 转换边 + 失败模式 |
| 分析 | `Exception` 字符串 | FailureAnalyzer 多信号根因归属 |
| 输出 | `result.json` | `agent_result.json` + `memory_graph.json` |

### 阶段一：探索式用例生成（v1 兼容）

LLM 逐步探索小程序，每步决策一个动作，VLM 观察结果，增量构建用例。
支持断点续传：若输出目录已有用例，会自动读取其 YAML 摘要传给 LLM 以跳过已覆盖功能，
编号从已有数量之后续接（如已有 case_01/case_02 则从 case_03 开始）。

```powershell
cd E:\WebTestPilot

# 默认路径（新项目首次生成）
python AppletTestPilot\explore_and_test.py

# 自定义路径 + 续接生成 + UTF-8 日志（避免 PowerShell 重定向编码乱码）

```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--source` | `./TestApplet` | 被测小程序源码目录（含 FRAMEWORK.md） |
| `--output` | `./input` | 产物根目录 → `cases/` + `bugs/`，已有用例可续接 |
| `--max-cases` | `99` | 安全上限（LLM 根据源码功能数自动决定实际数量） |
| `--log` | 无 | 日志文件路径（UTF-8 编码，替代 PowerShell `>` 重定向） |
python AppletTestPilot\explore_and_test.py --source AppletTestPilot\objects\TestApplet --output AppletTestPilot\results\phrase1\TestApplet --max-cases 20 --log AppletTestPilot\results\phrase1\TestApplet

生成流程：
1. 扫描已有 `case.yaml` → 提取前 6 步摘要传给 LLM → LLM 跳过已覆盖功能
2. FRAMEWORK.md → 分析功能 → 创建测试计划 → **按依赖拓扑排序**（无依赖用例排最前）
3. **逐用例执行 setup 函数**注入种子数据（如 `launch_home_with_merchant` 预创建商户）
4. LLM 逐步探索：每步提议动作 → Minium 执行 → VLM 观察 → LLM 判断 → 累积步骤
5. 弹窗类动作（删除/确认等）→ 等 0.5s → **pyautogui 屏幕截图**（捕获原生对话框）
6. 支持 **Scroll down / Scroll up / Scroll to '<text>'** 滚动查找屏幕外元素
7. 全量验证 100% PASS → 保存 case.yaml + 生成 Bug

### 阶段二：执行测试

```powershell
cd E:\WebTestPilot

# 单例
python AppletTestPilot\run_tests.py --mode single `
  --case input/cases/case_01/case.yaml

# 单例 + 缺陷注入
python AppletTestPilot\run_tests.py --mode single `
  --case input/cases/case_01/case.yaml `
  --bug input/bugs/case_01/bug.js

# 批量
python AppletTestPilot\run_tests.py --mode batch `
  --cases input/cases

# 批量 + 缺陷 + 筛选
python AppletTestPilot\run_tests.py --mode batch `
  --cases input/cases --bugs input/bugs --only 1,3,5-7

# 指定输出 + 禁用日志
python AppletTestPilot\run_tests.py --mode batch `
  --cases input/cases --output results/run1 --no-log
```

| 参数 | 模式 | 说明 |
|------|------|------|
| `--mode` | **必选** | `single` 或 `batch` |
| `--case` | single | case.yaml 路径 |
| `--bug` | single | bug.js 路径（可选） |
| `--cases` | batch | 包含 `case_*/case.yaml` 的目录 |
| `--bugs` | batch | 包含 `case_*/bug.js` 的目录（可选） |
| `--only` | batch | 筛选编号：`1,3,5-7` |
| `--output` | 通用 | 结果输出目录（默认 `./outputs`） |
| `--no-log` | 通用 | 禁用 output.log |

### 传统模式：一次性 YAML 生成

```powershell
python AppletTestPilot\generate_test_cases.py --count 5
python AppletTestPilot\generate_test_cases.py --count 3 --focus cart
```

## 输出格式

### result.json

```json
{
  "test_case": {
    "name": "Create Merchant Account",
    "setup_function": "launch_home",
    "steps": [
      {"action": "Click '创建商家'", "expectation": "Navigates to vendor join page"}
    ]
  },
  "steps": [
    {
      "step": {"action": "Click '创建商家'", "expectation": "Navigates to vendor join page"},
      "is_action_correct": true,
      "is_bug_reported": false,
      "start_time": 684798.34,
      "end_time": 684815.59
    }
  ],
  "is_task_complete": true,
  "duration": 45.3
}
```

| 字段 | 含义 |
|------|------|
| `is_action_correct` | 断言是否通过（操作产生了预期效果） |
| `is_bug_reported` | Agent 是否检测到异常（断言失败 = 预期与实际不符） |
| `is_task_complete` | 所有步骤全部通过 |

### trace.json

记录完整操作轨迹：`step_start` → `precondition`(可选) → `action_executed` → `postcondition`(可选) → `step_end`。异常时增加 `assertion_failed` / `bug_reported` / `exception`。

### history.json

每步页面状态快照：`page_id`、`prev_action`、`element_count`、`visible_texts`（前 20 个可见元素的文本）。

## 常见问题

**微信开发者工具连接失败**：检查 `.env` 中 `WX_DEVTOOLS_PATH` 和 `WX_PROJECT_PATH` 正确，且开发者工具已开启服务端口。

**视觉模型代码执行失败**：`sandbox.py` 内置 `from __future__ import annotations` 根除类型标注 NameError。如仍异常，查看 `trace.json` 变量追踪。

**输入框标签找不到**：`_find_input_by_label` 三层匹配：placeholder 属性 → label 文本 → 父容器关联，最终回退到首个可用输入框。

**Minium 日志过多**：引擎通过 `logging.Filter` 拦截 `minium.*` 日志。恢复：注释 `_MF` 类和 `addFilter` 调用。

**截图被覆盖**：截图文件名包含毫秒时间戳后缀（如 `screenshot_0002_65434.png`），不同 Session 不会冲突。

**弹窗/对话框无法识别**：Minium 截图运行在 WebView 内，无法捕获 `wx.showModal` 等微信客户端原生渲染的弹窗。已内置 pyautogui 屏幕级截图回退：弹窗类动作（删除/确认等）自动等待 0.5s 后用 pyautogui 截取全屏（含原生对话框）。确保 `pip install pyautogui`。可通过 `APPLET_SCREENSHOT_REGION=left,top,width,height` 裁剪截图区域。

**续接已有用例**：`--output` 指向已有用例的目录时，会自动读取每个 `case.yaml` 的前 6 步摘要传给 LLM，使其跳过已覆盖的功能，编号从已有数量后接续（case_01/case_02 已有 → 从 case_03 开始生成）。

**后续用例（上传产品/加入购物车等）探索失败**：依赖用例（如上传产品依赖已有商户）的 setup 函数现已在探索开始前自动执行。测试计划也会按依赖关系拓扑排序，确保"创建商户"等无依赖用例始终最先运行。若仍失败，检查 `benchmark/setup_functions.py` 中的 setup 函数是否正确。

**Agent 不知道可以滑动窗口**：已新增 Scroll 动作能力。LLM 可在用例中生成 `Scroll down` / `Scroll up` / `Scroll to '<text>'` 步骤，通过 `wx.pageScrollTo` 实现。探索阶段和生成阶段的 Prompt 均已包含滚动动作动词，删除产品等模板默认包含滚动步骤。

**页面元素过多找不到目标**：使用 `Scroll to '<text>'` 动作可滚动到指定文本元素。Agent 会先查找可见元素，再通过 XPath 搜索，最后滚动到底部兜底。

**Minium SDK 3.16.0 终端噪声**：SDK 会在 stderr 打印 `hook_navigation callback` 错误、`Could not found any element` 警告、`textarea.input not supported` 提示。这些非致命，引擎已通过 stderr 重定向 + logging filter 双层压制。若仍看到，使用 `--log` 参数将输出写入日志文件。

**PowerShell 日志乱码**：`>` 重定向默认写 UTF-16LE，编辑器以 UTF-8 打开会显示 NUL 间隔符乱码。使用 `--log output.log` 参数直接写 UTF-8 文件。

**setup_functions 导入失败**：`benchmark/setup_functions.py` 提供种子数据注入函数。若缺失，检查 `AppletTestPilot/benchmark/` 目录是否存在。

**Web UI 前端按钮无反应**：通常是浏览器缓存了旧版 HTML。按 `Ctrl+Shift+R` 强制刷新。若仍无效，检查浏览器控制台是否有 `SyntaxError` — 如有，重启 Web UI 服务器确保最新 `index.html` 被加载。

**Web UI 分析规划报 `Source path not found`**：路径解析支持 4 种输入：`TestApplet`（自动在 `objects/` 下查找）、`objects/TestApplet`（相对路径）、绝对路径、仅目录名。确保 `objects/TestApplet/` 目录存在且含 `src/app.js` + `project.config.json`。

**Web UI 分析规划报 JSON 解析错误**：LLM 返回非 JSON 时自动 fallback 到 `_default_tasks_from_wm()`，从页面路由自动推导 5 个测试任务。若仍失败，检查 DeepSeek API Key 和网络连接。

**Web UI 前端显示"SSE 连接中断"**：检查 Flask 服务器是否正常运行。在浏览器控制台查看 `/events` 请求状态。若 `EventSource` 连接失败，尝试重启 Web UI 并强制刷新页面。

**Web UI 后端运行但前端无事件推送**：确认 `install_hooks()` 被调用（查看终端日志 "install_hooks: stream=..., goal=..."）。若日志中出现此条但前端仍无事件，检查 Agent 线程是否崩溃（查看后续日志 "Agent crashed"）。

**Agent 反复点击保存/下滑/等待**：通常由 Planner LLM 调用失败触发 fallback。检查终端日志中是否有 `Planner error`、`Planner: empty LLM response` 或 `Planner: failed to parse JSON`。检查 DeepSeek API 配额和网络。若日志显示 `_symbolic_plan: found 0 inputs` 则说明 Minium 未返回 native input 元素（检查 SDK 版本或重启 DevTools）。

**Agent 反复填入同一字段**：检查终端日志 `_symbolic_plan` 中的 `text` 和 `attrs.value` 值。若 `text` 和 `attrs.value` 均为空，说明 Minium 输入后未回传值（SDK 3.16.x 已知问题，升级 SDK 或使用 `action_api` 的直接 input 方法）。

**VLM 调用失败 (Error code: 429)**：智谱 API 余额不足或配额超限。检查 `GUI_GROUNDING_MODEL_API_KEY` 对应的账户余额。

---

## 研究过程

### 项目分析

基于 WebTestPilot（ACM FSE 2026）论文成果，对 AppletTestPilot 进行了全面代码审查。WebTestPilot 与 AppletTestPilot 是同一仓库下的**姐妹项目**，共享相同的 Agentic 测试范式（条件→动作→断言循环），但目标平台不同：

| 维度 | WebTestPilot | AppletTestPilot |
|------|-------------|-----------------|
| **目标平台** | Web 应用（浏览器） | 微信小程序（移动端） |
| **浏览器引擎** | Playwright (Chromium) | Minium (微信开发者工具) |
| **动作执行** | GUI Grounding + SoM 标注 + LLM 代码生成 | LLM NLP 动作分发到 Minium API |
| **断言验证** | BAML 驱动的 LLM 代码生成 + 结构化数据提取 | VLM (GLM-4.1V) 截图描述 + LLM (DeepSeek) 断言代码生成 |
| **页面理解** | Accessibility Tree + 页面重识别 | VLM 截图描述 |
| **评测框架** | 完整的 baselines/ + experiments/ 体系 | 无 |

### 发现的不足

对比 WebTestPilot 的成熟度，AppletTestPilot 存在以下关键差距：

1. **Token 追踪缺失** — `StepResult.tokens` 始终为 0，API 调用消耗未记录
2. **无步骤级重试** — 偶发连接超时直接导致用例失败，缺少容错机制
3. **配置过于简单** — 仅 `max_tries` 一个参数，缺少模型级温度、Token 上限配置
4. **批量运行无汇总** — `run_batch` 仅在终端打印结果，无结构化 JSON 输出
5. **无评测模块** — 完全没有实验脚本，无法计算任务完成率、Bug 检测率等论文指标
6. **结果分散** — 各次运行的 `result.json` 散落不同目录，缺少统一的数据加载和聚合机制

### 优化方案设计

基于 WebTestPilot 的 `experiments/rq1/results.py` 和 `experiments/rq2/results.py` 的指标体系，为 AppletTestPilot 设计了三层优化：

```
Layer 1: 引擎优化 (Token 追踪 + 重试 + 配置增强)
Layer 2: 运行优化 (批量汇总输出)
Layer 3: 评测体系 (指标计算 + 报告生成 + 实验运行器)
```

---

## 优化内容

### 1. Token 追踪（2 个文件修改）

**`applettestpilot/clients/llm.py`**
- `call_llm()` 返回值从 `str | None` 改为 `LLMResponse | None`
- `LLMResponse` 数据类包含 `content`, `prompt_tokens`, `completion_tokens`, `total_tokens`
- 从 API 响应的 `usage` 字段自动提取 Token 消耗

**`applettestpilot/clients/vision.py`**
- `VisionClient.call_vision()` 每次调用后将 Token 用量存入 `_last_tokens`
- 新增 `get_last_tokens()` 方法供上层获取

**向下兼容修改：**
- `bug_generator.py:58` — `code = call_llm(...).content`
- `runner.py:240` — `resp = call_llm(...); new_content = resp.content if resp else None`
- `assertion_api/oracle.py` — `_call_vlm_and_execute()` 返回 Token 统计字典
- `assertion_api/__init__.py` — `verify_precondition/verify_postcondition` 返回 token 计数
- `orchestrator.py` — 每步累加 token 并传入 `StepResult`

### 2. 步骤级重试（`orchestrator.py`）

`AppletTestPilot.run()` 新增 `max_step_retries` 参数：
- **Bug/断言失败** → 直接标记失败，不重试（结果是确定性的）
- **连接超时等瞬态错误** → 最多重试 `max_step_retries` 次，间隔 1s
- 每次重试的 Token 独立累加

### 3. 配置增强（`config.py` + `config.yaml`）

新增 `ModelConfig` 数据类，为每种模型客户端独立配置：

```yaml
executor:
  max_tries: 3
  max_step_retries: 1    # 新增

vlm:                      # 新增 — VLM 视觉模型
  model: ""
  temperature: 0.3
  max_tokens: 1024

llm_assertion:            # 新增 — 断言代码生成
  model: ""
  temperature: 0.3
  max_tokens: 1024

llm_explore:              # 新增 — 探索动作提议
  temperature: 0.5
  max_tokens: 512

llm_generate:             # 新增 — 用例生成
  temperature: 0.7
  max_tokens: 4096
```

### 4. 批量运行汇总（`runner.py`）

`run_batch()` 返回值从 `(passed, failed)` 扩展为 `(passed, failed, summary_rows)`，自动在输出目录生成 `batch_summary.json`：

```json
{
  "total": 4, "passed": 3, "failed": 1, "pass_rate": 0.75,
  "total_time_s": 245.3, "has_bugs": true,
  "cases": [
    {
      "case": "case_01", "name": "...", "passed": true,
      "total_steps": 4, "passed_steps": 4, "bug_reported": false,
      "duration": 45.3, "tokens": 1234,
      "step_details": [...]
    }
  ]
}
```

---

## 评价指标

### 模块架构

```
AppletTestPilot/experiments/
├── __init__.py               # 公共 API 导出
├── metrics.py                # 指标计算（6 大类）
├── evaluate.py               # CLI 评测入口（v1 result.json）
├── run_experiment.py         # v1 端到端实验运行器
├── run_agent_experiment.py   # ★ v2 Agent 实验运行器
└── demo_eval.py              # 快速演示脚本
```

### 指标体系（对标 WebTestPilot RQ1/RQ2）

#### 1. 任务完成率 (Task Completion Rate)
```python
from experiments.metrics import compute_task_completion
per_case, overall = compute_task_completion(df)
```
- 定义：所有步骤 `is_action_correct=True` 的用例占比
- 输出：整体完成率 + 分用例完成率

#### 2. 正确轨迹分数 (Correct Trace Score)
```python
from experiments.metrics import compute_correct_trace
per_case, overall = compute_correct_trace(df)
```
- 定义：从第一步起连续正确的步数 / 总步数
- 反映 Agent 能推进多深后遇到失败

#### 3. Bug 检测指标 (Precision / Recall / F1)
```python
from experiments.metrics import compute_bug_detection
bug_metrics = compute_bug_detection(df)
# {"tp": 3, "fp": 2, "fn": 11, "precision": 0.6, "recall": 0.21, "f1": 0.32}
```
- 最后一步为预期 Bug 触发步
- 计算 TP（Bug 步正确报告）/ FP（非 Bug 步误报）/ FN（Bug 步漏报）

#### 4. 耗时统计 (Duration Statistics)
```python
from experiments.metrics import compute_duration_stats
stats = compute_duration_stats(df)
```
- `per_step`：每用例的步级耗时分布（count/mean/std/min/25%/50%/75%/max）
- `per_case`：每用例的总耗时分布
- `overall_step_stats` / `overall_case_stats`：全局汇总

#### 5. Token 用量统计 (Token Statistics)
```python
from experiments.metrics import compute_token_stats
stats = compute_token_stats(df)
# {"total_tokens": 12345, "mean_tokens_per_step": 280.6}
```

#### 6. 稳定性指标 (Stability Metrics)
```python
from experiments.metrics import compute_stability
stab = compute_stability(df)
# {"correct_trace_variance": 0.13, "task_completion_variance": 0.25, "fleiss_kappa": 0.82}
```
- **Correct Trace Variance**：多次运行间正确轨迹分数的方差
- **Task Completion Variance**：多次运行间任务完成的方差
- **Fleiss-Kappa**：多次运行间步骤正确性的评分者间一致性（需 ≥2 次运行）

### 数据加载

```python
from experiments.metrics import load_results_from_dir

df = load_results_from_dir(Path("outputs/"))
# 自动扫描 outputs/run_*/case_*/result.json
# 返回 DataFrame 含列：run_id, case_name, step_id, action,
#                    expectation, is_action_correct, is_bug_reported,
#                    duration, tokens
```

### 报告生成

```python
from experiments.metrics import generate_report, print_report

report = generate_report(df, output_dir=Path("evaluation/"))
# 生成 evaluation/evaluation_report.json + evaluation/raw_results.csv

print_report(report)
# 终端打印格式化报告
```

---

## 运行示例

### 评测已有结果

```powershell
cd E:\WebTestPilot

# 对已有 outputs/ 目录生成评测报告
D:\anaconda3\envs\applet\python.exe AppletTestPilot\experiments\evaluate.py \
  --results AppletTestPilot/outputs \
  --output AppletTestPilot/outputs/evaluation

# 同时导出 CSV
D:\anaconda3\envs\applet\python.exe AppletTestPilot\experiments\evaluate.py \
  --results AppletTestPilot/outputs \
  --csv metrics/raw_results.csv
```

输出示例：

```
============================================================
  APPLETTESTPILOT — EVALUATION REPORT
============================================================

  Summary
  ────────────────────────────────────────
  Runs: 14  |  Cases: 2  |  Steps: 44
  Task Completion Rate : 50.00%
  Correct Trace Score  : 67.26%
  Total Duration       : 1456.0s
  Total Tokens         : 0

  Bug Detection
  ────────────────────────────────────────
  TP=3  FP=2  FN=11
  Precision : 60.00%
  Recall    : 21.43%
  F1 Score  : 31.58%

  Duration
  ────────────────────────────────────────
  Per step  — mean: 33.1s  |  std: 29.1s
  Per case  — mean: 104.0s  |  std: 111.1s

  Tokens
  ────────────────────────────────────────
  Total        : 0
  Mean / step  : 0

  Stability
  ────────────────────────────────────────
  Correct Trace Var    : 0.1344
  Task Completion Var  : 0.25
  Fleiss-Kappa         : None

  Per-Case Breakdown
  ────────────────────────────────────────────────────────────
  _tmp                  completion: 60.00%  trace: 65.00%
  case                  completion: 44.44%  trace: 68.52%

============================================================
```

### 端到端实验运行

```powershell
# 1. 任务完成率实验（无 Bug 注入，3 次重复）
D:\anaconda3\envs\applet\python.exe AppletTestPilot\experiments\run_experiment.py \
  --cases AppletTestPilot/phrase1/TestApplet/cases \
  --mode task_completion \
  --runs 3 \
  --output AppletTestPilot/experiments/results

# 2. Bug 检测实验（注入 Bug，3 次重复）
D:\anaconda3\envs\applet\python.exe AppletTestPilot\experiments\run_experiment.py \
  --cases AppletTestPilot/phrase1/TestApplet/cases \
  --bugs AppletTestPilot/phrase1/TestApplet/bugs \
  --mode bug_detection \
  --runs 3 \
  --output AppletTestPilot/experiments/results

# 3. 完整实验（任务完成 + Bug 检测）
D:\anaconda3\envs\applet\python.exe AppletTestPilot\experiments\run_experiment.py \
  --cases AppletTestPilot/phrase1/TestApplet/cases \
  --bugs AppletTestPilot/phrase1/TestApplet/bugs \
  --mode full \
  --runs 3 \
  --output AppletTestPilot/experiments/results
```

### 快速演示

```powershell
# 对现有输出数据快速评测
D:\anaconda3\envs\applet\python.exe AppletTestPilot\experiments\demo_eval.py
D:\anaconda3\envs\applet\python.exe AppletTestPilot\experiments\demo_eval.py --results AppletTestPilot/outputs
```

### 编程调用

```python
import sys
from pathlib import Path
sys.path.insert(0, "AppletTestPilot")

from experiments.metrics import (
    load_results_from_dir,
    compute_task_completion,
    compute_correct_trace,
    compute_bug_detection,
    compute_duration_stats,
    compute_token_stats,
    compute_stability,
    generate_report,
    print_report,
)

# 加载数据
df = load_results_from_dir(Path("AppletTestPilot/outputs"))

# 单项指标
per_case, overall = compute_task_completion(df)
print(f"Task Completion: {overall:.2%}")

bug = compute_bug_detection(df)
print(f"Bug F1: {bug['f1']:.2%}")

# 全量报告
report = generate_report(df, Path("evaluation/"))
print_report(report)
```

---

## 实验结果

### 测试用例概况

| 用例 | 描述 | 步数 | Setup 函数 |
|------|------|------|------------|
| case_01 | 创建商家账户 | 4 | `launch_home` |
| case_02 | 上传产品 | 6 | `launch_home_with_merchant` |
| case_03 | 产品详情导航 | 1 | `launch_home_with_merchant_and_product` |
| case_04 | 产品详情页 | 1 | `launch_home_with_merchant_and_product` |

### 历史运行数据评测结果

基于 14 次历史运行、44 个步骤结果的评测：

| 指标 | 值 | 说明 |
|------|-----|------|
| 任务完成率 | 50.00% | 一半的用例全步通过 |
| 正确轨迹分数 | 67.26% | 平均每个用例能连续正确执行 2/3 的步骤 |
| Bug 精确率 | 60.00% | Bug 报告中有 60% 发生在正确位置 |
| Bug 召回率 | 21.43% | 仅约 1/5 的 Bug 步被成功检测 |
| Bug F1 | 31.58% | 精确率与召回率的调和平均 |
| 步均耗时 | 33.1s (±29.1s) | 单步含 VLM+LLM 调用 |
| 例均耗时 | 104.0s (±111.1s) | 因步数差异较大 |
| 正确轨迹方差 | 0.1344 | 多次运行间轨迹一致性较好 |
| 任务完成方差 | 0.25 | 不同运行间完成状态有一定波动 |

**分析：**
- 任务完成率 50% 表明约一半用例存在断言误判或动作执行问题
- Bug 召回率低 (21.43%) 是主要瓶颈——断言流水线漏报较多
- 耗时波动大 (±29s / step) 反映了 VLM 重试机制的随机性
- Token 追踪在历史数据中为 0（优化前未记录），后续运行将自动采集

### 输出文件结构

```
experiments/results/
└── experiment_20260516_HHMMSS/
    ├── experiment_config.json          # 实验参数记录
    ├── evaluation_report.json          # 评测报告（JSON）
    ├── raw_results.csv                 # 原始数据（CSV）
    ├── task_completion/                # 无 Bug 运行
    │   ├── run_1/
    │   │   ├── case_01/result.json
    │   │   ├── case_01/trace.json
    │   │   ├── case_01/history.json
    │   │   └── batch_summary.json
    │   └── run_2/ ...
    └── bug_detection/                  # 有 Bug 运行
        ├── run_1/
        │   └── batch_summary.json
        └── run_2/ ...
```

---

## 被测小程序源码诊断与修复

针对 TestApplet 源码进行了三轮系统性诊断和修复。

### 诊断为空的来源

| 轮次 | 错误信息 | 根因 | 严重度 |
|------|---------|------|--------|
| 1 | `FileExistsError: [WinError 183]` | `--log` 与 `--output` 传入同一路径，日志文件阻塞了 `cases/` 目录创建 | 阻塞 |
| 2 | `[loader] unexpected current frame status timedout` | `App.onLaunch()` 中同步写入 5 个 Storage Key 的大对象，阻塞渲染管线 | 致命 |
| 3 | `Error: timeout` in `WAServiceMainContext.js` | `onLoad()` 中调用 `ensureDemoData()` 写 Storage，首次渲染未完成即超时 | 致命 |
| 4 | `清除登录状态失败 TypeError: Failed to fetch` | `config.js` 中失效云 URL 使 DevTools 尝试云端通信 | 中等 |
| 5 | `SystemError webapi_getwxaasyncsecinfo` | 真实 AppID 触发基础库安全审计联网请求 | 致命 |
| 6 | `Error: tourist appid` (Minium 启动) | `touristappid` 不被 `cli.bat auto` 接受 | 阻塞 |
| 7 | `[] Failed to fetch` (lib: 3.16.x) | 基础库 3.16+ 强制隐私保护检查，无配置时触发 fetch | 致命 |

### 修复方案

#### 修复 1：日志路径冲突（`explore_and_test.py`）

```python
# 旧：仅当路径已存在且是目录时才追加 output.log
if log_path.is_dir():
    log_path = log_path / "output.log"

# 新：无后缀的路径始终视为目录
if log_path.is_dir() or not log_path.suffix:
    log_path = log_path / "output.log"
```

#### 修复 2：渲染管线超时（`app.js`）

```
Before:  onLaunch → ensureStorageInitialized → wx.setStorageSync × 5 (同步阻塞)
After:   onLaunch → ensureStorageInitialized (仅填充空默认值，无大量写入)
```

`onLaunch()` 不再执行任何重量级操作，仅初始化缺失 key 的空容器。

#### 修复 3：`WAServiceMainContext` 超时（全部 6 个页面）

```
Before:  onLoad → refresh → ensureDemoData → wx.setStorageSync → 首次渲染阻塞 → timeout
After:   onLoad → refresh (仅读取,快速返回) → 首次渲染完成
         setTimeout(100-150ms) → ensureDemoData → 二次渲染
```

核心原则：**Storage 写入必须推迟到首次渲染完成后**。通过 `setTimeout` 将写操作放到下一个事件循环。

#### 修复 4：云服务清理

| 操作 | 原因 |
|------|------|
| 删除 `src/config.js` | 包含失效腾讯云 URL (`14592619.qcloud.la`) |
| `project.config.json` 添加 `urlCheck: false` | 禁止域名白名单校验 |
| `project.config.json` 添加 `checkSiteMap: false` | 禁止 sitemap 检查 |

#### 修复 5-6：AppID 策略 — 真实 AppID → touristappid → 空字符串

```
wxID  →  基础库调用 webapi_getwxaasyncsecinfo  →  Failed to fetch
touristappid        →  DevTools 手动打开 OK，但 cli.bat auto 拒绝
"" (空字符串)       →  无 AppID 本地模式，DevTools + cli.bat 均接受，完全离线
```

`project.config.json` 最终配置：`"appid": ""`

#### 修复 7：基础库 3.16+ 隐私保护检查

基础库 3.16.0+ 引入了强制隐私保护检查。若 `app.json` 未显式声明 `__usePrivacyCheck__`，基础库会在启动时联网获取隐私配置。本地离线环境下请求超时导致 `[] Failed to fetch`。

```json
// app.json
"__usePrivacyCheck__": false
```

配置项精简：

| 配置 | 作用 |
|------|------|
| `app.json` 添加 `__usePrivacyCheck__: false` | 禁用隐私检查，消除 fetch 调用 |
| `app.json` 删除 `networkTimeout` | 不触发网络模块初始化 |
| `project.config.json` 添加 `urlCheck: false` | 禁止域名校验 |
| `project.private.config.json` 删除 | 避免 libVersion 被覆盖 |
| `project.private.config.json` 中 `useApiHook: false` | 禁止 API 钩子注入 |

### 项目目录清理

| 操作 | 原因 |
|------|------|
| 删除 `src/cms/discover/` | 孤儿 `Page({})`，未注册在 `app.json` |
| 删除 `src/components/tap-particles/` | 未被任何页面引用 |
| 创建 6 个页面 `.json` | 显式声明页面配置，提升编译器兼容性 |
| `app.json` 页面顺序 | TabBar 页面优先（index → cart → user → 子页面） |

### 修复后启动流程

```
App.onLaunch()
  └─ ensureStorageInitialized()    ← 仅检查 + 空填充 (微秒级)
       app 就绪 ✅

首页 onLoad()
  └─ refresh()                      ← 仅读取 Storage (微秒级)
       └─ setData(...)              ← 首次渲染 ✅

首页 onShow()
  └─ refresh()                      ← 二次读取，此时数据仍为空

setup_functions 按需注入
  └─ launch_home_with_merchant()   ← 通过 evaluate_js 写入 m_test_001
  └─ launch_home_with_merchant_and_product() ← 写入产品 + 购物车
```

---

## 架构决策：演示数据策略

### 问题

最初在 `app.js` 中添加了 `ensureDemoData()` 自动注入演示数据（商家、3 个产品、收藏、购物车、评论），导致小程序启动后立即处于"已有数据"状态，无法测试从零创建商家的完整流程。

### 决策：文档引导 > 代码注入

| 方式 | 优点 | 缺点 |
|------|------|------|
| ~~代码自动注入~~ | 页面立即显示功能组件 | 无法测试创建流程；每次重置都恢复数据 |
| **FRAMEWORK.md §8 文档引导** | 纯净启动态；LLM 参照文档探索完整路径 | 首次加载页面显示空态 |

### FRAMEWORK.md 第 8 节新增内容

在 `objects/TestApplet/FRAMEWORK.md` 末尾新增 **§8 测试数据参考**（~95 行），包含：

| 小节 | 内容 |
|------|------|
| 8.1 商家示例 | 完整 JSON 结构 |
| 8.2 产品示例 | 3 个产品完整数据 |
| 8.3-8.5 | 购物车、收藏、评论关联数据 |
| **8.6 推荐测试流程** | 10 步端到端路径：创建→上传→购物车→收藏→评论→删除 |
| **8.7 边界与异常** | 7 种异常场景（空输入/格式错误/不存在/边界值） |

### 数据流对比

```
Before (错误):
  App 启动 → ensureDemoData() 自动注入全部数据
  → 首页直接显示 3 个产品 → 无法测试"创建商家"流程
  → 每次重置都恢复数据 → 无法验证清空逻辑

After (正确):
  App 启动 → Storage 全空 → 首页显示"暂无商品"
  → LLM 读取 FRAMEWORK.md §8.6 推荐流程
  → Phase 1 逐步探索：创建商家 → 上传产品 → 加入购物车 → ...
  → setup_functions 按需注入依赖数据（merchant/product/cart）
  → 完整覆盖全生命周期
```

### setup_functions 作为唯一数据预置方式

启动后 Storage 全空，下列函数通过 Minium `evaluate_js` 注入特定数据状态：

| 函数 | 注入数据 | 对应测试场景 |
|------|---------|-------------|
| `launch_home` | 无（清空所有 key） | 从头创建商家 |
| `launch_home_with_merchant` | `merchant_v1` | 上传产品、编辑商家 |
| `launch_home_with_merchant_and_product` | `merchant_v1` + `products_v1` | 收藏、评论、购物车 |
| `launch_home_with_merchant_and_product_in_cart` | 上述 + `cart_v1` | 修改购物车、清空 |

---

## Minium 连接优化

针对小程序通过 Minium 启动失败的问题，在 `clients/minium.py` 中做了两项关键优化：

### 页面就绪等待（`_wait_for_page`）

`WXMinium.__init__` 虽然调用了 `launch_weapp()`，但返回时首页可能未渲染完成（Windows 上 IDE 冷启动需 5-10s + 项目编译时间）。

```python
def _wait_for_page(mini, timeout=45.0):
    """轮询直到 mini.page.path 非空，超时抛 RuntimeError"""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        pg = getattr(mini, "page", None) or mini.get_current_page()
        if pg is not None:
            path = getattr(pg, "path", "") or ""
            if path and path != "/":
                return pg
        time.sleep(0.5)
    raise RuntimeError(f"Mini program page not ready after {timeout}s")
```

### 自动重载开关

```python
# 旧：不自动重载
"auto_relaunch": False

# 新：运行态重启时自动恢复
"auto_relaunch": True
```

---

## Planner 优化历程（Agent 消极规划根因与修复）

Agent 在实际运行中反复出现"点击保存/下滑/等待"的消极规划行为，经过 10+ 轮诊断定位到 5 类根因。

### 诊断 1：`_PLAN_SYSTEM` 模板花括号转义丢失

**症状**：LLM 收到 `{{` `}}` 而非 `{` `}` → 无法理解 JSON 输出格式 → 空响应 → fallback → scroll/wait 死循环

**根因**：将 World Model 从 system prompt 移至 user message 后，`_PLAN_SYSTEM` 不再调用 `.format(world_model=...)`, `{{` `}}` 保持原样传给 LLM

**修复**：`self._system_prompt = _PLAN_SYSTEM.format()` 执行无参 format，将转义花括号还原

### 诊断 2：Minium 无法在混合选择器中返回 `<input>` 元素

**症状**：`page.get_elements("view, text, button, image, input")` 返回 15 个 text/view 元素，0 个 input → `_symbolic_plan()` 永远找不到输入框 → wait 循环

**根因**：微信小程序的 `<input>`/`<textarea>` 是**原生组件**，渲染在 WebView 外的独立层。Minium 的混合选择器只查询 WebView 层，native 组件被跳过

**修复**：`observe()` 分两步查询：
```python
# Step 1: WebView 元素
page.get_elements("view, text, button, image")
# Step 2: 原生组件（必须单独查）
page.get_elements("input")
page.get_elements("textarea")
```

### 诊断 3：Minium 属性格式不一致

**症状**：`element.attributes` 在 SDK 3.16.x 返回 `list`（`[["key","value"],...]` 或 `[{"name":"k","value":"v"},...]`），`.get("value")` 崩溃 `'list' object has no attribute 'get'`

**修复**：新增 `_normalize_attrs()` 函数，兼容 4 种格式统一转为 `dict`：

| 输入格式 | 示例 | 处理方式 |
|---------|------|---------|
| `dict` | `{"value":"13800138000"}` | 直接返回 |
| `list[tuple]` | `[["value","13800138000"]]` | 按 `item[0]`/`item[1]` 解析 |
| `list[dict]` | `[{"name":"value","value":"13800138000"}]` | 按 `name`/`value` 键解析 |
| `None` | `None` | 返回 `{}` |

### 诊断 4：输入值位置不一致（`text` vs `attributes["value"]`）

**症状**：`_symbolic_plan()` 检查 `inp.attributes.get("value")` 为空 → 认为字段未填 → 重复填入同一字段 → 死循环。但实际上 `excute_action` 后输入值已存入 `element.text`

**修复**：同时检查两个位置：`val = attrs.get("value") or inp.text or ""`

### 诊断 5：LLM 表单页负向测试偏好

**症状**：LLM 收到"测试商家创建"任务后，主动选择"先不填名称点保存测试空值校验"，而非"先填完所有字段再保存"

**修复**：
- `_fallback_action` 表单感知：表单页优先填入空字段（含智能测试数据：名称→"测试旗舰店"，手机→"13800138000"，价格→"199.00"），所有字段填满后才点保存
- `_PLAN_SYSTEM` 新增硬规则：`NEVER do negative testing (no clicking save on empty form)`、`If you just navigated to a form, start by typing the FIRST field`

### 诊断 6：`_fallback_action` 输入值检测与 `_symbolic_plan` 不同步

**症状**：`_symbolic_plan` 已修复输入检测（检查 `text` + `attrs.value`），但 `_fallback_action` 未同步修复 → LLM 调用失败触发 fallback 后，fallback 本身也死循环

**修复**：统一 `_fallback_action` 和 `_symbolic_plan` 的输入检测逻辑（tag 匹配 + text 检查 + placeholder 判断）

### 最终架构

```
Planner.plan()
  │
  ├─ LLM path (primary)
  │   └─ system_prompt: 纯指令 (~300 chars, 经 .format() 处理)
  │   └─ user_prompt: 当前状态 + history + app reference
  │   └─ 失败 → _fallback_action (表单感知)
  │
  └─ 辅助逻辑
      ├─ _normalize_attrs(): Minium 属性 4 格式统一
      ├─ observe(): 双查询分离 WebView + native
      └─ _parse_response(): 3 层 JSON 提取 (code block → raw → brace match)
```