# DATA_MODEL — Resident 数据模型（初版）

日期：2026-11-06 ｜ 状态：Phase 0 草案，Phase 1 落地时冻结 v1。

## 实体清单（总纲第七部分）

ResidentIdentity / PersonalityProfile / EmotionalState / Preference /
Relationship / Event / Memory / Knowledge / Belief / Desire / Goal / Task /
Activity / Capability / Plugin / Tool / Permission / ApprovalRequest /
ActionExecution / Reflection / ModelUsage / AuditRecord

## 核心表设计（SQLite，v1）

### 1. identity（一行）

```sql
id INTEGER PRIMARY KEY CHECK (id = 1),   -- 唯一 Resident
name TEXT NOT NULL,                       -- 核心身份（严格保护）
created_at TEXT,
core_persona TEXT,                        -- 基础性格描述（有限变化，留历史）
values_yaml TEXT,                         -- 价值观
preferences_yaml TEXT,                    -- 偏好（可渐变）
last_persona_revision INTEGER             -- 版本号，变更必须留历史行
```

### 2. persona_history（只增）

```sql
id INTEGER PRIMARY KEY, ts REAL, field TEXT, old_value TEXT, new_value TEXT,
reason TEXT, approved_by TEXT             -- approved_by='human' 或 'human:xxx'
```

### 3. emotion_state（一行）

```sql
id INTEGER PRIMARY KEY CHECK (id = 1),
dims TEXT                                 -- JSON: {joy: {v: 4.2, half_life_days: 30}, ...}
updated_at REAL
```

### 4. events（原始事件，只增，永不删）

```sql
id INTEGER PRIMARY KEY, ts REAL, type TEXT,     -- UserMessageReceived / GoalCreated ...
scope TEXT,                                       -- private/group/public
source TEXT,                                       -- 来源追踪：user/external/self/llm/hypothesis
actor TEXT, payload TEXT, raw TEXT
```

### 5. memories（六类）

```sql
id INTEGER PRIMARY KEY,
kind TEXT CHECK (kind IN
  ('episodic','semantic','associative','emotional','procedural','autobiographical')),
content TEXT, source TEXT,                -- user/external/self/llm/hypothesis
confidence REAL, verified INTEGER,        -- 0 假设 / 1 已验证
salience REAL, last_access REAL, ts REAL,
decay_state TEXT,                          -- active/fade/lost
links TEXT                                 -- JSON: 关联的记忆 id 列表
```

### 6. memory_fts（FTS5 影子表）

```sql
CREATE VIRTUAL TABLE memory_fts USING fts5(content, tokenize='unicode61');
-- 触发器：memories 增删改时同步（phase 1 用触发器或代码同步）
```

### 7. relationships（每关系一行）

```sql
id INTEGER PRIMARY KEY, name TEXT NOT NULL, scope TEXT,
familiarity REAL, trust REAL, affinity REAL,   -- 多维，非单一好感
status TEXT, events_yaml TEXT,                 -- 关系事件
known_yaml TEXT, unverified_yaml TEXT,         -- 双方已知 / 未确认信息
updated_at REAL
```

### 8. desires / goals / tasks / activities

```sql
desires:  id, name, strength REAL, source, created_at
goals:    id, text, desire_id, priority, status(pending/active/paused/done/failed),
          created_at, deadline, parent_id
tasks:    id, goal_id, text, status, attempts, budget_limit
activities:id, kind, started_at, ended_at, summary
```

### 9. capabilities / plugins / tools

```sql
capabilities: id, name, provided_by_plugin, version, status
plugins:      id, name, version, manifest TEXT, status(installed/enabled/disabled/failed)
tools:        id, name, plugin_id, schema TEXT, permission_required TEXT
```

### 10. permissions / approvals / audit / model_usage

```sql
permissions:  subject, resource, action, level(L0-L3), policy
approvals:    id, ts, request TEXT, decision, decided_by, scope
audit:        id, ts, actor, action, resource, result, detail
model_usage:  id, ts, task_class, model, in_tokens, out_tokens, cost_est, ok
```

## Belief 分层（总纲 7.1）

每条 knowledge/belief 必须带 `source`（user/external/self/llm/hypothesis）+
`verified`（0/1）。模型输出不得自动标 verified。

## 事件流保底

`data/events/*.jsonl` 与 events 表双写；原始文本永不只存总结。
