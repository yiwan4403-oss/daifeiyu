# 技术调研报告：PydanticAI · MCP Python SDK · companion-emergence

> 调研对象：为 Resident（Python / Windows 自主 AI 角色）做源码级选型调研。
> 调研方式：本机无 git 且无出网命令行，全部通过 GitHub API / raw.githubusercontent.com / PyPI JSON 逐文件读取源码取证；**未安装任何依赖、未运行任何代码**；README 与发布说明仅作背景线索，所有结论均以源码为准。
> 取证基准：pydantic-ai `main` 分支（最新 release v2.66.0，2026-11-04）；python-sdk `main` 分支（PyPI 最新 2.3.0）；companion-emergence `main` 分支（2026-11-05 推送）。

---

## 一、PydanticAI

### 1.1 基本事实（已核实）

| 项 | 事实 | 证据 |
|---|---|---|
| 仓库 | https://github.com/pydantic/pydantic-ai | GitHub API |
| 最新版本 | **v2.66.0**（2026-11-04 发布；另有 v1 系列 v1.107.x 同时维护） | `releases/latest` API |
| 许可证 | **MIT** | 仓库 API `license.key=mit` |
| 语言 / Python 要求 | 纯 Python；`pydantic-ai-slim` **requires-python >= 3.11**（classifiers 覆盖 3.11–3.15） | `pydantic_ai_slim/pyproject.toml` |
| 活跃度 | 21,053 stars、3,113 forks、1,776 open issues；主包按日发布 | 仓库 API |
| 包拆分 | 仓库是 uv workspace：核心 `pydantic_ai_slim/`（发布为 `pydantic-ai-slim`），`src/`（元包 `pydantic-ai`，把 provider SDK 作为 extras 聚合）、`pydantic_graph/`、`pydantic_evals/` 独立包 | 根目录树 |

**核心运行时依赖（slim，共 9 个）**：`anyio>=4.7.0`、`griffelib>=2.0`、`httpx2>=2.7`、`pydantic>=2.12`、`pydantic-graph`（同仓）、`opentelemetry-api>=1.28.0`、`typing-inspection>=0.4.0`、`genai-prices>=0.1.13`。**没有** starlette/uvicorn/数据库驱动等重型依赖——`web`、`cli`、`ui`、`realtime`、各 provider SDK（`openai`/`anthropic`/`google`…）全部是 optional extras。见 `pydantic_ai_slim/pyproject.toml` 的 `[tool.hatch.metadata.hooks.uv-dynamic-versioning]`。

### 1.2 Agent 主循环 / 工具调用设计（源码级）

**主循环 = 一张 pydantic-graph 图**，不是手写 while 循环。`pydantic_ai_slim/pydantic_ai/_agent_graph.py`：

- 图的节点类型从 `pydantic_graph` 导入：`BaseNode, End, Graph, GraphBuilder, GraphRunContext`；导出 `UserPromptNode / ModelRequestNode / CallToolsNode / build_agent_graph`。
- 单次 `Agent.run()` 的过程：`_prepare_run()`（组装 message_history、usage、run_id/conversation_id、deadline、retries、capabilities）→ `build_agent_graph(...)` → 图内循环「ModelRequestNode（调模型）→ CallToolsNode（执行工具）→ 再请求」，直到产出结果或撞上限。
- 工具执行入口是 `_tool_execution.py` 的 `process_tool_calls`（`_agent_graph.py` 直接 re-export）。
- **每步防失控**：
  - `UsageLimits.request_limit` 默认 **50**（"bounds the number of turns of the agent loop"，每步开头检查），另有 `cost_limit` / `tool_calls_limit` / `input_tokens_limit` / `output_tokens_limit` / `total_tokens_limit` / `per_request_input_tokens_limit`。证据：`pydantic_ai/usage.py` 的 `UsageLimits` 类与 `check_before_request`。
  - 单步重试上限 `MAX_MODEL_REQUEST_ATTEMPTS = 100`（防 RetryModelRequest 无限循环，`_agent_graph.py`）。
  - `timeout=` 参数 → 绝对 deadline，子 run 只能缩短不能延长；`RunContext.cancel()` / `RunCancelled` / `RunTimedOut`（`exceptions.py`）。
  - 取消/超时后**可恢复**：`RunCancelled.all_messages()` 返回完整可续跑历史，直接作为下一次 `message_history`。
- **工具调用编排**：
  - `EndStrategy = 'early' | 'graceful' | 'exhaustive'`（v2 默认 **graceful**）：决定「模型同时返回最终结果和函数工具调用」时谁先跑、是否并行、`ModelRetry` 是否压掉输出结果。文档字符串在 `_agent_graph.py`。
  - 工具并行执行：`ToolManager.parallel_execution_mode('sequential'|'parallel'|'batch')`；`ToolDefinition.sequential=True` 可做屏障（`tools.py`）。
  - 错误语义分层（`exceptions.py`）：`ModelRetry`（让模型看错误重试，计入重试预算）、`ToolFailed`（终端失败、不重试）、`CallDeferred` / `ApprovalRequired`（把工具调用挂起，支持**人在环审批**）、`SkipToolValidation/SkipToolExecution`（hook 短路）、`RetryModelRequest`（同一步换模型重试、模型无感）。
  - 工具级重试预算：`Tool(max_retries=...)`、agent 级 `retries={'tools':…,'output':…}`、工具超时 `Tool(timeout=…)`。
  - 提供商侧服务端长任务：Anthropic `pause_turn` / OpenAI background 模式的 "suspended response" 续跑链（`model_request()` 内的 continuation loop，`MAX_BACKGROUND_POLLS` / `MAX_GENERATION_CONTINUATIONS` 上限），可用 `PendingModelResponse` 输出"先挂起、稍后回查"。
