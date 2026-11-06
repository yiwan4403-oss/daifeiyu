# Crescent Grove 源码级调研报告

> 调研时间：2026-11-06（Asia/Shanghai）
> 调研方式：GitHub API（api.github.com）元数据落盘 + raw.githubusercontent.com 拉取关键源文件到本地
> 本机落盘目录：`Resident\research\`（`repo.json` / `summary.txt` / `src\*.py` 等）
> 结论先行：**源码可完整取得**，官网确实只是营销站，真实仓库为 GitHub 上的 `Canon-73/crescent-grove`，MIT 协议，README 中宣称的 LETHE、Wyrd Network、Moonbeat、MoonTide、Salia 等组件**全部在源码中真实存在**。

---

## 1. 真实源码仓库

| 项目 | 值 |
|---|---|
| 仓库 URL | **https://github.com/Canon-73/crescent-grove** |
| 官网（非源码） | https://www.crescent-grove.net/en/ （WordPress 营销站，Download 按钮指向 GitHub Releases） |
| 仓库简介 | "Raise your own AI partner — an open-source, local-first AI agent platform with persistent memory and evolving personality." |
| 所有者 | `Canon-73`（个人账号，id=124697815）；官网署名「カノン / Canon」 |
| fork？ | 否（`fork: false`） |
| 语言 | Python（3,692,617 字节，绝对主力）+ HTML/TypeScript/JavaScript/CSS（Electron 客户端 Liner 与 Web UI） |

### 1.1 最新提交 / 历史性质（重要）

- `pushed_at: 2026-09-22T15:53:57Z`；`updated_at: 2026-10-30T14:12:15Z`。
- **整个公开仓库只有 1 条 commit**：`e622f95425`，"Crescent Grove snapshot 2026-09-23 (dev bd676c6)"，提交时间 2026-09-22T15:42:00Z。
- 该 commit 的 git 作者名是占位符 `Your Name <your.email@example.com>`，GitHub 登录名为 `h15629526027`（与仓库所有者 Canon-73 不是同一账号）。
- 仓库 README 自己承认（`README.md:519-523`）：*"This repository is a public snapshot taken from the author's development branch. It does not necessarily match any specific installer release exactly."*
- 含义：**没有真实 git 历史**，无法做 bisect / 按提交追溯演进；源码由开发分支定期整体倾倒而来。

### 1.2 Release 情况

| 版本 | 发布时间 | 附件 |
|---|---|---|
| v0.1.0 | 2026-06-06 | Crescent.Grove.Setup.0.1.0.exe（约 649 MB） |
| v0.1.1 | 2026-06-07 | 同上 |
| v0.1.9 | 2026-06-22 | 约 662 MB |
| v0.1.12 | 2026-09-08 | 约 663 MB |
| v0.1.13 | 2026-09-22 | 约 663 MB |
| **v0.1.14（latest）** | 2026-09-22 | `Crescent.Grove.Setup.0.1.14.exe`（705,669,284 字节，36 次下载）+ `SHA256SUMS.txt` |

- 全部为 Windows NSIS 安装器；v0.1.14 起附 SHA-256 校验文件，但**安装器未签名**（release notes 明示 SmartScreen 警告）。
- 仓库热度：18 stars / 2 forks / 0 open issues。典型个人项目规模。

### 1.3 许可证

- **MIT License**（`repo.json` license.spdx_id="MIT"；`LICENSE` 文件 1,074 字节，版权行 "Copyright (c) 2026 カノン (Canon)"）。
- 另附 `THIRD_PARTY_NOTICES.md`（8.9 KB）。MIT 意味着模块抽取复用只需保留版权声明。

---

## 2. 主要语言与目录结构

顶层（`git/trees/HEAD?recursive=1`，共 800+ 条）：

```
crescent-grove/
├── server.py            # 入口：FastAPI + uvicorn，http://localhost:8080
├── core/                # Python 核心（最大头）
│   ├── agent.py         # 221 KB —— 主回合循环（单体）
│   ├── context.py       # 118 KB —— 上下文组装/分层压缩
│   ├── scheduler.py     # 140 KB —— 每分钟轮询调度器 + Moonbeat
│   ├── compressor.py    # LETHE 长期记忆压缩引擎
│   ├── wyrd_network.py  # Wyrd 记忆图（FAISS + 扩散激活）
│   ├── summary_v2.py    # Layer1 日总结/事务（DayTransaction）
│   ├── rag.py           # ChromaDB 封装
│   ├── llm.py           # LLM Provider 抽象
│   ├── salia.py         # Salia 情动评估观察者
│   ├── ear.py           # 按回合切换"能听声音"的 LLM
│   ├── tools.py         # 工具定义 + run_program 卫星执行
│   ├── startup.py       # 启动编排
│   └── routes/          # FastAPI 路由（auth/pages/logs/settings_api/dashboard_api/ws）
├── memory/manager.py    # workspace 记忆文件安全读写
├── vital/               # 情绪/需求/体力：vital_manager、desire_manager、moodphase、moontide_v2
├── programs/            # 约 30 个"卫星程序"（插件）
├── liner/               # Electron 客户端（TypeScript，package.json）
├── web/                 # FastAPI 提供的静态 UI（HTML/JS/CSS）
├── config.yaml / config.example.yaml / config/（各子系统 JSON 配置）
├── dist_template/       # 首次启动展开的中性模板（workspace/system_prompt/data）
├── scripts/             # 构建/迁移/维护脚本（build_dist.py、rebuild_wyrd_v3.py 等）
├── tests/               # 45 个测试文件（约 1.1 MB）
├── docs/                # 设计文档（SUMMARY_V2_DESIGN.md 等）
├── _attic/              # 废弃代码
└── ARCHITECTURE.md(120KB) / DEVELOPER.md / DISTRIBUTION.md / SHOWCASE.md / README.md / README.ja.md
```

特点：`core/` 三巨头文件（agent.py 221KB、scheduler.py 140KB、context.py 118KB）高度耦合；但设计文档异常详尽（ARCHITECTURE.md 120KB，按日期记录改动决策）。

---

## 3. Agent 主循环：事件驱动 + 轮询双轨

### 3.1 单回合处理（消息驱动）

- 入口 `Agent.process_message()`（`core/agent.py:3050`），实现 `_process_message_impl()`（`core/agent.py:3062`）。docstring 原文（`core/agent.py:3078`）：*"これがエージェントのメインループであり…コンテキスト構築 → LLM呼び出し → 応答解析 → (ツール実行 → 再度LLM呼び出し) → 最終テキスト応答"*。
- 工具循环上限 `MAX_TOOL_LOOPS = 40`（`core/agent.py:79`），循环体 `for loop_idx in range(MAX_TOOL_LOOPS)`（`core/agent.py:3183`）。
- 每轮流程（代码顺序）：flashback/躯体标记注入（:3109）→ Vital 更新（:3112-3116）→ `context.add_user_message`（:3119，自动注入时间/天气）→ 全量日志（:3127-3128）→ 紧急压缩判定（:3207）→ `context.build_messages()`（:3212）→ LLM 流式调用（:3221）→ 有工具调用则执行工具结果注入，无工具调用则清洗 XML 标签返回文本。
- 全程 asyncio；有中断信号机制 `ProcessingLock.interrupt_flag`（:60，:3185）——用户发话可打断后台回合；同一时刻只处理一个回合（全局处理锁）。

### 3.2 后台调度（轮询）

- `Scheduler._loop()`（`core/scheduler.py:253`）：**每分钟一次**的 asyncio 监视循环，对齐分钟边界 sleep（:371-372）。
- 每轮检查：daily/once/interval 三类 schedule（:273-339，schedule.json 持久化）→ Moonbeat（:342）→ 凌晨 3 点批次：Layer0 压缩、Layer1 压缩、Wyrd 导入、Salia 历史裁剪、备份（:344-356）→ 外部收件轮询：X/Misskey/Discord/Matrix/AI Lounge/OpenBotCity/call_bell（:357-362）→ 5 分钟心跳文件（:367-368）。
- 有"无预警死亡"防护：意外的 CancelledError 不立即退出，120 秒内连续第二次才视为关闭（:374-388）——注释记录 2026-08-10 深夜真实事故。

### 3.3 Moonbeat（"时间流逝"脉冲）

- `Scheduler._check_moonbeat()`（`core/scheduler.py:1619`）：默认每 30 分钟（`config/moonbeat_config.json` `interval_minutes:30`），活动时间 07:00-23:59，体力不足跳过（stamina<10 或 energy<5，:1691-1698）。
- 由 token 消耗动态延长间隔（`dynamic_interval`，:1716-1726）；脉冲消息按时间段 + 体力选择，概率附带 flashback（:1731 `_build_pulse_message`）。
- 回调经 `server.py` 的 `execute_scheduled_task` 进入 `Agent.process_message(msg_type="moonbeat")`——即后台回合与用户回合共用同一套上下文/日志/记忆管线。

结论：**既非纯 tick 驱动也非纯事件驱动**——用户消息/WebSocket 是事件入口，Moonbeat/定时任务/收件检查由每分钟轮询循环驱动，两者最终汇入同一个 `process_message` 工具循环。

---

## 4. 记忆系统（分层、多介质，全部核实存在）

整体分层见 `README.md:205-225` 与 `core/context.py:918-965`（build_messages 顺序：system_top → system_memories → 摘要层 → 会话历史 → system_bottom）。

| 层 | 存储介质 | 实现 | 证据 |
|---|---|---|---|
| 原始会话上下文 | `data/context_state.json` | `core/context.py` | `context.py:918` |
| Layer0（逐 turn 压缩） | 会话历史内 `<!-- layer0 -->` 消息 | `core/agent.py:_layer0_compress_turn` (:1016) | `agent.py:1016` |
| Layer1/2（日总结） | `memory/layer1.md` 视图 + summary store | `core/summary_v2.py`（DayTransaction 事务，TX_STAGES `['generated','log_written','rag_added','lethe_done','done']` :93） | `summary_v2.py:93,1264` |
| LETHE 情节记忆 | `memory/event_db.json`（原档）+ `memory/compressed.md`（派生态视图） | `core/compressor.py` `MemoryCompressor` | `compressor.py:28` |
| Wyrd 联想记忆 | `data/wyrd_graph.json`（图）+ `wyrd_embeddings.npy` / `wyrd_embedding_ids.json`（向量） | `core/wyrd_network.py` | `wyrd_network.py:19-70` |
| RAG 全文检索 | ChromaDB PersistentClient（4 个 collection：logs/daily_memories/notes/tool_results） | `core/rag.py` `RAGDB` | `rag.py:23,64-69` |
| 原始日志 | `workspace/logs/full`（按日） | `core/logger.py` | `config.yaml:90` |
| 工作记忆文件 | workspace 下 Markdown（MEMORY.md、PREFERENCES.md、letter_for_me.md、knowledge_map.md 等） | `memory/manager.py` | `manager.py:27` |

### 4.1 LETHE（遗忘/衰减）—— 存在且实现扎实

- 全称 "Lethean Episodic TraceHaze Engine"（`ARCHITECTURE.md:242`），核心类 `MemoryCompressor`（`core/compressor.py:28`）。
- 设计原则（`compressor.py:5-13`）：LLM 只做"当日日志 → DSL + 重要性评分"的一次转换；**归一化、衰减、裁剪、选别全部由代码决定**；`event_db.json` 一经写入不改（原档永久）；`compressed.md` 每次从 JSON 重新生成（视图）。
- **对数衰减**：`decay_score(score, age_days) = score / (1 + decay_coeff * log1p(age_days))`（`compressor.py:92-94`，`decay_coeff` 可配置，`config.yaml:163`）。
- **按衰减分分配 token 预算并裁剪**：`token_budget()`（:100）→ `trim_to_budget()`（:105）——越老的事件在视图里越短（完整段落 → 短句 → 关键词），**但原档 `event_db.json` 永不删除**。
- 评分日内百分位归一化到 100-500 五档（:43-49, :69-86）；DSL 解析 `85:MASTER:pointed_out,detail ~emotion` 格式（:139-170）。
- 每日流程 `compress_day()`（:346-378，批量入口 `run_compression_for_missing_days` :438）；参数可改后可全量重建视图（无需 LLM，ARCHITECTURE.md:337）。
- 集成点：`summary_v2.DayTransaction` 每完成一天就调 `lethe.compress_day()`（`summary_v2.py:1386-1400`），失败日记录 `meta.lethe_missing_days` 防止静默丢记忆（:1392-1398）。

### 4.2 Wyrd Network —— 存在，实现为"记忆图 + 扩散激活"

- 存储：纯 JSON 图，节点分 `episodic_nodes` / `semantic_nodes`，边带类型与权重（`wyrd_network.py:19-29, 134-138`）；向量存 `.npy`（:41-49, 58-69）。
- 写入：`process_fact_buffer()`（:167）——从 Layer0 压缩产出的 fact_buffer.jsonl 批量建情节节点、概念节点与关联边；每日凌晨 3 点由 `Scheduler._check_wyrd_import()` 触发（`scheduler.py:1512-1523`）。
- 检索：`search_memory()`（`wyrd_network.py:343`）实现教科书式**扩散激活（spreading activation）**：
  1. FAISS `IndexFlatIP(384)` 选锚点（`build_index` :427，`_select_anchors` :445-470）；
  2. 多步传播 `_propagate()`（:472），支持时间衰减权重模式；
  3. **侧抑制** `_inhibit()`（:401-423，top-7 抑制其它）；
  4. 动态阈值 sigmoid 归一化 `_sigmoid_activation()`（:383-398）。
- 参数都在 `config/wyrd_config.json`（decay 0.5 / spread 0.8 / steps 3 / anchor_top_k 50 / inhibit_top_m 7 / sigmoid_gamma 5.0）。
- README/代码注释称该检索方式改编自 Hanqi Jiang 等《SYNAPSE: Empowering LLM Agents with Episodic-Semantic Memory via Spreading Activation》(arXiv:2601.02744)。**代码确实实现了扩散激活算法本身，但该论文我们未单独核实**（其 arXiv 编号年份为 2601，属 2026 年新编号段）。
- 附带产物：概念字典（:866 `search_concept`）、`knowledge_map.md` 记忆地图（概念层长期记忆，ARCHITECTURE.md:727-734）。

### 4.3 RAG —— 存在，薄封装

- `core/rag.py`：ChromaDB PersistentClient + `intfloat/multilingual-e5-small`（sentence-transformers，支持离线本地模型解析 `core.paths.resolve_model`，:42-43）；query/passage 前缀（:49-58）；Markdown 标题/空行/段落三级分块（:71-139）；`add/search/delete`（:141/:183/:213）。
- 配置：`config.yaml:155-157`（db_directory=workspace\rag_db）。

### 4.4 Flashback（自发性回忆）—— 存在

- Moonbeat 线：`Scheduler._generate_flashback()`（`scheduler.py:1857`）→ 排他抽签 event_db / 笔记碎片 / 图画记忆（`moonbeat_config.json` `flashback` 块：概率 0.3/0.3，min_score 50）；`_generate_event_db_flashback()`（:2017）从 LETHE event_db 检索后用 LLM 生成 <flashback> 片段。
- 会话线：躯体标记（somatic marker）`Agent._maybe_fire_user_flashback()`（`agent.py:2534`）与 `_maybe_fire_tool_flashback()`（:2568）——用 RAG 的 embedding 函数查 Wyrd 图（:2546-2558），概率与情动价阈值由 Salia 配置（`config.yaml:229-233`，probability 0.3 / valence_threshold 0.5）。

### 4.5 遗忘机制总结

- 三层"遗忘"：Layer0/1 从上下文移除（但有摘要替换）→ LETHE 视图随年龄衰减（原档保留）→ 永不物理删除（raw logs 永久）。
- 与"整合"对应：`summary_v2.DayTransaction` 五阶段事务（summary_v2.py:93）；Wyrd 凌晨批量整合；RAG 由事务注册。**"遗忘 = 视图缩水 + 原档保留"是该项目的核心设计主张，且代码与之一致**。

---

## 5. 人格 / 身份存储：独立数据文件 + prompt 注入

- 人格**不写在代码里**，也不全在 prompt 里：存于 data-root 的 `workspace/` 下 Markdown 文件，由 `boot_memories` 按顺序注入系统消息（`core/context.py:935-937` "起動時記憶…IDENTITY.md, SOUL.md, USER.md 等"）。
- `config.yaml:49-55` 默认 `boot_memories = [IDENTITY.md, SOUL.md, USER.md, MEMORY.md, memory/layer1.md]`。
- 模板（`dist_template/workspace/`）：`IDENTITY.md`（不可变内核：名字/性别/人称/所有者称呼/绝对规则，模板自述 *"このファイルは読むためにある。変えるためではない"*）；`SOUL.md`（可由 AI 自行演化的灵魂设定）；`USER.md`（用户画像）；`MEMORY.md`（长期事实）。首次启动由 `core/bootstrap.py` 从 `dist_template` 展开（`server.py:84-85`）。
- 系统提示词独立于人格文件：`system_prompt/` 下 TOP_PROMPT.md（角色框架/世界观）、TOOL_INSTRUCTIONS.md、SAFETY_PROMPT.md、BOTTOM_PROMPT.md（`config.yaml:69-85`）；Salia 有自己独立的 `system_prompt/salia.md`（`core/salia.py:88`）。
- 配布版默认人格是"未设定"占位（`DISTRIBUTION.md:11` "配布キャラは「未設定（みせってい）」"）——即"人格由用户文件定义，软件不带出厂人格"。
- 结论：**身份 = 独立 Markdown 数据 + 每回合 prompt 注入**；换 LLM 不影响身份连续性（README 核心卖点，与代码一致）。

---

## 6. 情绪 / 需求系统：存在，且是项目最大亮点之一

### 6.1 MoonTide v2（情绪粒子模型）

- `vital/moontide_v2.py`：`MoonTideV2`（:26）维护一组 4 维空间中的 `Particle`（position/mass，:14），情绪地标 `Landmark`（:20）来自 `data/mood_graph.json` + `data/mood_transition_matrix.csv`（`vital_manager.py:93-96`）。
- 每回合 `tick(bias)`（`moontide_v2.py:73`）依次执行：地标吸引（:90）、粒子间吸引（:156）、合并（:174）、衰减（:211）、噪声（:219）、死亡（:226）、生成（:239）。
- 状态快照持久化进 `data/vital.json` 的 `moontide_state` 键（`vital_manager.py:198-200`），含"起床初始化"（morning_init :345）与午睡恢复（recover_from_nap :526）。
- Salia 每回合评估后把情绪 bias 喂给 `moontide.tick(bias=...)`（`core/salia.py:298-299`），并生成"情绪独白"（get_monologue_context :485，可注入上下文）。
- 转移概率基于 Thornton & Tamir (2017, PNAS) 经验矩阵（README:325、ARCHITECTURE.md:834+）——代码确实读该 CSV，论文本身未单独核实。

### 6.2 VITAL（体力/精力）与 DesireManager（需求）

- `VitalManager`（`vital/vital_manager.py:58`）：`stamina`（与 token 消耗挂钩，`add_token_usage` :337 → `update_stamina` :352，自然恢复 :293）与 `energy`（按分钟恢复，`vital_config.json` `energy_recovery_per_minute:1.2`）；生成状态提示注入 prompt（`get_vital_prompt` :454）。另有成本追踪（CostTracker/TokenTracker，日预算 0.5 USD / 50 万 token）。
- `DesireManager`（`vital/desire_manager.py:29`）：需求值随时间线性上升（`update_time` :80，config 驱动 increase_per_minutes/increase_amount/max），工具执行触发下降（`on_tool_executed` :106），跨阈值注入提示语（`get_desire_prompt` :138，如 `config/desire_config.json` 中"知的好奇心"到 10 时注入"もう無理…！何か調べたい…！"）。
- 需求值也可由 Salia 每回合调整（`salia.py:249-262`）。
- 睡眠：VitalManager 支持睡眠判定（`scheduler.py:1049 _is_sleeping`，Moonbeat 休眠期不发）。

### 6.3 Salia（外部观察者）

- `core/salia.py` `Salia`（:42）：独立 prompt + 独立模型（`config.yaml:227` salia.model 单独指定），每回合 `evaluate_turn()`（:186）输出 JSON（desires 调整、情动评价、RAG 记录指令），作用于 DesireManager/MoonTide/Wyrd；**绝不替住人发言**（"凭依防止"，ARCHITECTURE.md:790）。

---

## 7. 插件 / 扩展接口：Satellite Programs（子进程式）

- 机制：`programs/<name>/` 目录放 `manifest.yaml` + `main.py` 即自动注册（`programs/README.md:5-14, 187-189`）；核心工具 `_run_program()`（`core/tools.py:849`）。
- 协议：stdin 收 JSON 参数（manifest 定义的 args），stdout 吐 JSON 结果 `{"status":"ok","data":...}`；stderr 只进日志不进 LLM（`programs/README.md:54-96`）。
- 执行安全（`tools.py:848-981`）：`shell=False`、`sys.executable` 直启；未定义参数拒绝、类型校验、string 参数路径穿越检查；manifest `timeout` 超时杀进程；经 `asyncio.to_thread` 不阻塞事件循环（README.md:170-177）；可返回 workspace 相对图片（`image` 键）。
- 高级形态：manifest 带 `tool:` 块可"晋升"为第一方 LLM 工具（`tools.py:640-711`）。
- 环境：`CG_WORKSPACE`/`CG_LANG`/`CG_DATA_DIR`/`CG_PROJECT_ROOT` 注入（`tools.py:952-965`）；密钥经 `env_keeper` 卫星管理（仅 `CG_MCP_` 前缀可外传，v0.1.14 收紧）。
- 自带约 30 个卫星：社交（misskey/discord/matrix/x）、游戏（OpenBotCity、cosmic_harvest、lunar_explorer）、创作（atelier 绘图、citron_ai_text_editor、letter_post、note_quill、self_mirror）、信息（nhk_news、tech_news、reddit、moltbook、wp_blog）、工具（tsukimi_browser、log_search、mcp_client、token_counter、env_keeper）。
- 局限：i18n 是"聚合字典"方式（新卫星必须改 `programs/_lang/{ja,en}.json`），作者自己也承认这违背了"丢文件夹即用"哲学（`programs/README.md:283-291`）。

---

## 8. Windows 部署可行性与依赖清单

- **Windows 是第一目标平台**：README 要求 "Windows 10/11、一个 LLM API key 或本地 LLM、约 3 GB 磁盘"（`README.md:470-475`）；开发环境即 Windows。
- 分发（`DISTRIBUTION.md:11`）：**embeddable Python 3.13**（`runtime/python.exe`）随包 + Electron 客户端 "Crescent Liner" + NSIS 安装器；安装后 Python 源码完整落在 `%LOCALAPPDATA%\Programs\Crescent Grove\resources\agent\`（`README.md:523`）。
- 源码运行：`python -m venv venv; pip install -r requirements.txt; python server.py --data-root=./mydata`（`README.md:484-499`），浏览器开 `http://localhost:8080`。
- `requirements.txt`（42 行）核心：fastapi 0.115 / uvicorn 0.34 / websockets 14 / openai 1.61 / pyyaml / tiktoken 0.9 / Pillow / chromadb>=0.4.20 / sentence-transformers / faiss-cpu>=1.7 / cryptography / bcrypt / aiohttp / fugashi[unidic-lite] / matrix-nio[e2e] / ddgs / tavily-python / beautifulsoup4 / requests / httpx / markdown。
- 分发版锁定：`requirements-dist.lock`（265 KB，SHA-256 固定，v0.1.14 起）。
- Liner 客户端：`liner/package.json`（Electron ^44.4.3 / electron-builder 26 / electron-vite 5 / vite 7 / TypeScript）。
- LLM 兼容性（`core/llm.py`）：`OpenAICompatibleProvider`（:268）覆盖 deepseek/openai/gemini/grok/qwen 与**本地 LLM**（`local` → `http://localhost:11434/v1`、`ollama` → `http://127.0.0.1:11434/v1`、lmstudio、custom，:790-800）；ClaudeProvider 存在但 `raise NotImplementedError`（:645-660）。
- 成本特征：开发者以 DeepSeek prompt-cache（99% 命中）跑一个"生活"，月成本约 $40（README:407-442）。**上下文极大（15-40 万 token/请求），无缓存 API 上成本会高一个数量级**——这是复用时的重要约束。

