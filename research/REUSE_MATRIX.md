# REUSE_MATRIX — 模块复用矩阵

日期：2026-11-06 ｜ 原则：只抽“依赖干净、接口可注入 LLM、不绑定其主循环”的模块。

## 矩阵总览

| 来源 | 抽取模块 | 用途 | 许可证 | 抽取风险 |
| --- | --- | --- | --- | --- |
| HerAndHim | `memory` 包 | Markdown KV + 日志 + FTS5 + 写时整理 | **AGPL-3.0** | 中（许可证；需改写接口） |
| HerAndHim | `retrieval` 包 | BM25→dense 三级降级 + RRF + rerank | AGPL-3.0 | 中（依赖其存储格式） |
| HerAndHim | `scheduler` 包 | 日程 + 概率主动 + cron 封装 | AGPL-3.0 | 低 |
| HerAndHim | `storage` 包 | 数据目录/锁/迁移 | AGPL-3.0 | 低 |
| Crescent Grove | LETHE（compressor.py） | 对数衰减情节记忆（原档永不删，视图按预算裁剪） | MIT | 低（~数百行） |
| Crescent Grove | Wyrd Network | JSON 图联想 + 扩散激活 + 侧抑制 | MIT | 中（FAISS 可选替换 sqlite-vec） |
| Crescent Grove | MoonTide | 情绪粒子模型 | MIT | 低（纯数学） |
| Crescent Grove | DesireManager | 欲望/动机管理 | MIT | 低 |
| PaulusAI | security.py + grants.py + automode.py | 审批三件套 + 授权黑名单 + 审阅器 | MIT | 低（依赖最干净） |
| PaulusAI | memory.py + vectorstore.py | 事实真源 + 矛盾仲裁 + 派生索引 | MIT | 中（绑定 Chroma） |
| PaulusAI | affect.py + appraisal.py | PAD+16 情绪 OCC | MIT | 低（纯数学） |
| PaulusAI | mcp_client.py | MCP 客户端（stdio/HTTP/SSE） | MIT | 中 |
| Letta | 仅借思路 | 分层 blocks + ARCHIVAL_INSERT 去重提示词 | — | 不抽代码 |
| Mem0 | 原型期直接用 `mem0` 库 | 第一周验证记忆召回效果 | Apache-2.0 | 仅原型，不进长期底座 |

## 不建议抽取

| 来源 | 模块 | 原因 |
| --- | --- | --- |
| Crescent Grove | agent.py / context.py / scheduler.py | 三大单体 ~410KB，耦合深、个人运维假设多 |
| HerAndHim | agent.py | 2110 行 god object；消息驱动同步函数 |
| PaulusAI | 主循环/后台任务 | 全局共享 mood/skills；无规划器 |
| Letta | 整个 server | 45 万行自托管服务器，Postgres 默认，Windows 不支持 |

## 许可证注意事项

1. **AGPL-3.0（HerAndHim）**：抽用代码后，若对外提供服务必须开源改动。
   Resident 目前单机自用无问题；若要对外提供服务，需改写/隔离这些模块，或换实现。
2. MIT（Crescent Grove / PaulusAI）与 Apache-2.0（Mem0 / Letta）：保留版权声明即可。
3. 抽取进项目时，在文件头保留原许可证与出处注释。
