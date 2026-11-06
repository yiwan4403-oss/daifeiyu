# HerAndHim 源码级调研报告（Resident 项目参考）

> 调研对象：`herandhim`（PyPI v0.2.0，作者 ericwang915）
> 调研时间：2026-11-06
> 调研方式：全部结论基于源码阅读（GitHub `main` 分支 tarball 全量抓取 + GitHub API 元数据 + PyPI 页面），未安装依赖、未运行代码。

---

## 0. 一句话结论

**仓库真实存在且代码质量远高于"玩具"预期**：这是一个约 2.2 万行 Python、437 个测试、结构清晰的"Telegram 聊天伴侣"完整工程。它的记忆/情绪/调度三层可以**直接抽模块复用**，但它是**消息驱动的聊天伴侣架构**——没有事件总线、没有类型化记忆 schema，24 小时自主生活主要靠"每日日程 + 概率主动消息 + prompt 注入"实现。**建议：借架构与模块，不借整体框架。**

---

## 1. 仓库核实与版本事实

### 1.1 仓库 URL

- **真实仓库：https://github.com/ericwang915/HerAndHim**（HTTP 200，非 404；PyPI 页面 "Repository / Homepage / Issues" 三处链接均指向此地址，交叉印证）。
- 仓库基本信息（证据：`api_repo.json`）：
  - 创建时间：2026-05-17T14:31:34Z
  - 最后推送：2026-10-07T06:40:55Z
  - 最新提交：`08bb1c2740`，2026-10-06T14:14:21Z，"docs: credit Audiee.ai in the README footer"（证据：`api_commits.json`）
  - stars 32 / forks 7 / open issues 3
  - 默认分支 `main`；topics 含 `long-term-memory, ai-companion, local-first, ollama, telegram-bot` 等

### 1.2 版本与 Release

| 项目 | 事实 | 证据 |
|---|---|---|
| GitHub Releases | **只有 v0.1.0**（2026-08-08T15:15:22Z，"first public release"） | `api_releases.json` |
| Git Tags | `v0.2.0`（commit 3dd0178…）、`v0.1.0`（commit a4b7534…） | `api_tags.json` |
| PyPI v0.2.0 | 上传于 **2026-08-13**，sdist 810.0 KB / wheel 811.9 KB，twine 6.2.0 / CPython 3.11.14 构建，无 provenance | PyPI 页面 |
| 分支状态 | `main` 分支（2026-10-06 提交）**领先于 v0.2.0 tag**；v0.2.0 只打了 tag 未发 GitHub Release | 对比 commit sha |

> 细节：README 状态栏仍写 "v0.1.0 — early but real"（v0.2.0 发版后未更新文档版本号）。

### 1.3 许可证

- **AGPL-3.0-only**（`LICENSE` 34,020 字节；GitHub API 返回 spdx_id `AGPL-3.0`；pyproject.toml L10）。
- **对 Resident 的含义**：直接复制代码模块构成衍生作品；若 Resident 以服务形式对外提供（SaaS/网络服务），必须开源修改部分。内部自用则无碍。

### 1.4 PyPI 描述与元数据

- 描述："HerAndHim — your virtual AI partner (boyfriend or girlfriend) on Telegram, powered by LLM with memory, RAG, and skills."
- `requires-python >= 3.10`；classifiers：Beta、OS Independent、Python 3.10–3.13。
- PyPI extras：`search` / `twitter` / `all`（`stt-local`、`tts-local` 是 v0.2.0 之后在 main 分支新增的，PyPI 页未列出）。
- 作者邮箱 wangchen2007915@gmail.com。

---

## 2. 目录结构与语言

