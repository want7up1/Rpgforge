# RPGForge Project Guide

> 面向：GPT-5.5 / Codex / 开发 Agent
> 项目类型：Docker 部署的 Web 版 AI 文字 RPG 剧本生成与运行系统
> 核心模型：DeepSeek V4 Flash / DeepSeek V4 Pro
> 可选扩展：Xiaomi MiMo TTS（暂不实施）
> 目标：解决 AI 文字 RPG 的健忘、设定漂移、复杂世界观管理、上下文压缩和长期游戏状态维护问题。

---

## 0. 给 Codex 的总指令

你正在开发一个名为 **RPGForge** 的个人 AI 文字 RPG 引擎。项目目标不是传统聊天应用，而是一个可以通过 Docker 部署、通过网页访问的 AI 文字 RPG 管理系统。

开发时必须遵守以下原则：

1. **不要把它做成普通聊天机器人。** 这是一个“游戏状态驱动”的 AI RPG 引擎。
2. **LLM 负责叙事，系统负责状态。** 不允许长期依赖聊天上下文来记住世界设定、背包、NPC、任务和隐藏信息。
3. **DeepSeek V4 Flash / Pro 是唯一 AI 文本引擎。** 不要引入 OpenAI、Anthropic、Gemini、Ollama 等其他文本模型适配层，除非用户后续明确要求。
4. **TTS 暂不属于核心 MVP。** 若后续接入语音，优先使用 MiMo TTS，并做成可开关、可异步、可缓存的独立扩展服务。
5. **所有重要游戏数据必须结构化存储。** 世界书、模式注入、NPC、地点、任务、物品、状态、摘要、回合日志都必须入库。
6. **隐藏信息必须和玩家可见信息分离。** 防止 AI 直接剧透 GM 幕后信息。
7. **每回合必须保存日志。** 包括玩家输入、GM 输出、状态变化提案、摘要和使用模型。
8. **状态变更默认需要确认或可回滚。** 不要让模型不可控地直接修改游戏状态。
9. **核心 MVP 已搭建完成，后续优先实测和稳定性打磨。** 新增高级能力前，先确认现有剧情、记忆、状态和移动端体验稳定。
10. **所有功能必须能在 Docker Compose 中启动。** 用户应能通过浏览器访问 Web UI。

---

## 1. 项目目标

RPGForge 是一个私有部署的 AI 文字 RPG 系统。用户先与“规则生成器”讨论游戏类型、剧本、世界观和玩法规则；系统生成世界观、剧本、世界书、模式注入和初始游戏状态；随后用户创建新游戏并开始游玩。

游戏运行时，GM 每回合除了接受用户自由输入外，还必须默认提供 **A、B、C、D 四个行动选项**。前端必须将这四个选项渲染为可点击按钮，用户点击按钮后即作为本回合行动提交。自由输入框仍然保留，用于输入非预设行动。

系统每回合根据当前游戏状态、相关世界书、模式注入、压缩摘要和最近剧情组装 Prompt，由 DeepSeek V4 Pro 生成正式剧情，再由 DeepSeek V4 Flash 执行状态提取、上下文压缩、一致性检查等工具任务。

项目主要解决：

- AI 长篇文字游戏中的健忘问题
- 强设定、强关联世界观的持续一致性
- NPC、势力、地点、任务、物品的结构化管理
- 玩家可见信息与 GM 幕后信息分离
- 上下文压缩和长期摘要
- 自动世界书检索与模式注入
- 多回合游戏状态管理、存档、回滚
- 可选扩展：MiMo TTS 旁白和角色对白生成

---

## 2. 非目标

第一阶段不要做以下事情：

1. 不做多人在线 RPG。
2. 不做复杂账号系统。
3. 不做商城、订阅、支付。
4. 不做移动端原生 App。
5. 不做除 DeepSeek 外的其他文本模型适配。
6. 当前不做 TTS；如果后续接入语音，不做除 MiMo 外的其他 TTS 适配。
7. 不做复杂 3D 地图、战斗棋盘或图像生成。
8. 不做公开平台或社区分享系统。
9. 不做真人声音克隆的默认功能。
10. 不做复杂权限系统；本项目优先个人私有部署。

---

## 3. 推荐技术栈

### 3.1 前端

- Next.js
- React
- TypeScript
- Tailwind CSS
- shadcn/ui 可选

### 3.2 后端

- Python
- FastAPI
- SQLAlchemy 2.x
- Alembic
- Pydantic v2

### 3.3 数据库与缓存

- PostgreSQL
- pgvector
- Redis

### 3.4 异步任务

第一阶段可使用：

- RQ 或 Dramatiq

如果项目后续复杂化，可改 Celery。

