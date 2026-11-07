# RPGForge 剧本创作包

> 把本文整篇连同你的剧情想法一起发给外部 AI（Claude / ChatGPT），让它产出一份 `story_settings` JSON，再回到 RPGForge「导入剧本」粘贴即可新建游戏。

---

# RPGForge 设定填写说明

> 这份文档是给创作者和 AI 使用的通用填写指南；它不是可导入 JSON。真正可导入的是同一页面导出的 `story_settings` JSON。

- JSON 格式版本：`rpgforge.story.v2`
- 导入生效范围：只覆盖剧本设定源 `story_settings`，不覆盖回合历史、当前状态、摘要或存档进度。

## 给 AI 的修改指令模板

把下面这段和导出的 JSON 一起发给 AI：

```text
你正在修改 RPGForge 的 story_settings v2 JSON。
请严格保持 JSON 是完整合法对象，format_version 必须是 rpgforge.story.v2。
可以完整修改世界观、核心人物、分幕主线、主线轨迹、核心机制、行动风格规则、剧本素材库、[地点]、强制规则和生成参数。
不要添加 initial_state、回合历史、当前状态、状态增量、结算回执、存档进度、摘要、任务版本或 AI 思考过程。
不要把隐藏真相写进 public_facts、public_info、player_visible、角色公开简介或 act_plan 的 title/objective；幕标题和目标会进入玩家目标栏。
所有数组条目请保留稳定 id；如果必须改 id，请同步修改引用它的 act_id、completion_anchor、trigger、quest 或素材关系。
completion_anchors 的剧情达成方式可以自由，但 required 条件是自动转幕的实际判定依据；completion_signal 必须是可从已发生剧情识别的明确事件。
同一幕同一 alternative_group 内的 required 锚点是 OR，不同组及未分组 required 锚点之间是 AND；required:false 不阻塞转幕。
全部必需条件被结算确认为完成后会自动转幕，transition_to_next_act.condition 不是额外的程序门。
main_quest_path 是软主线轨迹，允许玩家自由探索、停留、社交和绕路，不要写成强制一本道。
hard_rules 是最高优先级强约束，不能被临场剧情或风格描述覆盖。
generation_parameters 只控制 GM 输出长度、格式节奏和上下文摘录长度，不要写剧情设定。
修改完成后只输出完整 JSON，不要解释、Markdown 代码围栏或注释。
```

## 推荐修改流程

1. 先下载 `story_settings JSON` 和本说明文档。
2. 把 JSON 与本说明一起交给 AI 或手动编辑。
3. 重点检查 `format_version`、所有 `id`、`act_id`、`completion_anchors` 和 `generation_parameters`。
4. 确认 JSON 可以被解析后，在 RPGForge 设置页导入。
5. 导入成功即保存设定；不会改变当前存档、回合历史、摘要或状态。

## 作者须知：公开目标、转幕与状态后果

### 公开目标不藏谜底

`act_plan[].title` 和 `act_plan[].objective` 会用于玩家目标栏；任务标题、`player_visible` 和角色公开介绍也应按玩家可读内容填写。不要把尚未揭露的真凶、隐藏身份或关键证物直接写进这些字段。
例如用“灯塔深处／追查现场线索”作为公开目标，把“地下室藏有走私旧账”放进 `worldview.hidden_facts` 或素材的 `gm_secret`，并说明何时才允许揭露。

### 必需条件达成后自动转幕

模型根据实际发生的正文显式上报已完成锚点，平台再按锚点 ID 校验和结算；`completion_signal` 是叙事完成信号，不是关键词触发器。

- 每个没有替代组的 `required: true` 锚点都必须完成。
- 同一幕内，填相同 `alternative_group` 的多个必需锚点组成 OR：任意完成一条即可满足该组。
- 不同替代组之间、替代组与未分组必需锚点之间是 AND：每一项条件都要满足。
- `required: false` 是可选内容，不阻塞转幕，也不能用它替代必需路线的 `required: true`。
- 全部必需条件被结算确认为完成后自动进入下一幕；最后一幕的必需条件达成后进入通关结算。转幕是故事阶段变化，不等于必须立即换地点。

例如“勘查灯室 A”独立必需，“找到脚印 B／取得证言 C”同属一个必需替代组，帮助渔民 D 可选；逻辑是 **A AND (B OR C)**，D 不参与门槛。若另有替代组 E/F，则变成 **A AND (B OR C) AND (E OR F)**。创作包完整范例提供 A/B/C/D 的合法 JSON。
`transition_to_next_act.target_act` 指定下一幕；`condition` 只解释叙事前提，`transition_style` 只描述转场写法。平台不会把 condition 当成第二道独立程序门，也不会因为写了“玩家再次确认”就在条件达成后额外等待。真正必须发生的前提应写成必需锚点和可识别的 completion_signal。

### 外部导入只接设定源

