# Letta vs Mem0 源码级调研报告（Resident 长期记忆系统选型）

- 调研对象：Letta（前 MemGPT，仓库 `letta-ai/letta`）与 Mem0（仓库 `mem0ai/mem0`）
- 调研方式：GitHub REST API 元数据 + raw.githubusercontent.com / data.jsdelivr.com / pypi.org 抓取**源码与打包元数据**，逐文件核实；未安装任何依赖、未运行任何项目代码。
- 数据获取时间：2026-11-06（GitHub 时间戳为 UTC）
- 环境限制说明：本机 GitHub API 匿名额度耗尽（403 rate limit），故目录清单改用 jsdelivr 数据接口、文件内容改用 raw 抓取；本机 pwsh 出站 HTTPS 对大文件下载不稳定，因此未做本地 clone，全部为定向文件取证。

---

## 0. 元信息（经 API/官方源核实）

| 项目 | 最新提交（default 分支） | 最新 release | 许可证 | 语言 | Stars |
|---|---|---|---|---|---|
| Letta `letta-ai/letta` | `8816d3a`（2026-10-18，`docs: remove desktop app mention from README (#3454)`） | **v0.16.8**（2026-05-14，为最终 Python 服务器版） | Apache-2.0（API 字段 `license.spdx_id`） | GitHub API `language` 返回 `{}`（代码已迁出）；历史主体 Python，新主线 TypeScript | 25,367 |
| Mem0 `mem0ai/mem0` | `ed1f10f`（2026-11-04，`fix(security): resolve 5 Vanta CRITICAL Dependabot vulnerabilities (#7825)`） | **v2.2.1**（2026-09-25，Python SDK；另有 ts-v3.3.1 等 Node/插件 tag） | Apache-2.0（API 字段） | Python | 68,500 |

### 0.1 关键事实：Letta 已经"不是原来的 Letta"了（必须最先说明）

1. `letta-ai/letta` 仓库 `main` 分支**只保留了 README、资产与历史文件**，`letta/` 包目录已不存在（raw 抓 `main/letta/__init__.py`、`main/pyproject.toml` 均 404）。README（main）原文：*"The current source code lives in letta-ai/letta-code… The archive branch contains the retired Letta V1 API server."*
2. 新主线仓库 `letta-ai/letta-code` 是 **TypeScript/React 的 Agent harness**（npm 包 `@letta-ai/letta-code`），记忆实现为 **MemFS（git 仓库形态的上下文/记忆文件系统）**、memory blocks、skills、recall subagent、dreaming/reflect（"sleep-time compute"）。
3. PyPI 上的 `letta` 包**最新版 0.34.12 已变成"Letta Code CLI"封装**：官方描述原文 *"This distribution is the Letta Code CLI, not a Python SDK or API server. For Python applications calling the Letta API, use letta-client."* —— 即 **2026 年 `pip install letta` 装到的不是 Python 记忆库，而是捆绑了 Node.js 运行时的 CLI**。
4. 因此"Letta Python 记忆框架"可评估的最终形态 = **tag 0.16.8（2026-05-14）的 V1 API 服务器**，且官方已将其标记为"retired"。本报告 Letta 部分即以此 tag 为取证对象。

### 0.2 PyPI 打包体积（实测元数据）

| 包 | 版本 | wheel | 体积 | 说明 |
|---|---|---|---|---|
| `mem0ai` | 2.2.1 | `mem0ai-2.2.1-py3-none-any.whl` | **351,907 B（约 344 KB）纯 Python** | sdist 256 KB |
| `letta`（V1 服务器） | 0.16.8 | `letta-0.16.8-py3-none-any.whl` | 1,541,384 B（约 1.5 MB）纯 Python | 但依赖清单极重（见 1.9） |
| `letta`（现 CLI 封装） | 0.33.x/0.34.x | `letta-0.33.1-py3-none-win_amd64.whl` | **约 72.7 MB（捆绑 Node 运行时）** | 平台 wheel：linux glibc2.28 / macOS14 / win_amd64 |

---

# 第一部分：Letta（tag 0.16.8，退役 Python V1 服务器）

## 1.1 架构：server/client，必须起服务

- `pyproject.toml`：`[project.scripts] letta = "letta.main:app"`；`server` extra = `fastapi>=0.115.6`、`uvicorn==0.29.0`、`websockets`。
- `letta/server/server.py`：`class SyncServer`，内部持有 30+ 个 Manager（OrganizationManager/UserManager/AgentManager/BlockManager/PassageManager/MessageManager/…），并显式区分 `settings.database_engine`：POSTGRES 时把 recall/archival storage 设为 postgres。
- 客户端是**独立包**：核心依赖含 `letta-client>=1.7.12`；`settings.py` 有 `default_base_url = "http://localhost:8283"`（工具执行时回连服务器）。
- 结论：**不是可嵌入的进程内库**，是 FastAPI 服务 + REST SDK 架构。

## 1.2 存储介质与核心 schema