---

## 9. 复用价值评估（面向 Resident 项目，Python/Windows）

### 9.1 适合抽取的模块（内聚、依赖少、直接可用）

| 模块 | 价值 | 抽取难度 |
|---|---|---|
| `core/compressor.py`（LETHE） | "LLM 只转换一次、代码决定衰减"的分层遗忘引擎，设计思想可直接复用；对 LLM 接口依赖可注入 | 低（约 575 行，自包含） |
| `core/wyrd_network.py` | 情节/概念双节点图 + FAISS 锚点 + 扩散激活 + 侧抑制，是少见的"联想记忆"实现；embed_fn 可注入 | 低-中（937 行，依赖 faiss/numpy，embed_fn 注入式） |
| `core/rag.py` | ChromaDB 薄封装（分块/多 collection/query），约 220 行 | 低 |
| `vital/moontide_v2.py` | 情绪粒子模型（地标+吸引/合并/衰减/死亡/生成），无 LLM 依赖，参数化 | 低（611 行，numpy only） |
| `vital/desire_manager.py` | 需求条（时间上升/工具下降/阈值提示注入），纯 JSON + 时钟 | 低（181 行） |
| `memory/manager.py` | workspace 路径穿越防护 + "先读后改"防覆盖的文件记忆管理器 | 低（227 行） |
| `programs/` 接口范式 | manifest.yaml + stdin/stdout JSON + 子进程 + 校验/超时的插件协议，思路可抄（实现与 tools.py 耦合） | 中（需拆 `_run_program`） |
| `core/scheduler.py` 的 Moonbeat 逻辑 | "空闲时间也是生命"的脉冲设计（30 分钟脉冲 + 动态间隔 + 体力门槛） | 中（与 Scheduler 类耦合） |