创作 JSON 使用 `story_settings` v2 的人物、世界观、分幕、机制、素材及 `generation_parameters`；它不是游戏存档。不要附带 `initial_state`、`state_json`、`story_progress`、`state_delta_json`、`settlement_receipt`、回合、摘要、任务 ID、`revision` 或 `timeline_generation` 等内部运行数据；这些不是外部剧本导入的状态接口。格式版本 `format_version` 仍须保留。
初始身份、开局已知信息和初始关系写进人物、世界观和故事前提；机制后果写成可观察的叙事事件，例如“沈兰把钥匙交给林决并说明用途”“接受包扎后伤口不再流血”“守门人因看到证据而由怀疑转为有限配合”。GM 写出实际后果后，平台再识别并结算物品、伤势、关系或已知事实；不要只写抽象的“关系升级”，也不要要求正文输出内部回执。
`core_mechanics.rule` 等文字提供叙事约束，不是可执行脚本；导入设定不会直接注入物品栏或重写已发生的状态。

## 一级模块说明

| 模块 | 中文含义 | 用途和剧情影响 | 导入是否生效 |
| --- | --- | --- | --- |
| game_profile | 游戏档案 | 标题、题材、简介、基调。影响游戏列表、导出文件名和 GM 对题材的第一判断。 | 导入生效 |
| worldview | 世界观 | 世界舞台、公开事实、隐藏事实、势力、地点。影响 GM 的世界一致性和可观察线索来源。 | 导入生效 |
| story_core | 故事核心 | 核心幻想、主线悬念、长期目标、当前幕、必须保留和禁止偏离。是防跑偏的最高层剧本承诺。 | 导入生效 |
| core_characters | 核心人物 | 主角、同伴、NPC、反派和关系弧。导入后会同步角色档案。 | 导入生效 |
| act_plan | 分幕主线 | 每幕公开目标、揭露范围和完成锚点。必需条件结算达成后自动转幕；condition 是叙事说明。 | 导入生效 |
| main_quest_path | 主线轨迹 | 软主线节点。告诉 GM 如何保持长期方向，但不剥夺玩家自由探索。 | 导入生效 |
| core_mechanics | 核心机制 | 成长、资源、调查、压力、判定、基地等长期玩法规则。 | 导入生效 |
| action_style_rules | 行动风格规则 | 按玩家输入匹配调查、社交、探索、战斗等行动写法。 | 导入生效 |
| story_material_library | 剧本素材库 | 按关键词召回地点、秘密、线索、势力、物品、压力和反转。 | 导入生效 |
| home_base | [地点] | 长期据点、安全屋、组织后台或移动基地。影响休整、升级、情报和关系推进。 | 导入生效 |
| hard_rules | 强制规则 | 最高优先级硬约束，覆盖临场发挥和普通风格描述。 | 导入生效 |
| generation_parameters | 生成参数 | 控制每回合输出长度、段落、标题、重点标记和近期回合摘录长度。 | 导入生效 |

## 字段填写说明

### game_profile

| 字段路径 | 作用 | 填写规则和剧情影响 | 导入是否生效 | 示例 |
| --- | --- | --- | --- | --- |
| game_profile.title | 游戏标题 | 1-40 字为宜；会同步到游戏标题。 | 导入生效 | [游戏标题] |
| game_profile.genre | 题材类型 | 写清时代、风格、玩法类型；不要堆太多标签。 | 导入生效 | [题材类型] |
| game_profile.description | 一句话简介 | 玩家和 GM 都可见的概述，不写隐藏真相。 | 导入生效 | [一句话剧情简介] |
| game_profile.tone | 整体基调 | 影响 GM 语言气质和场景氛围。 | 导入生效 | [基调关键词] |
| game_profile.logline | 故事钩子 | 给 GM 的一句话抓手，可比 description 更有戏剧性。 | 导入生效 | [一句话故事钩子] |

### worldview

| 字段路径 | 作用 | 填写规则和剧情影响 | 导入是否生效 | 示例 |
| --- | --- | --- | --- | --- |
| worldview.summary | 公开世界观摘要 | 玩家可理解的世界描述；不要写最终真相。 | 导入生效 | [公开世界观摘要] |
| worldview.setting | 初始舞台 | 开局常用地点或区域。 | 导入生效 | [初始地点] |
| worldview.public_facts[] | 公开事实 | 玩家开局或常识可知的信息。 | 导入生效 | [一条公开事实] |
| worldview.hidden_facts[] | 隐藏事实 | 只给 GM 保持一致性，不能直接剧透。 | 导入生效 | [一条隐藏事实，仅 GM 可见] |
| worldview.core_conflicts[] | 核心冲突 | 推动世界和势力行动的长期矛盾。 | 导入生效 | [一条核心冲突] |
| worldview.factions[] | 关键势力 | 供 GM 安排冲突、压力和 NPC 立场。 | 导入生效 | [势力名] |
| worldview.locations[] | 关键地点 | 供 GM 保持地点一致，避免凭空扩张。 | 导入生效 | [地点名] |

### story_core