- **图层的可扩展点**：`set_agent_graph_sleep()`（把 sleep 替换成 Temporal/DBOS/Prefect 的 durable sleep）、capabilities 的 `wrap_run/before_run/after_run/on_run_error` 钩子链（`agent/__init__.py` 的 `_run_lifecycle_hooks`）。

### 1.3 依赖注入（源码级）

- `Agent` 是泛型 `Agent[AgentDepsT, OutputDataT]`，构造参数 `deps_type=...`；运行时通过 `run(..., deps=...)` 或 `agent.override(deps=...)` 注入。证据：`agent/__init__.py`（`class Agent(AbstractAgent[AgentDepsT, OutputDataT])`、`_prepare_run` 的 `deps` 参数）。
- 注入的载体是 **`RunContext`**（`pydantic_ai/_run_context.py` 中的巨型 dataclass）：`ctx.deps`、`ctx.usage` / `ctx.usage_limits`、`ctx.deadline`、`ctx.tool_name/tool_call_id/retry/max_retries`、`ctx.messages`、`ctx.workspace`、`ctx.run_id/conversation_id`、`ctx.cancel()`、`ctx.enqueue()`（run 中注入新消息）、`ctx.emit()`（事件流）、`ctx.load_capability()`、`ctx.remaining_time()`。
- 工具函数签名约定：`def tool(ctx: RunContext[Deps], a: int) -> str` 或 `tool_plain`；`takes_ctx` 自动推断；`prepare=` 钩子可**每步按 ctx 决定工具是否注册**（`Tool.prepare_tool_def`，`tools.py`）。系统提示词也支持函数形式：`SystemPromptFunc = Callable[[RunContext[AgentDepsT]], str|None]`。
- 底层用 `ContextVar` 传播：`_CURRENT_RUN_CONTEXT` + `get_current_run_context()`（`_run_context.py`）。
- 另有 `validation_context`（透传给 pydantic 验证器）和 `@agent.system_prompt` 动态拼装。

### 1.4 结构化输出（源码级）

`pydantic_ai_slim/pydantic_ai/output.py` 定义 **四种输出模式**（`OutputMode = 'text'|'tool'|'native'|'prompted'|'image'|'auto'`，auto 由 `ModelProfile.default_structured_output_mode` 决定）：

1. **`ToolOutput(type_)`**：输出类型被编译成工具调用（`final_result` 工具），返回值经 pydantic 校验。支持多个候选输出类型（模型选择其一）、`strict=`、`sequential=`、`max_retries`。
2. **`NativeOutput(outputs)`**：用提供商的 native structured output（如 OpenAI Responses structured outputs / Gemini），不占工具通道。
3. **`PromptedOutput(outputs, template='...{schema}')`**：把 JSON Schema 塞进提示词，模型返回 JSON 文本再校验。
4. **`TextOutput(fn)` / `str`**：纯文本或文本→函数变换。

辅助件：`StructuredDict(json_schema)`（运行期动态 schema，返回带 schema 的 dict 子类）、`Choices(...)`（运行时枚举+描述，`Choice(value=callable)` 可挂动作）、`BoolCriteria`。**输出校验与重试**：`output validators`（逐次运行，`partial_output` 支持流式校验）+ `output_retries` 预算（`AgentRetries={'output':…}`，`_prepare_run` 中 `output_toolset.max_retries`）。strict 模式在 `ToolDefinition.strict` 上有逐 provider 语义（OpenAI 原生 strict / Google `VALIDATED` 等，见 `tools.py` 文档字符串）。

### 1.5 对"自主长任务"支持到什么程度（判断依据）

**单个 run 内部非常完备，但"跨天自主运行"不是本库职责**：

- 已有：请求步数/费用/token/工具次数四类硬限制、run 级 timeout、可恢复的取消（`RunCancelled.all_messages()`）、deferred tools + 人在环审批、后台/挂起任务的续跑、每步 hook（capabilities）、conversation 持久化语义（`conversation_id`、`message_history` 序列化、`Conversation` 对象）。
- 没有：**调度器/心跳/夜间任务**（无人值守的"下一次什么时候再跑"）、**自身状态存储**（情绪、记忆库）。这些被有意外置到：
  - `pydantic-ai-harness`（独立包：memory/planning/compaction/coder/sub-agents，pyproject 注记与 release notes 佐证）；
  - durable execution extras（`temporal` / `dbos` / `prefect` extras + `pydantic_ai/durable_exec/`），把整段 agent run 放进工作流引擎（activity 级重放）；
  - `StepPersistence`/`SqliteStepStore`（步骤级快照，v2.66.0 release notes 提及）。

**结论**：PydanticAI 是"单次 run 的自动驾驶仪"做得最好的 Python 框架之一——限制、超时、取消、恢复、审批全部内建且有明确错误类型。Resident 若以"事件驱动：事件→新 run（携带 history 与状态）→ 结束"的方式组织自主循环，PydanticAI 完全够用；若期待框架自带"跑 3 天的 agent 循环"，则需要自己写外层调度器（或引入 harness/durable extras）。

### 1.6 Windows 兼容与依赖体积

