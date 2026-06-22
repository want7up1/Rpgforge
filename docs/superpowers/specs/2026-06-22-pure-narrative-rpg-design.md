# 纯叙事化改造：删除全部量化数值，转向小说向 RPG

> 设计 spec · 2026-06-22 · 状态：待用户复核
> 关联：架构审计（个人记忆 `rpgforge-architecture-audit-2026-06`）、`docs/GAME_DIRECTION_AUDIT.md`、Round 44/45/47/51

## 1. 背景与目标

RPGForge 历经 40+ 轮，把唯一玩家可见产物 narrative 建模成"约束满足问题"，GM 退化成履约机器 = 用户反馈的"生硬"。本次做一次方向性收敛：

**删除游戏内全部玩家可见的量化数值，把状态完全用文字维持，做成彻底的叙事向 / 小说向 RPG。**

要删的数值（用户明确清单）：

1. 等级（level）
2. 经验（xp）
3. 属性（六维 attributes）
4. 技能及技能熟练度（skills / mastery）
5. NPC 关系的各种数值（relationship score / stage）

连带删除（它们本质也是"把拖延/失败换算成数字"）：

6. d20 判定层（action_resolver）+ 行动后果卡
7. 危机条 crisis（0–100）+ 压力时钟 pressure_clock（survival_clock 整体）

**核心原则**：不是"删数字"，而是"把每个数字原来承担的功能，改写成一条叙事机制"。删了不补 = 退化；补对了 = 升级。

**采用方案 B**（用户拍板）：映射表替代 + `gm_runtime.md` 正向重写。纯 prompt / 叙事层，不引入任何新的数值机制。方案 C（GM 正文换更强模型）作为 B 落地、观察真实文笔后的后续选项，不在本次范围。

## 2. 已敲定的决策

| # | 决策 | 说明 |
|---|---|---|
| D1 | 删除全部玩家可见数值 | 见 §1 清单（1–7）|
| D2 | 叙事状态结构化存文字 | 关系/状态仍由系统结构化记忆，但值全是文字（如 `status: "对你从猜忌转为并肩"`），**零数字**。保长局一致性，不退回纯散文记忆 |
| D3 | 失败/张力靠叙事机制 | 见 §4。不新增数值机制 |
| D4 | `act_pacing` 保留 | 它是**幕后**导演节奏信号（基于回合数、玩家不可见、非 RPG 数值），删它会复发 Round 51 治的"推不动"。保留 |
| D5 | 失败出口改叙事驱动 | crisis 归零驱动的 defeat 没了 → 由 extractor 语义判定终局失败（布尔信号，类比已有的 campaign_complete），失败结局机器（epilogue）保留、只换触发源 |
| D6 | 无破坏性迁移 | 事件溯源 + rebuild，旧字段休眠。诚实记录 rebuild 行为变化（见 §7）|

## 3. 删除清单（按层）

### 3.1 后端服务
- **`action_resolver.py`**：整文件删（d20 判定层）。
- **`survival_clock.py`**：整文件删（crisis + pressure_clock + crisis→defeat）。
- **`quantified_state.py`**：删 `_apply_xp_event` / `_apply_skill_event` / `_apply_ability_update` / `_apply_level_ups` / `_apply_skill_level_ups` / `_relationship_stage`（数字阶段）/ `_next_level_xp` / `_next_skill_level_xp` / `_mastery`。**保留并去数字化** `_apply_condition_update`（去 severity 数字、留文字 note）、`_apply_relationship_event`（去 score/stage 数字、留文字 status）。
- **`gameplay.py`**：删 `action_resolver` import、`_resolve_action_outcome`、对应 STAGE、`action_outcome` telemetry 与全链路透传。
- **`state_applier.py`**：删 `apply_survival_clocks` 调用（B3+A3 段）。
- **`state_v2.py`**：删 `_crisis_view`、`_progression`、`_skill_view`、attributes 注入（`protagonist_sheet` 里的 level/xp/attributes）、`_relationship_tracks` 的数字 stage。`protagonist_sheet` 收敛为纯文字档案。
- **`game_creator.py`**：删 crisis/pressure/`DEFAULT_PROTAGONIST_ATTRIBUTES`/progression 种子。
- **`script_exporter.py`**：删导出里的 crisis/attributes/progression/skills 段。