| 字段路径 | 作用 | 填写规则和剧情影响 | 导入是否生效 | 示例 |
| --- | --- | --- | --- | --- |
| story_core.premise | 剧本前提 | 本局最核心的承诺；GM 不应偏离。 | 导入生效 | [剧本前提] |
| story_core.core_fantasy | 核心幻想 | 玩家想体验的爽点或主题体验。 | 导入生效 | [核心幻想/爽点] |
| story_core.central_mystery | 核心悬念 | 贯穿全剧的问题；不要在前几回合直接解答。 | 导入生效 | [贯穿全剧的核心问题] |
| story_core.main_goal | 长期目标 | GM 拉回主线时使用的方向。 | 导入生效 | [长期目标] |
| story_core.emotional_arc | 情感弧 | 玩家情绪的长期走向，给 GM 把控基调推进。 | 导入生效 | [情感走向，如从戒备到信任] |
| story_core.narrative_style | 叙事风格 | GM 行文的语感取向，可比 tone 更具体。 | 导入生效 | [叙事语感，如短句冷硬] |
| story_core.current_act | 默认当前幕 | 新游戏初始幕；已有游戏实际进度优先看当前状态。 | 导入生效 | act_1 |
| story_core.must_preserve[] | 必须保留 | 用户强要求、正典设定、必须出现内容。 | 导入生效 | [必须保留的设定] |
| story_core.must_not_become[] | 禁止变成 | 类型红线，防止题材变味。 | 导入生效 | [类型红线] |
| story_core.forbidden_drift[] | 禁止偏离 | 剧情长期不能滑向的方向。 | 导入生效 | [禁止偏离的方向] |
| story_core.canon_terms[] | 正典词条 | 重要专名，帮助 GM 保持命名一致。 | 导入生效 | [重要专名] |

### core_characters[]

| 字段路径 | 作用 | 填写规则和剧情影响 | 导入是否生效 | 示例 |
| --- | --- | --- | --- | --- |
| core_characters[].id | 稳定角色 id | 用英文或拼音 snake_case；不要随意改。 | 导入生效 | main_char |
| core_characters[].name | 角色名 | 会同步到角色档案；不能为空。 | 导入生效 | [角色名] |
| core_characters[].aliases[] | 别名 | 供 GM 识别同一角色的其他称呼，避免改名后认不出。 | 导入生效 | [别名1]、[别名2] |
| core_characters[].role | 角色类型 | 建议 protagonist、companion、npc、antagonist、other。 | 导入生效 | protagonist |
| core_characters[].identity | 公开身份 | 玩家可见身份，不写隐藏身份。 | 导入生效 | [公开身份] |
| core_characters[].description | 公开介绍 | 玩家可见人物描述。 | 导入生效 | [公开人物描述] |
| core_characters[].appearance | 外貌 | 用于角色展示和视觉一致性。 | 导入生效 | [外貌描述] |
| core_characters[].dramatic_function | 戏剧功能 | 告诉 GM 该角色在主线中的作用。 | 导入生效 | [戏剧功能，如线索守门人] |
| core_characters[].desire/fear/leverage | 动机组 | 决定 NPC 行动、谈判筹码和关系变化。 | 导入生效 | [动机，如想夺回某物] |
| core_characters[].relationship_arc | 关系弧 | 该角色与主角关系的长期变化方向。 | 导入生效 | [关系变化方向] |
| core_characters[].public_limit | 公开边界 | 按公开可观察的行为边界填写；完整秘密另放 gm_secret。 | 导入生效 | 没有可信证据前不肯提供帮助 |
| core_characters[].portrait_prompt | 立绘提示词 | 用于生成角色立绘的描述；不写隐藏身份。 | 导入生效 | [立绘描述，不含隐藏身份] |
| core_characters[].visibility | 可见性 | visible 会展示给玩家；hidden 保留给 GM。 | 导入生效 | visible |

### act_plan[]

