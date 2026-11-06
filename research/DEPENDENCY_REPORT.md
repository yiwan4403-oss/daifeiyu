# DEPENDENCY_REPORT — 依赖清单与风险

日期：2026-11-06 ｜ Phase 0

## 将被纳入的最小依赖（Phase 1 起步集）

| 包 | 用途 | 许可证 | Windows | 备注 |
| --- | --- | --- | --- | --- |
| pydantic | 数据模型/配置校验 | MIT | ✅ | 纯 wheel |
| apscheduler 或自建 asyncio 调度 | 日程/节拍 | MIT（apscheduler） | ✅ | 也可 Phase 1 自建，Phase 2 再定 |
| PyYAML | 配置 | MIT | ✅ | |
| httpx | 模型网关 HTTP | BSD-3 | ✅ | 也可 requests |
| pytest | 测试 | MIT | ✅ | 开发依赖 |
| ruff | 静态检查 | MIT | ✅ | 开发依赖 |

*原则：优先标准库；能不加就不加。*

## 候选复用模块及其依赖（抽模块时才装）

| 来源模块 | 外部依赖 | 体积风险 |
| --- | --- | --- |
| HerAndHim retrieval（dense 部分） | sentence-transformers/torch | 大（~数 GB 级别），仅需要时启用 |
| HerAndHim scheduler | APScheduler | 轻 |
| Crescent Grove Wyrd | FAISS | 中；后期换 sqlite-vec |
| PaulusAI vectorstore | ChromaDB | 中 |
| Mem0（原型期/仿写对象） | 纯 Python 344KB（v2.2.1），向量库为主 | 轻；原型或仿写管线 |

## 明确不引入

| 项目 | 原因 |
| --- | --- |
| Letta | 45 万行自托管服务器；Postgres 默认；无 Windows 支持 |
| LangGraph / AutoGen | 框架黑盒；与身份连续性目标冲突（AD-10） |

## 许可证风险

| 来源 | 许可证 | 风险 |
| --- | --- | --- |
| HerAndHim | **AGPL-3.0** | 对外提供服务必须开源改动；单机自用无碍。抽取时留注释与出处 |
| Crescent Grove / PaulusAI | MIT | 保留版权声明 |
| Letta / Mem0 | Apache-2.0 | 保留 NOTICE |
| MCP Python SDK | MIT | 待 frameworks-mcp 报告复核 |

## 供应链安全（总纲 9.4）

- 抽取任何第三方代码前：人工审读 + 保留来源 commit hash + 记录审计结论
- 新依赖引入需在 DEPENDENCY_REPORT 登记：名称/版本/许可证/体积/用途
- 模型生成代码：先测试、后人工审、再进生产目录（总纲 3.5）