- 主库：Postgres（默认 `postgresql+pg8000://letta:letta@localhost:5432/letta`，见 `settings.py` 的 `letta_pg_uri` 属性），SQLAlchemy async（`letta/server/db.py` 用 `create_async_engine`，`letta/database_utils.py` 负责 pg8000/asyncpg URI 转换）。向量检索默认 pgvector（`passage.py` 的 `pad_embeddings`：嵌入统一 pad 到 `MAX_EMBEDDING_DIM`，注释明说 "necessary to ensure all stored embeddings are the same size… using pgvector"），可选 Turbopuffer/Pinecone。
- SQLite：**存在但为二等公民**——`settings.py` 有 `DatabaseChoice = {POSTGRES, SQLITE}` 与 `database_engine` 属性；`sqlite` extra = `aiosqlite` + `sqlite-vec>=0.1.7a2`；`block_manager.py` 里有大量 `dialect == "sqlite"` 分支（`INSERT ... OR IGNORE`、时间戳秒级取整、`func.lower().like()` 代替 ilike）。
- ORM 表（据 `block_manager.py`/`passage_manager.py` 引用及 alembic 迁移名推断，均为 SQLAlchemy 模型）：
  - 记忆块：`Block`（含 value/limit/label/description/read_only/metadata/tags/created_by_id/last_updated_by_id）+ 枢轴表 `blocks_agents`、`blocks_tags` + **`block_history`**（检查点表）。
  - 归档记忆：`ArchivalPassage`、`SourcePassage`（双表分家，迁移名 `54dec07619c4_divide_passage_table_into_...`）、`PassageTag`（标签联结表）、`ArchivesAgents`。
  - 事件/会话：`Message`（迁移 `95badb46fdf9_migrate_messages_to_the_orm`、`d6632deac81d_add_composite_index_to_messages_table` 等）、`Step`、`Run`、`Job`、`Group`、`Identity`、`Source`、`File`、`Provider`、`SandboxConfig` 等（迁移文件清单有 90+ 个）。
- 状态/配置还散落本地文件：`~/.letta` 目录、`LettaConfig` JSON（`server/server.py` 中 `config = LettaConfig.load()` / `config.save()`）。

## 1.3 记忆类型怎么建模

核心是 **"Block（类型化上下文块）" + "Passage（双层归档）" + "Message（事件日志）"** 三段式：

- **Block**（`letta/schemas/block.py`）：`value`（文本）、`limit`（**字符上限**，默认 `CORE_MEMORY_BLOCK_CHAR_LIMIT`）、`label`（任意字符串，内置 `human`/`persona` 两个子类 + `DEFAULT_BLOCKS=[Human(), Persona()]`）、`description`、`read_only`、`metadata`、`tags`、模板机制（`is_template/template_name`）、创建/最后修改人 `created_by_id/last_updated_by_id`。→ **等价于"任意多类型、带容量上限、可溯源的类型化记忆槽"**，六类记忆可直接用 6 个 label 的 block 表达。
- **Passage**（`letta/schemas/passage.py`）：`text` + `embedding` + `embedding_config` + `organization_id` + **`source_id` / `file_id` / `file_name`（来源文件）** + `metadata` + `tags` + `is_deleted`。分 `ArchivalPassage`（agent 自主归档，挂 `archive_id`）与 `SourcePassage`（来自外部文档，挂 `source_id`+`file_id`）。→ 事实/知识型记忆与"带出处文档片段"分层存储。
- **Message**（`letta/schemas/message.py`）：role 枚举 `["system","assistant","user","tool","approval","summary"]`，字段含 `agent_id`、`name`、`tool_calls/tool_call_id/tool_returns`、`step_id`、`run_id`、`otid`（幂等去重 id）、`group_id`、**`sender_id`（发送者，可为 identity 或 agent）**、`conversation_id`、`created_at`。→ 事件/自传式记忆 = 完整对话事件日志，天然带来源。

## 1.4 写入流程：没有自动"LLM 抽取"，写入由 agent 工具调用驱动

与 Mem0 不同，Letta V1 **没有内置的"消息 → LLM 抽取 → 入库"管线**：

- 归档写入入口 `PassageManager.insert_passage()`（`letta/services/passage_manager.py`）：拿到 `agent_state` 与文本 → 取/建默认 archive → 若有 embedding_config 就生成嵌入、**否则存无嵌入 passage（"text search only"）** → 直接建 `ArchivalPassage` 行 → 若 archive 用 Turbopuffer 再双写。**无去重、无冲突检测**（tags 才会 `list(set(tags))` 去重）。
- 谁触发写入？是 agent（LLM 通过工具调用 core-memory/archival 工具）或外部 API 调 block/passage 端点。服务端本身不做抽取与去重。

## 1.5 更新/纠错/遗忘机制（这部分设计很值得抄）

- **Block 检查点 + undo/redo**（`block_manager.py`）：`checkpoint_block_async()` 把当前状态写入 `BlockHistory`（含 `sequence_number`、value/label/limit/description/metadata、**`actor_type`（LETTA_USER/LETTA_AGENT）与 `actor_id`（谁改的）**），用 SQLAlchemy `version_id_col` 做乐观锁并发检查；`undo_checkpoint_block()`/`redo_checkpoint_block()` 沿线性历史回退/前进，并截断"未来"检查点。→ 这就是**内置的纠错+审计机制**。
- `update_block_async()`：检测 `PROMPT_AFFECTING_BLOCK_FIELDS = {description, label, limit, read_only, value}`，若变化则 **rebuild 所有挂接该 block 的 agent 的 system prompt**；no-op 更新直接跳过。
- `bulk_update_block_values_async()`：一次性批量改多个 block 的 value。
- 删除：`delete_block_async()` 连带清理 `blocks_agents`、`blocks_tags` 枢轴行后硬删；passage 提供 `update_*_passage_by_id_async()` 与 `delete_*_passage_by_id_async()`（hard delete，SQL 先删、Turbopuffer 双删）。
- 遗忘 = 显式删除 API；"被动遗忘"（衰减/过期）在 OSS 版中未见。

