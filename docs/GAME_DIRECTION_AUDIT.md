# RPGForge 游戏方向审查报告（2026-06-02）

> 本文档是「游戏方向」专项审查的产出与改进驾驶舱。与 [`GAME_SYSTEM_AUDIT.md`](GAME_SYSTEM_AUDIT.md) 的关系：
> - `GAME_SYSTEM_AUDIT.md` 审的是**状态系统正确性**（提取契约、数值结算、任务/线索/锚点是否被正确记录）——「记的对不对」。
> - **本文档审的是「作为一个游戏好不好玩」**——博弈、失败、闭环、能动性、上手体验——「值不值得玩」。
>
> 审查方法：从游戏设计三个维度（机制深度 / 叙事能动性 / 玩家全周期体验）切分，多 Agent 并行深审 + 代码逐条核实。**本轮只审查、未改任何代码**。项目定位为「单人自部署、自己玩、不公开、不盈利、不多人」，故审查**刻意排除**工程质量、测试、性能、token 成本、安全、部署等已被 Round 1–31 大量覆盖的方向。

---

## 0. 核心判断

**项目在「工程 / AI 链路 / 剧情遵循」上已投入过度（31 轮优化几乎全在让 AI 写得忠实、省 token、不跑偏），但作为一个「游戏」，它缺三样立身之本：博弈、失败、结局。** 当前形态更接近一台**带强约束的 AI 叙事生成器**，而非 RPG。继续加固「剧情遵循」的边际收益已接近零甚至为负（见 B5/B7），真正的缺口在机制、闭环与上手三处。

| 维度 | 健康度 | 一句话 |
|---|---|---|
| 剧情遵循 / 防剧透 / 状态记账 | ✅ 强（已过度） | Round 1–31 重点投入区，扎实 |
| **机制深度 / 博弈感** | 🔴 **基本缺失** | 无判定层 → 属性/技能/等级全是只写不读的装饰 |
| **叙事闭环 / 能动性** | 🔴 **断裂** | 无结局、无结局变体、选择不改变故事结构 |
| **玩家上手 / 全周期体验** | 🟠 **多处断点** | 冷启动无开场、游玩页无目标、零引导 |
| 沉浸氛围（视听） | 🟡 中 | 纯文字，无场景图/音乐 |

---

## 1. 三条主线（贯穿多数问题）

- **M1 没有判定层（机制根因）**：全代码库 `dice/roll/检定/成功率/概率/难度` 零命中。玩家行动的成败 100% 由 GM 即兴文字裁决，属性/技能/等级不构成任何数学上的成功率。由此派生出一整串「假机制」（A1–A6）。
- **M2 只能前进，不能失败、不能结束（叙事根因）**：无死亡/game over、压力时钟代价从不兑现、最后一幕完成后无结局流程。故事既不会输也不会真正赢，所有路径收敛到同一批锚点（B1–B4）。
- **M3 「防跑偏」用力过猛压制了能动性（方向反噬）**：DriftValidator / StoryDirector 为忠于预设剧本，会把玩家的发散探索与慢节奏扮演持续拉回主线（B5/B7）。这是 31 轮「防跑偏」优化的副作用，已到该松绑的拐点。

---

## 2. 问题清单

> 编号：A=机制层，B=叙事层，C=体验层。优先级：P0 决定「是不是游戏 / 故事完不完整 / 能不能上手」；P1 强烈建议；P2 锦上添花。

### A. 机制层 —— 为什么「不像游戏」

- **[A1 · P0 · 缺失] 玩家行动无成功/失败判定，属性与技能不构成成功率。** 全库无骰子/检定/概率代码；[`gm_runtime.md`](../api/app/prompts/gm_runtime.md) 规则 1–32 无「行动可能失败」概念（规则 25 只说「先解决直接结果，再引出新压力」）；[`drift_validator.md`](../api/app/prompts/drift_validator.md:3) 只要 GM 回应了行动就 `approved`，从不校验「按玩家能力这个行动本该失败」。**影响**：1 级和 50 级撬同一把锁、说同一句话，结果相同。没有风险=没有取舍=没有游戏。这是项目作为「游戏」最根本的缺口。**改进**：引入轻量判定层——StoryDirector 为玩家行动标 `difficulty`，后端用「相关属性/技能等级 + roll vs 阈值」算 `outcome`(critical/success/partial/failure)，把 outcome 作为**硬约束**写进 `gm_instruction`，GM 只负责叙事化既定结果。复用已有的 `OUTCOME_MULTIPLIER`([`quantified_state.py:69`](../api/app/services/quantified_state.py:69)) 反哺技能 XP。

