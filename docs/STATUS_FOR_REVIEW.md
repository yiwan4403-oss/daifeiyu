# Resident 工程现状报告（供架构审查）

日期：2026-11-07 ｜ 版本 v0.8.1 ｜ 仓库：https://github.com/yiwan4403-oss/daifeiyu （main @ 6eca71d，AGPL-3.0）

## 1. 一句话定位

Resident = 独立 Python 常驻进程的自主 AI 角色：统一身份 + 六类记忆 + 26 维情绪 + 自主生活节拍 + 自我开发能力（插件 SDK/审批/回滚）+ 外部适配器（CLI/QQ/B站/浏览器/文件/MCP）。DSH 只承担开发期工具角色，不是她的运行时。

## 2. 目录结构

```
Resident/
├── main.py / config.yaml / pyproject.toml / README.md / CHANGELOG.md / ARCHITECTURE.md
├── core/        agent(编排) · context_builder · event_bus · model_gateway
├── identity/    identity_manager(身份+变更历史) · emotion(26维半衰期) · relationships(多维关系)
├── memory/      manager(六类+FTS5+衰减+user_key) · event_store(只增+清洗) ·
│                arbiter(LLM记忆仲裁+情绪增量) · autobiography · beliefs
├── life/        desire · goals · activities · planner(活动决策) · scheduler(节拍) · bili_daily(生物钟)
├── development/ generator · tester(白名单+沙箱pytest) · builder · researcher · pipeline(审批/回滚) ·
│                mcp_client · self_maintenance
├── extensions/  sdk · manifest · registry · loader(版本目录/错误隔离)
├── security/    permission(L0-L3) · approval · audit
├── adapters/    cli · browser · windows · qq(OneBot反向WS) · bilibili(wbi/扫码/风控) · minecraft(骨架)
├── storage/     database(schema v1 + 迁移)
└── tests/       8 个测试文件，45 用例
```

## 3. 完成度与关键实现

### 3.1 人格与记忆（Phase 1/2，已跑通）

- 记忆：六类（episodic/semantic/associative/emotional/procedural/autobiographical），SQLite + FTS5（索引代码同步，本机 sqlite 不支持 fts5 'delete' 特令）、五因子显著性（v1 简化：基础 0.5 + 情绪 0.3 + 自我相关 0.2）、FADE/LOST 衰减（30 天豁免）、user_key 按人对齐（检索优先本人+全局）
- 记忆写入：LLM 仲裁 ADD/UPDATE/DELETE/NOOP（轻模型，单次调用同时输出情绪增量）
- 情绪：26 维 + 逐情绪半衰期衰减（companion-emergence 公式；love/belonging 不衰减；<0.01 删除）
- 关系：familiarity/trust/affinity 多维 + known/unverified 清单；交互自动更新
- 自传：每日/24h 过期重写，注入上下文
- Belief：source/verified 分层，模型输出不得自动标 verified
- 断点续接：重启后身份/记忆/事件延续（测试覆盖）

### 3.2 自主生活（Phase 3）

- 欲望（种子+满足/增长）→ 目标（可自建）→ 活动（单活动状态机）
- Scheduler：60s 节拍、空闲 10 分钟才启动、活动间隔 30 分钟、每小时 ≤6 次 LLM 决策、主动发言 8-23 点+60 分钟间隔
- B站生物钟：20-24 窗口随机醒、30% 不看、筛5深读2-3、分享≤3/天、沉默衰减（3天→2、7天→0）

### 3.3 自主开发（Phase 4）

- 缺口→生成（reason 模型 16k 输出+flash 降级）→ AST 依赖白名单（禁 os/subprocess/网络）→ 沙箱 pytest（无测试不许装）→ 版本化装配 → L2 人工审批 → 安装注册 → 回滚
- 真机验收：她自写“掷骰子”插件全链路通过
- MCP 2.3.0 stdio 客户端（真实 echo server 测试）

### 3.4 外部世界（Phase 5）

