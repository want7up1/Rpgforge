# AI Story Runtime Guide

本文说明 RPGForge 当前 AI 架构中两件事：

1. 游玩时，AI 生成剧情依据什么。
2. 创建世界时，系统会生成并保存哪些设定。

RPGForge 不是普通聊天应用。它的核心设计是：LLM 负责叙事和结构化提案，后端负责剧本约束、世界书、状态、记忆、任务队列和持久化。

## 1. 剧情生成流程

玩家在游戏中提交行动后，后端会按下面流程生成新回合：

```text
玩家输入
  -> 选择当前模式 selected_mode
  -> 检索世界书 related_lore
  -> 加载长期/章节/近期记忆 memory_summaries
  -> StoryDirector 生成本回合导演决策
  -> GM Runtime 生成玩家可见剧情和 A/B/C/D 选项
  -> DriftValidator 按需校验是否偏离剧本
  -> StateExtractor 提取状态变化
  -> StateApplier 更新结构化状态
  -> ContextCompressor 定期压缩长期记忆
```

其中 GM Runtime 是正式写剧情的模型调用。它不会只依赖聊天历史，而是读取结构化上下文。

## 2. GM 生成剧情依据

GM Runtime 的主要输入来自 `api/app/services/prompt_builder.py`。

### 2.1 story_director

`story_director` 是本回合导演层输出，来自 `api/app/services/story_director.py`。

它告诉 GM：

- 玩家这次行动的真实意图。
- 当前幕或当前阶段。
- 本回合场景目标。
- 建议使用的模式。
- 本回合真正应该使用的世界书标题。
- 本回合允许揭露的信息。
- 本回合禁止提前揭露的信息。
- 危机升级上限。
- 需要保持一致的人物、地点、状态和关系。
- 给 GM 的简短执行指令。

GM prompt 明确要求优先落实 `story_director.scene_objective`、`forbidden_reveals`、`pacing_limit` 和 `gm_instruction`。

### 2.2 campaign_contract

`campaign_contract` 是长期强约束。

它通常来自 `script_outline.campaign_contract`，并可能合并 `director_contract` 和 `story_contract`。

建议放入：

- 本局核心幻想。
- 贯穿全剧的核心悬念。
- 情绪弧线。
- 必须保留的用户要求。
- 禁止变成的方向。
- 禁止跑偏方向。
- 专有名词。
- 节奏规则。
- 当前幕 ID。
- 机制契约。

如果某个设定绝对不能被 AI 忘记，优先放进 `campaign_contract.must_preserve`、`campaign_contract.must_not_become` 或 `campaign_contract.forbidden_drift`。

### 2.3 story_blueprint

`story_blueprint` 是从完整 `script_outline` 中抽取出来的运行时剧本蓝图，来自 `api/app/services/story_blueprint.py`。

它会提供：

- `user_brief`：用户创作简报。
- `central_question`：核心悬念。
- `main_goal`：主线目标。
- `current_act`：当前幕目标、压力、允许揭露、禁止揭露、升级上限。
- `truth_map`：幕后真相和揭露条件。
- `clue_ladder`：线索阶梯。
- `pressure_clock`：压力时钟。
- `mechanics_contract`：核心机制规则。
- `worldview`：世界观摘要、基调、核心冲突。
- `forbidden_public_spoilers`：禁止公开剧透。

GM Runtime 不再直接吃完整 `script_outline`，而是吃 `story_blueprint`。这样可以减少 token，同时保留运行时真正需要的剧本控制信息。

### 2.4 current_state_v2

`current_state_v2` 是当前结构化状态视图。

它包括：

- 当前回合数。
- 当前时间和地点。
- 主角状态。
- 任务。
- NPC。
- 阵营。
- 物品。
- 技能、能力、状态、关系。
- 已知事实。
- 隐藏事实。
- 未解线索和开放线程。

GM 应遵守当前状态，不能让物品、NPC、地点、时间线凭空变化。

### 2.5 always_on_lore

