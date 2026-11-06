# ATTRIBUTIONS — 第三方代码来源与许可

Resident 整体以 **AGPL-3.0** 发布（满足并入 AGPL 模块的开源义务）。
本文件登记所有被引用/抽取的第三方代码及其来源 commit，逐条保留原许可与出处。

## 计划抽取（使用时在此登记来源 commit 与文件映射）

| 来源 | 许可证 | 用途 | 来源 commit | 本地文件 |
| --- | --- | --- | --- | --- |
| HerAndHim（github.com/ericwang915/HerAndHim） | AGPL-3.0 | memory/retrieval/scheduler/storage 参考实现 | 待抽取时记录 | 待定 |
| Crescent Grove（github.com/Canon-73/crescent-grove） | MIT | LETHE/Wyrd/MoonTide/Desire 参考实现 | 待抽取时记录 | 待定 |
| PaulusAI（github.com/Pavel6625/PaulusAI） | MIT | security/grants/automode 参考实现 | 待抽取时记录 | 待定 |
| Mem0（github.com/mem0ai/mem0） | Apache-2.0 | 记忆管线仿写对象 | 待抽取时记录 | 待定 |
| Letta（github.com/letta-ai/letta） | Apache-2.0 | 仅借 schema 思路 | — | — |
| companion-emergence（github.com/hanamorix/companion-emergence） | MIT | 衰减/遗忘/结晶公式 | 待抽取时记录 | 待定 |

## 规则

1. 每引入一个文件：记录来源 URL + commit hash + 许可证，并在文件头保留原版权声明。
2. AGPL 模块的修改必须随本仓库一并开源（本项目已整体 AGPL，天然满足）。
3. MIT/Apache 模块：保留其版权与 NOTICE 要求。
4. `data/`、`logs/`、`.env`、密钥永不提交。
