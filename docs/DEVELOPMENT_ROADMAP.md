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

## Phase 3：自主生活

Desire / Goal / Scheduler / Activity / Reflection / 主动行为。
按 AD-4 低频节拍；无消息时也按目标安排合理活动。

验收：无用户消息时，能按自己的目标安排合理活动。

## Phase 4：自主开发

Plugin SDK、Manifest、Capability Registry、Code Generator、Test Runner、
Plugin Loader、权限审批、版本回滚；MCP 2.3.0 接入外部工具。

验收：给定一个缺失能力，Resident 能完成研究→开发→测试→受控部署。

## Phase 5：外部世界

优先顺序：Browser → Windows → Minecraft → QQ → Bilibili。
所有平台共享同一身份/记忆/目标。

## Phase 6：持续进化

能力评估、长期行为分析、经验学习、插件维护、非核心模块的安全自我更新。

## 跨阶段待办（总纲 13.x）

上下文/人格连续性、API 预算、记忆真实性、目标合理性、主动联系边界、
数据安全、灾难恢复、版权合规、可观测指标（人格一致性/召回准确率/错误记忆率/
目标完成率/费用/运行时长）。