- **[A2 · P0 · 装饰性] XP/等级/技能/关系是纯单向记账，永不反哺判定或玩法。** [`quantified_state.py`](../api/app/services/quantified_state.py) 只累加（XP 按 base×难度×重要性、技能按 `10×难度×outcome`、关系按强度增减）；但 `attributes / skill level / mastery` 在 gameplay/prompt_builder/drift 中零命中。`project_state_for_scene` 甚至砍掉 `xp_log` 只把数字给 GM 看；规则 20 还**禁止**叙事里出现数值。**影响**：升级是纯庆祝动画，等级 5 与 50 在玩法上无差别，数值养成毫无回报闭环。**改进**：与 A1 配套——让等级/技能进入判定加值，让关系数值作为社交判定修正项与**选项可用门槛**（如 trust<30 时某说服选项不可用/大概率失败）。

- **[A3 · P1 · 缺失] 没有失败状态 / game over / 主角死亡。** grep `game_over/死亡/HP/defeat` 零命中。`OUTCOME_MULTIPLIER` 有 `failure:0.45`([`quantified_state.py:70`](../api/app/services/quantified_state.py:70)) 但 GM 从无产出 failure 的指令，该分支实际几乎永不触发；引擎只能「前进」，无回退/死局/终止路径。**影响**：不会输 → 谨慎决策与乱按结果趋同，博弈感被抽空。**改进**：不必做硬核 permadeath。引入主角**危机条**（单一 0–100 资源，受 conditions 严重度与战斗判定失败侵蚀），归零触发剧本化失败结局（被俘/重伤倒下，可由当前幕的「失败锚点」定义），给「输」一个叙事出口，但它必须真的可能发生。

- **[A4 · P1 · 装饰性] conditions/abilities 的 `severity/cooldown/resource_cost` 记录后无人消费。** [`extract_state_delta.md`](../api/app/prompts/extract_state_delta.md) 让 LLM 产出这些字段，`_apply_ability_update`/`_apply_condition_update`([`quantified_state.py:201`](../api/app/services/quantified_state.py:201)) 存进对象，state_v2 原样投影，但无任何扣减/冷却计数/severity 惩罚逻辑。**影响**：「中毒(high)」与「中毒(low)」玩法上无区别；带 cooldown 的强技能可每回合连发。**改进**：先收窄而非铺开——给 conditions 一个 `severity→判定减值` 映射，给 abilities 最简 `cooldown 回合计数`（后端记录上次使用 turn，未到冷却则该选项不可用/必失败）。

- **[A5 · P2 · 装饰性] 六大「模式」（战斗/潜行/社交…）走完全相同的代码路径，只是换一段提示词文本。** modes 即 `action_style_rules`，`select_action_style`([`story_settings.py:423`](../api/app/services/story_settings.py:423)) 命中触发词后只注入该 style 的 `rule` 文本，「战斗」与「社交」在引擎层无任何机制差异——都是「注入一段 rule 文本 → GM 自由叙事」，无战斗回合结构/先攻/距离/命中、无潜行暴露判定。**影响**：模式切换换皮不换骨。**改进**：战斗/潜行至少挂上 A1 判定层 + A3 危机条（战斗=连续攻防判定消耗危机条；潜行=暴露值累积判定），让「模式」对应不同的判定循环而非不同文风。

- **[A6 · P2 · 缺失] 无经济/资源稀缺，物品只增删。** grep `货币/gold/商店/交易` 零命中。`_apply_inventory`([`state_applier.py`](../api/app/services/state_applier.py)) 只做加/减/合并，物品无价值/重量/消耗压力；`home_base.upgrade_paths` 有字段但无成本消费逻辑。**影响**：资源管理这一 RPG 核心张力缺席，无「买不起 / 补给耗尽 / 救谁舍谁」的稀缺抉择。**改进**：给关键消耗品（医疗/弹药/食物）有限计数 + 消耗触发；让 `upgrade_paths` 真正扣减一种核心资源。先让「稀缺」存在，再谈交易。

### B. 叙事层 —— 讲不完故事，选择也不改变故事

