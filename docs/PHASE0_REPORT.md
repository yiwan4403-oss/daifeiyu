# PHASE0_REPORT — 源码研究与架构验证阶段提交

日期：2026-11-06 ｜ 提交人：开发执行助手 ｜ 接收：项目管理者

## 已完成事项

1. **任务 A 环境检查**：Python 3.12.10 / pip 25.0.1 ✅；Git 2.56.0 已装 ✅（winget）；
   uv 未装（暂用 pip）；旧工程与旧记忆已按指示全部删除。
2. **任务 B 源码研究**：5 路并行，全部**源码级取证**（非 README 结论），
   产出 5 份报告 + 行号级证据清单，源码镜像落盘：
   - crescent-grove.md（Canon-73/crescent-grove，MIT）
   - herandhim.md（ericwang915/HerAndHim，AGPL-3.0，43 条证据）
   - paulusai.md（Pavel6625/PaulusAI，MIT，44 条证据）
   - letta-mem0.md（Letta 45 万行服务器不采用；Mem0 仅原型期）
   - frameworks-mcp.md（PydanticAI v2.66.0 / MCP SDK v2.3.0 / companion-emergence，32 条证据）
3. **任务 C 选型**：见下“技术决策”。
4. **任务 D 文档**：RESEARCH_REPORT / ARCHITECTURE_DECISIONS / DEPENDENCY_REPORT /
   REUSE_MATRIX / DATA_MODEL / SECURITY_MODEL / DEVELOPMENT_ROADMAP 全部落盘。
5. **任务 E 最小骨架**：配置(YAML) + SQLite(schema v1) + EventBus + EventStore +
   ModelGateway(重试/统计) + Identity(留历史) + 记忆(FTS5) + CLI 循环；pytest 7/7 通过；
   冒烟实测：init → 对话 → 错误路径 → 持久化（resident.db 生成）全通。

## 技术决策（要点，详见 ARCHITECTURE_DECISIONS.md）

- AD-1 独立 Python 进程，不做平台插件
- AD-2 自建事件总线（四研究对象均无此物）
- AD-3 自建 SQLite 记忆层：六类 schema + FTS5 + 来源追踪 + 时间衰减；借 Letta 分层与
  Mem0 的 LLM 仲裁思路；向量后期 sqlite-vec
- AD-4 事件驱动 + 低频节拍，禁止高频 LLM 模拟思考
- AD-5 人格独立数据，prompt 仅渲染
- AD-6 Model Gateway 统一出口 + 任务分级模型
- AD-7 安全外置 L0–L3，模型不得自我授权；外部数据一律 untrusted
- AD-10（修订）编排层用 PydanticAI（v2.66.0，MIT），身份/记忆/生活全自建
- AD-14 衰减/遗忘/结晶公式取 companion-emergence，结晶必须人工审批
- MCP：Phase 4 起接入，锁 mcp 2.3.0

## 复用矩阵（详见 REUSE_MATRIX.md）

| 抽什么 | 从哪 |
| --- | --- |
| 记忆/检索/调度/存储四包 | HerAndHim（AGPL，注意开源义务） |
| LETHE 衰减、Wyrd 联想、MoonTide 情绪、DesireManager | Crescent Grove（MIT） |
| 审批三件套、facts 记忆、PAD+OCC 情绪、MCP 客户端 | PaulusAI（MIT） |
| 分层 blocks + 去重提示词（只借思路） | Letta |
| 第一周原型验证器（不进底座） | Mem0 |
| 编排/工具层 | PydanticAI |
| 衰减/遗忘/结晶公式 | companion-emergence |

## 依赖变化

- 已装：Git 2.56.0、PyYAML 6.0.1、pytest
- 未引入任何重型框架；Mem0/ChromaDB/torch 明确只在原型期按需装

## 已知风险

1. HerAndHim 为 AGPL-3.0：对外提供服务必须开源改动；单机自用无碍。
2. Crescent Grove 无真实 git 历史（单快照提交），抽模块时以“参考实现”对待。
3. PydanticAI v2 API 近期大改：锁定 v2.66.0。
4. MCP SDK v2 迭代快、FastMCP 已弃用：锁定 2.3.0，仅 Phase 4 引入。
5. 残留：research-src 与个别 ACL 锁定空目录（不解压残留），不影响交付。

## 下一阶段计划（Phase 1：最小 Resident）

在现有骨架上：
1. 接 PydanticAI 编排层（工具循环 + 结构化输出）
2. 真实 DeepSeek Key 接入与任务分级（chat/reason/light）
3. 记忆写入路径：LLM 仲裁 ADD/UPDATE/DELETE/NOOP + 五因子显著性
4. 身份与对话的断点续接验收（关→开→她还是她）
5. CLI 适配器完善（本地聊天窗口）

## 需要人工确认的事项

1. **AGPL 边界**：是否接受从 HerAndHim 抽包（对外服务需开源）；不接受则相关模块改写或
   只用思路。
2. **DeepSeek API Key**：新 key 放环境变量 `DEEPSEEK_API_KEY`（不进仓库）。
3. **PydanticAI 当编排底座**：是否同意 AD-10（其仅承担 loop+tooling，不拥有人格）。
4. 时间尺度维持 1:1（AD-9）是否确认。