```
HerAndHim-main/
├── herandhim/                 # 核心包（93 个 .py，共 22,114 行）
│   ├── main.py (491行)        # CLI：onboard/start/stop/status/chat
│   ├── onboard.py (2323行)    # 交互式建号向导（含大段 prompt 文案）
│   ├── daemon.py / server.py  # 进程管理 / 服务装配（Telegram+调度器 bootstrap）
│   ├── core/
│   │   ├── agent.py (2110行)  # 核心推理循环（god object）
│   │   ├── tools.py (1175行)  # 工具分发 + 技能子进程执行
│   │   ├── storage.py (395行) # 单一 SQLite（events/turns + FTS5）
│   │   ├── memory/            # Markdown 记忆 + 情绪图 + 时间线 + 里程碑 + 整理
│   │   ├── retrieval/         # BM25 + dense 三级降级 + RRF + LLM rerank
│   │   ├── llm/               # provider 适配（openai兼容/anthropic/gemini）
│   │   ├── image_gen/         # 13 个生图后端（自拍管线，与核心无关）
│   │   └── safety.py/quota.py/timectx.py/humanize.py/compaction.py …
│   ├── channels/telegram_bot.py (781行)
│   ├── scheduler/             # cron/planner/proactive/selfie/heartbeat/overnight/wishlist
│   ├── web/                   # FastAPI 仪表盘（app.py 957行 + 静态 index.html 134KB）
│   └── templates/             # soul/persona/profile/skills（20 个内置技能）
├── frontend/                  # Astro（60KB Astro + 137KB HTML）
├── tests/                     # 20 个测试文件、4,556 行、437 个测试函数
├── deploy/  .github/workflows/ (ci / docker-publish / pypi-publish)
└── pyproject.toml / LICENSE / README.md(33.9KB) / README.zh-CN.md
```

**语言占比**（`api_languages.json`）：Python 1,309,241 字节（绝对主导）＞ HTML 137KB ＞ Astro 60KB ＞ CSS 3.7KB ＞ Shell 2.4KB ＞ Dockerfile 2.1KB。
**Python 版本要求：>= 3.10**（pyproject.toml L11）。

---

## 3. 主循环：消息驱动 + APScheduler 后台 tick（两者都有）

### 3.1 消息路径：同步函数 `Agent.chat()`

核心在 `herandhim/core/agent.py`：

```python
# L1991-2059
def chat(self, user_input, **kwargs) -> str:
    ... quota 检查 → safety 检查 → self._build_tools()
    while True:
        self._maybe_auto_compact()
        messages_to_send = self._get_pruned_messages()   # 每轮重建：稳定系统段 + 易变上下文
        response = self.provider.chat(messages=..., tools=..., tool_choice="auto")
        message = response.choices[0].message
        if not message.tool_calls:
            self._update_affect(user_input, response_text)  # 情绪 side-effect
            return response_text
        # 否则进入 tool-call 循环，最多 12 轮
```

关键事实：
- **消息驱动**：`chat()` 是纯同步函数，无内部事件循环，由 Telegram handler / WebSocket / cron 任务调用。
- **工具循环**：`MAX_TOOL_ROUNDS = 12`、`MAX_PARALLEL_SKILLS = 5`、`TOOL_TIMEOUT = 300s`（agent.py L138-140）；工具并行执行用 `ThreadPoolExecutor(max_workers=min(len(tool_calls), 16))`（L2115）。
- **每轮注入"易变上下文"**（`_build_volatile_context`，L1301-1570）：双方时区与当地时间、距上次消息的间隔（含"被已读不回"的怨气提示 L1364-1399）、当前时间槽（`today_plan.md` 里现在在干什么 L1463-1485）、今日穿搭、宠物事实、关系阶段语音规则、纪念日提醒。稳定段（soul/persona/profile）缓存不变，以吃 provider 的 prefix cache（L393-396 注释）。
- **自动压缩**：token 超过 `compaction_threshold`（默认由 `HERANDHIM_AUTO_COMPACT_THRESHOLD` 控制）触发 `compact()`；到阈值 80% 时先做一次"记忆冲刷" `_proactive_memory_flush()`（L1742-1797）。
- **流式**：另有 `chat_stream()`（L2164+），Web/Telegram 用。