### 3.5 部署

- Docker Compose
- `.env` 配置
- 本地卷保存导出文件；音频卷仅在后续启用 TTS 扩展时使用

### 3.6 AI 服务

- DeepSeek V4 Flash：工具任务
- DeepSeek V4 Pro：创作任务和复杂任务
- Xiaomi MiMo TTS：可选文字转语音扩展，当前不纳入核心闭环

---

## 4. DeepSeek 模型分工

本项目只使用 DeepSeek V4 系列模型，并按 **1M 上下文窗口** 进行整体上下文预算设计。

注意：即使 DeepSeek V4 系列具备 1M 上下文能力，也不能把完整历史无限塞入模型。1M 上下文用于支撑复杂设定、长篇摘要、世界书召回和关键历史回溯；系统仍必须保留上下文压缩、世界书检索、结构化状态和摘要分层机制，以降低成本、提升速度并避免状态漂移。

### 4.1 DeepSeek V4 Flash

用于快速、结构化、成本敏感的任务：

- 访谈记录整理
- 用户输入意图识别
- 世界书关键词提取
- 世界书召回 query 改写
- 上下文摘要
- 回合摘要
- 章节摘要
- 状态变化提取
- JSON 格式化
- 一致性初筛
- 模式识别

### 4.2 DeepSeek V4 Pro

用于核心创作和复杂推理：

- 世界观生成
- 剧本生成
- 主任务系统提示词生成
- 复杂世界书生成
- 正式游戏剧情生成
- 关键 NPC 对话
- 剧情分支规划
- 矛盾修复
- 高风险剧情判定
- 长线伏笔规划

### 4.3 Model Router 规则

实现 `ModelRouter` 服务，统一调度：

```text
use_flash(task_type) -> 快速结构化任务
use_pro(task_type) -> 创作和复杂任务
```

不要在业务代码中散落模型名。所有模型名从环境变量读取：

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=
DEEPSEEK_FLASH_MODEL=deepseek-v4-flash
DEEPSEEK_PRO_MODEL=deepseek-v4-pro
```

---

## 5. 可选扩展：MiMo TTS 模块定位

MiMo TTS 是沉浸感扩展，不是核心游戏状态模块。当前项目暂不实施 TTS；如果后续恢复该扩展，TTS 必须异步执行，不能阻塞剧情文本显示。

### 5.1 TTS 流程

```text
GM 输出文本
  ↓
Flash 拆分旁白 / NPC 对白 / 系统提示
  ↓
创建 TTS jobs
  ↓
后台 worker 调用 MiMo TTS
  ↓
保存音频文件
  ↓
前端显示播放按钮
```

### 5.2 可选 TTS 范围

如果后续启用 TTS，第一版只实现：

- 旁白 TTS
- NPC 对白 TTS
- 手动播放
- 音频缓存
- TTS 开关

不要默认实现真人声音克隆。

### 5.3 声音配置

每个游戏有 voice profile：

- 旁白声音
- 系统提示声音
- 重要 NPC 专属声音

声音信息结构：

```json
{
  "speaker_name": "陆沉舟",
  "voice_provider": "mimo",
  "voice_mode": "voice_design",
  "voice_description": "三十多岁男性，声音低沉冷硬，语速偏慢，吐字清晰，情绪克制，带压迫感。",
  "style_prompt": "克制、紧张、低声",
  "speed": 1.0,
  "emotion": "tense"
}
```

### 5.4 TTS 缓存

按以下内容生成 hash：

```text
sha256(text + voice_profile + style + speed + emotion)
```

相同 hash 直接复用音频。

---

## 6. 系统模块

### 6.1 规则生成器

职责：

- 与用户讨论游戏需求
- 提取游戏类型、主角身份、风格、规则复杂度、失败代价、核心玩法、禁止元素
- 生成世界观、剧本、世界书、模式注入、初始状态
- 创建新游戏

流程：

```text
用户描述想法
  ↓
Flash 整理需求
  ↓
Pro 继续访谈或生成配置
  ↓
用户确认
  ↓