`always_on_lore` 是常驻世界书。

适合放：

- 核心世界规则。
- 主角身份规则。
- 必须长期遵守的机制。
- 当前章节必须一直记住的地点、NPC、阵营、诅咒、限制。

常驻世界书会按优先级排序，最多注入一部分高优先级条目。

### 2.6 related_lore

`related_lore` 是本回合按玩家输入、当前模式、近期回合、状态和 story blueprint 检索出来的世界书。

检索依据包括：

- 玩家输入。
- 游戏标题、题材、简介。
- 当前模式。
- 当前状态。
- story blueprint 中的目标、线索、压力、机制。
- 最近回合。
- 世界书关键词、触发词和本地向量。

GM prompt 要求只使用本回合召回的 `related_lore`，不要随意使用未召回的世界书细节。

### 2.7 memory_summaries

`memory_summaries` 是长期记忆摘要。

包括：

- `long_term`：长期摘要。
- `chapter`：章节摘要。
- `recent_turn_summaries`：最近回合摘要。

它用于减少对完整聊天历史的依赖。

### 2.8 recent_turns

`recent_turns` 是最近回合上下文。

当前为了节省 token，它不再传完整 `gm_output`，而是传：

- `turn_number`
- `player_input`
- `visible_summary`
- `hidden_summary`
- `gm_output_excerpt`
- `action_options`

`gm_output_excerpt` 是短片段，只用于承接最近画面。长期一致性主要依赖 `memory_summaries` 和结构化状态。

### 2.9 selected_mode

`selected_mode` 是当前触发的模式注入。

常见模式：

- 主线模式
- 调查模式
- 社交模式
- 探索模式
- 战斗模式
- 潜行模式

模式用于告诉 GM 当前场景应该采用什么玩法规则和叙事策略。

### 2.10 player_input

`player_input` 是玩家本回合行动。

GM 必须先回应玩家行动的直接结果，再引出新压力。不能跳过玩家行动直接升级主线。

## 3. 世界生成时会生成哪些设定

创建世界主要由 `GameGeneratorService.finalize_stream` 完成。

流程是：

```text
用户概念和访谈结果
  -> generate_config_outline.md 生成导演总纲
  -> generate_config_section.md 并行生成角色、世界书、模式、初始状态、规则
  -> 后端合并为 GeneratedGameConfig
  -> create_game_from_config 落库
```

最终结构是 `GeneratedGameConfig`。

### 3.1 基础信息

字段：

- `title`
- `genre`
- `description`

用途：

- 展示游戏。
- 给检索和 GM 提供题材上下文。

### 3.2 worldview

世界观字段。

建议包含：

- `summary`
- `tone`
- `setting`
- `core_conflicts`

用途：

- 给 GM 提供世界基调。
- 给 story blueprint 提供世界摘要。
- 给检索提供背景词。

### 3.3 script_outline

剧本骨架。

这是整个剧情控制的主容器。推荐包含：

- `title`
- `user_brief`
- `acts`
- `campaign_contract`
- `truth_map`
- `clue_ladder`
- `pressure_clock`
- `mechanics_contract`
- `forbidden_public_spoilers`

注意：运行时 GM 不直接吃完整 `script_outline`，而是通过 `campaign_contract` 和 `story_blueprint` 使用其中关键内容。

### 3.4 user_brief

用户创作简报。

推荐结构：

```json
{
  "story_background": "故事背景",
  "core_premise": "核心设定和主角处境",
  "must_include": ["必须出现的内容"],
  "forbidden_content": ["禁止出现或禁止偏离的内容"],
  "playstyle_preferences": ["玩法偏好"],
  "tone_preferences": ["风格偏好"],
  "raw_user_input": "用户原始输入"
}
```

用途：

- 保护用户原始意图。
- 后端会把 `must_include` 合并进 `campaign_contract.must_preserve`。
- 后端会把 `forbidden_content` 合并进 `campaign_contract.must_not_become` 和 `forbidden_drift`。