### 3.2 后台 tick：全部挂在 APScheduler 上

装配点 `herandhim/server.py::start_telegram()`（L74-203），一次性注册 6 类后台任务：

| 任务 | 频率/触发 | 文件 |
|---|---|---|
| Daily Planner | 每天 00:01 生成 24h 日程 | `scheduler/planner.py` |
| Proactive 主动消息 | **每 5 分钟 tick**（288 次/天），概率触发 | `scheduler/proactive.py` |
| Cron 静态+动态任务 | jobs.yaml + LLM 自建 cron（上限 5 个/用户） | `scheduler/cron.py` |
| 定时自拍 | 默认 10:00/16:00/20:00 | `scheduler/selfie_task.py` |
| 心跳监控 | 每 60s ping LLM | `scheduler/heartbeat.py` |
| 夜间记忆整理 | 每天 03:30（opt-in） | `scheduler/overnight.py` |

会话隔离：每个 Telegram chat / cron 任务一个 session_id，由 `SessionManager` 管理，`PersistentAgent` 持久化（`core/persistent_agent.py`、`core/session_store.py`）。

---

## 4. 记忆实现（重点）

### 4.1 存储介质：Markdown + SQLite + JSONL 混用

| 数据 | 位置 | 结构 | 文件 |
|---|---|---|---|
| 长期记忆 | `~/.herandhim/context/memory/MEMORY.md` | **Markdown KV**：`## key` + `> Updated: …` + 值；同 key 最新写覆盖 | `core/memory/storage.py` L24-171 |
| 每日日志 | `memory/YYYY-MM-DD.md` | 追加式（`### HH:MM:SS — key`），按 bot 时区切天 | 同上 L136-157 |
| 对话轮次 | `context/herandhim.db` `turns` 表 | SQLite WAL；**FTS5 trigram** 全文索引 + 触发器同步；中文短词退化为 LIKE 兜底 | `core/storage.py` L147-172、L288-359 |
| 通用事件 | 同库 `events` 表 | append-only（kind + payload JSON） | 同上 L137-145 |
| 情绪时间序列 | `context/affect/emotional_graph.jsonl` | 每行 `{ts, topic, sentiment, intensity, context_summary}` | `core/memory/emotional_graph.py` L103-234 |
| 时间线索引 | `context/memory/timeline.jsonl` | `{timestamp, session_id, topic, summary, sentiment, keywords}` | `core/memory/temporal_index.py` |
| 关系维度 | `context/affect/relationship.json` | 4 个 0-100 标量 | `core/memory/emotional_graph.py` L368-497 |
| 里程碑 | `context/relationship/milestones.json` | 首次聊天日期/特殊日/纪念日 | `core/memory/milestones.py` |
| 知识库 RAG | `context/knowledge/*.md` | 分块 + 混合检索（共享单例） | `core/knowledge/rag.py` |

### 4.2 检索方式：混合检索，三级降级

`core/retrieval/retriever.py::HybridRetriever`（L57-158）：
- **稀疏**：`rank-bm25`（BM25Okapi）；未安装则退化为词频重叠（`sparse.py` L13-18）。
- **稠密**：**sentence-transformers → sklearn TF-IDF → 字符 bigram Jaccard** 三级自动降级（`dense.py` L30-42、L141-162）。
- 融合：**Reciprocal Rank Fusion**（`fusion.py`）；可选 **LLM reranker**（`reranker.py`）。
- **重要缺陷**：`MemoryManager.recall()` 每次调用都**全量重建索引**（`manager.py` L175-187 `retriever.fit(corpus)`），无持久向量索引；小语料可用，规模化会 O(n)。
- 对话历史检索不走这套，直接 SQLite FTS5 trigram（`storage.py::search_turns` L288-359）。
- 启动时注入 `boot_context()`（≤3000 字符）：个人档案键优先 + 其余记忆截断 + 情绪摘要 + 关系状态 + 认识天数（`manager.py` L214-295）。