| 字段路径 | 作用 | 填写规则和剧情影响 | 导入是否生效 | 示例 |
| --- | --- | --- | --- | --- |
| act_plan[].id | 幕 id | 必须唯一，建议 act_1、act_2 等；幕数按故事规模安排。 | 导入生效 | act_1 |
| act_plan[].title | 幕标题 | 会用于玩家目标栏；用不泄露未揭真相的公开标题。 | 导入生效 | 灯塔深处 |
| act_plan[].objective | 本幕目标 | 会用于玩家目标栏；写当前可公开的方向，不写谜底。 | 导入生效 | 顺着已发现的线索继续调查 |
| act_plan[].dramatic_question | 戏剧问题 | 决定本幕张力，不等于任务清单。 | 导入生效 | [本幕戏剧问题] |
| act_plan[].must_hit_beats[] | 必经节拍 | 本幕希望出现的关键剧情节拍，给 GM 软引导。 | 导入生效 | [关键节拍] |
| act_plan[].allowed_reveals[] | 允许揭露 | 本幕可以透露的信息边界。 | 导入生效 | [本幕可揭露的信息] |
| act_plan[].forbidden_reveals[] | 禁止揭露 | 本幕不能提前说出的真相。 | 导入生效 | [本幕禁止揭露的真相] |
| act_plan[].completion_anchors[] | 完成锚点 | 推进到下一幕前需要自然满足的条件。 | 导入生效 | [完成条件] |
| completion_anchors[].id | 锚点 id | 必须全局唯一；状态提取器用它标记完成。 | 导入生效 | act_1_anchor_1 |
| completion_anchors[].title | 锚点标题 | 供进度提示与 GM 识别，按可公开展示填写。 | 导入生效 | 取得关键证据 |
| completion_anchors[].required | 是否必达 | true 表示推进到下一幕前必须满足；默认 true。 | 导入生效 | true |
| completion_anchors[].alternative_group | 替代组 | 同一幕多个 required 锚点填相同值时，完成其中任意一个即可满足该组；普通必达锚点留空。 | 导入生效 | entry_path |
| completion_anchors[].description | 锚点说明 | 解释这个锚点要达成什么，给 GM 参考。 | 导入生效 | [锚点要达成什么] |
| completion_anchors[].completion_signal | 完成信号 | 写成可从剧情文本识别的明确事件。 | 导入生效 | [可识别的剧情事件] |
| transition_to_next_act.target_act | 下一幕目标 | 只能指向存在的 act id；最后一幕可留空对象。 | 导入生效 | act_2 |
| transition_to_next_act.condition | 叙事转场说明 | 不是独立程序门；真正的必需前提应写成 required 锚点。 | 导入生效 | 现场证据齐备后顺线索深入 |
| transition_to_next_act.transition_style | 转场写法 | 给 GM 的叙事衔接建议，不改变锚点判定。 | 导入生效 | 顺线索深入 |

### main_quest_path[]

| 字段路径 | 作用 | 填写规则和剧情影响 | 导入是否生效 | 示例 |
| --- | --- | --- | --- | --- |
| main_quest_path[].id | 主线节点 id | 稳定唯一，便于 AI 修改和引用。 | 导入生效 | main_quest_1 |
| main_quest_path[].act_id | 所属幕 | 必须对应 act_plan[].id。 | 导入生效 | act_1 |
| main_quest_path[].title | 任务标题 | 可作为玩家可见任务名。 | 导入生效 | [任务标题] |
| main_quest_path[].objective | 软目标 | 给 GM 的推进方向，不强制玩家立刻执行。 | 导入生效 | [软目标] |
| main_quest_path[].player_visible | 玩家提示 | 可公开显示，不写 GM 秘密。 | 导入生效 | [玩家可见提示] |
| main_quest_path[].completion_signal | 完成信号 | 和锚点一样，写可识别事件。 | 导入生效 | [可识别事件] |
| main_quest_path[].optional | 是否支线 | true 表示可选支线，不阻塞主线推进；默认 false。 | 导入生效 | false |

### core_mechanics[]

| 字段路径 | 作用 | 填写规则和剧情影响 | 导入是否生效 | 示例 |
| --- | --- | --- | --- | --- |
| core_mechanics[].id | 机制 id | 稳定唯一。 | 导入生效 | investigation |
| core_mechanics[].name | 机制名 | 简短说明机制。 | 导入生效 | [机制名] |
| core_mechanics[].rule | 机制规则 | 写 GM 必须长期遵守的可执行规则。 | 导入生效 | [GM 长期遵守的规则] |
| core_mechanics[].progression | 推进方式 | 阶段、触发方式或叙事代价。 | 导入生效 | [推进方式] |
| core_mechanics[].visibility | 可见性 | public、mixed、gm_only。 | 导入生效 | mixed |

### action_style_rules[]

| 字段路径 | 作用 | 填写规则和剧情影响 | 导入是否生效 | 示例 |
| --- | --- | --- | --- | --- |
| action_style_rules[].id | 行动风格 id | 稳定唯一。 | 导入生效 | investigation |
| action_style_rules[].name | 风格名 | 简短标识该行动风格，便于诊断。 | 导入生效 | [风格名] |
| action_style_rules[].triggers[] | 触发词 | 玩家输入命中后更容易选中该风格。 | 导入生效 | [触发词1]、[触发词2] |
| action_style_rules[].rule | 行动写法规则 | 告诉 GM 该类行动怎么写结果、代价、线索。 | 导入生效 | [该类行动的写法规则] |
| action_style_rules[].priority | 优先级 | critical、high、medium、low；冲突时高优先。 | 导入生效 | high |
| action_style_rules[].enabled | 是否启用 | false 后不参与匹配。 | 导入生效 | true |

### story_material_library[]

