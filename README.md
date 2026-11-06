# Resident

独立自主生活与自我进化型 AI。她不是聊天机器人，也不是命令执行 Agent——
她是一个拥有持续身份、记忆、情绪、关系、目标和自主活动能力的常驻存在。

> 项目代号：Resident ｜ 主要语言：Python ｜ 环境：Windows 10/11
> 模型：DeepSeek 优先，不绑定单一模型

## 目录

- `docs/` — 设计文档（架构决策 / 数据模型 / 安全模型 / 路线图 / Phase 报告）
- `research/` — Phase 0 源码研究报告与证据
- `core/` — 运行时、事件总线、模型网关、上下文构建
- `identity/` — 身份与人格
- `memory/` — 记忆与事件存储
- `storage/` — SQLite schema 与迁移
- `adapters/`（规划中）— CLI / Minecraft / …
- `security/`（规划中）— 权限、审批、审计、沙箱

## 快速开始（当前骨架）

```powershell
python main.py --init     # 初始化数据目录与身份
$env:DEEPSEEK_API_KEY = "sk-..."
python main.py            # 前台对话（exit 退出）
```

测试：

```powershell
python -m pytest tests -q
```

## 她已具备的能力（v0.6.0）

- **人格与记忆**：26 维情绪（半衰期衰减）、六类记忆 + FTS5 检索、自传、Belief 分层、
  断点续接（重启还是她）
- **自主生活**：欲望/目标/活动/规划器/调度器，没人时也自己过日子
- **自主开发**：发现缺口 → 生成插件 → 白名单检查 → 沙箱测试 → 人工审批 → 安装 → 回滚
- **外部世界**：web_fetch、白名单文件读写、MCP 外部工具（stdio）
- **持续进化**：健康检查、指标、经验沉淀

CLI 命令：`/plugins` `/pending` `/approve <id>` `/reject <id>` `/rollback <插件>` `/health`

## 核心原则

1. 身份唯一：所有平台、所有模型共享同一个她。
2. 人格独立于 Prompt；记忆独立于模型。
3. 核心与插件分离；安全由程序执行，不由 LLM 自觉。
4. 先研究，再设计；先稳定核心，再赋予能力；先保证人格连续性，再追求自主进化。

详见 `docs/`。
