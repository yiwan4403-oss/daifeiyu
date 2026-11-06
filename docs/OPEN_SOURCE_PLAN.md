# OPEN_SOURCE_PLAN — 开源操作方案

日期：2026-11-06 ｜ 决策：Resident 整体 **AGPL-3.0** 开源。

## 为什么 AGPL-3.0

Resident 将并入 HerAndHim 的 AGPL 模块，copyleft 要求合并作品同许可发布——
AGPL-3.0 是兼容且自洽的选择；MIT/Apache 模块不受影响（保留原声明即可）。

## 义务清单（AGPL 合规）

1. **源码可得**：仓库公开，任何通过 QQ/MC 等网络与 Resident 交互的用户都能拿到源码。
   - 做法：公开仓库 + README 首屏放仓库地址 + 机器人侧“源码”指路（她可以答“我的源码在…”，或配置文件里加 source_url，Phase 5 时随适配器展示）。
2. **保留版权声明**：每个借用文件头保留原作者 + 许可证；ATTRIBUTIONS.md 记录来源 commit。
3. **修改开源**：对 AGPL 模块的一切修改都随仓库发布（本仓库整体 AGPL，天然满足）。
4. **不提交的**：`data/`（记忆）、`logs/`、`.env`（密钥）、个人配置 —— 已进 `.gitignore`。

## 发布步骤（一次配置）

1. GitHub 新建空仓库（建议名：`resident` 或 `daifeiyu-resident`）。
2. 给我仓库地址；或给我一个有 push 权限的 token（仅写这一个仓库，用完可删）。
3. 我执行：
   ```powershell
   git remote add origin <url>
   git branch -M main
   git push -u origin main
   ```
4. 仓库设置：开 Issues；README 写清“源码获取”与角色说明。

## 日常开发节奏

- 每次功能完成即 commit + push；`CHANGELOG.md` 同步。
- 他人 PR/Issue 由你定夺，我协助评估。
- 敏感功能（账号凭证、内部服务器地址）用配置文件示例 + 环境变量，不进仓库。

## 风险与应对

| 风险 | 应对 |
| --- | --- |
| 记忆/隐私数据泄露 | data/ 永不提交；示例数据脱敏 |
| 泄露 API Key | .env 进 gitignore；历史泄露需立即轮换 key |
| 开源后被抄 | AGPL 下抄了也得开源；品牌靠“她”本身 |