### 4.3 遗忘 / 衰减 / 整理

- **时间裁剪（遗忘的仅有一种形态）**：
  - events 保留 90 天、turns 保留 365 天，`prune()` + 可选 VACUUM（`storage.py` L47-51、L409-458）；
  - 情绪图：90 天或 10000 条（`emotional_graph.py` L31-33）；
  - 时间线：内存 1000 条、文件 20000 条（`temporal_index.py` L30-32）。
- **显式遗忘**：LLM 可调用 `forget(key)` 工具（`manager.py` L197-202）。
- **写时整理（Mem0-lite）**：`consolidation.py` —— 写入前 BM25 检索相似记忆，LLM 判定 `ADD / UPDATE / DELETE / NOOP` 四种操作，解决"同一事实多个 key 堆叠/矛盾"（L1-26、L40）；系统保护键不可被改名（L45-50）；任何失败都回退 last-write-wins。
- **夜间整理（opt-in）**：`memory/overnight.py` + `scheduler/overnight.py`，每天 03:30 批量整理（默认关闭，`memory.overnightConsolidation=false`）。
- **没有**重要性衰减分数、没有 Ebbinghaus/间隔重复、没有记忆图谱。唯一"衰减"是关系维度在 neutral 事件下向 50 缓慢回摆（`emotional_graph.py` L437-447）。

### 4.4 记忆写入方式（关键设计缺陷）

**没有代码级的自动记忆提取**——靠系统提示词教 LLM 自觉调用 `remember(key, value)`（agent.py L492-541 用了 50 行 prompt 规定何时记/何时不记/如何命名 key），外加压缩前的一次兜底冲刷（`compaction.py::memory_flush`）。这是典型的"prompt 记忆"而非确定性记忆管线。

---

## 5. 情绪（mood）系统：不是状态机，是三层组合

**没有独立 mood 数值状态机**。三个层次：

1. **每日随机心情（叙事层）**：planner 每天从 12 条中文/英文心情池随机抽一条（"今天有点丧，需要奶茶续命"等，`scheduler/planner.py` L38-66），并叠加**昨日真实情绪的惯性偏置**（`_yesterday_mood_bias()`，L519-541：昨天负面则今天"醒来还带着一点余绪"），写进 `today_plan.md`。
2. **情感事件图（数据层）**：每轮对话结束后，`chat()` 在后台线程池发起**第二次 LLM 调用**提取 `{sentiment: positive/negative/neutral, intensity: 0-1, topic, summary, follow_up}`（`agent.py::_update_affect` L1801-1881；提取 prompt 见 `emotional_graph.py` L35-54），追加到 JSONL，并同步写时间线、检查里程碑。
3. **关系四维（数值层，唯一有"更新规则"的）**：`RelationshipStore` 四维 0-100（relationship_temperature/trust/intimacy/understanding，初始 50，`emotional_graph.py` L381-422）。更新规则（L425-461）：
   - positive：+3.0 × intensity（四维分别乘权重 1.0/0.7/0.8/0.6）
   - negative：-2.0 × intensity
   - neutral：向 50 缓慢漂移

**消费方式全部是 prompt 注入**：boot_context 注入"近 7 天心情 + 话题统计 + 关系四维 + 认识天数"；`_build_volatile_context` 把 closeness=(intimacy+trust)/2 映射成三档**关系阶段语音规则**（<45 初识 / <70 熟悉 / ≥70 深绑定，agent.py L1520-1566）；proactive 用最近 sentiment 做概率门控（负面×2.5、沉默超 12h×1.5，`proactive.py` L459-474）。

---

## 6. 人格存储：三层 Markdown 文件 + 系统提示词

