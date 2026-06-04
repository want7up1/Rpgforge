# 创建冒险页重设计：设定看板 + 分类 Tab + 改动闪烁

- 日期：2026-06-04
- 范围：前端 `web/app/games/new/page.tsx` 重设计为主，配套一处后端 prompt 调整
- 状态：设计已与用户逐块确认，待写实现计划

## 1. 背景与痛点

当前「创建冒险」页是两栏布局（左：想法输入 + 对话记录；右：生成流程 + 已确认设定折叠卡 + 生成结果蓝图 + 原始 JSON）。用户精修剧本时暴露 5 个痛点：

1. **对话堆叠埋没最新**：设定确认是聊天，消息一条条向下堆，越聊越长，最新回复沉到底部看不到。
2. **设定不可浏览**：生成出来的剧本（机制/角色/幕/素材/强约束）没有结构化入口，只有几个字段的蓝图或一坨 JSON。
3. **进度不清**：生成世界时不知道进行到哪、还剩多少。
4. **改一处要重来**：确认阶段想改某条需求只能重新对话；生成世界后想微调一个角色/机制只能整体重 roll。
5. **思考流太吵**：流式 reasoning/正文默认铺屏，干扰阅读。

## 2. 目标与非目标

**目标（第一期 P1）**
- 把「已收到/已生成的设定」做成可浏览、可点开、可手动编辑的**分类 Tab 看板**。
- 对话退居底部停靠条，不淹没设定；最新回复一句话摘要常显。
- 本轮对话/生成改动了哪些 → 以 **+N 角标 + block 闪烁 + 变更摘要条**直观提示。
- 手动编辑的 block 被系统**锁定**，后续对话/生成不会改回，但仍作为上下文供 AI 联动生成其它内容。
- 生成进度以 **Tab 逐个点亮**表达；思考流默认收起。

**非目标（P1 不做，留后续）**
- 「🔄 单独重生成此 block」（需新后端接口）——P1 只做手动编辑。
- 拖拽式「设定积木库」跨剧本复用（独立特性，另开 spec）。
- 手动建草稿入口（`createManualGame`）保持现状不动。

## 3. 整体布局（方案 A：设定看板为主 + 底部对话停靠）