- **[B1 · P0 · 闭环断裂] 最后一幕完成后无任何结局/通关流程，游戏永久悬停在末幕。** `Game.status` 字段存在但**恒为默认 `"draft"`**（[`game.py:31`](../api/app/models/game.py:31)）——grep 全库无任何一处给 `game.status` 赋新值，它从未被用于「游戏完成」语义（所有 `.status=` 都是 job/delta 的）。[`generate_config_section.md:72`](../api/app/prompts/generate_config_section.md:72)：末幕 `transition_to_next_act` 留空对象；`_can_advance_to_act`([`state_applier.py:2016`](../api/app/services/state_applier.py:2016)) 末幕返回 False，但 `ready_for_next_act` 仍永久算成 True 却无处可去。前端 [`play/page.tsx`](../web/app/games/[id]/play/page.tsx) 无任何终局/谢幕 UI。**影响**：打穿五幕高潮后 GM 仍机械续命，玩家**永远等不到「剧终」**，最有仪式感的时刻反而最泄气。**改进**（成本极低、ROI 极高）：末幕 required 锚点全完成 → 置 `game.status="completed"` → 复用 GM 一次性生成 epilogue（喂 `campaign_contract.emotional_arc` + `truth_map` + 玩家关键抉择历史）→ 前端切「剧终」卡片 + 旅程回顾 + 开新档。

- **[B2 · P0 · 缺失] 无结局变体，玩家几十回合抉择不影响如何收场。** `acts`/`truth_map` 无 outcome/variant/ending 字段，真相是固定单值；`main_quest_path` 是软主线，所有玩家最终汇到同一组锚点；`relationships/known_facts` 有记录但无机制映射成不同结局走向。**影响**：即便补了 B1，所有人、所有抉择都导向同一收场——选择只改「过程的文字」，不改「故事的结构与结局」，叙事重玩价值≈0。**改进**：在末幕/`campaign_contract` 增 `ending_variants`（按关键 relationship 阶段 / 某 hidden_fact 是否触达 / 某 NPC 存活与否分叉），结局生成时按当前 state 选支。这是单人 AI RPG 最低成本的重玩钩子。

- **[B3 · P0 · 不合理] pressure_clock 的「代价」从不兑现——无 tick 计数、无 consequence 触发。** `pressure_clock` 设计含 `tick_condition/consequence`，但运行时无任何代码读取或推进它（[`state_v2.py:39`](../api/app/services/state_v2.py:39) 只把 `location.pressure` 当展示文本透传）；叠加 M2 无失败机制，「拖延的代价」无处兑现。**影响**：压力时钟是纯修辞，玩家很快发现拖延/瞎逛毫无后果，A/B/C/D 之间没有真正的下行风险与权衡。**改进**：给 pressure_clock 真实的回合/事件 tick 计数（存 state），到阈值由 StoryDirector 强制注入 consequence（关闭某线索路径 / 某 NPC 关系恶化 / 某资源锁死）。不必做 Game Over，但**必须有不可逆的局部代价**。

- **[B4 · P1 · 能动性] 所有路径收敛到同一组 required 锚点，无替代/跳过通关。** `_can_advance_to_act`([`state_applier.py:2016`](../api/app/services/state_applier.py:2016))：`all(required_anchor in completed)` 才能转幕，无替代路径；StoryDirector 在 required 未完成时把 `scene_objective` 钉在未完成锚点上。**影响**：故事骨架是单一线性管道，玩家能决定「怎么走过这段」，不能决定「换条路 / 跳过」，长线重玩高度雷同。**改进**：给锚点引入「可替代组」（同幕 N 选 M 即可转幕），或允许 required 锚点有多个互斥 `completion_signal`（战斗解决 vs 谈判 vs 潜行绕过），让方式选择真正改变剧情结构。

- **[B5 · P1 · 能动性受压制] DriftValidator 把「未铺垫的新势力/真相」判 major 重写，但玩家自由输入的发散探索正会触发这条红线。** [`drift_validator.md:7`](../api/app/prompts/drift_validator.md:7) 规则 4 不区分「GM 自己跑偏」与「玩家主动要求」；[`gm_runtime.md`](../api/app/prompts/gm_runtime.md) 规则 6「玩家可自由行动」与规则 26「新势力/地点/Boss 必须已铺垫」自相矛盾，校验层站在规则 26 一边。**影响**：玩家想开辟剧本没预设的支线时被静默拽回，自由输入框是表达自由的**假象**。**改进**：drift_validator 增「玩家来源豁免」——若新内容由 `player_input` 直接驱动且不违反 forbidden_reveals/hidden_facts 边界，则不判 major，允许 GM 即兴扩展为支线。把「忠于剧本」收窄到「不提前剧透真相」，而非「不许长出剧本外的枝叶」。

