# AI Story Runtime Guide

本文说明 RPGForge 当前 AI 剧情运行链路，以及外部 AI 写剧本时应遵守的 `story_settings v2` 结构。

当前设计方向是**纯叙事化 RPG**：系统不再维护玩家可见的等级、经验、属性、技能熟练度、关系分数、骰子判定、危机条或压力时钟。长期一致性依赖文字化状态、剧本锚点、导演层决策、输出观测和后台维护。

## 1. 核心数据源

### 1.1 story_settings v2

`story_settings` 是每局游戏最重要的持久剧本源。它保存在 `game_configs.story_settings`，由生成器、导入器、设定编辑页和模块合并流程共同维护。

主要结构：

- `game_profile`：标题、题材、简介等游戏外壳。
- `worldview`：世界观、地点、势力、公开事实和隐藏事实。
- `story_core`：核心幻想、主线目标、情绪弧、文风、禁止漂移方向。
- `core_characters`：主角、NPC、身份、动机、公开信息和隐藏信息。
- `act_plan`：分幕结构、目标、完成锚点、允许/禁止揭露、转幕目标。
- `main_quest_path`：玩家可见或半可见的主线节点。
- `core_mechanics`：非数值化的长期规则，告诉 GM 这个世界如何运转。
- `action_style_rules`：按玩家输入匹配的行动风格规则。
- `story_material_library`：可召回的剧情素材、线索、地点、秘密、人物资料。
- `home_base`：据点、后台、基地或其他可反复返回的叙事空间。
- `hard_rules`：最高优先级的必须遵守、绝对禁止、揭露和连续性规则。
- `generation_parameters`：篇幅、段落、近期回合摘录等软参考。

外部 AI 写剧本时，应以 `/api/generator/authoring-kit` 导出的创作包为准。

### 1.2 runtime_story

`runtime_story` 是后端从 `story_settings` 和当前状态构造出的运行视图，核心入口在 `api/app/services/story_settings.py`。

使用方：

- StoryDirector 使用完整运行视图，决定本回合该怎么推进。
- GM 使用裁剪后的运行视图，不看到未来幕的详细内容。
- StateExtractor 使用状态维护投影，只拿与锚点、任务、素材和连续性相关的必要字段。
- Drift/观测类逻辑使用运行视图做一致性检查，不直接改写剧本设定。

### 1.3 state_json 与 state_v2

`state_json` 是持久运行状态；`state_v2` 是系统派生的结构化视图，入口在 `api/app/services/state_v2.py`。

当前保留的玩家侧状态类型：

- 当前场景：回合、时间、地点、在场 NPC、文字化处境压力。
- 主角档案：姓名、身份、文字化处境。
- conditions：中毒、受伤、被通缉等处境，全部使用文字 status/note。
- relationships：NPC 对主角的态度变化，全部使用文字 status/note。
- quest_log：任务当前状态。
- open_threads：未解线索和已解决线索。
- story_progress：当前幕、已完成锚点、转幕历史、结局状态。
- npc_registry：NPC 身份、状态、位置和态度。

## 2. 一回合生成流程

玩家提交行动后，后端的大致链路如下：

```text
玩家输入
  -> 结算待处理状态 delta
  -> 选择 action_style_rules
  -> 召回 story_material_library
  -> 加载 memory_summaries
  -> 构造 state_v2 与 runtime_story
  -> StoryDirector 产出导演决策
  -> PromptBuilder 组装 GM system/user payload
  -> GM Runtime 生成 narrative + A/B/C/D
  -> OutputObserver 做确定性观测
  -> 命中当前幕禁止揭露整串时，做一次最小化重写
  -> 写入 Turn
  -> StateExtractor 提取文字化状态 delta
  -> StateApplier 应用状态并重建 state_v2
  -> ContextCompressor 更新摘要
```

同步回合接口会在请求路径内完成状态提取。异步 job 路径会先把回合返回给前端，再由 turn maintenance job 在后台执行状态提取、状态应用、上下文压缩和审计。

## 3. StoryDirector

入口：`api/app/services/story_director.py`
Prompt：`api/app/prompts/story_director.md`

StoryDirector 不写正文。它只输出本回合导演决策：

- `player_intent`
- `current_act`
- `scene_objective`
- `mode_recommendation`
- `allowed_reveals`
- `forbidden_reveals`
- `pacing_limit`
- `gm_instruction`
- `risk_note`
- `cost_if_fails`

当前设计没有骰子和成功率。`risk_note` / `cost_if_fails` 用来告诉 GM：这个行动有什么风险、失败时会有什么叙事代价。GM 再按剧情逻辑写出“是，但...”或“否，但...”的后果。

## 4. act_pacing

入口：`api/app/services/act_pacing.py`

`act_pacing` 是确定性节奏信号，不写状态。它根据当前回合、上次锚点进展回合、当前幕未完成 required 锚点计算：

- `pressure`: `low` / `rising` / `high` / `ready`
- `turns_in_act`
- `turns_since_anchor`
- `next_required_anchor`