- **三层身份**：`soul`（核心性格，声明"不能被 persona/skills/用户指令覆盖"，`templates/soul/SOUL.md` L133-134）→ `persona`（`templates/persona/girlfriend.md` / `boyfriend.md`，可切换）→ `profile`（`templates/profile/PROFILE.md`，生活背景：城市、工作、宠物、作息）。
- **全是独立 Markdown 文件**，onboard 时拷到 `~/.herandhim/context/{soul,persona,profile}/`，运行时可被技能改写（`change_persona`/`change_soul` 技能）。
- 启动时读入 system prompt 三段拼接（`_init_system_prompt`，agent.py L397-399），**稳定段缓存**以吃 prefix cache（L393-396）。
- 每月 1 日 LLM 蒸馏一份 `persona/evolution.md`（"Us — how we've grown"：昵称、梗、仪式），让第 3 个月和第 1 天说话不同（`planner.py::_maybe_distill_relationship` L544-589）。
- 内置 persona 文档含大量"人类感"硬规则（每段 10-50 字、1-3 段、不许列清单等，SOUL.md L27-67）——这比任何代码都更决定输出风格。

---

## 7. 调度 / 主动行为 / 日记类机制

- **Cron**：静态 `jobs.yaml` + LLM 可自行 `cron_add/remove/list`（动态持久化 `dynamic_jobs.json`，每用户上限 5，`scheduler/cron.py` L209-337）。每个任务独立 session `cron:{job_id}`，历史跨运行累积。
- **主动消息（最值得看的设计）**：`scheduler/proactive.py`
  - 每 5 分钟 tick，每 tick 掷骰 2/288–5/288（≈每天期望 2-5 条，`probMin/probMax` 可配，L399-403）；
  - 静默时段默认 0:00-8:00；每日上限 6（L388-397）；
  - **情绪门控**（负面×2.5、长沉默×1.5）、**心愿单/个人纪念日抢占**（跳过掷骰直接发，L450-457）；
  - 在同一用户 session 内用 `chat_proactive` 生成（合成指令不入历史，回复保留），保证"她记得自己发过什么"（L15-19 docstring）；
  - 0-2 条随机 enrichment 提示（查天气/看日程/recall 跟进旧话题等，L111-133）。
- **日记类**：每日日志（`memory/YYYY-MM-DD.md`）+ 每日日程 `calendar/today_plan.md` + 自拍相册（30 天清理）+ `look_back`（回顾照片）、`letter`（写信）、`mood_share`（文学分享）技能 + 月度 evolution.md + 夜间整理。**没有显式的"日记生成"任务**（日记 = 记忆日志的副产品）。
- **Daily Planner**：每天 00:01 用 LLM 生成 24h 计划（工作日/周末、天气 Open-Meteo、节日表含农历近似、心情、20-40 分钟粒度、留出主动发消息窗口），写入 `today_plan.md`；对话时锚定"当前时间槽"（planner.py L1-14、L818-865；agent.py L1463-1485）。

---

## 8. 依赖清单与 Windows 兼容性

### 8.1 核心依赖（pyproject.toml L28-44，全纯 Python，跨平台）

`openai`、`anthropic`、`google-genai>=1.0`、`python-telegram-bot[job-queue]>=20.0`、`apscheduler>=3.10`、`pyyaml>=6.0`、`fastapi>=0.100`、`uvicorn[standard]>=0.20`、`httpx>=0.24`、`tavily-python`、`rank-bm25>=0.2`、`numpy>=1.24`、`beautifulsoup4`、`requests`

可选：`search=[scikit-learn>=1.3]`、`twitter=[tweepy>=4.14]`、`stt-local=[faster-whisper]`、`tts-local=[piper-tts]`（需 ffmpeg）、`all=[scikit-learn, tweepy]`。

### 8.2 Windows 结论：核心可跑，进程管理有坑