| 字段路径 | 作用 | 填写规则和剧情影响 | 导入是否生效 | 示例 |
| --- | --- | --- | --- | --- |
| story_material_library[].id | 素材 id | 稳定唯一，建议用可读英文或拼音。 | 导入生效 | material_1 |
| story_material_library[].title | 素材标题 | GM 诊断和召回时显示。 | 导入生效 | [素材标题] |
| story_material_library[].type | 素材类型 | location、npc、item、secret、clue、pressure、twist 等。 | 导入生效 | location |
| story_material_library[].keywords[] | 关键词 | 用于语义召回；写清专名和别名。 | 导入生效 | [关键词1]、[关键词2] |
| story_material_library[].triggers[] | 触发词 | 玩家输入直接命中时强召回。 | 导入生效 | [触发词] |
| story_material_library[].priority | 召回优先级 | critical/high/medium/low；越高越容易被召回打分选中。 | 导入生效 | high |
| story_material_library[].always_on | 常驻注入 | critical 核心设定可 true；太多会耗 token。 | 导入生效 | false |
| story_material_library[].visibility | 可见性 | public、mixed、gm_only，控制素材信息暴露范围。 | 导入生效 | mixed |
| story_material_library[].public_info | 公开信息 | 玩家可见，不写秘密。 | 导入生效 | [玩家可见信息] |
| story_material_library[].gm_secret | GM 秘密 | 只供 GM 保持一致，不能直接剧透。 | 导入生效 | [仅 GM 可见的秘密] |
| story_material_library[].content | 完整素材 | 告诉 GM 这条素材如何影响剧情。 | 导入生效 | [这条素材如何影响剧情] |
| story_material_library[].usage | 使用规则 | 何时召回、如何给线索、不能揭露什么。 | 导入生效 | [何时召回、怎么给线索] |
| story_material_library[].enabled | 是否启用 | false 后不参与召回匹配。 | 导入生效 | true |

### home_base

| 字段路径 | 作用 | 填写规则和剧情影响 | 导入是否生效 | 示例 |
| --- | --- | --- | --- | --- |
| home_base.id | 据点 id | 稳定唯一。 | 导入生效 | home_base |
| home_base.name | 据点名 | 可以是基地、安全屋、组织后台或移动据点。 | 导入生效 | [据点名] |
| home_base.role | 剧情作用 | 说明据点如何服务休整、情报、升级和关系推进。 | 导入生效 | [据点的剧情作用] |
| home_base.public_functions[] | 公开功能 | 玩家可用的功能。 | 导入生效 | [玩家可用功能] |
| home_base.hidden_hooks[] | 隐藏钩子 | GM 后续可用秘密。 | 导入生效 | [GM 隐藏钩子] |

### hard_rules

| 字段路径 | 作用 | 填写规则和剧情影响 | 导入是否生效 | 示例 |
| --- | --- | --- | --- | --- |
| hard_rules.must_follow[] | 必须遵守 | 最高优先级正向规则。 | 导入生效 | 每回合给出 A/B/C/D 四个行动选项。 |
| hard_rules.must_not[] | 绝对禁止 | 不能被剧情、风格或模型自由发挥覆盖。 | 导入生效 | [绝对禁止的内容] |
| hard_rules.reveal_rules[] | 揭露规则 | 控制秘密怎么慢慢出现。 | 导入生效 | 隐藏真相只能通过线索逐步揭露。 |
| hard_rules.continuity_rules[] | 连续性规则 | 控制人物、物品、地点、状态不乱变。 | 导入生效 | 人物动机和地点状态必须一致。 |
| hard_rules.gm_output_rules[] | 输出规则 | 可以补充正文风格和显示边界，但不能破坏系统四选项契约。 | 导入生效 | 正文不输出状态结算。 |

### generation_parameters

| 字段路径 | 作用 | 填写规则和剧情影响 | 导入是否生效 | 示例 |
| --- | --- | --- | --- | --- |
| narrative_target_min_chars | 目标最少字数 | 影响剧情丰富度和 token 消耗。 | 导入生效 | 800 |
| narrative_target_max_chars | 目标最多字数 | 越大越丰富也越耗 token。 | 导入生效 | 1200 |
| narrative_min_chars | 硬性最低字数 | 避免 GM 回复过短。 | 导入生效 | 700 |
| paragraph_min / paragraph_max | 段落范围 | 控制阅读节奏。 | 导入生效 | 3 / 6 |
| scene_heading_max | 标题数量上限 | 0 表示不鼓励标题；过高会像大纲。 | 导入生效 | 1 |
| emphasis_min / emphasis_max | 重点标记数量 | 控制 `**重点**` 数量。 | 导入生效 | 2 / 4 |
| recent_turn_excerpt_chars | 近期回合摘录长度 | 越高上下文越完整，越低越省 token。 | 导入生效 | 420 |

## 修改风险和校验重点

- `format_version` 必须保持 `rpgforge.story.v2`。
- `act_plan[].id`、`main_quest_path[].act_id`、`transition_to_next_act.target_act` 必须互相对应。
- `completion_anchors[].id` 必须全局唯一；重复会导致导入失败。
- `completion_signal` 要写成剧情中能自然出现、状态提取器能识别的事件。
- `public_*`、`player_visible`、角色公开字段及 `act_plan[].title/objective` 不能写隐藏真相。
- `gm_secret`、`hidden_facts` 可以写完整秘密，但 GM 只能转化成线索，不应直接剧透。
- `story_material_library[].always_on=true` 的素材会更稳定进入上下文，但过多会增加 token 消耗。
- `generation_parameters.recent_turn_excerpt_chars` 越大，近期回合上下文越完整；越小越省 token。
- `initial_state`、状态增量、回执、存档、当前状态、回合历史和摘要不在这个 JSON 内；状态后果应写为明确叙事，导入设定不会自动重写已经发生的剧情进度。