- QQ：OneBot v11 反向 WS（NapCat v4.18.42 + QQNT 9.9.33 实连），私聊自动回复、owner 可下命令、按 QQ 号隔离上下文/关系/记忆；群聊只记录
- B站：wbi 签名搜索、视频信息、扫码登录（generate 真机通过，poll 待用户扫码）、风控参数表（程序化执行）、me/dm_status/send_dm（三条硬限制：只发 owner、必须互关 attribute=6、csrf）
- Browser（只读抓取+证书降级）、Windows（白名单 list/read）、Minecraft 骨架

### 3.5 安全

- L0-L3 权限矩阵、审批队列（模型不得自我批准）、审计表、外部内容一律 untrusted、事件写入清洗（防乱码入库）

## 4. 测试报告

```
python -m pytest tests -q
→ 45 passed, 1 warning（development/tester.py 的 Tester 类被 pytest 误收集，仅警告）
```

覆盖：身份持久化、事件/记忆往返、FTS 检索、仲裁（mock LLM）、显著性/衰减状态机、情绪衰减数学、关系更新、信念分层、自传、预算护栏、调度节拍/免打扰、插件全链路（生成→测试→审批→安装→回滚）、MCP 真实往返、QQ 反向 WS 真实 websockets 往返、B站登录/风控 mock、生物钟挑选/额度/衰减、事件清洗。

## 5. 环境

Python 3.12.10；pydantic-ai 2.66.0（编排底座）；PyYAML；websockets 17.4；mcp 2.3.0（锁版）；pytest；Git 2.56。Windows 10/11，DeepSeek API（chat=flash、reason=v4-pro、light=flash），日预算 0.5 USD 护栏。

## 6. 已知薄弱点 / 技术债（欢迎重点审查）

1. **人格层很薄**：目前只有 identity.core_persona 一段文本 + context_builder 模板；原项目的 persona 五段式（我是谁/说话/我在意什么/我绝不会/日记标准）未迁移；人格演化机制（哪些可自改）只有 SECURITY_MODEL 文档约定，无代码实现
2. **记忆整合**：consolidate 是纯规则（衰减状态机），没有周期性 LLM 整合/冲突仲裁（arbiter 只在写入时裁决）；全局 vs 按人记忆的作用域策略靠 user_key 简单实现
3. **上下文构建**：无预算分配（HerAndHim 的 boot 预算/索引优先机制未引入），多模块信息（情绪/关系/自传/信念/记忆/事件）平铺，长度靠手工截断
4. **自主节拍**：活动决策每小时 ≤6 次是硬编码策略，无费用/价值感知的优先级
5. **QQ 群聊**：只记录不回应；群消息作用域（scope=group）未被上下文利用
6. **B站生物钟**：日记是规则拼接文本，非 LLM 写“给主人的信”；分享走 proactive 打印，未接私信/评论通道（等登录态）
7. **插件隔离**：同进程 import（错误隔离有，进程隔离无）；依赖安装未实现（白名单仅检查 import）
8. 双日记（给主人的信 + 不加滤镜的那本）未实现；persona 注入优先级（身份字段 vs persona 文件）未定义

## 7. 当前阻塞与待办

- B站真机扫码：等用户实名小号扫码（generate 已验证，poll/凭据落盘待扫）；owner_mid 待填
- Minecraft 适配器实连：走 ToolDelta，待服务器就绪
- 下一步按 GPT 建议：先健康检查（已做：目录/依赖/库/配置/测试均正常），再进入人格与记忆系统深化

## 8. 希望审查的问题

1. 人格演化的实现边界（自改/审批/历史追溯）怎么做成代码而非文档？
2. 记忆整合：多久跑一次 LLM 整合？冲突仲裁放在写入时还是整合时？user_key 作用域 vs 全局事实的分层怎么定？
3. 上下文预算分配（多模块注入的优先级与截断策略）？
4. 自主节拍如何加入“价值/费用感知”而不只是硬上限？
5. 插件系统需要进程级隔离吗（同进程隔离何时不够）？