创建游戏
```

输出对象：

- worldview
- script_outline
- system_prompt
- lore_entries
- modes
- initial_state
- voice_profiles 可选

---

### 6.2 世界书系统

世界书是解决健忘的核心模块。

每个世界书条目必须包含：

- title
- type
- keywords
- trigger_words
- priority
- always_on
- visibility
- public_info
- gm_secret
- content
- usage_note
- embedding

世界书类型：

```text
core_rule
protagonist
npc
faction
location
item
plot_hook
mechanic
secret
```

世界书召回策略：

1. always_on = true 的高优先级条目每回合注入。
2. 根据玩家输入、当前地点、当前 NPC、当前任务生成检索 query。
3. 使用关键词匹配 + 向量检索混合召回。
4. 按 priority、相似度、当前上下文相关度排序。
5. 限制注入数量，避免上下文膨胀。

---

### 6.3 剧本系统

剧本不是固定小说，而是可变剧情骨架。

剧本结构：

```json
{
  "title": "雁回镇旧案",
  "acts": [
    {
      "act": 1,
      "name": "失踪镖队",
      "purpose": "让玩家接触核心谜团",
      "entry_conditions": ["玩家抵达雁回镇"],
      "major_events": ["发现无名尸", "获得赤铜鱼符"],
      "possible_outcomes": ["信任县衙", "怀疑县衙", "逃离雁回镇"]
    }
  ]
}
```

规则：

- 不要强制玩家必须走某条路线。
- 剧本负责提供压力、事件和后果。
- 玩家行为可以改变剧本路径。

---

### 6.4 模式注入系统

模式控制当前回合的玩法规则。

基础模式：

- 主线模式
- 调查模式
- 战斗模式
- 社交模式
- 潜行模式
- 探索模式
- 存档模式
- 复盘模式
- 设定修复模式

模式结构：

```json
{
  "name": "调查模式",
  "triggers": ["调查", "检查", "搜索", "询问", "线索"],
  "injection": "当前进入调查模式。GM 不应直接给出真相……",
  "priority": "medium",
  "enabled": true
}
```

模式选择流程：

```text
玩家输入
  ↓
Flash 识别意图
  ↓
匹配 trigger
  ↓
选择最高优先级模式
  ↓
注入 Prompt
```

---

### 6.5 游戏状态系统

当前状态是游戏运行核心。不要依赖纯文本上下文保存状态。

状态结构示例：

```json
{
  "current_turn": 1,
  "time": {
    "current": "秋末，申时",
    "pressure": "三日后县衙封案"
  },
  "location": {
    "current": "雁回镇义庄",
    "known_locations": ["雁回镇", "白骨观旧址"]
  },
  "protagonist": {
    "name": "未定",
    "identity": "失忆镖师",
    "body": "轻微疲惫",
    "mind": "记忆断片",
    "skills": ["观察", "短兵器", "江湖规矩"],
    "weaknesses": ["记忆缺失"]
  },
  "inventory": [],
  "quests": [],
  "npcs": [],
  "factions": [],
  "variables": {},
  "known_facts": [],
  "hidden_facts": [],
  "open_threads": []
}
```

---

### 6.6 上下文压缩系统

上下文分四层：

1. 固定系统提示词
2. 相关世界书
3. 当前结构化状态
4. 压缩剧情摘要 + 最近回合

摘要类型：

- turn summary：每回合摘要
- chapter summary：每 10-20 回合摘要
- long-term memory summary：长期不可遗忘事实
- open threads：未解伏笔
- player-known facts：玩家已知信息
- gm-hidden facts：GM 幕后信息

摘要必须分离玩家可见与 GM 幕后。

---

### 6.7 状态变更提取器

每回合 GM 输出后，使用 Flash 提取状态变化。

输出 JSON：

```json
{
  "time_delta": "半刻钟",
  "location_change": null,
  "inventory_add": [],
  "inventory_remove": [],
  "npc_updates": [],
  "quest_updates": [],
  "variable_updates": {},
  "new_lore_candidates": [],
  "new_known_facts": [],
  "new_hidden_facts": []
}
```

状态变更默认进入 pending，用户确认后写入当前状态。

---

### 6.8 一致性检查器

使用 Flash 做轻量检查，必要时用 Pro 修复。

检查内容：

- 是否违反世界规则
- NPC 行为是否违背动机
- 是否剧透隐藏信息
- 物品是否凭空出现或消失
- 时间线是否冲突
- 地点移动是否合理
- 任务状态是否矛盾
- 当前模式规则是否被违反

输出：

```json
{
  "has_conflict": true,
  "conflicts": [
    {
      "type": "hidden_info_leak",
      "description": "GM 直接泄露了陆沉舟参与旧案。",
      "severity": "high",
      "suggestion": "改写为陆沉舟神情异常，并留下账册线索。"
    }
  ]
}
```

---

## 7. 每回合游戏循环

标准游戏循环：

```text
1. 用户输入行动，或点击 A/B/C/D 行动按钮
2. Flash 识别当前模式
3. 检索相关世界书
4. 读取当前状态
5. 读取摘要和最近回合
6. Prompt Builder 组装 Prompt
7. Pro 生成 GM 剧情，并生成 A/B/C/D 四个行动选项
8. Flash 提取状态变化
9. Flash 一致性检查
10. 保存回合日志
11. 前端显示剧情和 A/B/C/D 行动按钮
12. 状态变化自动写入或进入审核流程
13. 后台生成摘要
14. 可选扩展：如果未来启用 TTS，再创建语音任务
```

A/B/C/D 按钮规则：

```text
A/B/C/D 是 GM 给出的建议行动，不是唯一行动。
用户可以点击按钮快速选择，也可以在自由输入框中输入自定义行动。
按钮文本必须具体，不允许出现“继续”“看看”“随便走走”这类无意义选项。
每个选项应代表不同策略、风险或信息方向。
```

---

## 8. Prompt Builder 结构

每回合传给 Pro 的 Prompt 应由系统组装，不要直接把所有历史对话塞进去。

虽然 DeepSeek V4 系列按 1M 上下文窗口设计，但 Prompt Builder 仍应遵循“高价值上下文优先”原则：优先注入系统规则、当前状态、相关世界书、关键摘要、最近回合和当前模式，而不是无差别注入全部历史。

结构：

```text
【系统提示词】
本局 GM 规则、玩家权限、叙事规则。

