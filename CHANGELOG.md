# CHANGELOG

## [0.4.0] - 2026-11-06

Phase 3 完成（自主生活 v1）：

- Desire：种子欲望 + 满足/饥饿式强度变化
- Goal：创建/列表/暂停/完成，规划器可自主立目标
- Activity：单活动状态机，今日小结
- Planner：低频 LLM 决策（干什么 / 是否主动说话 / 是否立目标）+ 定期自我观察
- Scheduler：后台节拍（tick/空闲阈值/活动间隔/每小时决策上限/主动发言免打扰窗口）
- CLI：她会在没人说话时自己过日子（活动/目标/主动发言出现在控制台）
- 真机验证：空闲 2 小时后她选择“学点新东西”，并自主立了目标“每周学一个小知识攒成小百科”
- 测试：25/25

## [0.3.0] - 2026-11-06

Phase 2 完成：

- 记忆：memories.meta 分类元数据 + beliefs 表（source/verified 分层，LLM 输出不得自动标 verified）
- 情绪：26 维 + 逐情绪半衰期衰减（companion-emergence 公式；love/belonging 不衰减；<0.01 消失）；
  对话后由仲裁器同一次 LLM 调用提取情绪增量
- 关系：familiarity/trust/affinity 多维 + known/unverified 清单；交互自动更新熟悉度与好感
- 自传：每日/按需生成第一人称自传，注入上下文
- 上下文：情绪摘要 + 当前关系 + 自传 + 已验证信念 + 相关记忆 + 最近事件
- 真机验证：对话、情绪评估、关系更新、自传、跨会话记忆全部通过
- 测试：20/20

## [0.2.0] - 2026-11-06

Phase 1 完成：

- 编排层：PydanticAI 2.66（Agent + 工具循环 + 分级模型 chat/reason/light + 预算护栏）
- 模型网关：base_url 统一、usage 统计落 model_usage 表
- 记忆仲裁：LLM 裁决 ADD/UPDATE/DELETE/NOOP + 内容查重 + 五因子显著性（v1 简化）+ FADE 衰减状态机
- CLI 适配器：adapters/cli.py（asyncio 循环，exit 退出）
- FTS5 索引改为代码同步（本机 sqlite 不支持 fts5 'delete' 特令）
- 真机验证：DeepSeek 端到端对话 + 记忆写入 + 检索通过
- 测试：14/14 通过（仲裁/去重/显著性/衰减/预算/断点续接）

## [0.1.0] - 2026-11-06

Phase 0 完成，最小骨架落地：

- 环境：Python 3.12 + Git 2.56 + PyYAML + pytest
- 骨架：配置(YAML)、SQLite schema v1、EventBus、EventStore、ModelGateway、
  IdentityManager（变更留历史）、MemoryManager（FTS5）、CLI 循环
- 文档：RESEARCH_REPORT / ARCHITECTURE_DECISIONS / DEPENDENCY_REPORT /
  REUSE_MATRIX / DATA_MODEL / SECURITY_MODEL / DEVELOPMENT_ROADMAP / PHASE0_REPORT
- 测试：7/7 通过