```
┌─ 创建冒险  · 步骤条[想法→确认→生成→审阅] ───────────────┐
│ 变更摘要条：本次更新了 角色(+1)、约束(必须遵守+2)  [点角标跳转] │
│ ┌ Tab 栏 ────────────────────────────────────────────┐ │
│ │ ①世界与基调4  ②角色5 +1  ③剧情3  ④机制3  ⑤约束红线4 +2  ⑥素材12 │ │
│ └────────────────────────────────────────────────────┘ │
│ ┌ 当前 Tab 的 block 网格（卡片：图标 + 标题，可点开） ──────┐ │
│ │ [🌍世界观] [🎯核心悬念] [🎭基调] [✨爽点] …               │ │
│ │ 生成中显示骨架占位；刚改的块闪烁高亮 + "刚更新"           │ │
│ └────────────────────────────────────────────────────┘ │
│ ┌ 底部对话停靠条（桌面可拖高，移动端固定） ────────────────┐ │
│ │ 💬 引导：已记下…（最新回复一句话摘要）       [⌃ 历史]    │ │
│ │ [追加要求 / 修正方向… ____________________]   [发送]     │ │
│ └────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

- 看板是页面主体；对话是手段，退居底部。
- 「⌃ 历史」点开为**向上滑出的面板**，显示完整对话历史；再点收起。
- 底部停靠条桌面端**可拖动调高**（拖把手），移动端固定高度。

## 4. 分类（6 个顶部 Tab）

Tab 切换（非折叠滚动）。每个 Tab 显示该类 block 数量；本轮有改动时显示 `+N` 红色角标（脉动）。

| # | Tab | 收纳的 story_settings 字段 | 备注 |
|---|---|---|---|
| ① | 世界与基调 | `game_profile`(标题/类型/基调/logline)、`worldview`、`story_core` 的 premise/core_fantasy/central_mystery/main_goal/emotional_arc/narrative_style | 对话阶段 story_background/core_premise/tone 落这里 |
| ② | 角色 | `core_characters[]`（每个角色一个 block） | 对话阶段通常为空，生成时填充 |
| ③ | 剧情结构 | `act_plan[]`（每幕一个 block，含锚点）、`main_quest_path[]` | |
| ④ | 玩法机制 | `core_mechanics[]`、`action_style_rules[]` | 对话阶段 playstyle_preferences 落这里（粗） |
| ⑤ | 约束与红线 | `hard_rules.*`、`story_core` 的 must_preserve/must_not_become/forbidden_drift/canon_terms；对话阶段的 must_include/forbidden_content | **单独配色（橙/红）**，最醒目 |
| ⑥ | 素材库 | `story_material_library[]` | |
| ⑦ | 高级（可折叠，低优先） | `generation_parameters`（篇幅参数） | 默认收起，避免噪声 |

**统一看板贯穿两阶段**：设定确认阶段，coarse 的 `confirmed_requirements`（6 字段）主要填充 ①④⑤；生成世界阶段，完整 `story_settings` 填满全部 Tab。同一组件、同一分类，进度天然分层。

## 5. 改动指示（diff + 角标 + 闪烁 + 摘要条）

- **计算方式**：每次对话/生成返回完整设定后，与上一份做浅层 diff，按字段归类到 6 个 Tab，统计每类新增/变更条数。
  - 对话阶段：diff 前后 `confirmed_requirements`。
  - 生成阶段：首次生成把所有非空类标为"新"；重新生成则 diff 前后 `story_settings`。
- **角标**：受影响 Tab 显示 `+N`（数量，非红点），脉动动画。
- **block 闪烁**：切进受影响 Tab，变更的 block 闪烁高亮约 1 秒并标"刚更新"。
- **变更摘要条**：看板顶部一条「本次更新了：角色(+1)、约束(必须遵守+2)」，点角标/条目可跳到对应 Tab/block。
- **持续期**：**当次会话常驻**（不自动淡出）；**下次会话/生成时清空并重新计算**。

## 6. 点开 block：详情/编辑（居中弹窗 Modal）

点 block → 居中 Modal：
- **查看**该 block 全部字段（不再只看蓝图 6 字段或啃 JSON）。
- **编辑**任意字段直接改 → 保存。列表型字段（如角色的 aliases、机制的 triggers）支持增删行。
- **删除**该 block。
- **🔓 解锁/恢复 AI 原值**：已手动改过的 block 显示此按钮，点了恢复 AI 最近一次生成的值并解除锁定（防手抖改错）。
- P1 **不含**「🔄 重新生成此 block」。

Modal 关闭后回到看板；被编辑的 block 标「✏ 已手动修改」。

## 7. 手动编辑的锁定语义（行为契约）

- 任何手动编辑 → 该 block/字段标记为**用户锁定**（`✏ 已手动修改`）。
- 锁定值在后续对话/生成时，作为**用户权威值**传给 AI：
  - AI **不得覆盖/改回**该值（即使对话历史里是旧值）。
  - AI **仍须读取并借鉴**该值，让其它新生成内容与之**联动一致**（剧情是联动的；例：用户把"红伞女人"改为"黑伞女人"，AI 后续生成的传说/线索须围绕"黑伞"展开）。
  - 锁定只防覆盖，不阻止 AI 新增其它内容。
- 「🔓 解锁/恢复 AI 原值」可解除锁定。
- 「确认并开始冒险」时，存入存档的是**用户编辑后的版本**（`generatedConfig` 已含手改），不是 AI 原版。

**实现要点**：
- 前端维护一份「锁定字段路径集合」（locked paths），编辑即加入，解锁即移除。
- 对话阶段：把锁定后的 `confirmed_requirements` + `locked_fields` 一起发给 `createGeneratorChatJob`；`generator_interview.md` 增加规则——对 `locked_fields` 列出的字段，保持原值不变、仅作上下文参考，可继续补全其它字段。
- 生成阶段：finalize 已接收 `confirmed_requirements` 作为输入，使用用户编辑后的值即可；如需更强保证，同样透传 locked 标记，prompt 声明其为 ground truth。
- 编辑生成后的 `story_settings` block 仅改前端 `generatedConfig`，`createGeneratedGame` 原样提交，**无需新后端接口**。

## 8. 生成进度 + 思考流

- **进度 = Tab 逐个点亮**：finalize 的分段生成（outline + 各 section）映射到 6 个 Tab。每类：待生成（灰）/ 生成中（转圈）/ 完成（✓）。附「已生成 N/6 类」文字。
  - 复用现有 `section_update_callback(key,label)` 的分段事件，把 key/label 映射到 Tab。
- **思考流默认收起**：现有 reasoning/正文双流塞进「🧠 查看 AI 思考过程」`<details>`，默认 closed；想看才展开，不再铺屏。
- 顶部步骤条（想法→确认→生成→审阅）保留，作为宏观阶段指示。

## 9. 组件拆分（高内聚、可独立测试）

新增/重构组件（建议放 `web/components/generator/`）：

- `SettingsBoard`：看板容器，管 Tab 状态 + 当前 Tab 内容 + 变更摘要条。
- `BoardTabs`：Tab 栏，渲染分类 + 数量 + `+N` 角标。
- `BoardBlockGrid` + `BoardBlockCard`：某 Tab 的 block 网格与卡片（含骨架态、闪烁态、锁定标记）。
- `BlockDetailModal`：查看/编辑/删除/解锁。
- `ChatDock`：底部对话停靠条（输入 + 发送 + 最新回复摘要 + 历史触发）。
- `ChatHistorySheet`：上滑历史面板。
- `GenerationProgress`：Tab 点亮式进度 + 思考流折叠。
- 纯函数 `lib/generatorBoard.ts`：
  - `buildBoardModel(confirmedRequirements | storySettings)` → 6 类的 block 列表（单一数据映射来源）。
  - `diffBoard(prev, next)` → 每类变更计数 + 变更 block id 集合。
  - 锁定路径工具：`applyEdit`、`lockPath`、`unlockPath`、`isLocked`。

`buildBoardModel` 同时吃 coarse 的 `confirmed_requirements` 和完整 `story_settings`，输出同一种 BoardModel，保证两阶段共用一套渲染。

## 10. 数据流与状态

页面状态在 `NewGamePage`：
- `idea`、`history`、`confirmed`（confirmed_requirements）、`generatedConfig`、`lockedPaths`、`lastChange`（diff 结果）、`activeTab`、进度态。
- 对话：`handleChat` 返回新 `confirmed` → `diffBoard(prevConfirmed, newConfirmed)` 算 `lastChange` → 更新角标/闪烁；锁定字段在请求里透传。
- 生成：`handleFinalize` 流式分段 → 更新 `GenerationProgress`；完成得 `generatedConfig` → 切换 BoardModel 数据源到 story_settings，整体标"新"。
- 编辑：Modal 保存 → 改 `confirmed` 或 `generatedConfig` 对应路径 + `lockedPaths` 加入。
- 创建：`createGeneratedGame(generatedConfig)`（已含手改）。

## 11. 后端改动（最小）

- `app/prompts/generator_interview.md`：新增规则——请求中携带的 `locked_fields`（用户已手动确认的字段）必须原值保留、不得重写，仅作上下文参考；其余字段照常抽取/补全。
- `app/schemas/generator.py`：`GeneratorChatRequest` 增加可选 `locked_fields: list[str]`（默认空，向后兼容）。
- finalize 侧：若透传 locked 标记，`generate_config_*` prompt 声明其为 ground truth（可选，P1 可仅靠"使用编辑后的 confirmed_requirements"达成）。
- **无新增 LLM 调用、无新表、无新业务端点**。遵守 CLAUDE.md：改了 prompt 记录规则编号（在 OPTIMIZATION_PLAN.md）。

## 12. 测试

- 前端纯函数单测：`buildBoardModel`（coarse / 完整两种输入）、`diffBoard`（新增/变更/无变化）、锁定路径增删与"恢复 AI 原值"。
- 组件交互：Tab 切换、角标渲染、Modal 编辑保存回写、锁定标记显示、历史面板上滑。
- 后端：`generator_interview` 携带 `locked_fields` 时返回的 confirmed_requirements 保留锁定字段原值（占位符数据，遵守剧本隐私）。
- `next build`（tsc + lint）通过；后端 `pytest` 在容器内跑。

## 13. 分期

- **P1（本次）**：看板 + 6 Tab + 改动指示 + Modal 查看/编辑/删除/锁定/解锁 + 底部对话停靠（可拖高）+ 上滑历史 + 进度点亮 + 思考收起 + 锁定 prompt。
- **P2+**：单独重生成此 block；设定积木库跨剧本复用；进度更细的子项流。

## 14. 已决决策（避免反复）

- 布局 A（看板为主 + 底部停靠）。
- 6 分类 + 高级类；**顶部 Tab 切换**（非折叠）。
- 角标用 **+N 数量**；变更指示**当次会话常驻、下次会话重算**。
- block 详情用**居中 Modal**。
- P1 **只手动编辑**，不做单独重生成。
- 手改即**锁定**：不被改回，但 AI 仍借鉴其值联动生成；配「解锁/恢复 AI 原值」。
- 底部对话停靠条**桌面可拖高**；历史为**上滑面板**。