## 1.6 检索方式与召回策略

- **归档检索 = 向量相似度**：默认 pgvector（嵌入 pad 至 `MAX_EMBEDDING_DIM` 后入库），可选 Turbopuffer/Pinecone；`archival_memory_token_limit = 8192` 控制注入上下文上限。
- **无 BM25/FTS/混合打分**（OSS 主路径）：无嵌入的 passage 只能文本直存（注释 "text search only"，未见到文本搜索引擎实现）；标签通过 `PassageTag` 联结表支持过滤与计数（`get_unique_tags_for_archive_async`、`get_tag_counts_for_archive_async`）。
- 消息检索：`Message` 表有复合索引迁移（`d6632deac81d_add_composite_index_to_messages_table`），用于会话回放/搜索。
- 召回策略是"agent 主动调用检索工具，结果注入上下文"，而非独立 query API 的混合排序。

## 1.7 依赖体积与 Windows

- `pyproject.toml`（0.16.8）**直接依赖约 70 项**，其中包括与"记忆"无关的重型组件：`llama-index`、`temporalio`、`grpcio+grpcio-tools`、`matplotlib`、`markitdown[docx,pdf,pptx]`、`trafilatura`、`readability-lxml`、`ddtrace`、`datadog`、`clickhouse-connect`、`mcp[cli]`、`openai[realtime]`、`anthropic`、`google-genai`、`sentry-sdk[fastapi]`、`opentelemetry-*`（钉死 1.30.0）、`faker`、`black[jupyter]`、`datamodel-code-generator`、`ruff` 等。实际安装体积按依赖树估算数百 MB 级（未实测，因禁止安装）。
- Windows：0.16.8 wheel 是纯 Python（1.5 MB），但其 workflows 只有 `code_style_checks/docker-image/migration-test/poetry-publish/send-message-integration-tests/test-pip-install`，**没有 windows 测试矩阵**；`sqlite-vec` 依赖是预发布版本（`>=0.1.7a2`）。新版 CLI 封装（0.33.x+）明确支持 Windows x64 wheel，但 README 注明 **Windows 上默认禁用自动 dreaming/reflection**（需 `LETTA_ENABLE_WINDOWS_AUTO_REFLECTION=1`）——说明 Windows 是次等平台。

---

# 第二部分：Mem0（OSS v2.2.1，`mem0ai`）

## 2.1 架构：进程内可嵌入库（另有可选的托管服务）

- 核心用法 `from mem0 import Memory`（`mem0/memory/main.py`），同步 `Memory` + 异步 `AsyncMemory` 双实现；配置文件驱动（`MemoryConfig` 纯 pydantic dict）。
- 无需起任何服务：向量库默认 **Qdrant 本地嵌入模式**（`qdrant.py`：无 host/url 时 `params["path"]=path`、`is_local=True`，本地模式内部用 sqlite 持久化）；也可选 FAISS（本地文件）、Chroma（本地目录）；或连外部 Qdrant/pgvector/Elasticsearch/Milvus/Pinecone 等 25+ 种后端（`vector_stores/configs.py` 的 `_provider_configs` 表）。
- 仓库内另有 `server/`（自托管 REST 服务）与云平台，但 pip 库本身完全独立。

## 2.2 存储介质与核心 schema

- **记忆本体存向量库**：每条记忆 = 向量 + payload（`main.py::_create_memory`）：`data`（事实文本）、`hash`（md5(data)）、`text_lemmatized`（BM25 用词形还原）、`created_at/updated_at`、会话键 `user_id/agent_id/run_id`、`actor_id`、`role`、`attributed_to`、可选 `expiration_date` + 任意自定义 metadata。
- **审计与最近消息存 SQLite**（`mem0/memory/storage.py`，默认 `~/.mem0/history.db`，`MEM0_DIR` 可改）：
  - `history` 表：`id, memory_id, old_memory, new_memory, event, created_at, updated_at, is_deleted, actor_id, role` —— **每次 ADD/UPDATE/DELETE 都留痕（旧值/新值/操作者/角色）**。
  - `messages` 表：`id, session_scope, role, content, name, created_at`，每 scope 只保留最近 10 条（写入时自动驱逐）。
- **实体库**：独立 collection `<collection>_entities`（`_entity_collection_name`），payload = `data, entity_type, linked_memory_ids[]` + 会话键 —— 相当于一个轻量"实体↔记忆"倒排图。
- 遥测副作用文件：`~/.mem0/config.json`（存匿名 user_id，`memory/setup.py`）。

## 2.3 记忆类型建模

- 官方枚举 `MemoryType = {SEMANTIC, EPISODIC, PROCEDURAL}`（`configs/enums.py`），但 **`add()` 实际只落地了 `PROCEDURAL`**（生成过程性摘要记忆），semantic/episodic 未在写入路径区分——通用记忆都是"事实文本+自由 metadata"。
- 六类记忆的实现路径：`metadata={"memory_type": "<六类之一>"}` + 检索时 `filters={"memory_type": ...}`（metadata 过滤支持 eq/ne/in/gt/gte/lt/lte/contains/icontains/AND/OR/NOT，见 `main.py::_process_metadata_filters`）。**无强 schema，靠约定**。
- 事件类记忆 = 普通记忆带 `expiration_date` 或时间标注；自传/过程 = procedural 记忆或 metadata 标记。