- 核心依赖全部是纯 Python（anyio/httpx2/pydantic/pydantic-graph/opentelemetry-api 等），`pyproject.toml` 中**没有任何 `sys_platform == 'win32'` 的条件依赖**（对比 MCP SDK 的 pywin32）。异步子进程/文件/网络都走 anyio/httpx2 的跨平台抽象。
- 体积评估：`pydantic-ai-slim` 本体 + 9 个核心依赖（pydantic 生态为主）；不装 extras 就没有任何 provider SDK、没有 HTTP 服务器栈。对"Windows 桌面/常驻进程"场景非常友好；唯一注意点是 Python 版本 ≥3.11。

### 1.7 PydanticAI 结论：适合借用什么 / 不适合什么

**适合借用（建议做编排底座）**：
- Agent 主循环 + 工具调用全套语义（图执行、并行工具、`ModelRetry`/`ToolFailed`/HITL 审批/延迟工具、end_strategy）。
- 依赖注入（`RunContext`/`deps_type`）与结构化输出四种模式 + 输出校验重试——Resident 的"情绪状态→回复"每一步都能拿到强类型结果。
- 长任务护栏：UsageLimits、timeout、可恢复取消——直接满足自主角色的失控防护。
- 多模型适配（字符串换模型）+ 失败回退（`FallbackModel`/`RetryModelRequest`）。

**不适合（勿期待、需自建或外挂）**：
- 跨天调度、心跳、记忆/情绪存储——框架刻意不做，需 Resident 自己实现（或引入 harness / durable extras，会显著增重）。
- MCP 集成在 `mcp` extra 里且依赖第三方 `fastmcp-slim`（非官方 python-sdk 本体），版本兼容链条更长（pyproject 注释："FastMCP 4 (MCP SDK v2) is supported concurrently with FastMCP 3; resolvers only select FastMCP 4 with a pre-release opt-in"）。
- 大版本迁移压力：v1→v2 API 变动大（`Usage`→`RunUsage`、默认 end_strategy 变更、包名拆分），v3 已在 TODO 中；跟进成本高。

---

## 二、MCP Python SDK（官方）

### 2.1 基本事实与成熟度（已核实）

| 项 | 事实 | 证据 |
|---|---|---|
| 仓库 | https://github.com/modelcontextprotocol/python-sdk（"The official Python SDK for Model Context Protocol servers and clients"） | GitHub API |
| 版本 | PyPI `mcp` 最新 **2.3.0**（"Production/Stable" classifier）；main 分支 requires-python **>=3.11** | PyPI JSON / `pyproject.toml` |
| 许可证 | MIT | PyPI / 仓库 |
| 归属 | "Model Context Protocol a Series of LF Projects, LLC"（Linux 基金会系列项目），Anthropic 系 maintainer | PyPI 元数据 |
| 活跃度 | 24,776 stars、4,102 forks、395 open issues，近 24h 内有推送；测试配置 `fail_under = 100`（100% 覆盖率门禁） | GitHub API / `pyproject.toml` |
| 结构 | uv workspace：`src/mcp`（SDK）+ `src/mcp-types`（独立 `mcp-types` 包，**运行时依赖只有 pydantic + typing-extensions**） | `pyproject.toml` |

**重要成熟度信号（v2 世代，2026 年刚重写）**：v1 的 `FastMCP` 已变为弃用 shim（`src/mcp/server/fastmcp.py` 仅 769 字节），v2 主类是 `MCPServer`（`src/mcp/server/mcpserver/server.py`）与统一客户端 `Client`（`src/mcp/client/client.py`）。协议本身也在 2026 年发生了一次世代切换（见下）。对我们要"外包外部工具标准化"的决策：**生态标准与 Linux 基金会治理是加分项，但 SDK API 处于快速迭代期**。

### 2.2 协议版本（源码证据）

`src/mcp-types/mcp_types/version.py`：

- `KNOWN_PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28")`
- `LATEST_PROTOCOL_VERSION = "2026-07-28"`；握手世代（initialize handshake）最新为 `LATEST_HANDSHAKE_VERSION = "2025-11-25"`；`MODERN_PROTOCOL_VERSIONS = ("2026-07-28",)`（"stateless per-request envelope"，无 initialize 握手、用 `server/discover` 探测）。
- 最老可协商版本 = `2024-11-05`（`OLDEST_SUPPORTED_VERSION`）——兼容面很宽。
- 客户端 `Client.mode = 'legacy' | 'auto' | <2026-07-28 版本串>`，`auto` 默认先 `server/discover` 探测、失败回退 initialize（`client.py` 的 `__post_init__` 与 `negotiate_auto`）。

### 2.3 传输层（源码证据）

三种传输在客户端与服务端都有实现：

- **stdio**（`src/mcp/client/stdio.py`、`src/mcp/server/stdio.py`）：子进程 + stdin/stdout 上的**换行分隔 JSON-RPC**（`_parse_line` / `model_dump_json` + `\n`）。客户端参数 `StdioServerParameters(command, args, env, cwd, encoding, encoding_error_handler)`。关闭协议 = 关 stdin → 等待 2s → 杀整个进程树。
- **Streamable HTTP**（`src/mcp/client/streamable_http.py`、`src/mcp/server/streamable_http.py` 52KB）：部署推荐传输；服务端产出 **Starlette ASGI app**（`MCPServer.streamable_http_app()`，可挂进 FastAPI），支持 `stateless_http`、会话管理（`StreamableHTTPSessionManager`，空闲超时/最大会话数）、事件存储（SSE 流）、本地默认启用 **DNS rebinding 防护**（`sse_app()` 里 `TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=[...localhost...])`）。
- **SSE**（`src/mcp/client/sse.py`、`src/mcp/server/sse.py`）：保留的旧传输（HTTP GET /sse + POST /messages/）。
- 另有**进程内直连**：`Client(server_instance)` 直接用 `InMemoryTransport`/`DirectDispatcher`，无 JSON-RPC 帧（`client.py` 的 `_connect_inproc`）——对 Resident"内部模块间调用"非常实用。

