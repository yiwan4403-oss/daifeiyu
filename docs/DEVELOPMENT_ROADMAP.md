# DEVELOPMENT_ROADMAP — Resident 开发路线图

日期：2026-11-06 ｜ 每阶段结束向管理者提交：完成项/源码证据/决策/依赖变化/风险/下一阶段/待人工确认。

## Phase 0：源码研究与架构验证（进行中）

- [x] 环境检查（ENVIRONMENT.md）
- [x] 五个方向源码研究（5 份报告 + 证据清单）
- [x] 选型（RESEARCH_REPORT §9）
- [x] 四件套文档 + DATA_MODEL + SECURITY_MODEL + 本文件
- [x] 最小工程骨架（任务 E）与验收（pytest 7/7 + 冒烟通过）

## Phase 1：最小 Resident（进行中）

目标：启动系统、Model Gateway、Identity、基础对话、SQLite、Event Store、基础记忆、持久化。

- [x] PydanticAI 编排层 + 工具循环 + 分级模型（chat/reason/light）
- [x] 预算护栏（daily_usd）与 usage 统计
- [x] 记忆仲裁 ADD/UPDATE/DELETE/NOOP + 查重 + 显著性 + FADE 衰减
- [x] CLI 适配器 adapters/cli.py
- [x] 断点续接测试（身份/记忆/事件重启延续）
- [x] 真机 DeepSeek 端到端验证
- [ ] 验收确认（管理者复核）

验收：**关闭并重新启动后，Resident 延续之前的身份和对话经历。**（测试已覆盖，待实测复核）

## Phase 2：人格与长期记忆（进行中）

六类记忆 + 检索 + 整合；情绪系统（companion-emergence 衰减公式）；关系系统；自传系统；Belief 分层。

- [x] 六类记忆 schema 补全（meta 元数据）
- [x] 情绪系统 26 维 + 半衰期衰减 + 对话情绪增量提取
- [x] 关系系统（familiarity/trust/affinity + 关系事件）
- [x] 自传系统（每日刷新，注入上下文）
- [x] Belief 分层（source/verified）
- [x] 上下文构建升级（情绪/关系/自传/信念）
- [ ] 验收确认（管理者复核）

验收：长期测试中人格一致，重要经历可准确回忆。（测试与真机冒烟已覆盖，待持续运行观察）

## Phase 3：自主生活（进行中）

Desire / Goal / Scheduler / Activity / Reflection / 主动行为。

- [x] 欲望系统（种子 + 满足/增长）
- [x] 目标管理（规划器可自主立目标）
- [x] 活动状态机 + 今日小结
- [x] 生活规划器（低频 LLM 决策 + 自我观察）
- [x] 调度器（节拍/空闲/间隔/上限/免打扰）
- [x] CLI 集成（她会在空闲时自己过日子）
- [ ] 验收确认（管理者复核）

验收：无用户消息时，能按自己的目标安排合理活动。（真机已演示：空闲 2h → 自主选择“学点新东西”并立下目标）

## Phase 4：自主开发（进行中）

Plugin SDK、Manifest、Capability Registry、Code Generator、Test Runner、Plugin Loader、权限审批、版本回滚；MCP 后续接入。

- [x] Plugin SDK / Manifest / Registry / Loader（版本目录 + 错误隔离）
- [x] Development Engine：生成 → 白名单 → 沙箱测试 → 装配 → 审批 → 安装 → 回滚
- [x] 研究工具（GitHub 搜索 + 只读抓取）
- [x] 安全层（L0–L3 权限、审批、审计；模型不得自我批准）
- [x] CLI 审批命令 + 她的能力工具（dev_request）
- [x] 真机验收：掷骰子插件全链路跑通
- [x] MCP 2.3.0 接入（stdio 客户端 + 真实 server 测试）
- [x] 验收确认（管理者复核）

验收：给定一个当前缺失的普通软件能力，Resident 能够完成研究、开发、测试和受控部署。
（已真机演示：掷骰子插件 生成→测试→审批→安装→可调用）

## Phase 5：外部世界（进行中）

优先顺序：Browser → Windows → Minecraft → QQ → Bilibili。

- [x] Adapter 统一协议（base.py）
- [x] Browser 适配器（web_fetch，untrusted，证书降级）
- [x] Windows 适配器（白名单 file_list/file_read）
- [x] Minecraft/QQ/Bilibili 协议文档与骨架
- [ ] Minecraft 实连（待服务器地址与机器人账号）
- [ ] QQ / Bilibili 实连（待账号与风控评估）

验收：所有平台共享相同身份、记忆和目标。（CLI/Browser/Windows 已共享同一核心）

## Phase 6：持续进化（进行中）

- [x] 插件健康检查 + 异常自动禁用（审计留痕）
- [x] 运行指标（调用数/token/费用/记忆/事件/活动）
- [x] 经验学习（指标观察沉淀为 procedural 记忆）
- [ ] 能力评估与长期行为分析（积累数据后迭代）

验收：能够通过实际经历发现不足，并产生可验证的改进。

## 跨阶段待办（总纲 13.x）

上下文/人格连续性、API 预算、记忆真实性、目标合理性、主动联系边界、
数据安全、灾难恢复、版权合规、可观测指标（人格一致性/召回准确率/错误记忆率/
目标完成率/费用/运行时长）。