- **[B6 · P1 · 缺失] 无「地图/可去地点」概念，探索是伪开放。** state 里 `location` 只有 `current/to/from`（单一当前地名字符串），无「已知地点/可前往目的地」结构；lore 的 location 类型是被动召回的背景资料，非玩家可见地图节点；前端只展示一个当前地名。**影响**：世界是线性走廊，玩家无法形成「我想去哪」的心理地图，探索完全依赖 GM 当回合给的出口。**改进**：state 维护 `known_locations`（已解锁地点 + 简述），前端侧栏做「已知/可前往」列表，点击=生成「前往 X」行动。不必做网格地图，只要把「世界有多大、我能去哪」显性化。

- **[B7 · P1 · 能动性受压制] StoryDirector 每回合把 scene_objective 钉在「推进当前幕目标」，玩家纯扮演/停留意图被持续轻推回主线。** [`story_director.md`](../api/app/prompts/story_director.md) 规则 + fallback 硬编码 `gm_instruction="先回应玩家本次行动，再推进当前幕目标"`([`story_director.py:214`](../api/app/services/story_director.py:214))；gm 规则 8 要求每回合都「引出新的行动压力」。虽有规则 31「不要强制带走想停留的玩家」，但默认倾向持续向前推。**影响**：玩家想享受日常对话/关系经营/闲逛时，系统每回合都把 objective 重新指向主线锚点，慢节奏沉浸被推进欲望稀释。**改进**：引入轻量「节奏意图」识别（玩家连续 N 回合纯社交/探索时），允许 StoryDirector 输出 `scene_objective="维持当前情境，不推进主线"` 并暂缓压力升级。

- **[B8 · P2 · 不合理] A/B/C/D 每回合临时生成、瞬时易失，无跨回合承接，选择缺乏路径依赖。** gm 规则 4/5 要求每回合新生成四选项，选了 B 之后上一回合的 A/C/D 永久消失；`open_threads` 记录未解线程但不回流成可选行动。**影响**：决策是瞬时的，被放弃的选项不留「我本可以…」的张力或回访入口，回合之间像独立小品而非累积的抉择链。**改进**：把玩家明确表达过但未执行的意图（放弃的选项 / open_threads）沉淀成侧栏「悬而未决」列表，可一键转为行动。

### C. 体验层 —— 玩家旅程的断点

- **[C1 · P0 · 旅程断点] 开局冷启动：生成完世界后，第一回合是个空白输入框，没有 AI 写的开场白。** [`game_creator.py:21`](../api/app/services/game_creator.py:21) 初始 state `current_turn=0`，不预生成任何开场剧情；前端首回合空状态文案为「还没有回合。输入行动开始第一回合。」**影响**：玩家苦等几分钟生成完世界，进游戏却面对空白框——主角在哪、看到什么、刚发生什么全要自己脑补打字。最该有沉浸感的第一秒最空。**改进**：生成阶段额外产出一段开场序章（200–400 字）写入 turn 0；或进游戏自动触发一次开场回合。

- **[C2 · P0 · 缺失] 游玩主界面看不到自己的「目标」。** [`play/page.tsx`](../web/app/games/[id]/play/page.tsx) 全文无当前幕目标/主线/悬念/任务渲染（已 grep 确认），topbar 只显示回合数+地点+时间；目标只存在于概览页和 status 页。**影响**：RPG 最基本的「我现在该干嘛」在最常驻的页面缺席，隔天回来根本不记得在追查什么。**改进**：play 页侧栏固定显示「当前幕目标 + 1–2 条进行中任务/未解线索」——数据 stateV2 里现成（`quest_log.active`、`story_progress.current_act`），只是没用。

- **[C3 · P0 · 上手门槛] 整个产品零新手引导。** 全仓库无 tutorial/onboarding；play 页直接呈现「行动/对话/叙述/继续」四个模式按钮，但无任何地方解释它们的区别、何时用哪个、自由输入能做什么。**影响**：第一次玩的人（包括隔几个月回来的作者本人）完全靠试，核心玩法契约（我能做任何事、目标是什么）从未对玩家言明。**改进**：首次进 play 页弹一次性引导卡（localStorage 记忆），解释四种输入模式 +「你可以尝试任何行动」；模式按钮加 tooltip。