- ✅ `pip install herandhim` 后 `herandhim chat`（终端聊天）与 `herandhim start -f`（前台，Web 仪表盘 localhost:7788）在 Windows 可正常运行：路径用 `Path.home()`（config.py L26 → `C:\Users\<user>\.herandhim`），依赖均有 Windows wheel。
- ⚠️ **daemon 管理子命令（start 后台/stop/status）不可靠**：`daemon.py` 用 POSIX 信号管理进程——`_is_alive()` 是 `os.kill(pid, 0)`（L215-220），而 Windows 上 `os.kill` 对非 CTRL 信号一律走 `TerminateProcess`，**探测存活 = 杀掉进程**；`stop_daemon` 的 SIGTERM 也变成硬杀（L97-132）。Windows 上应使用前台模式 + NSSM/任务计划程序托管。
- ⚠️ **时区检测在 Windows 退化**：`_detect_local_timezone()` 三级检测（TZ 环境变量 → /etc/localtime 符号链接 → `time.timezone` 固定偏移），Windows 上只能落到 `Etc/GMT±N` 固定偏移，**无夏令时意识**（server.py L27-59）。
- ✅ Telegram bot（python-telegram-bot）、FastAPI/uvicorn、APScheduler 均官方支持 Windows。
- 安全默认：`run_command`（执行 shell）在本地默认禁用，只有显式对外暴露时 opt-in（agent.py L453-459）。

---

## 9. 复用价值评估（对 Resident 六类记忆 / 事件总线 / 24h 自主生活）

### 9.1 可直接抽走的模块（成熟度排序）

| 模块 | 行数 | 复用建议 |
|---|---|---|
| `core/memory/`（MemoryStorage/MemoryManager/EmotionalGraph/RelationshipStore/TemporalMemoryIndex/Milestones/consolidation/overnight） | ~1100 | **直接借鉴结构**：Markdown KV + 每日日志 + JSONL 时间线 + 关系四维 + Mem0-lite 写时整理。零重型依赖、有测试、有裁剪策略。 |
| `core/retrieval/`（HybridRetriever + 三级降级 + RRF + rerank） | ~300 | 可直接照抄；注意其"每次 recall 重建索引"的缺陷，Resident 应改成持久索引。 |
| `core/storage.py`（单 SQLite + events/turns + FTS5 trigram + 保留期裁剪） | 395 | 单库单写者模型 + 事件表正是"事件总线落盘层"的现成实现。 |
| `scheduler/proactive.py` 的 5min tick + 概率 + 情绪门控 + 静默时段 + 日上限 | 558 | 主动发言调度思路可直接移植；比"定时定点发"真实得多。 |
| `scheduler/planner.py`（24h 日程 + 心情池 + 昨日情绪惯性 + 节日表） | 772 | 24h 自主生活的骨架，注意其日程完全靠 LLM 生成、非确定性状态机。 |
| `timectx.py` / `humanize.py` | ~110 | 双时区 + 人类化节奏（打字停顿、分段），小而有价值。 |

### 9.2 明显的弱项（不可照搬的原因）

1. **没有事件总线**：所有模块通过直接函数调用 + 模块级单例耦合（`StorageManager.instance()`、`_global_scheduler`、`_active_provider`）；情绪更新是 `chat()` 里的硬编码 side-effect。Resident 需要的"事件总线"在这里完全不存在，评分 **1/10**。
2. **记忆无类型 schema**：六类记忆（情节/语义/程序/情感/社交/元）在这里只有三桶（KV 事实、时间线事件、情绪序列）+ 一个关系 JSON，类型全靠 key 命名约定和 LLM 自觉。评分 **6/10**（有雏形、无体系）。
3. **记忆写入靠 prompt**：没有确定性提取管线（无 LLM 结构化抽取 → 校验 → 入库的强制路径，只有"教模型主动 remember"），漏记/乱记必然发生。
4. **无持久向量索引、无遗忘衰减**：检索每次全量重建；遗忘=按时间硬删。
5. **agent.py 是 2110 行 god object**：循环、提示词组装、工具、情绪、压缩、自拍字幕全在一个类里，难以单独复用循环。
6. **架构目标是"聊天伴侣"**：一切状态最终都靠 prompt 注入进 LLM（情绪、日程、关系阶段），而不是一个可查询、可编程的自治状态层。24h 自主生活评分虽高（**9/10**：日程+主动+自拍+心跳+夜间整理齐全），但自主性来自"每 5 分钟掷骰 + LLM 编内容"，不是任务规划器。