---

## 如何阅读这个范例

- 幕标题、幕目标、任务标题与玩家提示都按可公开显示来写。
  第二幕使用“灯塔深处／追查现场线索”，不把尚未揭露的旧账写进目标栏。
- 第一幕的必需条件是：`act_1_inspect_lamp` **AND**
  （`act_1_second_person_tracks` **OR** `act_1_second_person_testimony`）。
  后两条都写 `required: true` 和同一个 `alternative_group`；不是把它们写成可选项。
  若另有一个替代组，该组也必须至少完成一条；不同组之间仍是 AND。
- `act_1_help_fishermen` 是 `required: false` 的可选支线。
  两条必需条件满足后，即使没帮助渔民、也没走另一条调查路线，平台仍会自动进入第二幕。
- `transition_to_next_act.condition` 复述同一组叙事前提，`transition_style` 描述转场写法。
  真正必须兑现的新前提应写成必需锚点及明确的 `completion_signal`，不能只藏在 condition 里。
- 这个 JSON 是设定源，不是开局状态或存档。比如“找到残页后将证据交给沈兰”应作为可观察的
  剧情后果写入机制或素材说明；不要在 JSON 顶层附带物品栏、`initial_state` 或结算回执。


## 完整范例剧本（可直接导入，照此结构填写）