### 2.4 工具注册模型（源码证据）

服务端注册链（v2）：

1. `MCPServer("name")` 上的装饰器 `@server.tool(...)`（还有 `@server.resource("uri://...")`、`@server.prompt()`）——见 `mcpserver/server.py`。
2. 工具本体：`mcpserver/tools/base.py` 的 `Tool.from_function()`：
   - **函数签名 + docstring → JSON Schema**：`func_metadata(fn, skip_names=[context_kwarg])` 生成 pydantic 参数模型，`arg_model.model_json_schema(by_alias=True, schema_generator=UntitledJsonSchema)` 即输入 schema；`description` 默认取 docstring；lambda 必须显式命名；工具名有合法性校验（`validate_and_warn_tool_name`）。
   - **Context 注入**：`find_context_parameter(fn)` 自动识别签名里的 context 参数（`Context` 携带请求上下文、服务端 logger、采样/elicitation 能力等）。
   - **参数解析器（Resolve）**：`Resolve(...)` 参数可声明"从资源/上下文取值的惰性参数"，支持 `InputRequiredResult` 多轮向客户端要输入（2026-07-28 协议特性）。
   - **错误边界**（`Tool.run`）：参数校验失败 → `ToolError`（模型可读的 isError 结果）；预期错误保留原文；意外异常 → `UnexpectedToolError`（**原文不外泄给客户端**，只记服务端日志）——这条对"外部插件"安全模型很有价值。
3. 结果转换为 `CallToolResult`（text/blob/structured_content；`output_schema` 支持结构化输出校验），`ToolManager`（`mcpserver/tools/tool_manager.py` + `resolve.py` 36KB）负责 lookup/调用。

客户端（`client.py` 的 `Client`）：`async with Client(url | StdioServerParameters | Transport | Server) as c: await c.call_tool(name, args)`；带响应缓存（`SEP-2549` ttl）、`HEADER_MISMATCH` 自动重列工具重试、InputRequired 自动多轮驱动、订阅（`client.listen(tools_list_changed=...)`）、分页 list、进度回调。服务端还有认证栈（`server/auth/`：OAuth 授权服务器 provider / Bearer token verifier + `AuthSettings`）、middleware 链、extensions 机制（`SEP-2133`）。

### 2.5 Windows 下怎么用（源码证据，这条最扎实）

`src/mcp/client/stdio.py` + `src/mcp/os/win32/utilities.py`：

- Windows 上启动子进程：`CREATE_NO_WINDOW` 标志（不弹控制台窗）；若事件循环不支持异步子进程（SelectorEventLoop）自动回退到 `subprocess.Popen` + anyio `FileReadStream` 包装的 `FallbackProcess`。
- **进程树终止用 Job Object**：`CreateJobObject` + `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`，`AssignProcessToJobObject`；关闭 job 句柄即杀全树（Windows 无 SIGTERM 树级信号，代码注释明确："Windows kills hard"）。这就是 `pywin32>=311` 条件依赖的用途。
- 环境变量白名单：Windows 上默认只继承 `APPDATA/HOMEDRIVE/HOMEPATH/LOCALAPPDATA/PATH/PATHEXT/PROCESSOR_ARCHITECTURE/SYSTEMDRIVE/SYSTEMROOT/TEMP/USERNAME/USERPROFILE`，且跳过 shell 函数注入（`get_default_environment`）。
- 可执行文件解析：`get_windows_executable_command` 依次试 `shutil.which` 后补 `.cmd/.bat/.exe/.ps1`。
- 服务端 `stdio_server()` 跨平台可用；HTTP 传输用 uvicorn（依赖已含，`uvicorn>=0.31.1`）。

### 2.6 是否值得把"外部工具标准化"外包给 MCP（结论）

**值得，且是当前最优解**，理由（源码支撑）：

1. **生态即协议**：Claude Desktop、几乎所有 agent 框架都吃 MCP；我们的插件若以 MCP server 形式发布，等于免费获得外部工具池（`mcp` 包既做 client 也做 server，Resident 可以同时"消费外部插件"与"把自己暴露为 MCP server"）。
2. **类型体系可单独依赖**：`mcp-types` 包（`src/mcp-types/`，依赖仅 pydantic+typing-extensions）可单独引用来"只说协议话、不带传输栈"（`src/mcp/types/__init__.py` 的模块文档明说此用法）。
3. **Windows 支持有真投入**：Job Object 进程树管理、CREATE_NO_WINDOW、env 白名单、WinError 重试——比大多数自研插件宿主强。
4. **免费获得**：分页、进度、采样、elicitation（多轮向模型要输入）、OAuth 认证、DNS rebinding 防护、错误边界（意外异常不外泄）——自己实现这些的工程量远大于接入成本。

**代价与注意**：