【当前模式注入】
例如：调查模式 / 战斗模式 / 主线模式。

【世界核心规则】
always_on 的高优先级世界书。

【本回合相关世界书】
根据玩家输入、当前状态、NPC、地点、任务召回。

【当前游戏状态】
结构化状态。

【长期摘要】
不可遗忘事实。

【阶段摘要】
最近一章剧情。

【最近回合】
最近 3-6 回合原文。

【玩家输入】
用户当前行动。

【输出要求】
输出玩家可见剧情，不输出内部 JSON。
每回合必须生成 A/B/C/D 四个行动选项，并在结构化字段中返回，供前端渲染为按钮。
```

---

## 9. 数据库设计

### 9.1 games

```sql
id UUID PRIMARY KEY
title TEXT NOT NULL
genre TEXT
description TEXT
status TEXT
created_at TIMESTAMP
updated_at TIMESTAMP
```

### 9.2 game_configs

```sql
id UUID PRIMARY KEY
game_id UUID REFERENCES games(id)
system_prompt TEXT
worldview JSONB
script_outline JSONB
generation_notes TEXT
created_at TIMESTAMP
updated_at TIMESTAMP
```

### 9.3 lore_entries

```sql
id UUID PRIMARY KEY
game_id UUID REFERENCES games(id)
title TEXT NOT NULL
type TEXT
keywords TEXT[]
trigger_words TEXT[]
priority TEXT
always_on BOOLEAN DEFAULT FALSE
visibility TEXT
public_info TEXT
gm_secret TEXT
content TEXT NOT NULL
usage_note TEXT
embedding VECTOR
created_at TIMESTAMP
updated_at TIMESTAMP
```

### 9.4 modes

```sql
id UUID PRIMARY KEY
game_id UUID REFERENCES games(id)
name TEXT NOT NULL
triggers TEXT[]
injection TEXT NOT NULL
priority TEXT
enabled BOOLEAN DEFAULT TRUE
created_at TIMESTAMP
updated_at TIMESTAMP
```

### 9.5 game_states

```sql
id UUID PRIMARY KEY
game_id UUID REFERENCES games(id)
current_turn INTEGER
state_json JSONB
summary TEXT
created_at TIMESTAMP
updated_at TIMESTAMP
```

### 9.6 turns

```sql
id UUID PRIMARY KEY
game_id UUID REFERENCES games(id)
turn_number INTEGER
player_input TEXT
gm_output TEXT
visible_summary TEXT
hidden_summary TEXT
state_delta_json JSONB
model_used TEXT
created_at TIMESTAMP
```

### 9.7 state_deltas

```sql
id UUID PRIMARY KEY
game_id UUID REFERENCES games(id)
turn_id UUID REFERENCES turns(id)
delta_json JSONB
status TEXT
approved_at TIMESTAMP
created_at TIMESTAMP
```

status：

```text
pending
approved
edited
rejected
```

### 9.8 summaries

```sql
id UUID PRIMARY KEY
game_id UUID REFERENCES games(id)
type TEXT
range_start_turn INTEGER
range_end_turn INTEGER
content TEXT
important_facts JSONB
created_at TIMESTAMP
```

### 9.9 entities

```sql
id UUID PRIMARY KEY
game_id UUID REFERENCES games(id)
entity_type TEXT
name TEXT
public_info TEXT
hidden_info TEXT
state_json JSONB
embedding VECTOR
created_at TIMESTAMP
updated_at TIMESTAMP
```

### 9.10 可选扩展表：voice_profiles

```sql
id UUID PRIMARY KEY
game_id UUID REFERENCES games(id)
target_type TEXT
target_id UUID
speaker_name TEXT
voice_provider TEXT
voice_mode TEXT
voice_id TEXT
voice_description TEXT
style_prompt TEXT
speed FLOAT
emotion TEXT
enabled BOOLEAN DEFAULT TRUE
created_at TIMESTAMP
updated_at TIMESTAMP
```

### 9.11 可选扩展表：tts_jobs

```sql
id UUID PRIMARY KEY
game_id UUID REFERENCES games(id)
turn_id UUID REFERENCES turns(id)
segment_id TEXT
speaker_name TEXT
text TEXT
text_hash TEXT
voice_profile_id UUID
provider TEXT
status TEXT
audio_url TEXT
audio_format TEXT
duration_ms INTEGER
error_message TEXT
created_at TIMESTAMP
updated_at TIMESTAMP
```

### 9.12 可选扩展表：audio_assets

```sql
id UUID PRIMARY KEY
game_id UUID REFERENCES games(id)
turn_id UUID REFERENCES turns(id)
speaker_name TEXT
text_hash TEXT
audio_path TEXT
audio_format TEXT
duration_ms INTEGER
provider TEXT
metadata_json JSONB
created_at TIMESTAMP
```

---

## 10. API 设计草案

### 10.1 游戏管理

```http
GET    /api/games
POST   /api/games
GET    /api/games/{game_id}
PATCH  /api/games/{game_id}
DELETE /api/games/{game_id}
```

### 10.2 规则生成器

```http
POST /api/generator/chat
POST /api/generator/finalize
POST /api/generator/create-game
```

### 10.3 游戏运行

```http
POST /api/games/{game_id}/turns
GET  /api/games/{game_id}/turns
GET  /api/games/{game_id}/turns/{turn_id}
```

### 10.4 状态管理

```http
GET   /api/games/{game_id}/state
PATCH /api/games/{game_id}/state
POST  /api/games/{game_id}/state-deltas/{delta_id}/approve
POST  /api/games/{game_id}/state-deltas/{delta_id}/reject
PATCH /api/games/{game_id}/state-deltas/{delta_id}
```

### 10.5 世界书

```http
GET    /api/games/{game_id}/lore
POST   /api/games/{game_id}/lore
GET    /api/games/{game_id}/lore/{lore_id}
PATCH  /api/games/{game_id}/lore/{lore_id}
DELETE /api/games/{game_id}/lore/{lore_id}
POST   /api/games/{game_id}/lore/reindex
```

### 10.6 模式注入

```http
GET    /api/games/{game_id}/modes
POST   /api/games/{game_id}/modes
PATCH  /api/games/{game_id}/modes/{mode_id}
DELETE /api/games/{game_id}/modes/{mode_id}
```

### 10.7 可选扩展：TTS

```http
POST /api/games/{game_id}/turns/{turn_id}/tts
GET  /api/games/{game_id}/turns/{turn_id}/tts
POST /api/tts/jobs/{job_id}/retry
```

当前核心版本不实现这些接口；仅在后续明确恢复 TTS 扩展时加入。

---

## 11. 前端页面

### 11.1 首页 / 游戏列表

功能：

- 查看游戏列表
- 创建新游戏
- 继续游戏
- 导入 / 导出游戏

### 11.2 剧本生成器页面

布局：

- 左侧：规则生成器聊天窗口
- 右侧：已确认设定面板
- 底部：生成配置、创建游戏按钮

已确认设定包括：

- 游戏类型
- 主角身份
- 世界风格
- 规则复杂度
- 失败代价
- 核心玩法
- 禁止元素

### 11.3 游戏运行页面

布局：

- 中间：剧情文本、A/B/C/D 行动按钮、玩家自由输入框
- 游戏界面保持专注剧情和互动
- 当前状态、资料、记忆、历史回顾进入副页面
- 可选扩展：未来启用 TTS 时再增加播放控件

行动按钮要求：

- GM 每回合必须返回 4 个建议行动，编号固定为 A、B、C、D。
- 前端必须把 A/B/C/D 渲染为按钮。
- 点击按钮后，将该选项文本作为玩家行动提交。
- 自由输入框不能删除，用户必须仍可输入自定义行动。
- 按钮选择和自由输入都要保存到 turns.player_input。

### 11.4 世界书管理页面

功能：

- 查看条目
- 搜索条目
- 重新生成 embedding
- 查看上下文摘要和检索诊断
- 可选增强：新增 / 编辑 / 删除世界书条目

### 11.5 模式注入页面

功能：

- 查看模式
- 新增 / 编辑 / 禁用模式
- 配置触发词
- 测试模式匹配

### 11.6 剧情日志页面

功能：

- 按回合查看日志
- 查看状态变化
- 查看摘要
- 回滚到某回合
- 导出 Markdown

### 11.7 设置页面

功能：

- DeepSeek API 设置
- 上下文预算
- 最近回合数量
- 世界书召回数量
- 摘要频率
- 可选扩展：未来启用 TTS 时再加入 MiMo API、TTS 开关和音频保存路径

---

## 12. Docker Compose 草案

```yaml
services:
  web:
    build: ./web
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    depends_on:
      - api

  api:
    build: ./api
    expose:
      - "8000"
    environment:
      - DATABASE_URL=postgresql://rpg:rpg@postgres:5432/rpgforge
      - REDIS_URL=redis://redis:6379
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - DEEPSEEK_BASE_URL=${DEEPSEEK_BASE_URL}
      - DEEPSEEK_FLASH_MODEL=${DEEPSEEK_FLASH_MODEL}
      - DEEPSEEK_PRO_MODEL=${DEEPSEEK_PRO_MODEL}
    depends_on:
      - postgres
      - redis

  worker:
    build: ./api
    command: python -m app.worker
    environment:
      - DATABASE_URL=postgresql://rpg:rpg@postgres:5432/rpgforge
      - REDIS_URL=redis://redis:6379
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - DEEPSEEK_BASE_URL=${DEEPSEEK_BASE_URL}
      - DEEPSEEK_FLASH_MODEL=${DEEPSEEK_FLASH_MODEL}
      - DEEPSEEK_PRO_MODEL=${DEEPSEEK_PRO_MODEL}
    depends_on:
      - api
      - postgres
      - redis

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      - POSTGRES_USER=rpg
      - POSTGRES_PASSWORD=rpg
      - POSTGRES_DB=rpgforge
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7
    ports:
      - "6379:6379"