### 3.2 Prompt
- **`extract_state_delta.md`**：删 `xp_events` / `skill_events` / `ability_updates` 输出数组 + 规则 7/8；关系/状态提取改"只产出文字事实，不打分"；**新增**：终局失败的 `defeat` 语义上报（类比已有 `completed_anchors` / campaign_complete）。
- **`story_director.md`**：删规则 12（action_check 标注 + 属性）；**新增**定性赌注输出（见 §4）。
- **`gm_runtime.md`**：删 action_outcome 硬约束消费；**新增** yes-but/no-but 结果框架；**正向重写**（见 §5）。
- **`generate_epilogue.md`**：defeat 分支去掉"危机条归零"措辞，改叙事/锚点驱动的败局描述。

### 3.3 Schema / 路由
- **`schemas/state_delta.py`**、**`schemas/turn.py`**：删 `action_outcome`、xp/skill/ability 相关字段。
- **`story_director.py`（StoryDirectorDecision）**：删 `action_check` / `resolved_outcome` 字段；新增定性赌注字段。
- **`routers/gameplay.py`**、**`turn_maintenance_jobs.py`**：删 `action_outcome` 透传；defeat 触发改读 extractor 的叙事 defeat 信号。

### 3.4 前端
- **`web/lib/stateV2.ts`**：删 `ProgressionState`、skills、attributes、crisis、pressure、relationship 数字。
- **`web/lib/gameExperience.ts`**：删 `extractActionOutcome` / `ActionOutcomeView` / 后果卡；删 xp/技能结算段；**新增**散文增量结算段（"[某 NPC]开始把你当自己人"式，无数字）。
- **`web/app/games/[id]/play/page.tsx`**、**`status/page.tsx`**、**`characters/page.tsx`**、**`page.tsx`**：删 crisis 条 / 等级经验 / 属性 / 关系数值的展示。
- **`web/lib/characters.ts`**、**`web/lib/types.ts`**、**`web/lib/generatorBoard.ts`**：去关系/属性数字字段。
- **`globals.css`**：删 crisis 条样式。

## 4. 无数字版张力设计（核心章节）

把删掉数字的"功能"逐条改写成叙事机制：

| 删掉的数字 | 它原来在干的活 | 无数字替代机制 |
|---|---|---|
| d20 / 危机条 | 强制偶尔失败、制造博弈 | ① **Director 定性赌注**（无数字）：每个有不确定性的玩家行动，Director 输出 `risk_note`（本场风险点）+ `cost_if_fails`（失败的具体叙事代价，如"暴露身份/失去某人信任"），替代原 action_check。<br>② **GM yes-but/no-but 框架**：GM 想结果时不问"成功了吗"，而问"这一拍付出什么代价 / 留下什么钩子"——成功必带代价、失败必留转机，而非二元成败。这是写作/即兴经典手法，天生比骰子更小说 |
| 经验/等级/技能 | 玩家"我在变化"的反馈 | 把"变化感"叙事化：回合结算条改散文增量，GM 在质变节点点一笔，不靠 +N |
| 关系分数 | 长局廉价记忆锚 | D2 结构化存文字 + 强化 `narrative_recap` 携带关系/处境的散文增量 |
| 压力时钟 | 推进节奏 | `act_pacing` 保留（D4）|
| 危机归零 → defeat | "输"的出口 | D5：extractor 语义判定终局失败 → defeat 布尔 → epilogue 败局结语 |

**最吃重的是第一行的 yes-but/no-but 框架**——它从根上消解"没有骰子会不会变有求必应"的最大风险：规则不再奖励"让玩家成功"，而是要求每一拍都带代价或钩子，张力自带。这是 spec 落地时 prompt 设计的重点，不是顺手删删。

## 5. 文笔升级（把省下的预算再投资）

删数字释放了 prompt 注意力与 token，回投三处（按 ROI）：

