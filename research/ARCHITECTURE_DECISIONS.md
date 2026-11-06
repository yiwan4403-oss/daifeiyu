# ARCHITECTURE_DECISIONS — Resident 架构决策记录

日期：2026-11-06 ｜ 状态：Phase 0 初版，每条决策带理由与备选。

---

## AD-1：独立 Python 进程，不做任何平台插件

- **决定**：Resident 是独立常驻进程（Windows 前台/后台模式），不寄生 DSH/ToolDelta。
- **理由**：24h 自主生活、崩溃自恢复、身份连续性都需要掌控进程生命周期；插件随宿主更新即废（DSH v3→v4 注入格式破坏、ToolDelta/FateArk 更新阻塞均有前车之鉴）。
- **备选**：DSH 插件（已否决）。

## AD-2：自建事件总线

- **决定**：`core/event_bus.py` 统一事件（UserMessageReceived、ScheduledActivityDue、MemoryCreated、GoalCreated、TaskFailed……），所有模块通过事件解耦。
- **理由**：四个研究对象**没有一个有事件总线**（HerAndHim 直接调用+单例，1/10）；没有它，插件、调度、记忆、适配器必然纠缠成 god object。
- **证据**：herandhim.md（无事件总线评分）；crescent-grove agent.py 410KB 单体即反面教材。

## AD-3：自建 SQLite 记忆层（六类 schema + FTS5 + 时间衰减 + 来源追踪）

- **决定**：`memory/` 自建透明 SQL 表：episodic / semantic / associative / emotional /
  procedural / autobiographical + event_store（JSONL 原始事件，永不只存总结）。
  检索：FTS5 关键词 → BM25 打分 → 关联图扩散（借 Wyrd 思路）；后期按需加 sqlite-vec。
  写入：LLM 仲裁 ADD/UPDATE/DELETE/NOOP（借 Mem0 思路），但决策记录可查、不黑盒。
- **理由**：Letta 太重（45 万行/Postgres/不支持 Windows）；Mem0 黑盒+每轮 LLM 费钱+480MB 依赖。
- **原型期**：可用 Mem0 快速验证召回效果，但写入路径隔离在 `memory/` 接口后，随时可换。

## AD-4：主循环 = 事件驱动 + 低频后台节拍

- **决定**：消息事件即时响应；自主行为由后台 tick（默认 60s 状态更新、5–30 分钟活动决策、
  每小时目标检查）驱动。**不**高频调 LLM 模拟思考；LLM 调用按事件触发+预算封顶。
- **理由**：总纲明确“不得通过无限频率调用 LLM 模拟思考”；经济成本受控。
- **复用**：HerAndHim scheduler（APScheduler 封装）思路、Crescent Grove Moonbeat 脉冲思想。

## AD-5：人格独立于 Prompt（Identity 模块）

- **决定**：`identity/` 存核心身份（严格保护）、基础性格（有限变化、留历史）、价值观、
  偏好（可渐变）、当前情绪（可自然变化）、关系（独立记录）。Prompt 只是渲染层。
- **理由**：总纲 2.2；换模型/换入口人格不丢。

## AD-6：Model Gateway 统一模型调用 + 任务分级

- **决定**：`core/model_gateway.py` 唯一出口；支持 DeepSeek / OpenAI 兼容 / 本地模型；
  超时/重试/限流/token 与费用统计。任务分级：日常对话用 flash 级；复杂规划用推理级；
  记忆整理用轻量级；代码生成用代码强模型。
- **理由**：总纲 4.1/4.2；禁止模块直连 API。

## AD-7：安全外置，模型不得自我授权

- **决定**：`security/` 权限 L0–L3（读/规划 → 工作区写+测试 → 授权部署/外部操作 →
  人工确认的核心修改/删除/支付），权限绑定资源+动作，审计全记录；审批/授权由程序执行，
  模型只能发起申请。外部数据（网页/GitHub/MCP 结果）一律 untrusted，不得升格为系统指令。
- **复用**：PaulusAI 审批三件套（security/grants/automode）优先抽取。

## AD-8：核心与插件/适配器分离

- **决定**：core 不依赖任何平台；`adapters/` 统一事件/动作协议；插件系统（Plugin SDK、
  Capability Registry、生命周期、隔离）在 Phase 4 建设。初期只有 CLI 适配器（验证核心），
  随后接 Minecraft；QQ/Bilibili 延后。
- **理由**：总纲 2.4/2.5；先跑通一个环境。

## AD-9：时间尺度 1:1 现实时间

- **决定**：先按现实时间 1:1 运行（她和你同步作息）；加速模式作为配置项预留。
- **理由**：目标场景是陪真实用户；作息、日记、梦境都锚定真实时钟。

## AD-10（修订）：编排层采用 PydanticAI，身份/记忆/生活全部自建

- **决定**：用 **PydanticAI（MIT，v2.66.0）** 承担主循环编排与工具调用语义
  （ModelRetry/ToolFailed/人在环审批/延迟工具/长任务护栏/结构化输出）；
  **不用** LangGraph/AutoGen 等重型框架。
- **边界**：PydanticAI 不拥有 Resident 的人格、记忆、情绪、调度——那些是自建模块，
  通过 RunContext 注入。PydanticAI 只是“大脑皮层接线”，不是“灵魂”。
- **理由**：纯 Python、依赖少（9 个）、工具语义完备、护栏内建，省掉自写循环的坑；
  同时其刻意不做跨天调度与记忆存储，正好与自建模块分工不冲突。
- **MCP**：Phase 4 起用 mcp 2.3.0（锁版本）做外部工具/插件标准化；核心自带权限层。

## AD-14：衰减与遗忘公式采用 companion-emergence 参数

- **决定**：情绪衰减 `new = old · (1/2)^(Δt / half_life)`（逐情绪半衰期，<0.01 删除）；
  记忆显著性 = 五因子加权（情绪/共现/回忆/灵魂/新鲜度）+ FADE/LOST 状态机；
  人格漂移“结晶”机制引入，但**结晶结果必须过人工审批**才生效（compliance 差异）。
- **理由**：三套公式有源码与阈值可查（decay.py / salience.py），比自拟参数可信。

## AD-11：存储与可观测

- **决定**：`data/` SQLite 单文件 + `data/events/*.jsonl` 原始事件；日志轮转；
  备份自动+恢复演练；指标（人格一致性、记忆召回准确率、错误记忆率、目标完成率、
  费用、运行时长）从 Phase 1 起埋点。
- **理由**：总纲 13.7/13.10；“不能只靠人工主观感受判断有没有进步”。

## 待研究问题（总纲第十三部分）

上下文/人格连续性、API 预算、记忆真实性、目标合理性、主动联系边界、数据安全、
灾难恢复、人格自改边界、版权与平台规则——逐项在对应 Phase 前给出子决策。