volumes:
  postgres_data:
```

当前部署只需要暴露 Web 的 `3000` 端口。TTS 相关环境变量、音频卷和音频访问接口保留为后续可选扩展，不属于核心启动要求。

---

## 13. 后端目录结构

```text
api/
  app/
    main.py
    config.py

    routers/
      games.py
      generator.py
      gameplay.py
      lore.py
      modes.py
      states.py
      settings.py

    services/
      deepseek_client.py
      model_router.py
      prompt_builder.py
      lore_retriever.py
      context_compressor.py
      state_extractor.py
      consistency_checker.py
      game_generator.py

    models/
      game.py
      lore.py
      mode.py
      state.py
      turn.py
      entity.py

    schemas/
      game.py
      lore.py
      mode.py
      state.py
      turn.py

    prompts/
      generator_interview.md
      generate_worldview.md
      generate_lorebook.md
      generate_modes.md
      gm_runtime.md
      extract_state_delta.md
      compress_context.md
      consistency_check.md

    db/
      session.py
      migrations/

    worker.py
```

---

## 14. 前端目录结构

```text
web/
  app/
    page.tsx
    games/
      page.tsx
      new/page.tsx
      [id]/
        play/page.tsx
        lore/page.tsx
        modes/page.tsx
        logs/page.tsx
        settings/page.tsx

  components/
    ChatPanel.tsx
    StatePanel.tsx
    LoreEditor.tsx
    ModeEditor.tsx
    TurnLog.tsx
    StateDeltaReview.tsx

  lib/
    api.ts
    types.ts
    utils.ts