- **[C4 · P1 · 旅程断点] 生成耗时长（1 outline + 9 分区，全 high reasoning，并发 4）却无 ETA，还把 LLM 思考流/任务 ID 直接糊给玩家。** [`game_generator.py:62`](../api/app/services/game_generator.py:62) `FINALIZE_SECTION_SPECS` 9 个分区全 `reasoning_effort="high"`；前端唯一时间信息是超时错误里的「已等待 15 分钟」，无预估/进度百分比；生成面板默认展开思考过程/字数计数/任务 ID。**影响**：玩家面对无 ETA 的黑盒，不知是 30 秒还是 5 分钟，焦虑劝退首次尝试。**改进**：给明确预期（如「通常 2–4 分钟，正在生成 X/9」），用 9 个分区做确定性进度条；思考过程默认折叠，只露一句人话进度。

- **[C5 · P1 · 缺失] 不满意的世界无法重 roll，只能删库重来。** 生成结果只有「确认并开始冒险」一个出口，无「重新生成 / 换一个」；生成完确认后只能「重新开始当前剧本」（设定不变）或删除游戏。**影响**：AI 生成必有命中率问题，不满意时要么将就玩、要么删掉重走全流程，缺 AI 生成产品标配的「再 roll 一次」。**改进**：生成结果区加「重新生成」（复用已确认采访结果）；进一步可「只重生成角色 / 只重生成五幕」——后端 finalize 已是分区结构，天然支持局部 re-roll。

- **[C6 · P1 · 缺失] 存档无后悔药：无自动存档、无「撤销上一回合 / 回退到第 N 回合」，play 页够不到存档入口。** [`progress_saves.py:66`](../api/app/services/progress_saves.py:66) 是手动整局快照、覆盖式（`load_progress_save` 先 `_clear_runtime_progress` 清空再恢复）；无任何回退机制。**影响**：玩家做了后悔的选择、或 AI 把剧情写崩，唯一退路是事先手动存过档——对每回合 ~70k token、写崩代价很大的游戏，缺最基本的后悔药体验风险高。**改进**：(a) 每回合自动滚动快照（留最近 N 个）+ play 页「撤销上一回合」；(b) 用已有 turns 历史做「回退到第 N 回合」（截断而非全量快照）；(c) play 顶栏加快速存档入口。

- **[C7 · P2 · 不合理] 信息割裂：回顾「关系/历史/目标」要在 status/history/memory/characters 四个整页间横跳，每次整页重载。** 四个独立路由各自全量 `getGame/getTurns`；NPC 关系在 status、立绘在 characters、过往剧情在 history，三处分裂；play 页 inspector 只读且只显示前 3 个角色 / 1 条摘要。**影响**：长期游玩「读档回顾」成本很高。**改进**：play 页内做抽屉/侧滑面板（角色/状态/近期剧情），或嵌一个可展开的「角色+关系+目标」合并视图，减少跳转。

- **[C8 · P2 · 缺失] 沉浸感全靠纯文字，无场景图/音乐/氛围；存了 `portrait_prompt` 却无配图链路消费。** `web/public` 只有 logo；角色头像还要玩家手动上传，AI 不生成；`initial_state` 存了 `portrait_prompt` 但无任何配图生成消费它。**影响**：作为「沉浸式」文字 RPG，氛围营造偏薄。**改进**（体验上限项）：低成本先做 (a) 用每回合 `active_scene.location/time/pressure` 驱动一套氛围底色/光照 CSS 主题切换；愿接图像模型再做 (b) 用 `portrait_prompt` 自动生成立绘、用场景描述生成开场图。

- **[C9 · P2 · 缺失] 「换玩法重开同一个世界」不被支持。** `restart_game_progress`([`progress_saves.py:66`](../api/app/services/progress_saves.py:66)) 只把 state 重置回 `initial_state_json`，设定原样不动；要换玩法只能去 memory 页手改 story_settings 的裸 JSON，或彻底新建一局。**影响**：「同一个世界这次走武力路线」这种正常多周目诉求没有顺手入口。**改进**：概览页/重开流程加「换玩法重开」——复用 worldview + core_characters，只重新生成 `act_plan / action_style_rules / main_quest_path`（后端分区生成天然支持），让玩家选新玩法偏好后局部重 roll。