### 3.5 campaign_contract

战役契约。

推荐结构：

```json
{
  "premise": "本局最核心的剧本承诺",
  "player_fantasy": "玩家想体验的核心幻想",
  "central_question": "贯穿全剧的核心悬念",
  "emotional_arc": "情绪弧线",
  "must_preserve": ["必须保留的设定"],
  "must_not_become": ["禁止变成的方向"],
  "tone_do": ["必须保持的味道"],
  "tone_dont": ["不能滑向的味道"],
  "relationship_arcs": [],
  "forbidden_drift": ["禁止跑偏方向"],
  "canon_terms": ["专有名词"],
  "pacing_rules": ["节奏规则"],
  "current_act": "act_1"
}
```

用途：

- 约束长期剧情方向。
- 防止 AI 把故事变成另一种题材。
- 防止提前进入终局、世界级危机、新组织、新 Boss。
- 保护用户要求。

### 3.6 acts

幕结构。

推荐结构：

```json
{
  "id": "act_1",
  "name": "第一幕名称",
  "objective": "玩家本幕目标",
  "dramatic_question": "本幕核心戏剧问题",
  "pressure": "本幕主动逼近玩家的压力",
  "must_hit_beats": ["必须发生或铺垫的节点"],
  "allowed_reveals": ["本幕允许揭露的信息"],
  "forbidden_reveals": ["本幕不能提前揭露的信息"],
  "relationship_turn": "本幕关键关系变化",
  "escalation_limit": "本幕危机升级上限",
  "completion_signal": "进入下一幕的条件"
}
```

用途：

- StoryDirector 用它判断当前幕目标。
- GM 用它控制揭露节奏。
- DriftValidator 用它判断是否跑偏。

### 3.7 truth_map

真相地图。

推荐结构：

```json
{
  "truth": "GM 知道的幕后真相",
  "public_mask": "玩家初期看到的表象",
  "reveal_condition": "允许揭露的条件"
}
```

用途：

- 记录幕后真相。
- 防止 GM 忘记主线。
- 配合 `clue_ladder` 控制逐步揭露。

注意：不要把真相地图直接写进玩家公开简介或 `known_facts`。

### 3.8 clue_ladder

线索阶梯。

推荐结构：

```json
{
  "stage": "第一层线索",
  "clue": "玩家可发现的线索",
  "points_to": "线索指向的人、地点、物件或矛盾",
  "do_not_reveal": "此阶段不能直接说出的真相"
}
```

用途：

- 调查玩法的核心依据。
- 防止 AI 一次性揭露答案。
- 给每回合提供可验证发现。

### 3.9 pressure_clock

压力时钟。

推荐结构：

```json
{
  "name": "压力来源",
  "tick_condition": "何时推进",
  "consequence": "推进后的后果",
  "visibility": "public|mixed|gm_only"
}
```

用途：

- 让世界主动推进。
- 让玩家拖延或失败有代价。
- 给 GM 提供场景压力。

### 3.10 mechanics_contract

机制契约。

推荐结构：

```json
{
  "name": "机制名称",
  "rule": "必须长期遵守的规则",
  "progression": "阶段、数值或触发方式",
  "visibility": "public|mixed|gm_only"
}
```

用途：

- 约束成长、资源、判定、能力限制和失败代价。
- 世界书生成阶段会要求核心机制进入 lore entries。

### 3.11 characters

角色档案。

生成字段包括：

- `name`
- `aliases`
- `role`
- `identity`
- `description`
- `appearance`
- `visibility`
- `dramatic_function`
- `desire`
- `fear`
- `leverage`
- `relationship_arc`
- `public_limit`

用途：

- 创建角色档案。
- 给角色页面展示。
- 可从角色和世界书同步角色记录。

注意：角色公开档案不要写隐藏真相。

### 3.12 lore_entries

世界书。

生成字段包括：

- `title`
- `type`
- `keywords`
- `trigger_words`
- `priority`
- `always_on`
- `visibility`
- `public_info`
- `gm_secret`
- `content`
- `usage_note`