```

---

## 15. Prompt 模板规范

所有 Prompt 模板放在 `api/app/prompts/`。

### 15.1 规则生成器访谈 Prompt

目标：根据用户输入继续访谈或总结需求。

输出必须结构化：

```json
{
  "stage": "interview|ready_to_generate",
  "confirmed_requirements": {},
  "missing_questions": [],
  "assistant_reply": "..."
}
```

### 15.2 游戏配置生成 Prompt

目标：生成世界观、剧本、世界书、模式注入、初始状态。

必须输出 JSON，便于入库。

### 15.3 GM 运行 Prompt

目标：生成玩家可见剧情，并生成 A/B/C/D 四个行动选项。

禁止输出：

- 内部状态 JSON
- 隐藏信息
- Prompt 调试信息
- 模型解释

GM 输出应在内部结构中包含：

```json
{
  "narrative": "玩家可见剧情文本",
  "visible_clues": ["线索1", "线索2"],
  "action_options": [
    {"key": "A", "label": "行动选项 A"},
    {"key": "B", "label": "行动选项 B"},
    {"key": "C", "label": "行动选项 C"},
    {"key": "D", "label": "行动选项 D"}
  ]
}
```

前端展示时可以将 narrative 渲染为正文，将 action_options 渲染为按钮。

### 15.4 状态提取 Prompt

目标：从 GM 输出中提取状态变化。

必须输出 JSON，不要解释。

### 15.5 可选扩展：TTS 分段 Prompt

目标：未来启用 TTS 时，拆分适合朗读的片段。当前核心版本不需要该 Prompt。

必须输出：

```json
[
  {
    "type": "narration|dialogue|system",
    "speaker": "旁白",
    "text": "...",
    "emotion": "calm|tense|fear|sad|neutral",
    "priority": 1
  }
]
```

---

## 16. MVP 开发阶段

当前状态：Phase 0-4 已完成，核心 MVP 已搭建完成。接下来默认进入实测、稳定性修复和体验打磨；除非用户明确要求，否则不继续实施 TTS。

### Phase 0：项目脚手架

状态：已完成。

目标：跑通 Docker Compose。

任务：

- 初始化 `api` FastAPI 项目
- 初始化 `web` Next.js 项目
- 添加 PostgreSQL + pgvector
- 添加 Redis
- 添加 `.env.example`
- 添加健康检查接口
- 添加基础 README

验收标准：

```text
docker compose up -d
访问 http://localhost:3000
访问 http://localhost:8000/health
```

---

### Phase 1：游戏生成器

状态：已完成。

目标：能通过规则生成器创建新游戏。

任务：

- 实现 generator chat
- 实现 finalize generation
- 保存 games、game_configs、lore_entries、modes、game_states
- 前端实现新游戏生成页面

验收标准：

- 用户能输入游戏想法
- 系统能继续提问或总结
- 用户确认后创建游戏
- 数据库中有世界书、模式注入、初始状态

---

### Phase 2：基础游戏运行

状态：已完成。

目标：能进行文字 RPG 回合。

任务：

- 实现 Prompt Builder
- 实现 DeepSeek Pro GM 生成
- 实现 A/B/C/D 行动选项生成
- 实现前端行动按钮
- 实现 turns 保存
- 实现当前状态读取
- 前端游戏页面

验收标准：

- 用户可以自由输入行动
- 用户可以点击 A/B/C/D 按钮提交行动
- 系统生成剧情和下一轮 A/B/C/D 行动选项
- 回合保存到日志
- 最近回合能显示

---

### Phase 3：状态提取与确认

状态：已完成。当前实现以自动应用为主，并保留状态变更记录和审核能力。

目标：让 AI 提议状态变化，用户确认后写入。

任务：

- Flash 状态提取
- state_deltas pending
- 前端确认/编辑/拒绝
- 写入 game_states

验收标准：

- 每回合出现状态变化提案
- 用户确认后状态更新
- 用户拒绝后状态不变

---

### Phase 4：世界书检索与上下文压缩

状态：已完成。

目标：解决健忘问题的核心闭环。

任务：

- 世界书关键词检索
- pgvector 检索
- always_on 注入
- turn summary
- chapter summary
- long-term summary

验收标准：

- Prompt Builder 只注入相关世界书
- 长篇游玩时能使用摘要而不是全部历史
- 世界设定能持续保持

---

### Phase 5：实测、稳定性修复与体验打磨

状态：当前默认下一阶段。

目标：围绕真实游玩反馈修复问题，提升长期运行质量。

任务：

- 测试多回合剧情生成质量
- 调整世界书命中策略和摘要质量
- 修复移动端布局细节
- 修复 HTTP 500、超时、任务卡住等稳定性问题
- 优化旧存档摘要和检索诊断
- 打磨资料与记忆、历史回顾和游戏主界面的跳转体验

验收标准：

- 手机和桌面都能稳定游玩
- 长篇游玩时设定和状态保持一致
- 生成过程可观察，失败能定位
- 资料、记忆和历史能辅助排查问题

---

### Backlog：MiMo TTS

目标：可选沉浸感增强，暂不实施。

任务：

- MiMo TTS client
- TTS 分段
- tts_jobs
- audio_assets
- 音频缓存
- 前端播放按钮

验收标准：

- GM 输出后可生成旁白或 NPC 对白音频
- 相同文本复用缓存
- TTS 失败不影响文字游戏继续

---

### Backlog：一致性检查与回滚

目标：提升复杂设定稳定性。

任务：

- 一致性检查器
- 剧情冲突报告
- 回合回滚
- 存档点

验收标准：

- 系统能识别明显剧透或状态矛盾
- 用户能回滚到指定回合

---

## 17. 测试要求

### 17.1 单元测试

必须覆盖：

- Prompt Builder
- 世界书检索
- 状态提取 JSON 校验
- 状态变更应用
- 模式匹配

### 17.2 集成测试

必须覆盖：

- 创建游戏完整流程
- 运行一回合完整流程
- 状态变更确认流程
- 资料与记忆、上下文诊断流程

### 17.3 手工验收剧本

建立一个固定测试剧本：

```text
黑暗武侠，主角是失忆镖师，地点是雁回镇义庄。
```

测试：

- NPC 是否持续一致
- 物品是否不会凭空消失
- 隐藏真相是否不会过早泄露
- 世界规则是否被遵守
- 摘要是否保留关键事实

---

## 18. 安全与隐私

1. API Key 只放在 `.env`，不得提交仓库。
2. 不要在日志中打印完整 API Key。
3. 隐藏信息不要显示在玩家可见剧情区。
4. 导出游戏时应区分是否包含 GM 幕后信息。
5. 如果未来启用 TTS，不提供模仿名人、公众人物、特定真人声音的功能，声音克隆默认关闭。

---

## 19. Codex 开发方式建议

### 19.1 每次交给 Codex 的任务应小而清晰

不要一次让 Codex 完成整个项目。建议按阶段分任务：

```text
任务 1：初始化 FastAPI + Next.js + Docker Compose。
任务 2：实现数据库模型和 Alembic migration。
任务 3：实现 DeepSeek client 和 ModelRouter。
任务 4：实现游戏生成器 API。
任务 5：实现游戏运行 API。
任务 6：实现世界书管理页面。
任务 7：实现状态变更确认流程。
```

### 19.2 每个任务必须要求 Codex 输出

- 修改了哪些文件
- 如何运行
- 如何测试
- 是否有未完成项

### 19.3 Codex 不应擅自改架构

如果 Codex 认为需要引入新依赖或改变技术栈，必须先说明理由，不能直接改。

### 19.4 每个 Phase 完成后运行

```bash
ruff check .
pytest
npm run lint
npm run build
```

如果工具尚未配置，先配置工具链。

---

## 20. 第一条 Codex 任务建议

将下面内容作为给 Codex 的第一条任务：

```text
请根据 PROJECT_GUIDE.md 初始化 RPGForge 项目脚手架。