---

## 3. 做得好的地方（放心清单，不要在这些方向继续过度投入）

- **剧情遵循 / 防剧透**：truth_map / clue_ladder / forbidden_reveals / DriftValidator 体系扎实，AI 跑偏与提前剧透已被有效抑制（Round 16–24）。
- **状态记账正确性**：event-sourcing 重放幂等、数值公式/clamp/level-up 边界全部正确（见 `GAME_SYSTEM_AUDIT.md` §3）。
- **省 token / 可观测**：prefix cache 固化、场景投影、agent_traces + judge 全链路可观测（Round 18–24）。

> 提醒：B5/B7 表明「防跑偏」已到拐点，继续加固是负收益。后续重心应从「让 AI 更听话」转向「让游戏更好玩」。

---

## 4. 优先级裁决与分阶段路线图

> 排序原则：先补「是不是游戏 / 故事完不完整 / 能不能上手」的根（第一梯队），再做需要架构设计的大改（第二梯队），最后是重玩深度与氛围（第三梯队）。每项落地后打 `[x]`，并在 `OPTIMIZATION_PLAN.md` §1 追加对应 Round。

### 第一梯队 — 低成本、立竿见影（建议优先）
- [x] **B1 结局闭环**（Round 33）：末幕 required 锚点全完成 → `game.status="completed"` → `EpilogueGenerator` 生成 epilogue（独立 timeout/fallback）→ 前端「剧终」卡片。
- [x] **C1 开局序章**（Round 33，仅 AI 生成流程）+ **C2 play 页目标条**（Round 33）：建游戏后生成开场写入 turn 0；story 列顶部固定显示当前幕目标 + 锚点进度 + active 任务/线索。
- [x] **C3 首次引导卡**（Round 33）：首次进 play 一次性引导卡（localStorage 记忆）+ 模式按钮 tooltip。

### 第二梯队 — 价值最大、需架构设计（建议作为独立大版本）
- [ ] **A1 轻量判定层**：difficulty → 属性/技能 + roll → outcome 作为硬约束喂 GM。**做完它，A2–A5 一次性全部获得意义。**
- [ ] **A2 数值反哺**：等级/技能进判定加值；关系数值作社交判定修正 + 选项门槛。
- [ ] **B3 压力时钟兑现** + **A3 危机条/失败出口**：tick 计数 → consequence；危机条归零触发剧本化失败。
- [ ] **B5 松绑校验器**：drift_validator 增「玩家来源豁免」，把「忠于剧本」收窄到「不提前剧透真相」。
- [ ] **C5 重 roll** + **C6 后悔药（撤销/回退回合 + 自动存档）**。

### 第三梯队 — 重玩深度与氛围（锦上添花）
- [ ] **B2 结局变体**（按关键 state 分支）+ **B4 锚点可替代组**（多路通关）。
- [ ] **A4 cooldown/severity 生效** + **A5 模式挂判定循环** + **A6 资源稀缺**。
- [ ] **B6 已知地点列表** + **B7 节奏意图识别** + **B8 悬而未决列表**。
- [ ] **C7 play 内信息聚合** + **C8 氛围主题/配图** + **C9 换玩法重开**。

---

## 5. 审查方法、范围与勘误

- **方法**：3 个 general-purpose Agent 并行深审（机制 / 叙事能动性 / 全周期体验），分区不重叠；所有 file:line 证据经主线复核。
- **范围**：只审游戏方向，**未改任何代码**。明确排除工程/测试/性能/token/安全/部署/多人/商业化。
- **勘误记录（保持诚实）**：多 Agent 初稿有一处事实误差——称「`Game` 模型无 `status` 字段」。复核为：**字段存在但恒为默认 `"draft"`，全库无任何 `game.status=` 赋值**（[`game.py:31`](../api/app/models/game.py:31)），从未被用于游戏生命周期。**B1 结论不变，证据反而更精确**（字段在、但是死字段，无需建表即可启用通关态）。
- **落地约定**：改 `app/services/*` / prompt 后必须重建镜像 `docker compose up -d --build api worker web`；后端测试在容器内 `docker compose exec api pytest tests/`；prompt 改动记录规则编号到 `OPTIMIZATION_PLAN.md`。