## 2.4 写入流程：LLM 抽取 → 去重 → 入库（V3 "分阶段流水线"，`main.py::_add_to_vector_store`）

1. **Phase 0 上下文**：从 SQLite 取该会话最近 10 条消息（`db.get_last_messages`）。
2. **Phase 1 现有记忆召回**：把新消息整段 embed，向量检索 top-10 已有记忆（去重/关联的依据）。
3. **Phase 2 单次 LLM 抽取**：system 用 `ADDITIVE_EXTRACTION_PROMPT`（`configs/prompts.py`，agent 场景追加 `AGENT_CONTEXT_SUFFIX`），user 由 `generate_additive_extraction_prompt()` 组装（Summary/最近消息/已抽取/已有记忆/新消息/观察日期），要求输出 JSON `{"memory":[{"text","attributed_to","linked_memory_ids"}]}`；提示词明确要求**每条事实自包含（15-80 词）、逐消息穷尽抽取、禁止无中生有、区分 user/assistant 来源（attributed_to）、关联已有记忆**。
4. **Phase 3 批量 embedding**（失败逐条回退）。
5. **Phase 4/5 去重**：**md5(text) 精确去重**——与已有记忆 hash 集合、批内 seen 集合比对，命中即跳过（注释 "Skipping duplicate memory (hash match)"）。不再用相似度阈值去重（那是 v1/v2 时代的做法）。
6. **Phase 6 批量插入**向量库（失败逐条回退；全部失败抛 `VectorStoreError`，且**只有确认入库的记录才写 history/返回**——v2.2.1 release notes 明确此修复）。
7. **Phase 7 实体链接**：spaCy 抽取实体（`utils/entity_extraction.py`，类型 PROPER/QUOTED/TOPIC/IDENTIFIER；无 spacy 则静默跳过）→ 批嵌入 → 实体库精确文本匹配或 cosine≥0.95 视为同一实体 → 更新其 `linked_memory_ids`，否则新建。
8. **Phase 8** 消息落 SQLite（保留最近 10 条）。

LLM/embedding 均为外部服务（默认 OpenAI `gpt-5-mini` / `text-embedding-3-small`，可换 Ollama/LiteLLM/Groq/Together/Vertex/Gemini 等，`pyproject` llms extra + `configs/`）。

## 2.5 冲突处理

- **v3 算法是 "ADD-only，不覆盖"**：PyPI README 原文 *"Single-pass ADD-only extraction — one LLM call, no UPDATE/DELETE. Memories accumulate; nothing is overwritten."*（与源码一致：抽取输出只含 ADD + `linked_memory_ids`）。
- 矛盾/更新类信息靠 **linked_memory_ids 显式关联**（提示词：矛盾也算可链接关系），**不做自动裁决**；裁决责任上移给上层应用。
- 旧版冲突提示词 `DEFAULT_UPDATE_MEMORY_PROMPT`（ADD/UPDATE/DELETE/NONE 四操作 + `old_memory` 字段 + "矛盾则删除"示例）**仍存在于 `configs/prompts.py`，但 2.2.1 主流程已不引用**（`main.py` 导入清单无它）——保留为遗留/平台功能。
- 显式纠错 API：`update(memory_id, text/metadata/expiration_date)`（重嵌入 + 向量库 update + history 记 UPDATE，身份字段 immutable）、`delete()`（软删：向量删除 + history `is_deleted=1`）、`delete_all(filters)`、`reset()`、`history(memory_id)` 返回完整变更链。

## 2.6 检索方式与召回策略（`main.py::_search_vector_store` + `utils/scoring.py`）

**多信号混合打分**：
1. 查询预处理：`lemmatize_for_bm25` + spaCy 实体抽取。
2. 语义检索：embed 查询 → 向量库 `search`，**过取 `max(top_k*4, 60)` 作为候选池**。
3. 关键词检索：向量库 `keyword_search`（Qdrant 用 `bm25` 命名稀疏向量槽 + fastembed `Qdrant/bm25` 编码器，对 `text_lemmatized` 字段；需 `mem0ai[extras]`，装不上就自动禁用并告警；FAISS/Chroma 无此能力）。
4. BM25 分数 sigmoid 归一化（`normalize_bm25`，中点/陡度随查询词数自适应）。
5. 实体 boost：查询实体 → 实体库检索（相似度≥0.5 才算命中）→ 对 linked 记忆加分 `boost = similarity × 0.5 × 1/(1+0.001·(n-1)²)`（链接越多单次权重越低），上限 0.5。
6. `score_and_rank`：**`combined = (semantic + bm25 + entity_boost) / max_possible`**（分母 1/2/2.5 视信号有无），**semantic 分低于 `threshold`（默认 0.1）直接淘汰**（门槛只看语义分）；可选 `rerank=True` 走 LLM 重排器（`RerankerFactory`）；`explain=True` 返回各信号分解。
7. 过滤：`filters` 必含 user_id/agent_id/run_id 之一 + 任意 metadata 操作符（AND/OR/NOT/eq/ne/gt/gte/lt/lte/in/nin/contains/icontains/`*`）；`expiration_date` 过期默认隐藏（`show_expired` 可放开）。