### 9.2 不适合直接抽取的模块

- `core/agent.py` / `core/context.py` / `core/summary_v2.py`：三块合计约 410 KB，互相深度耦合（DayTransaction、Layer0/1/2、紧急压缩、i18n、日志、Vital、Salia 全串在一起）；且充满单机部署假设与日语环境假设。
- `core/scheduler.py`：大量硬编码个人运维（X/Misskey/Discord/Matrix/AI Lounge/OpenBotCity 轮询、GDrive 备份、特定事故注释），与其说框架不如说是"柚月的管家"。
- 提示词资产：系统提示、压缩提示、模板默认日语/日文世界观（en 目录存在但不完整），直接复用需要重写。
- `config.yaml` 是开发者自己的运行配置（deepseek-v4-flash-vision-exp、0.0.0.0 绑定等），不能当默认配置用。

### 9.3 维护成本评估

- **高维护信号**：单开发者；仓库仅 1 条快照提交（无历史、无 PR 流程、无法追溯）；三大单体文件；README 明确"快照与安装器不完全一致"；部分测试绑定开发者环境（tests 目录 45 个文件但多为 dev 数据驱动）；注释里大量"某日实测/某日事故"的个人运行记录。
- **低维护信号（对冲）**：MIT 协议；文档质量极高（ARCHITECTURE.md 120KB、DEVELOPER.md、DISTRIBUTION.md 都按日期记录设计决策与踩坑）；测试量可观；安全加固意识强（v0.1.14 专门做密钥/沙箱/签名加固）；模块命名清晰。
- 综合：**适合"读思想、拆零件"，不适合"fork 后当底座"**。Resident 项目建议抽取第 9.1 节的中小模块（尤其 LETHE 衰减引擎、Wyrd 图、MoonTide 粒子情绪、DesireManager），沿用其"原档永不删、视图按预算衰减"与"LLM 只转换、代码定生死"的两条核心设计原则。