- `mcp` 完整包的核心依赖包含 **starlette + uvicorn + sse-starlette**（server 栈）+ pywin32（Windows）——只做客户端也会带上；在意体积就只依赖 `mcp-types` + 自写 stdio/HTTP 客户端，或接受完整包（对 Resident 常驻程序，这个体积可接受）。
- API 处于 v2 早期：FastMCP 已弃用、`ping`/`logging`/`roots`/`subscribe_resource` 等已标记 deprecated（2026-07-28 移除），跟进成本真实存在；锁 `mcp==2.3.0` 并跟踪升级。
- 插件安全模型要自己定：MCP 只规定"tools/resources/prompts"结构与 isError 语义，**不规定沙箱/权限**（服务端只保证异常不外泄；"工具能干什么"是插件作者的事）。Resident 应要求插件提供 stdio 命令 + 权限清单，由宿主决定放行。

---

## 三、companion-emergence（情绪/记忆衰减研究项目）

### 3.1 真实仓库核实结果

- **真实仓库：`hanamorix/companion-emergence`（https://github.com/hanamorix/companion-emergence ）**。GitHub 全站搜索 `companion-emergence` 的唯一同名仓库（`search/repositories` API，total=10 中仅此一个 exact name 匹配）。
- 元数据（GitHub API）：Python 语言、MIT、**2026-04-21 创建、2026-11-05 仍在推送**、64 stars / 12 forks / 186 open issues。描述："Local-first AI companion framework — persistent memory, emotional state, dreaming, embodied avatar. Desktop app + Python brain. macOS · Linux · Windows. Runs against Claude."
- 技术栈（README 自述，仅作背景）：Python 3.13 框架 + Tauri 2 桌面壳（NellFace）+ FastAPI bridge；LLM 通过 **Anthropic `claude` CLI 子进程**调用；SQLite 记忆库 + Hebbian 连接矩阵；**明确标注 pre-1.0**（"breaking changes can land in any release"）。约 2,480 个单元/集成测试。
- **与 ailover-atlas.com 项目页的关系：未核实**。调研期间该域名 DNS 解析失败（EAI_AGAIN），Wayback Machine 无存档（CDX 查询为空）。仅能确认：名字完全一致、主题完全一致、站点同时列出 OpenHer / ghost-bf 等同类项目；hanamorix/companion-emergence 是唯一候选仓库。**凡本节结论均出自该仓库源码，与 ailover-atlas 页面无关**。
- 源码规模佐证其"研究项目"属性：`brain/` 下 160+ 文件，情绪/遗忘/成长/梦/悲伤/主观时间/身体状态各有独立子包。

### 3.2 情绪表示（多少维）——已核实源码

`brain/emotion/vocabulary.py`：