## 2.7 依赖体积与 Windows

- 核心依赖仅 8 个：`qdrant-client, pydantic, openai, httpx, posthog, pytz, sqlalchemy, protobuf`；wheel 344 KB 纯 Python；Python ≥3.10。
- 可选重型件：`nlp`=spacy；`extras`=fastembed（BM25）、sentence-transformers、transformers；`vector-stores`=chromadb/faiss-cpu/pgvector(psycopg)/pymilvus/pinecone/redis/elasticsearch 等——**按需安装，默认不拉**。
- C 扩展：核心无；`pydantic-core`/`protobuf` 有官方 Windows wheel；chromadb（含 onnxruntime）、faiss-cpu 均有 Windows wheel 但体积大。
- Windows 证据：`qdrant.py::reset()` 专门处理本地模式在 **Windows/NFS 下 sqlite 句柄未释放**导致删除集合残留的问题（注释明写 "where an open file blocks unlink (Windows, NFS)"）→ 说明官方代码对 Windows 有针对性处理；但 CI 仅 `ubuntu-latest`（`ci.yml`，Python 3.10–3.12 矩阵），**Windows 无 CI 保障**。
- 隐私注意：PostHog 遥测**默认开启**（`memory/telemetry.py`，热路径采样率 0.1），`MEM0_TELEMETRY=False` 环境变量关闭；单机部署务必显式关闭。

---

# 第三部分：对 Resident 需求的适配度评分（5 分制）

需求基线：单机单用户、SQLite 起步、六类记忆、来源追踪、纠错/冲突处理、Python 可嵌入。

| 维度 | Letta 0.16.8 | Mem0 2.2.1 | 依据（源码证据） |
|---|---|---|---|
| 独立可嵌入的 Python 库 | **1** | **5** | Letta=FastAPI 服务+独立 letta-client；新 pip letta 是捆绑 Node 的 CLI。Mem0=`from mem0 import Memory` 进程内使用，本地向量库内嵌 |
| 单机单用户 | 2 | 5 | Letta 为 org/user 多租户 + 服务/DB/OTEL 全家桶；Mem0 单进程 + 本地 qdrant/faiss + SQLite |
| SQLite 起步 | 2 | 4 | Letta 有 DatabaseChoice.SQLITE + sqlite-vec，但默认与主力路径是 Postgres+pgvector，SQLite 是兼容分支。Mem0 历史/审计在 SQLite，但**记忆本体在向量库**，无法纯 SQL 直查主存（FAISS/Qdrant 本地模式各自用文件/sqlite 落盘） |
| 六类记忆建模 | **4** | 3 | Letta Block=label 类型化+limit+description+tags+模板+read_only，可天然承载六类。Mem0 只有 procedural 显式落地，其余靠 metadata 约定 + filters |
| 来源追踪 | 4 | 4 | Letta：message.sender_id/step_id/run_id、block.created_by/last_updated_by、BlockHistory.actor_id/actor_type、passage.source_id/file_id。Mem0：user_id/agent_id/run_id/actor_id/role/attributed_to + history 表 old/new/event/actor 全审计 |
| 纠错/冲突 | **4** | 4 | Letta：BlockHistory checkpoint/undo/redo + 乐观锁 + 显式 update/delete（但无自动冲突检测）。Mem0：hash 去重 + linked 关联 + 显式 update/delete 全留痕（但 v3 不自动覆盖矛盾） |
| 写入自动化（LLM 抽取） | **1** | **5** | Letta 无内置抽取管线（靠 agent 工具调用/API 显式写）。Mem0 自带单次 LLM 抽取→去重→实体链接流水线 |
| 检索能力 | 3 | **4** | Letta：pgvector 语义检索+tags+消息搜索，无 BM25/混合。Mem0：语义+BM25+实体 boost 三信号融合、threshold/top_k、可选 LLM rerank |
| 依赖体积 / Windows | 1 | 4 | Letta 0.16.8 约 70 个直接依赖（llama-index/temporalio/grpc/matplotlib/ddtrace/clickhouse…）；新 letta wheel 70 MB+。Mem0 核心 8 依赖 344 KB，纯 Python；Windows 无 CI 但代码有针对性处理 |
| **综合适配度** | **≈2.2** | **≈4.2** | — |

---

# 第四部分：结论（Resident 选型）

## Letta → **只借设计，不建议用（其代码）**

理由（均来自源码）：
1. **产品线已转向**：Python V1 服务器 0.16.8 已官宣"retired"，主线变成 TypeScript 的 `letta-code`（Agent harness + MemFS(git) + Cloud）；PyPI `letta` 包已变成捆绑 Node.js 的 CLI（72 MB 平台 wheel），官方明言"不是 Python SDK 或 API server"。
2. **架构不可嵌入**：必须起 FastAPI 服务 + 独立客户端包；单机嵌入场景完全错配。
3. **依赖爆炸**：0.16.8 直接依赖约 70 项含大量与记忆无关的企业组件；SQLite 是二等公民（Postgres+pgvector 优先），Windows 无 CI 矩阵。
4. **没有写入选管**：无 LLM 自动抽取、无去重、无冲突检测——这些 Resident 需要的核心能力都要自己补。
5. **但它的设计极值得抄**：① Block 模型（任意 label 类型化记忆槽 + 字符上限 + description + tags + read_only + 模板）；② BlockHistory 检查点/undo/redo + actor 溯源（天然满足"纠错/冲突"与"来源追踪"）；③ Passage 的 archival/source 双层 + source_id/file_id 出处字段；④ Message 全字段事件日志（sender_id/step_id/run_id/otid 幂等）。这四件套可以原样映射到 Resident 的 SQLite schema 上。