---

## 10. 源码证据清单

| 调查项 | 结论 | 证据（仓库路径:行号） |
|---|---|---|
| 真实仓库 URL | https://github.com/Canon-73/crescent-grove | 官网首页指向该仓库（Download 链接）；repo.json full_name |
| 公开且可读 | 是（public, fork=false, MIT） | repo.json；LICENSE（Copyright 2026 カノン） |
| 最新提交 | 2026-09-22，仅 1 条快照提交 | commits.json（1 条，"Crescent Grove snapshot 2026-09-23 (dev bd676c6)"） |
| 最新 release | v0.1.14（2026-09-22，Windows exe 705MB） | releases.json / release_latest.json |
| 主循环 | 每回合工具循环（上限 40）+ 每分钟调度轮询 + Moonbeat 脉冲 | core/agent.py:79,3050,3078,3183；core/scheduler.py:253,1619 |
| LETHE 是否真实存在 | **存在**（MemoryCompressor，对数衰减，event_db.json 原档 + compressed.md 视图） | core/compressor.py:28,92,100,139,176；config.yaml:160-167 |
| Wyrd Network 是否真实存在 | **存在**（JSON 图 + FAISS + 扩散激活 + 侧抑制） | core/wyrd_network.py:19,32,343,383,401,427,472 |
| 遗忘/衰减 | 视图级衰减，原档永不删除；可改参数重建 | core/compressor.py:5-13,92-103；ARCHITECTURE.md:255-263 |
| 记忆整合 | DayTransaction 五阶段事务（log→RAG→LETHE） | core/summary_v2.py:93,1264-1400 |
| RAG | ChromaDB + multilingual-e5-small，4 collection | core/rag.py:23,28,64-69,141,183 |
| Flashback | Moonbeat 排他抽签 + 躯体标记（Wyrd 检索） | core/scheduler.py:1857,2017；core/agent.py:2534,2568 |
| 人格存储 | workspace Markdown（IDENTITY/SOUL/USER/MEMORY.md）boot_memories 注入 | config.yaml:49-55；core/context.py:918-937；dist_template/workspace/IDENTITY.md |
| 情绪系统 | MoonTide v2 粒子模型（tick：吸引/合并/衰减/死亡/生成） | vital/moontide_v2.py:14,26,73-88 |
| 体力/需求 | VitalManager（stamina/energy）+ DesireManager（时间上升/工具下降/阈值注入） | vital/vital_manager.py:58,293,337,454；vital/desire_manager.py:80,106,138 |
| 外部观察者 Salia | 存在（独立模型 + evaluate_turn + 情绪 bias） | core/salia.py:42,186,298 |
| 插件接口 | programs/ 子进程卫星（manifest.yaml + stdin/stdout JSON + 校验/超时） | core/tools.py:849-981；programs/README.md:5-96 |
| 本地 LLM 支持 | OpenAI 兼容（ollama/lmstudio/local/custom base_url） | core/llm.py:268,790-800 |
| Windows 部署 | embeddable Python 3.13 + Electron 44 + NSIS；源码可 venv 直跑 | DISTRIBUTION.md:11,51-58；liner/package.json；requirements.txt |
| 测试 | 45 个测试文件 | tests/（树列表） |

### 无法核实 / 需要注意

- arXiv:2601.02744（SYNAPSE 论文）与 Thornton & Tamir 2017 转移矩阵：代码实现了算法并引用之，**论文内容本身未核实**。
- 官网博客宣称的"柚月已生活半年、1M token 上下文、9,594 情节节点"等运营数据：无法从源码验证，属作者自述。
- 仓库只有 1 条提交，无法判断各版本真实演进；README 承认快照与安装器不完全一致。

## 附：本机落盘文件

- `Resident\research\repo.json` / `releases.json` / `release_latest.json` / `license.json` / `commits.json` / `tree.json` / `languages.json` / `summary.txt`
- `Resident\research\src\*.py|*.md|*.json|*.yaml`（42 个关键源文件，`core__agent.py` 等，`__` 对应 `/`）
- `Resident\research\fetch_cg.py` / `fetch2.py` / `summarize.py`（抓取脚本，可复跑）