支持类型包括：

- `core_rule`
- `protagonist`
- `npc`
- `faction`
- `location`
- `item`
- `plot_hook`
- `mechanic`
- `secret`
- `clue`
- `pressure`
- `twist`

用途：

- `always_on=true` 的条目会常驻注入。
- 其他条目按关键词、触发词、本地向量和 story blueprint 检索。
- `gm_secret` 只给 GM 保持一致性，不能直接剧透。
- `usage_note` 告诉 GM 何时注入、如何给线索、不能揭露什么。

### 3.13 modes

模式注入。

生成字段包括：

- `name`
- `triggers`
- `injection`
- `priority`
- `enabled`

推荐至少包含：

- 主线模式
- 调查模式
- 社交模式
- 探索模式

题材需要时加入：

- 战斗模式
- 潜行模式
- 生存模式
- 解谜模式

用途：

- 根据玩家输入触发不同玩法规则。
- 例如调查模式要求给线索不给答案，社交模式要求遵守 NPC 欲望、恐惧和关系阶段。

### 3.14 initial_state

初始状态。

生成字段包括：

- `current_turn`
- `time`
- `location`
- `protagonist`
- `progression`
- `skills`
- `abilities`
- `conditions`
- `relationships`
- `inventory`
- `quests`
- `npcs`
- `factions`
- `variables`
- `known_facts`
- `hidden_facts`
- `open_threads`

用途：

- 初始化 `GameState`。
- 后续回合通过状态提取和状态应用更新。
- GM 通过 `current_state_v2` 读取当前状态。

注意：`initial_state` 只写开局已经成立的状态，不要写完整未来剧情计划。

### 3.15 system_prompt

系统规则。

用于补充本局 GM 的题材、基调和叙事规则。

注意：它不能覆盖 RPGForge 的全局输出契约。GM 仍必须输出 JSON，包含：

- `narrative`
- `visible_clues`
- `action_options`

## 4. 哪些设定最影响剧情稳定性

优先级从高到低：

1. `campaign_contract`
2. `story_blueprint.current_act`
3. `truth_map`
4. `clue_ladder`
5. `pressure_clock`
6. `current_state_v2`
7. `always_on_lore`
8. `related_lore`
9. `memory_summaries`
10. `recent_turns`

如果某个设定非常重要，不建议只写在正文描述里。应该至少放进以下之一：

- `campaign_contract.must_preserve`
- `campaign_contract.forbidden_drift`
- `campaign_contract.canon_terms`
- `acts.must_hit_beats`
- `acts.forbidden_reveals`
- `truth_map`
- `clue_ladder`
- `lore_entries`
- `initial_state.hidden_facts`

## 5. 推荐剧本输入模板

如果手动给 AI 提供剧本，推荐使用下面模板。