```json
{
  "format_version": "rpgforge.story.v2",
  "game_profile": {
    "title": "雾港灯塔失踪案",
    "genre": "悬疑推理",
    "description": "新到任的港务调查员追查灯塔看守人离奇失踪。",
    "tone": "阴郁、克制、注重细节",
    "logline": "一座停转的灯塔，一个消失的看守人，把新来的调查员拖进雾港的旧秘密。"
  },
  "worldview": {
    "summary": "雾港是常年大雾的边境渔港，灯塔是全镇唯一的航行依靠，最近无故熄灭。",
    "setting": "雾港码头与断崖灯塔",
    "public_facts": [
      "灯塔已熄灭三夜，渔船不敢出海。"
    ],
    "hidden_facts": [
      "灯塔地下室藏有走私货物的旧账。"
    ],
    "core_conflicts": [
      "真相被镇上有头脸的人遮掩。"
    ],
    "factions": [
      "港务局",
      "渔民行会"
    ],
    "locations": [
      "雾港码头",
      "断崖灯塔",
      "[地点]"
    ]
  },
  "story_core": {
    "premise": "调查员林决奉命查清灯塔看守人失踪案。",
    "core_fantasy": "用观察、问询和危险抉择，一层层揭开小镇旧秘密。",
    "central_mystery": "看守人是逃走、被害，还是发现了不该看的东西？",
    "main_goal": "查清灯塔看守人失踪真相。",
    "emotional_arc": "从例行公事到被迫直面小镇的集体沉默。",
    "narrative_style": "冷静、细节密集、不给超自然答案。",
    "current_act": "act_1",
    "must_preserve": [
      "大雾笼罩的灯塔",
      "看守人失踪的悬念"
    ],
    "must_not_become": [
      "不要变成超自然恐怖",
      "不要提前坐实凶手"
    ],
    "forbidden_drift": [
      "不要引入魔法或怪物"
    ],
    "canon_terms": [
      "雾港",
      "断崖灯塔",
      "看守人韩牧"
    ]
  },
  "core_characters": [
    {
      "id": "lin_jue",
      "name": "林决",
      "role": "protagonist",
      "identity": "新到任的港务调查员",
      "description": "刚调来雾港、急于证明自己的调查员。",
      "appearance": "灰呢大衣，随身带一本翻旧的勘查手册。",
      "visibility": "visible",
      "dramatic_function": "推动调查的主角",
      "desire": "靠破案站稳脚跟",
      "fear": "发现真相牵连到自己的上级",
      "leverage": "对细节有近乎偏执的记忆力",
      "relationship_arc": "从孤身外来者到赢得部分镇民信任",
      "public_limit": "不能提前断定凶手"
    },
    {
      "id": "shen_lan",
      "name": "沈兰",
      "role": "npc",
      "identity": "灯塔看守人的女儿",
      "description": "守着空灯塔、对外来者警惕的年轻女子。",
      "appearance": "渔家粗布衣，袖口沾着灯油。",
      "visibility": "visible",
      "dramatic_function": "线索守门人",
      "desire": "找回失踪的父亲",
      "fear": "父亲卷入了见不得光的事",
      "leverage": "知道灯塔地下室的入口",
      "relationship_arc": "从敌意防备到有限合作",
      "public_limit": "尚未建立信任前，不愿提供额外线索"
    }
  ],
  "act_plan": [
    {
      "id": "act_1",
      "title": "熄灭的灯塔",
      "objective": "在灯塔现场找到失踪案的第一条线索。",
      "dramatic_question": "看守人是自己离开，还是出了事？",
      "pressure": "镇上有人希望此事尽快了结。",
      "must_hit_beats": [
        "勘查灯塔现场",
        "确认看守人最后的行踪"
      ],
      "allowed_reveals": [
        "失踪当晚灯塔曾有第二个人"
      ],
      "forbidden_reveals": [
        "走私旧账的存在"
      ],
      "relationship_turn": "沈兰开始动摇是否信任林决。",
      "escalation_limit": "只推进到现场线索层，不引入凶手对峙。",
      "completion_anchors": [
        {
          "id": "act_1_inspect_lamp",
          "title": "勘查灯室",
          "required": true,
          "alternative_group": "",
          "description": "确认灯塔是被人为熄灭。",
          "completion_signal": "发现灯油被人为放空的痕迹。"
        },
        {
          "id": "act_1_second_person_tracks",
          "title": "核实现场痕迹",
          "required": true,
          "alternative_group": "second_person_evidence",
          "description": "证明失踪当晚灯塔不止看守人一人。",
          "completion_signal": "找到不属于看守人的脚印或物件。"
        },
        {
          "id": "act_1_second_person_testimony",
          "title": "核实证人证言",
          "required": true,
          "alternative_group": "second_person_evidence",
          "description": "通过另一条调查路线确认当晚有来客。",
          "completion_signal": "证人明确说出当晚见到另一人进入灯塔的时间和经过。"
        },
        {
          "id": "act_1_help_fishermen",
          "title": "帮助滞港渔民",
          "required": false,
          "alternative_group": "",
          "description": "可选的人情支线，不是失踪案转幕条件。",
          "completion_signal": "帮助渔民修好临时雾号，并得到他们的感谢。"
        }
      ],
      "transition_to_next_act": {
        "target_act": "act_2",
        "condition": "确认人为熄灯，并通过现场痕迹或证人证言核实当晚有来客。",
        "transition_style": "顺线索深入"
      }
    },
    {
      "id": "act_2",
      "title": "灯塔深处",
      "objective": "追查现场线索，取得能解释失踪案的关键证据。",
      "dramatic_question": "看守人是因为这本旧账才消失的吗？",
      "pressure": "港务局开始施压要求结案。",
      "must_hit_beats": [
        "进入地下室",
        "找到走私旧账残页"
      ],
      "allowed_reveals": [
        "旧账牵连港务局旧人"
      ],
      "forbidden_reveals": [
        "最终主使身份"
      ],
      "relationship_turn": "沈兰与林决形成脆弱合作。",
      "escalation_limit": "只揭露旧账残页，不揭露最终主使。",
      "completion_anchors": [
        {
          "id": "act_2_find_ledger",
          "title": "取得关键证据",
          "required": true,
          "alternative_group": "",
          "description": "拿到指向下一步的实物证据。",
          "completion_signal": "获得走私旧账残页。"
        }
      ],
      "transition_to_next_act": {}
    }
  ],
  "main_quest_path": [
    {
      "id": "main_quest_1",
      "act_id": "act_1",
      "title": "勘查灯塔现场",
      "objective": "找到失踪案的第一条线索。",
      "player_visible": "检查熄灭的灯塔。",
      "completion_signal": "发现灯油被人为放空的痕迹。",
      "optional": false
    },
    {
      "id": "main_quest_2",
      "act_id": "act_2",
      "title": "继续调查灯塔",
      "objective": "查清现场线索指向的后续真相。",
      "player_visible": "顺着已发现的线索继续调查。",
      "completion_signal": "获得走私旧账残页。",
      "optional": false
    }
  ],
  "core_mechanics": [
    {
      "id": "investigation",
      "name": "调查推进",
      "rule": "给线索不给答案，隐藏真相必须通过可观察痕迹逐步揭露。",
      "progression": "本幕全部必需条件达成后自动转幕，同组替代路线任一完成即可。",
      "visibility": "public"
    }
  ],
  "action_style_rules": [
    {
      "id": "main_story",
      "name": "主线推进",
      "triggers": [
        "主线",
        "推进",
        "追查"
      ],
      "rule": "围绕当前幕目标推进，但不强迫玩家离开当前场景。",
      "priority": "high",
      "enabled": true
    },
    {
      "id": "investigation",
      "name": "调查行动",
      "triggers": [
        "调查",
        "检查",
        "线索",
        "搜索"
      ],
      "rule": "提供可验证线索和代价，不直接泄露隐藏真相。",
      "priority": "critical",
      "enabled": true
    },
    {
      "id": "social",
      "name": "社交试探",
      "triggers": [
        "询问",
        "交涉",
        "试探"
      ],
      "rule": "让 NPC 通过语气、回避和交换条件透露信息。",
      "priority": "medium",
      "enabled": true
    }
  ],
  "story_material_library": [
    {
      "id": "lighthouse",
      "title": "断崖灯塔",
      "type": "location",
      "keywords": [
        "灯塔",
        "灯室",
        "断崖"
      ],
      "triggers": [
        "灯塔",
        "灯室",
        "断崖"
      ],
      "priority": "critical",
      "always_on": true,
      "visibility": "mixed",
      "public_info": "全镇唯一的航行依靠，已熄灭三夜。",
      "gm_secret": "灯塔地下室藏有走私货物旧账。",
      "content": "灯塔是第一幕核心地点，灯室痕迹和地下室入口指向失踪真相。",
      "usage": "玩家调查灯塔、灯室或断崖时注入，不直接说出地下室旧账。",
      "enabled": true
    },
    {
      "id": "shen_lan_material",
      "title": "看守人之女沈兰",
      "type": "npc",
      "keywords": [
        "沈兰",
        "看守人",
        "灯油"
      ],
      "triggers": [
        "沈兰",
        "看守人",
        "地下室"
      ],
      "priority": "high",
      "always_on": false,
      "visibility": "mixed",
      "public_info": "守着空灯塔、对外来者警惕的年轻女子。",
      "gm_secret": "沈兰知道灯塔地下室的入口。",
      "content": "沈兰是关键线索人，会在被取得信任后透露地下室入口。",
      "usage": "玩家提到沈兰、看守人或地下室时注入。",
      "enabled": true
    }
  ],
  "home_base": {
    "id": "home_base",
    "name": "[地点]",
    "role": "休整、情报整理与关系推进据点。",
    "public_functions": [
      "整理线索",
      "歇脚"
    ],
    "hidden_hooks": [
      "据点旧航海图标注了灯塔地下室入口。"
    ],
    "upgrade_paths": [
      "情报角",
      "档案柜"
    ],
    "npc_services": [
      "老港工帮忙辨认旧账笔迹"
    ],
    "scene_uses": [
      "回合间总结线索"
    ]
  },
  "hard_rules": {
    "must_follow": [
      "每回合输出玩家可见剧情，并给出 A/B/C/D 四个具体行动选项。"
    ],
    "must_not": [
      "不要引入超自然元素",
      "不要提前揭露最终主使"
    ],
    "reveal_rules": [
      "隐藏真相只能通过线索逐步揭露。"
    ],
    "continuity_rules": [
      "人物动机和地点状态必须保持一致。"
    ],
    "gm_output_rules": [
      "正文不输出状态结算。"
    ]
  },
  "generation_parameters": {
    "narrative_target_min_chars": 800,
    "narrative_target_max_chars": 1200,
    "narrative_min_chars": 700,
    "paragraph_min": 3,
    "paragraph_max": 6,
    "scene_heading_max": 1,
    "emphasis_min": 2,
    "emphasis_max": 4,
    "recent_turn_excerpt_chars": 420
  }
}
```

