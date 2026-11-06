# RESEARCH_REPORT — Resident 候选项目源码研究报告

日期：2026-11-06 ｜ 阶段：Phase 0 ｜ 方法：源码级取证（行号证据见各 `research/*.md`）

结论先行：**没有项目值得整体作为底座**。HerAndHim 可抽四个包当零件；
Crescent Grove 可抽四个小模块；PaulusAI 可抽安全三件套+记忆+情绪+MCP 客户端；
Letta 不碰；Mem0 仅作第一周原型；框架层建议自建薄循环。

---

## 1. Crescent Grove

- 仓库：https://github.com/Canon-73/crescent-grove （官网 crescent-grove.net 仅营销站）
- 许可证：MIT ｜ 语言：Python + Electron ｜ Windows-first
- 版本：v0.1.14；仓库仅 1 条快照提交（2026-09-22），**无真实 git 历史**
- README 宣称组件全部核实存在：
  - LETHE 对数衰减情节记忆：`core/compressor.py:28`
  - Wyrd Network 联想图（JSON 图 + FAISS + 扩散激活 + 侧抑制）：`core/wyrd_network.py:343`
  - Moonbeat 30 分钟脉冲：`core/scheduler.py:1619`
  - MoonTide 情绪粒子：`vital/moontide_v2.py:73`
  - Salia 观察者 LLM：`core/salia.py:186`
  - 插件系统（子进程卫星，manifest + stdin/stdout JSON）：`core/tools.py:849`
  - 主循环 = 事件 + 轮询双轨，工具循环上限 40 轮：`core/agent.py:3183`
- 结论：不适合 fork 当底座（agent/context/scheduler 三大单体 ~410KB、耦合深、个人运维假设多）。
  可抽：LETHE、Wyrd、MoonTide、DesireManager（约 2000 行，依赖少，LLM 可注入）。

## 2. HerAndHim

- 仓库：https://github.com/ericwang915/HerAndHim ｜ PyPI v0.2.0（2026-08-13）
- 许可证：**AGPL-3.0**（对外提供服务需开源改动，注意）｜ Python >=3.10
- 规模：93 个 .py，22,114 行，437 个测试；main 最后提交 2026-10-06
- 主循环：消息驱动同步 `chat()` + APScheduler 六个后台任务
- 记忆：Markdown KV + 每日日志 + SQLite FTS5 + JSONL 情绪图/时间线；写时整理（Mem0-lite）
- 检索：BM25 → dense 三级降级 + RRF + LLM rerank
- 调度：24h 日程 planner + 每 5 分钟概率主动消息 + cron + 心跳 + 夜间整理
- 情绪：无状态机；每日随机心情 + LLM 情感事件 + 关系四维 0–100
- 短板：**无事件总线**（1/10）；记忆无类型 schema、写入靠 prompt 教 LLM（6/10）；
  “自主”=掷骰+LLM 编内容，非任务规划（9/10）；agent.py 是 2110 行 god object
- Windows：核心可跑；daemon 用 os.kill(pid,0) 在 Windows 会误杀进程、时区退化固定偏移
- 结论：抽 `memory / retrieval / scheduler / storage` 四个包当零件；骨架自建。

## 3. PaulusAI

- 仓库：https://github.com/Pavel6625/PaulusAI （= Pavel Shlepnev）
- 许可证：MIT ｜ Python 3.10+ ｜ 6,443 行实现 + 4,102 行测试
- 最新提交 2026-11-05（v1.5.2 头），release v1.4.0（2026-11-01）
- 主循环：手工工具循环（感知→组上下文→推理→**安全门**→行动→持久化），安全门插在模型输出与副作用之间
- 记忆：episodic.jsonl（有界 2000）+ facts.json（唯一真源，LLM 仲裁去重/矛盾覆盖）+ semantic.md
  + Chroma 派生索引（关键词回退）；salience×0.9/次 consolidation，<0.05 遗忘
- 情绪：PAD 三维 + 16 情绪 OCC（affect.py / appraisal.py，纯数学可独立成库）
- MCP：纯客户端（stdio/HTTP/SSE/OAuth），工具默认全门控，结果打 untrusted 标签
- 安全：write/run/send/email 逐个审批；auto 模式审阅器“少看原则”；grant 黑名单
  （rm/curl/sudo/sh -c 永不可授权）；审计日志；sandbox local/docker/ssh；fail-closed 计费
- 短板：mood/skills 全局共享、技能检索仅关键词、无自主规划器（正是 Resident 要补的层）
- Windows：官方仅 Linux；shell=True、shlex posix=True 需适配
- 结论：抽 审批三件套（security/grants/automode）> memory+vectorstore > affect+appraisal > mcp_client。

