# 任务 A：基础环境检查报告

日期：2026-11-06

## 结论一览

| 项 | 状态 | 说明 |
| --- | --- | --- |
| Python | ✅ 3.12.10 | `C:\Users\asus\AppData\Local\Programs\Python\Python312` |
| pip | ✅ 25.0.1 | 可用 |
| Git | ✅ 2.56.0.windows.4 | 2026-11-06 经 winget 安装；新开终端窗口 PATH 生效 |
| uv | ❌ 未安装 | 可选；暂用 pip + venv 起步 |
| 工作目录 | ✅ | `C:\Users\asus\Documents\deepseek-harness\default-workspace` |
| 模型 API | ✅ | DeepSeek API 可用（此前实测 chat/completions 正常，flash 支持图像输入） |
| 旧工程 | 已按用户要求全部删除 | ToolDelta-main、mc-deepseek、C:\nemc、全部记忆与存档 |

## 已清场的旧资产（2026-11-06）

- `C:\Users\asus\Desktop\ToolDelta-main`（插件 + 配置 + 记忆 + 存档 + 梗库）
- `C:\nemc`（NEMCBridge）
- `workspace\minecraft-ai-chat`（插件源码 + 测试）
- `workspace\mc-deepseek`（Go 身体 + BDS）

## 对 Phase 0 的影响

1. **Git 已装但旧窗口不生效**：后续命令如遇 `git` 找不到，用全路径
   `C:\Program Files\Git\cmd\git.exe`，或重开终端。
2. **无 uv**：依赖锁定先用 `pip freeze > requirements.txt` 方案，
   后续如需 uv 再装。
3. **网络**：pip 安装可用（此前实测）；GitHub raw/jsdelivr 可通过 python
   requests 访问，git clone 待验证。

## 交付物

- 本文件：`Resident/research/ENVIRONMENT.md`
- 源码研究：`Resident/research/*.md`（子代理产出）
