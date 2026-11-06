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

## 核心原则

1. 身份唯一：所有平台、所有模型共享同一个她。
2. 人格独立于 Prompt；记忆独立于模型。
3. 核心与插件分离；安全由程序执行，不由 LLM 自觉。
4. 先研究，再设计；先稳定核心，再赋予能力；先保证人格连续性，再追求自主进化。

详见 `docs/`。