当 pressure 为 `rising` 或 `high` 时：

- StoryDirector 应明显把 scene objective 收拢到下一个 required 锚点。
- GM 的 A/B/C/D 至少留一条能推进锚点的行动选项。

这用于避免玩家长期停留在准备、休整、训练或原地调查循环里。

## 5. GM Runtime

入口：`api/app/services/gameplay.py`
Payload 构造：`api/app/services/prompt_builder.py`
Prompt：`api/app/prompts/gm_runtime.md`

GM 的输出结构固定：

```json
{
  "narrative": "玩家可见剧情文本",
  "visible_clues": ["本回合玩家可见线索"],
  "action_options": [
    {"key": "A", "label": "具体行动选项 A"},
    {"key": "B", "label": "具体行动选项 B"},
    {"key": "C", "label": "具体行动选项 C"},
    {"key": "D", "label": "具体行动选项 D"}
  ]
}
```

GM 必须遵守：

- 不输出内部 JSON、状态结算、调试信息或隐藏事实。
- 不在正文里输出 XP、技能、关系分数、危机值等数值机制。
- 先回应玩家本次行动的直接结果，再引出新压力。
- 使用剧情内动作、感官、对白和代价来体现风险。
- 不把召回素材当作必须逐条塞进正文的清单。

## 6. OutputObserver 与禁止揭露兜底

入口：`api/app/services/output_observer.py`

OutputObserver 只做确定性观测，结果写入 telemetry，不直接决定剧情质量。它会记录例如：

- 字数与格式观测。
- 是否疑似重复上一回合开头。
- 当前幕 forbidden reveals 是否被整串命中。
- 行动选项是否符合基本结构。

同步强改写只保留一个极窄兜底：如果 GM 正文整串命中当前幕禁止提前揭露的内容，系统会让 GM 做一次最小化重写，只删除或改写提前揭露部分。其他偏离由后台审计和 trace 观察处理。

## 7. StateExtractor

入口：`api/app/services/state_extractor.py`
Prompt：`api/app/prompts/extract_state_delta.md`

StateExtractor 只提取已经在 GM 输出中明确发生的变化。它不创作剧情，也不推断隐藏真相。

当前 delta 类型包括：

- `time_delta` / `time_current`
- `location_change`
- `inventory_add` / `inventory_remove`
- `npc_updates`
- `quest_updates`
- `faction_updates`
- `protagonist_updates`
- `variable_updates`
- `new_known_facts`
- `new_hidden_facts`
- `open_thread_updates`
- `condition_updates`
- `relationship_events`
- `story_progress_update`

已删除的旧数值字段不属于标准 delta 契约。

锚点推进完全依赖 `story_progress_update.completed_anchors`。如果 GM 文本已经明确满足当前幕 completion signal，Extractor 必须写入对应锚点 id；否则当前幕不会推进。

失败结局使用 `story_progress_update.defeat = true`，只在主角旅程已不可挽回地失败时上报。普通挫折、受伤、暂时被俘应写成 condition，而不是 defeat。

## 8. StateApplier

入口：`api/app/services/state_applier.py`

StateApplier 将 delta 应用到持久状态，并派生新的 `state_v2`。它负责：

- 更新时间和地点。
- 合并 NPC、任务、势力、物品、事实和线索。
- 合并文字化 conditions 与 relationships。
- 标记完成锚点、转幕、胜利或失败结局。
- 同步主线任务和开放线索状态。

StateApplier 不处理等级、经验、技能熟练度、属性检定或关系分数。

## 9. ContextCompressor

入口：`api/app/services/context_compressor.py`
Prompt：`api/app/prompts/compress_context.md`

ContextCompressor 维护长期记忆、近期摘要和叙事连续性摘要。GM 使用这些摘要承接长局语气、人物关系和关键事实，但不能把摘要逐条复述为本回合新进展。

## 10. Trace、审计与调试

所有 LLM 调用会记录到 `agent_traces`，包括 prompt、输出、模型、token、latency 和错误信息。管理页和 admin API 可用于排查：

- StoryDirector 是否给出有效风险和锚点推进方向。
- GM 是否忽视 `act_pacing` 或 `risk_note`。
- StateExtractor 是否漏报 completed anchors。
- OutputObserver 是否持续报重复、格式或禁止揭露 flags。
- 后台 drift 审计是否显示长期偏离趋势。

## 11. 外部 AI 写剧本的最低要求

外部 AI 产出的 JSON 至少应包含：

- `format_version`
- `game_profile.title`
- `story_core.main_goal`
- 至少一个 `act_plan`，且每幕有明确 completion anchors。
- `core_characters` 中至少有主角和关键 NPC。
- `hard_rules` 中写清必须遵守与绝对禁止。

导入端点会做归一化和基础校验，但弱剧本仍可能导致游玩时缺少锚点、缺少冲突或缺少转幕抓手。创作包里的 warnings 应在创建游戏前处理。