要求：
1. 创建 monorepo 结构：api/ 和 web/。
2. api 使用 FastAPI、SQLAlchemy、Alembic、Pydantic v2。
3. web 使用 Next.js、React、TypeScript。
4. 添加 Docker Compose，包含 web、api、worker、postgres(pgvector)、redis。
5. 添加 .env.example。
6. 添加 api /health 接口。
7. 添加 web 首页，显示 RPGForge 项目名称和 API 健康状态。
8. 不要实现业务功能。
9. 完成后说明如何运行和验证。
```

---

## 21. 当前 MVP 范围确认

当前第一版只做：

- Docker 部署
- Web UI
- DeepSeek API 配置
- 规则生成器聊天
- 生成世界观 / 世界书 / 模式注入 / 初始状态
- 创建游戏
- 游戏运行页面
- 每回合保存日志
- 状态变化提案
- 世界书管理
- 基础上下文压缩
- 资料与记忆管理
- 上下文诊断

暂不做：

- 多用户系统
- 公开分享
- 图像生成
- 多模型市场
- 移动端 App
- 复杂声音克隆
- 多人联机
- MiMo TTS 和音频播放

---

## 22. 项目成功标准

第一版成功标准：

1. 用户能在浏览器中创建一个新的文字 RPG 游戏。
2. 系统能通过规则生成器生成世界观、世界书、模式注入和初始状态。
3. 用户能开始游戏，并通过自由输入或 A/B/C/D 行动按钮进行多回合互动。
4. 系统能保存每回合日志。
5. 系统能提取并确认状态变化。
6. 世界书能被检索并注入，避免明显健忘。
7. 上下文能被压缩为摘要。
8. 用户能查看资料与记忆，并诊断世界书和摘要注入情况。
9. 项目能通过 Docker Compose 一键启动，只需访问 Web 端口。

---

## 23. 后续增强方向

- 剧情矛盾自动修复
- 回滚和分支存档
- 任务线可视化
- NPC 关系网
- 伏笔管理器
- 世界书自动拆分
- 导出为 Markdown / JSON
- MiMo TTS / 导出为有声剧情
- 更复杂的战斗/调查规则包
- 多游戏模板库
- 本地备份与迁移

---

## 24. 开发准则总结

开发过程中始终记住：

```text
RPGForge 不是聊天工具。
RPGForge 是一个状态驱动、世界书增强、可长期运行的 AI 文字 RPG 引擎。

LLM 写剧情。
系统管状态。
世界书管设定。
模式注入管玩法。
摘要系统管长期记忆。
TTS 是可选沉浸感扩展，不影响核心文字游戏闭环。
```