## Mem0 → **适合直接嵌入**（唯一现成候选），附带三点取舍

理由（均来自源码）：
1. 真正的可嵌入库：344 KB 纯 Python wheel、8 个核心依赖、同步/异步双 API、本地 qdrant（内嵌）/FAISS/Chroma 免服务部署；可完全离线私有（关掉 `MEM0_TELEMETRY` 后）。
2. 写入选管完整：LLM 单次抽取（含 attributed_to 来源标注、逐条穷尽、防编造约束）→ md5 去重 → 批量入库（只上报真实入库记录）→ spaCy 实体链接（精确+0.95 相似度合并）→ SQLite 全量审计（ADD/UPDATE/DELETE old→new + actor + role）。
3. 检索是它的强项：语义 + BM25 稀疏向量 + 实体 boost 三信号融合、语义门槛、可选 LLM 重排、丰富 metadata 过滤。
4. 取舍点（必须在 Resident 设计里消化）：
   - **主存不是 SQLite 表**：记忆本体在向量库 payload 里。若 Resident 坚持"SQLite 单一主存"，方案是：a) 用 Mem0 本体但接受 qdrant-local 目录（其内部即 sqlite）或 FAISS 文件 + history.db 的混合布局；b) **自建 SQLite 主存，仿写 Mem0 的写入选管与打分公式**（管线逻辑不长且都是纯 Python，抄袭成本低、可控性最高）。
   - **冲突是"关联"不是"裁决"**：v3 ADD-only 不覆盖矛盾记忆；Resident 需要"纠错/冲突裁决"必须自己做一层（例如对 linked_memory_ids 或同实体记忆做一致性检查/LLM 仲裁）——好消息是 update/delete/history API 已提供完整底座。
   - **类型无 schema**：六类记忆只能靠 `metadata["memory_type"]` 约定 + filters 实现，没有 Letta 式强类型约束；需要 Resident 自己在封装层强制枚举与校验。
   - 抽取决不免费：每次 add 需一次 LLM 调用 + 若干 embedding 调用（默认 OpenAI，可换 Ollama/LiteLLM/DeepSeek 等）。

## 最终建议（给 Resident）

**"Mem0 直接嵌入（或仿写其管线），Letta 只抄 schema 设计"**：
- 起步路径 A（快）：`mem0ai` + qdrant local（`path=本地目录`）+ SQLite history.db + `MEM0_TELEMETRY=False`；六类记忆用 `metadata["memory_type"]` 六值枚举；来源用 `user_id/actor_id/attributed_to`；纠错用 `update()/delete()/history()`。
- 起步路径 B（更贴"SQLite 单一主存"）：自建 SQLite schema（抄 Letta 的 block + block_history + passage(source_id/file_id) + message(sender_id) 四表设计），写入管线与混合打分**仿写 Mem0**（LLM 抽取 prompt、md5 去重、实体链接、`(semantic+bm25+entity)/max_possible` 公式），BM25 可用 SQLite FTS5 或本地 fastembed 替代。
- 明确不建议：以任何形式依赖 Letta 代码（退役 Python 服务器或 TS harness）作为 Resident 的记忆内核。

---

# 第五部分：源码证据清单

（ref 均以抓取当日为准；`@main` = 默认分支 main，`@0.16.8` = tag 0.16.8）