---

## 给 AI 的硬指令

把上面的「字段填写指南」当规则，把「完整范例剧本」当模板，结合用户给你的剧情想法，
产出一份**全新的** `story_settings` JSON。务必遵守：

1. **只输出一个合法 JSON 对象**，不要解释、Markdown 代码围栏或注释。
2. `format_version` 必须是 `rpgforge.story.v2`。
3. 使用范例中的 `story_settings` 顶层键；生成参数放在 `generation_parameters`。
   不要自创顶层字段，不要套入 `config`、游戏存档或内部运行状态。
4. 标题、题材、简介写进 `game_profile`（不是顶层），它们决定游戏标题。
5. `core_characters[].name` 必须唯一且非空；`act_plan[].id` 与所有
   `completion_anchors[].id` 必须全局唯一。
6. 秘密、真凶、反转**不要**写进公开字段，尤其是玩家目标栏会显示的
   `act_plan[].title`、`act_plan[].objective`，以及任务名和 `player_visible`；
   秘密正文放进 `worldview.hidden_facts` 或 `story_material_library[].gm_secret`，
   再用 `act_plan[].forbidden_reveals`、`hard_rules.must_not` 约束揭露时机。
7. 本创作模板至少写 2 幕（`act_plan`），每幕至少 1 个 `required: true` 的完成锚点。
   同组替代路线是 OR，不同组及未分组的必需锚点之间是 AND；`required: false` 不阻塞。
   全部必需条件被结算确认为完成后，平台自动转幕；`transition_to_next_act.condition`
   仅作叙事说明，不是独立程序门，也不会额外等待玩家按“继续”或口头确认。
8. 不要输出 `initial_state`、`state_json`、`story_progress`、状态增量、回执或任务版本。
   初始设定和后续状态后果写进人物、世界观、机制规则及明确的叙事事件，
   让 GM 写出实际获得/失去物品、伤势解除、关系变化或事实揭露，再由平台结算。
9. 产出后自检：JSON 能被 `JSON.parse` 解析，且字段名与范例一致。