## 4. Letta（前 MemGPT）

- 仓库：https://github.com/letta-ai/letta ｜ Apache-2.0
- **现状（补充核实）**：Python 服务器 0.16.8 已官宣退役，main 已迁往 TypeScript 的
  letta-code；`pip install letta` 变成捆绑 Node 的 CLI → 不再适合嵌入
- 仍值得抄：**schema 设计** —— Block + BlockHistory(undo/redo) + Passage(source_id 溯源)
  + Message 事件日志
- 结论：不采用代码；只借 schema 思路。

## 5. Mem0

- 仓库：https://github.com/mem0ai/mem0 ｜ Apache-2.0 ｜ Python
- **v2.2.1 是 344KB 纯 Python 可嵌入库**（非早期 ~480MB 印象）：自带 LLM 抽取 → md5 去重 →
  实体链接 → 语义+BM25+实体 boost 混合检索 → SQLite 全审计管线
- 注意：主存是向量库而非 SQLite；冲突仅“关联”不自动裁决；六类记忆要靠 metadata 约定
- 结论：**适合嵌入/仿写其管线**（抽取→去重→链接→混合检索→审计），schema 抄 Letta 的
  Block/BlockHistory/Passage(source_id 溯源)/Message 事件日志；仍不作长期底座。

## 6. 记忆层总决策（详见 ARCHITECTURE_DECISIONS.md）

自建 SQLite 记忆层：FTS5 全文 + 时间衰减 + 来源追踪 + 六类记忆 schema；
借 Letta 的分层与去重思路、Mem0 的 LLM 仲裁决策；向量需求后期用 sqlite-vec（远轻于 ChromaDB）。

## 7. 研究产物清单

- `research/crescent-grove.md`（源码证据清单）
- `research/herandhim.md`（43 条证据）
- `research/paulusai.md`（44 条证据）+ `research/paulusai-src/`
- `research/letta-mem0.md` + `research/HerAndHim-main/` 源码镜像
- `research/frameworks-mcp.md`（32 条证据）
- `research/ENVIRONMENT.md`

## 8. 框架与协议层（frameworks-mcp 报告）

- **PydanticAI v2.66.0（MIT，Python≥3.11，纯 Python 依赖 9 个）**：主循环是 pydantic-graph 图；
  工具语义完备（ModelRetry / ToolFailed / 人在环审批 / 延迟工具）；RunContext DI；
  四种结构化输出；内建长任务护栏（默认 50 步、费用/token 上限、可恢复取消）。
  **选为编排/工具调用底座**（只承担 loop+tooling，不承担身份/记忆/情绪/调度）。
- **MCP Python SDK v2.3.0（LF 项目，MIT）**：Windows 支持扎实（Job Object 进程树终止、
  CREATE_NO_WINDOW、env 白名单）；签名+docstring 自动生成 JSON Schema；异常不外泄。
  **Phase 4 起用于插件/外部工具标准化**；锁 2.3.0，FastMCP 已弃用不用。
- **companion-emergence（hanamorix/companion-emergence，MIT，pre-1.0）**：26 维情绪
  （11 core+11 complex+4 body，逐情绪半衰期 0.125–730 天，love/belonging 不衰减）、
  记忆遗忘 = 五因子显著性（0.30 情绪+0.20 Hebbian+0.20 回忆+0.20 灵魂+0.10 新鲜度）
  + FADE/LOST 状态机、双情绪共现“结晶”人格漂移（半衰期 45 天）。
  **只借公式与阈值**（衰减/遗忘/结晶），不整仓引入；其“人格漂移无人工审批”不合我们的安全模型，须加审批。

## 9. 选型结论（任务 C）

四种路线的对比与最终选择：

| 路线 | 评价 |
| --- | --- |
| 完全自主开发 | 重复造轮子；工具循环/衰减公式有现成可借 |
| 以 Crescent Grove 为核心 | 无 git 历史、三大单体耦合深、个人运维假设多 → 否 |
| 复用多项目独立模块 | ✅ 采用：HerAndHim 四包、Crescent Grove 四模块、PaulusAI 安全/记忆/情绪、companion-emergence 公式 |
| Agent 框架当底层 | ✅ **局部采用**：PydanticAI 只当编排/工具层；拒绝 LangGraph/AutoGen 类黑盒 |

**最终架构**：PydanticAI（loop+tooling） + 自建 Identity / Memory（SQLite+FTS5+衰减）/
Life（调度+欲望+目标）/ Security（L0–L3+审批）/ EventBus / ModelGateway
+ 适配器（先 CLI，后 MC）。