- 基线 **26 个情绪**，分三类：**11 core**（love, joy, grief, anger, fear, desire, arousal, pride, shame, tenderness, awe）、**11 complex**（nostalgia, jealousy, guilt, relief, loneliness, curiosity, gratitude, defiance, vulnerability, belonging, memory_grief）、**4 body**（climax, touch_hunger, comfort_seeking, rest_need）。
- 每个 `Emotion(name, description, category, decay_half_life_days, intensity_clamp=10.0)`：
  - 强度统一钳制在 **[0, 10]**（`intensity_clamp=10.0`）。
  - **逐情绪半衰期**：`arousal=0.5 天、climax=0.125 天、anger=1 天、touch_hunger=1.5、desire/curiosity/relief=2、joy/awe=3、fear/defiance/vulnerability=5、pride/tenderness/jealousy=7、loneliness=10、shame/guilt/gratitude=14、nostalgia=21、memory_grief=30、grief=60 天**；`love` 与 `belonging` 为 **`None`（identity 级，不随时间衰减）**。
  - **可扩展**：`register()` 允许 persona 从 `emotion_vocabulary.json` 注册 `persona_extension` 情绪（`persona_loader.py` 完整实现加载 + 自愈：词汇表损坏时从记忆反推重建，`_heal_referenced_but_unregistered`）。
  - 拼写归一：`canonical_name()`（小写、`-`→`_`、`a_b_blend` 两段排序归一）。
- `brain/emotion/state.py`：当前情绪状态 = `emotions: {name: intensity}` + `dominant`（最高强度者，平局按插入序）+ `residue`（最近 16 条情绪事件快照，用于跨轮次/梦的余韵）。全部写入走 `set()`（校验词汇表与钳制）。
- `brain/emotion/arousal.py`：**7 级 arousal 谱系**（TIER_DORMANT=0 → CASUAL=1 → WARMED=2 → REACHING=3 → CHARGED=4 → HELD=5 → EDGE=6），由 `raw = Σ(情绪强度×权重)`（arousal×1.0, desire×0.7, tenderness×0.2, love×0.15）− 抑制项（grief×0.9, shame×0.7, fear×0.5）+ 体温加成（每度 +0.3），再按阈值 [0.5, 2, 5, 8, 11] 离散化。
- `brain/emotion/aggregate.py`：从记忆集合合成"当前情绪"用 **max-pooling**（每情绪取最强信号，非平均）；`climax≥7` 触发 reset 钩子（arousal×0.2、desire×0.6、comfort_seeking+2、rest_need+2、climax 归零）——即"事后不应期"建模。
- `brain/emotion/influence.py`：情绪 → 行为偏置的结构化中间层（`InfluenceHints`：dominant_emotion / arousal_tier / tone_bias∈{neutral,tender,crisp,generative} / voice_register / suggested_length_multiplier），由各 provider 渲染成 Claude prefill、OpenAI 结构化块等——**情绪不直接写 prompt，而是结构化注入**。

### 3.3 记忆与情绪衰减公式——已核实源码

**情绪衰减**（`brain/emotion/decay.py`，全文只有这一个公式）：

```
new = old · (1/2)^(elapsed_days / decay_half_life_days)      # 指数半衰期衰减
若 new < _NOISE_FLOOR(=0.01) → 删除该情绪通道
若 decay_half_life_days is None（love/belonging）→ 不衰减
elapsed_days = elapsed_seconds / 86400
```

配套（`brain/dev_constants.py`）：`EMOTION_VALUE_CAP=10.0`；**记忆存储值的保底** `EMOTION_FADE_FLOOR_FRACTION = {"love": 1/3, "belonging": 1/3}`（爱/归属永不降到存储值的 1/3 以下）；默认半衰期 14 天；重复展示折扣 `EMOTION_REPEAT_WINDOW_H=24h、EMOTION_REPEAT_FACTOR=0.5`（24h 内重复展示的信号按 0.5、0.25…折算）。新引擎（`emotion/engine.py`）还定义了 short/long 双平均线（24h 短 / 30 天长）与 shift 检测。

**记忆衰减（显著性 + 状态机）**，`brain/forgetting/salience.py`：

```
salience = 0.30·emotion + 0.20·hebbian + 0.20·recall + 0.20·soul + 0.10·freshness     # 全部 [0,1]
```

- `emotion` = max(记忆情绪峰值/10, peak 残留)；peak 残留 = `1.5·log1p(peak)/log1p(10) · linger`，linger 在 180 lived-days 线性归零——"曾经重要过的记忆不会因情绪衰减而立即失势"。
- `hebbian` = 激活次数/20；`recall` = 回忆次数/10；`soul` = 是否被灵魂结晶（0/1）。
- `freshness = 1 − clamp(lived_hours / horizon_eff)`，horizon 基线 **2160 lived-hours（≈90 个"主观日"）**，随 `importance` 拉伸（`importance_stretch`，gain 52）。

**遗忘状态机**（`brain/forgetting/policy.py` + `brain/forgetting/__init__.py` + `brain/dev_constants.py`）：

- 阈值（dev_constants，注释明确"删除地板是不可下调的不变量"）：`FADE_THRESHOLD=0.25`（salience 低于它 active→fading）、`LOST_THRESHOLD=0.10` 且 **连续 2 次 pass**（`LOST_PASS_COUNT=2`）→ fading→lost（写墓碑进 graveyard → 硬删除 → 移除 Hebbian 边 → 触发 grief）。
- 有效 fade 阈值 = `FADE_THRESHOLD / (1 + narrative_weight + FADE_IMPORTANCE_GAIN(2.0)·importance_ratio)`——叙事压力与重要性只推迟 fade，**绝不降低删除地板**。
- 豁免：灵魂结晶/候选审核中；**RECENT_LIVED_HOURS=720（30 天 wall-clock）内新建记忆**；迁移 7 主观日宽限；冷启动全部豁免。
- 工程细节：forgetting pass 逐条记忆**断点续跑**（`forgetting_progress.json` cursor，keyset 语义），每条的 counter 即时落盘，聊天间隙可让路（`should_pause`）。

### 3.4 人格漂移机制——已核实源码

人格的"漂移"不是改写 prompt，而是**词汇表与行为结晶（crystallization）**：

1. `brain/growth/scheduler.py`（`run_growth_tick`）：按 `throttle_days` 节流的周期性 tick，调用各 crystallizer，**"Crystallizers decide; the scheduler applies"——无人工审批门、无候选队列**；提案原子写入 `emotion_vocabulary.json`（`.new + os.replace` + `.bak` 轮转）并追加 `emotion_growth.log.jsonl`（生物式档案）。名称有字符白名单校验；重名幂等跳过。
2. `brain/growth/crystallizers/vocabulary.py`（当前已实现的结晶器，**确定性本地启发式，刻意不用 LLM 命名**）：挖掘活跃记忆中"反复出现的双情绪组合"——**≥3 条活跃记忆、其 top-2 情绪强度均 ≥6.0** → 提议一个新情绪 `"<a>_<b>_blend"`（persona_extension，半衰期 45 天，score=均值/10 封顶 1.0）。**人格因此"长出新情绪词"**，新词参与衰减/聚合/影响下游。
3. 其他结晶器（存在但处于演进中）：`growth/crystallizers/reflex.py`（28.8KB，条件反射弧的涌现与修剪 `ReflexArcProposal`/`ReflexPruneProposal`）、`growth/crystallizers/creative_dna.py`（23.6KB，创意指纹）。`growth/proposal.py` 定义提案类型（"Proposals are the brain's *decisions*"）。
4. 支撑结构：`brain/soul/`（人格把"load-bearing"记忆结晶为灵魂条目，用户可审、可撤销、永不静默改写）；`brain/felt_time/`（lived_age：主观年龄按活跃速率增长，MAX_LIVED_RATE 封顶；heavy 叙事线程让主观时间变慢）；`brain/attunement/`（对用户的阅读从"hunch"成熟为"known"，成型阈值 3/10 次观测）。

### 3.5 companion-emergence 结论：适合借用什么 / 不适合什么

**适合借用（作为 Resident 情绪/记忆子系统的设计蓝图）**：

- **逐情绪半衰期 + 指数衰减 + 噪声地板 0.01 + identity 级不衰减**（`decay.py`）——公式简洁、可调、测试友好，直接可移植。
- **遗忘三级状态机**（salience 复合评分 → FADE/LOST 双阈值 + 连续 pass 计数 + 30 天豁免 + "删除地板不可下调"设计原则）——比"定期清库"或"纯 TTL"合理得多，且带 graveyard/grief 的可审计性。
- **人格漂移 = 结晶器 + 提案 + 原子落盘 + 生长日志**（`growth/` 全套），尤其是"新情绪从反复共现中结晶"这一确定性算法。
- 情绪→行为的**结构化中间层**（`influence.py` 的 InfluenceHints）而非把情绪文本塞进 prompt。
- 工程细节可直接抄：SQLite busy timeout 策略、Windows WinError 32 重试（`FILE_RETRY_ATTEMPTS=8`）、崩溃自愈（`.bak` 轮转 + 从记忆重建词汇表）。

**不适合**：

- **整体架构**（Tauri 壳 + FastAPI bridge + 靠 `claude` CLI 子进程跑 LLM）与 Resident（Python/Windows、独立编排底座）重叠度低，不应整仓引入。
- **pre-1.0 契约**：README 明示 API/文件格式任意版本可破坏；依赖其内部模块需自担迁移成本。
- 情绪维度（26 维 + 身体情绪 + 性相关通道）是为"亲密陪伴"场景设计的，Resident 需裁剪（但衰减/遗忘机制本身与场景无关）。
- 记忆检索栈重（本地 reranker/embedding/LLM judge 自调优——`brain/memory/` 下有 LoRA/全量微调管线的代码），不建议照搬，只借评分公式。

---

## 四、汇总判断（针对 Resident）

| 项目 | 一句话定位 | 建议 |
|---|---|---|
| **PydanticAI** | 单次 agent run 的编排与工具调用引擎，长任务护栏内建但调度/状态外置 | **用作编排底座**：主循环、工具、DI、结构化输出、可恢复取消全部采用；自主循环（心跳/调度）与记忆/情绪存储由 Resident 自建。锁 `pydantic-ai-slim`，不装 harness/durable extras 起步 |
| **MCP Python SDK** | 外部工具/插件标准化的行业事实标准，官方 SDK 的 Windows 与安全边界支持扎实 | **外包插件协议**：插件 = MCP server（stdio 优先，Windows 已有 Job Object/无窗/白名单支持）；Resident 用官方 `mcp` 做客户端，可选把自己暴露为 MCP server。注意锁 `mcp==2.3.0`（v2 API 迭代中），权限模型自行加在宿主层 |
| **companion-emergence** | 情绪/记忆衰减与人格漂移的"研究原型"，公式完整可考、工程细节扎实但 pre-1.0 且场景绑定 | **只借机制不引代码**：移植半衰期衰减、salience 遗忘状态机、结晶式人格漂移三套公式与阈值设计，重写进 Resident 自己的状态模块 |

**组合形态建议**：Resident = PydanticAI（run 引擎）+ 自建状态层（借 companion-emergence 的公式）+ MCP（插件边界）+ 自建调度器（事件驱动地发起新 run）。三者接口清晰、职责不重叠，是当前证据下最省工程量且升级风险可控的组合。

---

## 源码证据清单

### PydanticAI（pydantic/pydantic-ai，main 分支，release v2.66.0）
1. `pydantic_ai_slim/pyproject.toml` — MIT、requires-python ≥3.11、9 个核心依赖、extras 清单（openai/anthropic/google/mcp/cli/web/temporal/dbos/prefect…）。
2. `pydantic_ai_slim/pydantic_ai/_agent_graph.py` — `build_agent_graph`、`UserPromptNode/ModelRequestNode/CallToolsNode`、`EndStrategy`（默认 graceful）、`MAX_MODEL_REQUEST_ATTEMPTS=100`、`set_agent_graph_sleep`、suspended-response 续跑链。
3. `pydantic_ai_slim/pydantic_ai/agent/__init__.py` — `class Agent(AbstractAgent[AgentDepsT, OutputDataT])`、`deps_type`、`run()` 参数（usage_limits/cancellation_token/timeout/retries/capabilities/workspace/spec）、`_prepare_run` 的重试预算解析、`_run_lifecycle_hooks`。
4. `pydantic_ai_slim/pydantic_ai/_run_context.py` — `RunContext` 全部字段（deps/usage/usage_limits/deadline/cancel/enqueue/emit/load_capability）、`_CURRENT_RUN_CONTEXT` ContextVar。
5. `pydantic_ai_slim/pydantic_ai/usage.py` — `UsageLimits(request_limit=50, cost_limit, tool_calls_limit, …)` 及 `check_before_request`；`RunUsage.requests` 语义。
6. `pydantic_ai_slim/pydantic_ai/exceptions.py` — `ModelRetry`、`ToolFailed`、`CallDeferred`、`ApprovalRequired`、`SkipToolValidation/Execution`、`RetryModelRequest`、`RunCancelled.all_messages()`、`RunTimedOut`、`UsageLimitExceeded`、`ModelAPIError` 分类体系。
7. `pydantic_ai_slim/pydantic_ai/output.py` — `ToolOutput/NativeOutput/PromptedOutput/TextOutput`、`OutputMode`、`StructuredDict`、`Choices`、`BoolCriteria`。
8. `pydantic_ai_slim/pydantic_ai/tools.py` — `Tool` 构造（max_retries/prepare/args_validator/strict/sequential/requires_approval/timeout/defer_loading）、`ToolDefinition.kind ∈ {function,output,external,unapproved}`、`SystemPromptFunc`/`ToolFuncContext` 类型、`GenerateToolJsonSchema`。

### MCP Python SDK（modelcontextprotocol/python-sdk，main 分支；PyPI mcp 2.3.0）
9. `pyproject.toml` — MIT、requires-python、核心依赖（anyio/httpx2/mcp-types/pydantic/starlette/uvicorn/sse-starlette/jsonschema/**pywin32(win32)**/pyjwt…）、`fail_under=100`、workspace 成员。
10. `src/mcp-types/mcp_types/version.py` — 5 个协议版本、`LATEST_PROTOCOL_VERSION="2026-07-28"`、`LATEST_HANDSHAKE_VERSION="2025-11-25"`、`MODERN_PROTOCOL_VERSIONS`。
11. `src/mcp/__init__.py` — 公开 API（`Client`、`ClientSession`、`StdioServerParameters`、`stdio_client/stdio_server`）；`mcp.types` 镜像自 `mcp_types`。
12. `src/mcp/server/mcpserver/server.py` — `MCPServer.run(transport="stdio"|"sse"|"streamable-http")`、`streamable_http_app()/sse_app()`（Starlette）、认证、`_handle_call_tool` 错误边界、`@server.resource/prompt`。
13. `src/mcp/server/mcpserver/tools/base.py` — `Tool.from_function()`（签名/docstring→JSON Schema、context 注入、错误分类 ToolError/UnexpectedToolError）、`Tool.run()`。
14. `src/mcp/client/client.py` — `Client`（URL/stdio/Transport/in-process 四种连接）、`mode` 协商、call_tool（缓存、HEADER_MISMATCH 重试、InputRequired 驱动）。
15. `src/mcp/client/stdio.py` — NDJSON 协议、`StdioServerParameters`、关闭升级序列、`get_default_environment` 白名单。
16. `src/mcp/os/win32/utilities.py` — `CREATE_NO_WINDOW`、Job Object（KILL_ON_JOB_CLOSE）、`FallbackProcess`、`get_windows_executable_command`、`rebind_std_handle_to_fd`。
17. PyPI `mcp/json` — 版本 2.3.0、"Production/Stable"、LF Projects 归属。

### companion-emergence（hanamorix/companion-emergence，main 分支）
18. `brain/emotion/vocabulary.py` — 26 维基线情绪表（11 core + 11 complex + 4 body）、per-emotion `decay_half_life_days`（0.125–730 天、None=identity）、`intensity_clamp=10.0`、`register()`/`canonical_name()`。
19. `brain/emotion/decay.py` — 指数衰减公式 `new=old·(1/2)^(Δt/half_life)`、`_NOISE_FLOOR=0.01`。
20. `brain/emotion/state.py` — `EmotionalState`（emotions/dominant/residue=16 条上限）、`set()` 钳制与校验。
21. `brain/emotion/arousal.py` — 7 级 arousal 谱系与加权公式、抑制项、体温耦合。
22. `brain/emotion/aggregate.py` — max-pooling 合成、climax≥7 的 reset 钩子。
23. `brain/emotion/influence.py` — `InfluenceHints`（tone_bias/voice_register/length_multiplier）规则表。
24. `brain/emotion/persona_loader.py` — persona 词汇加载、损坏自愈、从记忆重建缺失情绪。
25. `brain/forgetting/salience.py` — 复合公式 `0.30·emotion+0.20·hebbian+0.20·recall+0.20·soul+0.10·freshness`、freshness 线性衰减（2160 lived-hours 基线）、peak 残留（λ=1.5、180 lived-days）。
26. `brain/forgetting/policy.py` — FADE/UNFADE/LOSE 状态机、豁免门（soul/审核/30 天 recent/迁移宽限）、importance 拉低有效 fade 阈值。
27. `brain/forgetting/__init__.py` — `run_pass` 编排（graveyard→hard_delete→grief、断点续跑、失败关闭语义）。
28. `brain/dev_constants.py` — `FADE_THRESHOLD=0.25`、`LOST_THRESHOLD=0.10`、`LOST_PASS_COUNT=2`、`RECENT_LIVED_HOURS=720`、`FADE_IMPORTANCE_GAIN=2.0`、`HORIZON_IMPORTANCE_GAIN=52.0`、`EMOTION_HALF_LIFE_DAYS` 全表、`EMOTION_FADE_FLOOR_FRACTION={love:1/3, belonging:1/3}`、Windows 文件重试常量。
29. `brain/growth/scheduler.py` — `run_growth_tick`（节流、crystallizer 决策、无人工审批、原子写 vocabulary + growth log）。
30. `brain/growth/crystallizers/vocabulary.py` — 双情绪 blend 结晶算法（≥3 条记忆、top-2 均 ≥6.0 → `a_b_blend` 新情绪，half-life 45 天）。
31. `brain/growth/proposal.py` — `EmotionProposal`/`ReflexArcProposal`/`ReflexPruneProposal` 类型。
32. GitHub API：仓库元数据（2026-04-21 创建、MIT、pre-1.0、64 stars）；`search/repositories?q=companion-emergence` 唯一性确认；README（背景：claude CLI 依赖、Task Scheduler、Windows x86_64 bundle）。

### 未核实项（明示）
- ailover-atlas.com `/en/projects/companion-emergence/` 页面内容：域名解析失败 + Wayback 无存档，**页面与 hanamorix/companion-emergence 的对应关系基于名称/主题/唯一性推断，未直接核实**。
- 三个项目的任何"运行行为"均未执行验证（未安装依赖、未跑代码），结论全部来自静态源码阅读。