### 元信息类
| # | 来源 | 证据点 |
|---|---|---|
| M1 | `api.github.com/repos/letta-ai/letta`（HTTP 200，2026-11-06） | license=Apache-2.0；stars 25,367；`language: null`；default_branch=main；pushed_at 2026-10-18 |
| M2 | `api.github.com/repos/letta-ai/letta/releases/latest` | 最新 release `0.16.8`（2026-05-14 发布，assets 为空） |
| M3 | `api.github.com/repos/letta-ai/letta/commits?per_page=1` | 最新提交 `8816d3a`，2026-10-18，message "docs: remove desktop app mention from README (#3454)" |
| M4 | `raw.githubusercontent.com/letta-ai/letta/main/README.md` | "current source code lives in letta-ai/letta-code"；"archive branch contains the retired Letta V1 API server" |
| M5 | `api.github.com/repos/mem0ai/mem0`（HTTP 200） | license=Apache-2.0；language=Python；stars 68,500；pushed_at 2026-11-04 |
| M6 | `api.github.com/repos/mem0ai/mem0/releases?per_page=15` | Python release `v2.2.1`（2026-09-25，"Mem0 Python SDK (v2.2.1)"）；另有 ts-v3.3.1、pi-agent、opencode 等 tag |
| M7 | `api.github.com/repos/mem0ai/mem0/commits?per_page=1` | 最新提交 `ed1f10f`，2026-11-04，security fix (#7825) |
| M8 | `raw.githubusercontent.com/letta-ai/letta/main/pyproject.toml` → **HTTP 404**；`.../main/letta/__init__.py` → 404 | main 分支已无 Python 包（代码迁出证据） |
| M9 | `data.jsdelivr.com/v1/packages/gh/letta-ai/letta-code@main` | 新仓库为 TS 工程：`src/**/*.ts|.tsx|.mdx`、`package.json` 型结构（Ink/React 组件、memory-filesystem.ts、memory-git.ts、subagents/recall.md 等） |
| M10 | `pypi.org/pypi/letta/json` | 最新版 **0.34.12** = "Letta Code CLI"（捆绑 Node.js）；描述原文 "not a Python SDK or API server… use letta-client"；0.33.x win_amd64 wheel ≈ 72.7 MB；0.16.8 wheel = 1,541,384 B（py3-none-any） |
| M11 | `pypi.org/pypi/mem0ai/2.2.1/json` | wheel `mem0ai-2.2.1-py3-none-any.whl` = 351,907 B；requires_dist 核心 8 项 + extras（nlp/vector-stores/llms/extras）；README 内嵌 "New Memory Algorithm (April 2026)：ADD-only… Multi-signal retrieval" |

### Letta @0.16.8 类
| # | 文件 | 证据点 |
|---|---|---|
| L1 | `pyproject.toml` | 包名 `letta`、version 0.16.8、requires-python `<3.14,>=3.11`；~70 项直接依赖（llama-index、temporalio、grpcio、matplotlib、markitdown、trafilatura、ddtrace、datadog、clickhouse-connect、mcp[cli]、openai[realtime]…）；extras：`postgres`(pgvector/pg8000/psycopg2/asyncpg)、`sqlite`(aiosqlite, sqlite-vec>=0.1.7a2)、`server`(fastapi/uvicorn/websockets)、`desktop`；`letta = letta.main:app`；依赖 `letta-client>=1.7.12` |
| L2 | `letta/settings.py` | `DatabaseChoice{POSTGRES,SQLITE}`；`letta_pg_uri` 默认 `postgresql+pg8000://letta:letta@localhost:5432/letta`；`database_engine` 属性；`default_base_url="http://localhost:8283"`；`archival_memory_token_limit=8192`；OTEL/ClickHouse/uvloop/granian 等运维开关 |
| L3 | `letta/server/db.py` | SQLAlchemy `create_async_engine` + NullPool/asyncpg connect args（SSL require）；`db_registry.async_session()` 事务封装 |
| L4 | `letta/database_utils.py` | pg8000↔asyncpg URI 转换（`convert_to_async_uri`/`convert_to_sync_uri`）→ Postgres 主路径证据 |
| L5 | `letta/server/server.py` | `class SyncServer` 持有 30+ Manager；POSTGRES 时设 `recall_storage_type/archival_storage_type = "postgres"`；`GitEnabledBlockManager`（git 记忆仓库，可选）；`LettaConfig.load()/save()` 本地状态文件 |
| L6 | `letta/schemas/block.py` | `Block(value, limit=字符上限, label, description, read_only, metadata, tags, is_template/template_name, created_by_id, last_updated_by_id)`；`Human/Persona` 子类；`DEFAULT_BLOCKS=[Human(), Persona()]`；`BlockUpdate/CreateBlock` |
| L7 | `letta/services/block_manager.py` | SQLite 分支（`prefix_with("OR IGNORE")`、时间戳取整、lower().like()）；`BlocksTags/BlocksAgents` 枢轴表；`checkpoint_block_async`（BlockHistory + `version_id_col` 乐观锁 + actor_type/actor_id 溯源）；`undo/redo_checkpoint_block`；`PROMPT_AFFECTING_BLOCK_FIELDS` 变更后重建 agent system prompt；`bulk_update_block_values_async`；`delete_block_async` 级联清枢轴 |
| L8 | `letta/schemas/passage.py` | `Passage(text, embedding, embedding_config, source_id, file_id, file_name, metadata, tags, is_deleted, archive_id)`；`pad_embeddings` 到 `MAX_EMBEDDING_DIM`（注释：pgvector 需要等长向量） |
| L9 | `letta/services/passage_manager.py` | `ArchivalPassage`/`SourcePassage` 双 ORM（`letta/orm/passage.py`）；`insert_passage()`：无 embedding 时"text search only"直存、**无去重**；Turbopuffer 双写；`update/delete_*_passage_by_id_async`（hard delete）；`PassageTag` 联结表 + 标签去重 `list(set(tags))` |
| L10 | `letta/schemas/message.py` | `Message` 字段：role∈{system,assistant,user,tool,approval,summary}、`sender_id`、`step_id`、`run_id`、`otid`（幂等）、`group_id`、`conversation_id`、`tool_calls/tool_call_id/tool_returns`、`created_at`；`MessageCreate.otid` 生成逻辑 |
| L11 | `data.jsdelivr.com/v1/packages/gh/letta-ai/letta@main`（旧树缓存） | alembic 迁移清单：blocks→ORM、block_history、passages ORM 分表、messages ORM、identities、steps、jobs、groups、sources→ORM、files→ORM 等 90+ 迁移；workflows 无 windows 矩阵（code_style_checks/docker-image/migration-test/poetry-publish/…） |
| L12 | `raw.githubusercontent.com/letta-ai/letta-code/main/README.md` | letta-code 定位（stateful agent harness）；MemFS git 记忆；Windows：自动 dreaming 默认禁用、`LETTA_ENABLE_WINDOWS_AUTO_REFLECTION=1` 打开；pip 封装轮子平台矩阵 |

### Mem0 @main（2.2.1）类
| # | 文件 | 证据点 |
|---|---|---|
| N1 | `pyproject.toml` | version 2.2.1；核心依赖 8 项（qdrant-client/pydantic/openai/httpx/posthog/pytz/sqlalchemy/protobuf）；extras：nlp(spacy)、extras(fastembed/sentence-transformers/transformers)、vector-stores(chromadb/faiss-cpu/psycopg+pgvector/…)、llms(litellm/ollama/groq/…)；requires-python `>=3.10,<4.0` |
| N2 | `mem0/configs/base.py` | `MemoryConfig{vector_store(默认 provider="qdrant"), llm, embedder, history_db_path=~/.mem0/history.db, reranker, version="v1.1", custom_instructions}`；`MemoryItem` |
| N3 | `mem0/memory/storage.py` | `SQLiteManager`：`history` 表 DDL（id/memory_id/old_memory/new_memory/event/created_at/updated_at/is_deleted/actor_id/role）+ `messages` 表（每 scope 保留最近 10 条，DELETE…NOT IN 驱逐）+ 迁移逻辑 + `add_history/batch_add_history/get_history` |
| N4 | `mem0/memory/main.py` | `Memory`/`AsyncMemory`；`add()` 必填 user_id/agent_id/run_id 之一；`_add_to_vector_store` Phase 0–8 全流程（SQLite 上下文→向量召回 top10→`ADDITIVE_EXTRACTION_PROMPT` 单次 LLM→批量 embed→**md5 hash 去重**→批量 insert/逐条回退/全败抛 `VectorStoreError`→实体链接(精确或 ≥0.95)→消息落库）；`_create_memory`（payload: data/hash/text_lemmatized/created_at/updated_at）；`update()`（重嵌入+UPDATE 历史）；`delete()`（软删 is_deleted=1）；`history()`；`reset()`；身份键不可经 metadata 注入（`_strip_identity_keys`） |
| N5 | `mem0/configs/prompts.py` | `ADDITIVE_EXTRACTION_PROMPT`（逐条穷尽抽取、attributed_to=user/assistant、linked_memory_ids、禁止编造/回声抽取/跨消息污染）；`AGENT_CONTEXT_SUFFIX`；`generate_additive_extraction_prompt`；遗留 `DEFAULT_UPDATE_MEMORY_PROMPT`（ADD/UPDATE/DELETE/NONE + old_memory）——2.2.1 主流程未导入（`main.py` 导入清单无此物） |
| N6 | `mem0/memory/main.py::_search_vector_store` + `mem0/utils/scoring.py` | 过取 `max(top_k*4,60)`；`keyword_search`（Qdrant bm25 稀疏槽 + fastembed Qdrant/bm25，缺失自动降级）；`normalize_bm25` sigmoid；实体 boost（相似度≥0.5、权重 `sim×0.5×1/(1+0.001(n-1)²)`）；`score_and_rank` 融合公式 `(semantic+bm25+entity)/max_possible∈{1,1.5,2,2.5}`、semantic 门槛 threshold(默认0.1)、`explain` 分解 |
| N7 | `mem0/memory/main.py::_process_metadata_filters` | metadata 过滤操作符 eq/ne/gt/gte/lt/lte/in/nin/contains/icontains + AND/OR/NOT + 通配符 |
| N8 | `mem0/vector_stores/qdrant.py` | 本地嵌入模式（无 host 即 `path=`，`QdrantLocal`）；bm25 命名稀疏向量；`reset()` 注释明确处理 **Windows/NFS 下 sqlite 句柄未释放**；`update` 不新建点（update_only） |
| N9 | `mem0/vector_stores/faiss.py` | 本地文件方案：`<collection>.faiss` 索引 + `.json` docstore（安全反序列化限制）；距离策略 euclidean/cosine/IP；无 keyword_search（混合检索自动禁用） |
| N10 | `mem0/vector_stores/configs.py` | 默认 provider="qdrant"；25+ 后端注册表；默认路径 `/tmp/<provider>` |
| N11 | `mem0/configs/enums.py` | `MemoryType{SEMANTIC,EPISODIC,PROCEDURAL}`；`main.py::add` 只接受 PROCEDURAL，其余为通用事实 |
| N12 | `mem0/utils/entity_extraction.py` | spaCy 实体抽取（PROPER/QUOTED/TOPIC/IDENTIFIER），无 spacy 返回 []（实体链接静默跳过） |
| N13 | `mem0/memory/telemetry.py` | PostHog 默认开启（热路径采样 0.1、生命周期事件 100%）；`MEM0_TELEMETRY` 环境变量关闭；上报 os/python 版本等 |
| N14 | `mem0/memory/setup.py` | `~/.mem0/config.json`（匿名 user_id）；`MEM0_DIR` 环境变量覆盖 |
| N15 | `.github/workflows/ci.yml` | 仅 `runs-on: ubuntu-latest`（Python 3.10/3.11/3.12 矩阵）→ 无 Windows CI |

---

*报告完。所有结论均基于上表列出的源码与官方元数据；未安装依赖、未运行任何被调研项目代码。*