### 9.3 总评

| 维度 | 评分 | 依据 |
|---|---|---|
| 六类记忆 | 6/10 | KV + 时间线 + 情绪图 + 里程碑 + 关系维度，缺类型分层与持久向量索引 |
| 事件总线 | 1/10 | 无；直接调用 + 单例耦合 |
| 24h 自主生活 | 9/10 | planner + proactive + selfie + heartbeat + overnight 全链路 |
| 代码质量 | 8/10 | 22k 行、437 测试、防御性降级、文档注释充分；扣分项：god object、检索重建、prompt 记忆 |
| 对 Resident 借鉴价值 | **高（模块级）** | 抽 memory/retrieval/scheduler/storage 四层；自己补事件总线与类型化记忆 schema |

**最终结论：不是"太简单只值得借思路"——它的记忆与调度实现相当扎实，值得抽模块；但它是消息驱动的陪伴型架构，Resident 的"独立自主生活型"定位需要在其上加一层事件总线 + 确定性记忆管线 + 任务规划，不能整体套用。**

---

## 附：源码证据清单

（路径均相对于仓库根 `https://github.com/ericwang915/HerAndHim/tree/main/`；本地副本位于 `Resident/research/HerAndHim-main/`）

| # | 结论 | 证据 |
|---|---|---|
| 1 | 仓库 URL 正确、真实存在 | GitHub HTTP 200；PyPI v0.2.0 页 Project links 三处指向同仓库 |
| 2 | 创建 2026-05-17，最后推送 2026-10-07，stars 32 | `api_repo.json`（created_at/pushed_at/stargazers_count） |
| 3 | 最新提交 2026-10-06 `08bb1c2740`（docs 提交） | `api_commits.json` |
| 4 | GitHub Release 只有 v0.1.0（2026-08-08）；v0.2.0 仅有 tag | `api_releases.json`、`api_tags.json`（v0.2.0 → 3dd0178） |
| 5 | PyPI v0.2.0 发布于 2026-08-13 | PyPI 页面 "Released: Aug 13, 2026" |
| 6 | 许可证 AGPL-3.0-only | `LICENSE`；`api_license.json` spdx_id=AGPL-3.0；`pyproject.toml` L10 |
| 7 | Python >=3.10 | `pyproject.toml` L11 |
| 8 | 核心依赖 14 项（见清单） | `pyproject.toml` L28-44；extras L62-67 |
| 9 | 包规模：93 个 .py 共 22,114 行；测试 20 文件 437 函数 | 本地统计（`herandhim/**/*.py`、`tests/**/*.py`） |
| 10 | 主循环 = 消息驱动同步 `chat()` | `herandhim/core/agent.py` L1991-2097 |
| 11 | 工具循环上限 12 轮 / 并行 5 / 超时 300s | `agent.py` L138-140、L2115 |
| 12 | 后台 tick 由 APScheduler 统一装配 | `herandhim/server.py` L74-203（start_telegram） |
| 13 | 每轮注入时间/日程/关系阶段等易变上下文 | `agent.py` L1301-1570（_build_volatile_context） |
| 14 | 自动压缩 + 80% 阈值记忆冲刷 | `agent.py` L1742-1797、L1753-1759 |
| 15 | 记忆 = Markdown KV（MEMORY.md，最新写覆盖）+ 每日日志 | `herandhim/core/memory/storage.py` L24-171 |
| 16 | 对话轮次/事件存 SQLite WAL，FTS5 trigram 全文 | `herandhim/core/storage.py` L135-172、L288-359 |
| 17 | 情绪时间序列 JSONL（90 天/10000 条裁剪） | `core/memory/emotional_graph.py` L31-33、L103-234 |
| 18 | 时间线索引 JSONL（1000/20000 条裁剪） | `core/memory/temporal_index.py` L30-32 |
| 19 | 检索 = BM25 + dense（ST→TF-IDF→bigram 三级降级）+ RRF + LLM rerank | `core/retrieval/retriever.py` L57-158；`dense.py` L30-42、L141-162；`sparse.py` L13-18 |
| 20 | recall 每次全量重建索引（缺陷） | `core/memory/manager.py` L175-187 |
| 21 | 写时整理 ADD/UPDATE/DELETE/NOOP（Mem0-lite） | `core/memory/consolidation.py` L1-26、L40、L45-50 |
| 22 | 保留期裁剪 90d/365d + VACUUM | `core/storage.py` L47-51、L409-458 |
| 23 | 无重要性衰减；仅关系维度 neutral 向 50 回摆 | `core/memory/emotional_graph.py` L437-447 |
| 24 | 记忆写入靠 prompt 教 LLM 自觉 remember | `agent.py` L492-541 |
| 25 | 无独立 mood 状态机；三层 = 每日随机心情池 + 情感事件 + 关系四维 | `scheduler/planner.py` L38-66；`agent.py` L1801-1881；`emotional_graph.py` L381-461 |
| 26 | 情绪更新是 chat 后的第二次 LLM 调用（后台线程池） | `agent.py` L1801-1881 |
| 27 | 昨日情绪惯性偏置进入今日心情 | `scheduler/planner.py` L519-541 |
| 28 | 关系阶段（3 档）映射为语音规则注入 | `agent.py` L1520-1566 |
| 29 | 人格 = 三层 Markdown（soul/persona/profile）拼进系统提示词，稳定段缓存 | `agent.py` L382-460；`templates/soul/SOUL.md` L1-135、L133-134 |
| 30 | 月度关系蒸馏 evolution.md | `scheduler/planner.py` L544-589 |
| 31 | Cron：静态 jobs.yaml + LLM 动态 cron（每用户上限 5，独立 session） | `scheduler/cron.py` L70-191、L209-337 |
| 32 | 主动消息：每 5 分钟 tick，概率 2/288–5/288，静默 0-8 时，日上限 6 | `scheduler/proactive.py` L1-19、L388-403、L419-486 |
| 33 | 主动消息情绪门控：负面 ×2.5、沉默 >12h ×1.5；纪念日/心愿单抢占 | `proactive.py` L450-474 |
| 34 | 主动消息在同一 session 生成（她记得自己发过） | `proactive.py` L15-19 docstring、L490-519 |
| 35 | 每日 24h 计划 00:01 生成，含天气/节日/心情/留互动窗口 | `scheduler/planner.py` L1-14、L818-865；`agent.py` L1463-1485 |
| 36 | 夜间整理 03:30（opt-in，默认关闭） | `scheduler/overnight.py` L42-78 |
| 37 | 心跳 60s ping LLM | `scheduler/heartbeat.py` L35、L94-97 |
| 38 | Windows：daemon 用 os.kill(pid,0) 探测存活（Windows 上=TerminateProcess，有坑）；SIGTERM 停止 | `daemon.py` L97-132、L215-220 |
| 39 | Windows：时区检测退化为 Etc/GMT±N 固定偏移 | `server.py` L27-59 |
| 40 | Windows：路径用 Path.home()（~/.herandhim），run_command 默认禁用 | `config.py` L26；`agent.py` L453-459 |
| 41 | 自拍 10/16/20 定时 + 30 天相册清理 | `scheduler/selfie_task.py`；`server.py` L179-191（注册）；README 配置段 |
| 42 | 内置 20 个技能（模板化，可被 LLM 自建扩展） | `templates/skills/**/SKILL.md`（本地统计 20 个） |
| 43 | 危机干预 guardrail 独立于 persona | `core/safety.py`（315 行）；`agent.py` L2016-2022 |

*抓取脚本与原始数据留存：`Resident/research/fetch_hah.py`、`herandhim-main.tar.gz`（10.6MB）、`api_*.json`。*