1. **`gm_runtime.md` 正向重写**（ROI 最高）：审计点名根因——34 条里 26 条是负向禁令。删掉数值合规后，把"禁止 X"翻成正向工艺锚点（演而非讲 / 对白推进剧情 / 感官具体 / 角色内心）。删数字腾出的篇幅正好给它。
2. **叙事工艺层加权**：Round 45 已把 voice/情绪弧提进 system 稳定前缀；数字海退潮后其相对注意力权重自然上升，可再细化。保留 narrative_recap 连续性轨 + recent_turns 梯度承接（防退化的家底，全留）。
3. **（后续·方案 C）** GM 正文换更强模型——天花板最高，但引入模型/成本变量，本次不做。

## 6. 数据流（改造后）

```
玩家输入
  → StoryDirector（产出 scene_objective + 定性赌注 risk_note/cost_if_fails，不再有 action_check）
  → GM（读定性赌注 + act_pacing + 叙事状态，用 yes-but/no-but 写下一拍，自主决定成败与代价）
  → output_observer（剧透整串门，保留）
  → 返回玩家
  → [异步] StateExtractor（产出文字状态事实 + completed_anchors + defeat 语义信号，不再有 xp/skill/ability/score）
  → state_applier（应用文字 delta，不再调 survival_clock / action_resolver）
  → maintenance（campaign_complete→victory / defeat→defeated，触发 epilogue）
```

## 7. 迁移与向后兼容

- **无破坏性迁移**：事件溯源 + rebuild。旧存档 state JSON 里的 skills/xp/progression/attributes/crisis/pressure/action_outcome/relationship-score 字段，新代码不再读写 → 自然休眠，无需 migration（同 Round 47/49 模式）。
- **诚实记录的 rebuild 行为变化**：① 旧存档 rebuild 后不再有 crisis/pressure → 危机驱动的 defeat 不再复现（改由叙事 defeat 信号，旧回合无此信号 → 旧局默认不 defeat，更宽容、不崩）。② 关系/状态投影从数字变文字，前端展示变化但不报错。
- **结构化记忆键保留**：conditions / relationships / story_progress / anchors / quests 的容器键保留，只是值去数字化。

## 8. 影响文件清单（实施核对用）

后端服务 8 · Prompt 4 · Schema/路由 4 · 前端 ~9 = **约 25 文件**。详见 §3。

## 9. 分批实施（ROI + 向后兼容）

- **批 1（后端核心）**：删 action_resolver / survival_clock / quantified_state 数值段；改 state_v2 / state_applier / gameplay / game_creator；改 schema/路由；defeat 触发改写。跑通容器 pytest + ruff。
- **批 2（Prompt + 张力设计）**：extract_state_delta / story_director / gm_runtime（含正向重写 + yes-but 框架）/ generate_epilogue。这批是文笔成败所在，单独验证。
- **批 3（前端清理 + 散文结算）**：删数值展示，加散文增量结算段。eslint/vitest/tsc/next build。

每批向后兼容、无迁移，可独立部署。

## 10. 测试与验证

- TDD：容器内 `pytest tests/` + `ruff check app tests`；前端 `eslint .` / `vitest` / `tsc --noEmit` / `next build`。
- 重点守护测试：① state_applier 不再调 survival_clock（防残留）；② extractor defeat 信号 → maintenance defeated 链路；③ 旧存档 rebuild 不崩、不再产出数字字段；④ quantified_state 关系/状态去数字化后仍正确 upsert 文字。
- Docker 重建 api/worker/web + 真实游玩冒烟：读一段、做选择、看是否仍有失败/代价/张力、确认无数字泄漏到玩家侧。

## 11. 不做 / 风险 / 已知取舍

- **不做**：换正文模型（方案 C，后续）、新增任何数值机制、改事件溯源/迁移框架。
- **最大风险**：无骰子后 GM 滑向"有求必应、张力软掉"。缓解 = §4 yes-but 框架 + Director 定性赌注 + §5 正向重写；**须真实游玩验证规则遵守度**，纯函数测不了文笔。
- **次风险**：长局关系/状态文字漂移（数字记忆锚更稳）。缓解 = D2 结构化 + narrative_recap 强化。
- **取舍**：玩家失去"升级/+经验"的即时正反馈快感；本设计认为这与"小说向"目标一致（小说不发经验值），用散文质变点替代。