```json
{
  "title": "剧本标题",
  "genre": "题材类型",
  "description": "一句话简介",
  "worldview": {
    "summary": "世界观短摘要",
    "tone": "叙事基调",
    "setting": "初始舞台",
    "core_conflicts": ["核心冲突"]
  },
  "script_outline": {
    "title": "剧本标题",
    "user_brief": {
      "story_background": "故事背景",
      "core_premise": "核心设定和主角处境",
      "must_include": ["必须出现的内容"],
      "forbidden_content": ["禁止出现或禁止偏离的内容"],
      "playstyle_preferences": ["玩法偏好"],
      "tone_preferences": ["风格偏好"],
      "raw_user_input": "原始创作说明"
    },
    "campaign_contract": {
      "premise": "本局最核心的剧本承诺",
      "player_fantasy": "玩家想体验什么",
      "central_question": "贯穿全剧的核心悬念",
      "emotional_arc": "情绪弧线",
      "must_preserve": ["绝对要保留的设定"],
      "must_not_become": ["绝对不能变成的方向"],
      "forbidden_drift": ["禁止跑偏方向"],
      "canon_terms": ["专有名词"],
      "pacing_rules": ["节奏规则"],
      "current_act": "act_1"
    },
    "acts": [
      {
        "id": "act_1",
        "name": "第一幕名称",
        "objective": "玩家本幕目标",
        "dramatic_question": "本幕戏剧问题",
        "pressure": "本幕压力",
        "must_hit_beats": ["必须发生或铺垫的节点"],
        "allowed_reveals": ["允许揭露的信息"],
        "forbidden_reveals": ["不能提前揭露的信息"],
        "relationship_turn": "关键关系变化",
        "escalation_limit": "危机升级上限",
        "completion_signal": "进入下一幕的条件"
      }
    ],
    "truth_map": [
      {
        "truth": "GM 幕后真相",
        "public_mask": "玩家初期看到的表象",
        "reveal_condition": "允许揭露的条件"
      }
    ],
    "clue_ladder": [
      {
        "stage": "第一层线索",
        "clue": "玩家可发现的线索",
        "points_to": "线索指向什么",
        "do_not_reveal": "这一阶段不能直接说出的真相"
      }
    ],
    "pressure_clock": [
      {
        "name": "压力来源",
        "tick_condition": "什么时候推进",
        "consequence": "推进后的后果",
        "visibility": "public|mixed|gm_only"
      }
    ],
    "mechanics_contract": [
      {
        "name": "机制名称",
        "rule": "长期规则",
        "progression": "成长或触发方式",
        "visibility": "public|mixed|gm_only"
      }
    ],
    "forbidden_public_spoilers": ["不能公开剧透的真相"]
  }
}
```

## 6. 常见问题

### 6.1 为什么 AI 会跑偏？

常见原因：

- 强约束只写在普通描述里，没有进入 `campaign_contract`。
- 真相和线索没有拆成 `truth_map` 和 `clue_ladder`。
- 当前幕没有写 `forbidden_reveals` 和 `escalation_limit`。
- 关键世界规则没有写入 `always_on` 世界书。

### 6.2 为什么有些设定没有被使用？

可能原因：

- 世界书没有被召回。
- 没有关键词或触发词。
- `usage_note` 不清楚。
- 设定只在完整 `script_outline` 里，但没有进入 `campaign_contract` 或 `story_blueprint` 会抽取的字段。

### 6.3 如何避免提前剧透？

把秘密分别写入：

- `truth_map.truth`
- `truth_map.reveal_condition`
- `acts.forbidden_reveals`
- `clue_ladder.do_not_reveal`
- `forbidden_public_spoilers`
- `lore_entries.gm_secret`
- `initial_state.hidden_facts`

公开字段只写表象。

### 6.4 什么应该写进世界书？

适合写进 `lore_entries`：

- 核心地点。
- 关键 NPC。
- 重要阵营。
- 物品。
- 世界规则。
- 能力机制。
- 线索。
- 压力来源。
- 反转材料。

如果它需要在某些关键词出现时被召回，就应该写进世界书。

### 6.5 什么应该写进状态？

适合写进 `initial_state` 或后续状态：

- 当前地点。
- 当前时间。
- 主角身体/精神状态。
- 当前持有物品。
- 已接任务。
- NPC 当前态度。
- 已知事实。
- 隐藏事实。
- 未解线程。
- 技能、能力、关系、条件、经验。

状态描述的是“当前已经成立的事实”，不是未来剧情计划。

## 7. 实用建议

- 强约束写进 `campaign_contract`。
- 剧情结构写进 `acts`。
- 幕后真相写进 `truth_map`。
- 调查推进写进 `clue_ladder`。
- 主动压力写进 `pressure_clock`。
- 世界固定信息写进 `lore_entries`。
- 当前事实写进 `initial_state`。
- 禁止公开的信息同时写进 `forbidden_public_spoilers`、`forbidden_reveals`、`gm_secret` 或 `hidden_facts`。

这样 AI 在生成剧情时既能保留剧本丰富度，又能减少跑偏和提前剧透。
