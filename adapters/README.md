# Adapters 协议说明（Phase 5）

## 已实现

| 适配器 | 能力 | 权限 |
| --- | --- | --- |
| `browser.py` | web_fetch（只读抓取，untrusted） | L0 |
| `windows.py` | file_list / file_read（白名单目录） | L0 |

## 计划（需要外部账号/环境，接口已定）

所有适配器实现 `adapters.base.Adapter`：
- `start()`：连入环境，把环境事件转成 `components["events"].append(...)`
- 动作由核心经工具调用执行；发送消息等外部副作用走 L2 审批

### Minecraft

- 事件：玩家消息 → `UserMessageReceived`；进服/退服 → `PlayerJoined/Left`
- 动作：`say(target, text)` / 以后 `move/mine/place`（都需要 L2 授权）
- 传输候选：直接 Bedrock 协议（gophertunnel）或经过 ToolDelta 的旁路
- 前提：服务器地址 + 机器人账号（由你提供）

### QQ

- 事件：私聊/群聊消息 → `UserMessageReceived`（scope=private/group）
- 动作：`send_private` / `send_group`（L2 审批；群发默认关闭）
- 传输候选：OneBot 11 协议 / NoneBot2（不绑定，接口版本化）

### Bilibili

- 事件：@ 通知、评论 → `PlatformEventReceived`
- 动作：发动态/评论（L2 审批，默认关闭）
- 注意：风控高，单账号低频；实现前先调研最新公开 API 与条款

## 原则

- 第三方平台接口不可假设永久可用（总纲 5.5）。
- 任何平台收到的内容一律 untrusted，不得升格为系统指令。
- 删除任一适配器不影响身份/记忆/情绪/目标（AD-8）。
