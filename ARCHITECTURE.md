# ARCHITECTURE — Resident 架构总览

> 权威来源：`docs/ARCHITECTURE_DECISIONS.md`（决策与理由）、
> `docs/DATA_MODEL.md`（数据）、`docs/SECURITY_MODEL.md`（安全）。
> 本文件只给总览，与决策文档冲突时以决策文档为准。

## 总览

```
adapters/  CLI · Minecraft · (QQ/Bili/Browser 后续)
    │ 统一事件/动作协议
core/      runtime · cognition · event_bus · context_builder · decision_engine · model_gateway
identity/  identity_manager · personality · values · preferences · emotion · relationships
memory/    episodic/semantic/associative/emotional/procedural/autobiographical + event_store
life/      desire_system · goal_manager · scheduler · activity_manager · reflection
security/  permission(L0-L3) · approval · audit · sandbox · backup · rollback
storage/   SQLite v1 schema · migrations
api/       本地管理 API（后续）
```

- **编排层**：PydanticAI（loop + tooling，不拥有人格）
- **模型**：ModelGateway 唯一出口，任务分级（chat / reason / light / code）
- **数据**：SQLite（事件只增 + 六类记忆 + FTS5 + 衰减）+ JSONL 原始流
- **节拍**：事件驱动 + 低频后台 tick；禁止高频 LLM 模拟思考

## 主循环（Phase 1 目标）

```
事件(用户消息/定时) → 检索记忆 → 构建上下文(身份+状态+记忆)
  → LLM 决策(回复/工具调用) → 权限检查 → 执行 → 记录 → 反思 → 持久化
```

## 边界

- 核心不依赖任何平台；删除任一适配器不影响身份/记忆/情绪/目标。
- 外部内容一律 untrusted；模型不得自我授权；核心身份修改需 L3 人工确认。
