# 新增设定 AI 补全 —— 设计文档

- 日期：2026-06-05
- 主题：看板「新增设定项」时，用户只填标题/名称，AI 参考精简剧本大纲补全其余字段
- 状态：已与用户对齐，待实现

## 1. 背景与动机

刚完成「全看板统一字段规格」后，所有可新增数组项（角色/幕/主线节点/机制/行动风格/素材）的新增表单都走同一套 `newItemBlock` + 完整字段。但字段一多，人工逐项填写负担重。诉求：**用户只填标题/名称，AI 按该剧本的大纲把其余字段补成合理建议**，用户可改后保存。

## 2. 目标 / 非目标

**目标**
- 在**某个游戏的设定页**（`/games/[id]/settings`）的「新增设定」弹窗里，提供「✨ AI 补全」。
- 用户填好身份字段（标题/名称）后点一下，AI 参考**精简剧本大纲**补全其余字段，直接填入表单（用户可改）。
- 覆盖全部 6 类可新增数组项。
- 新增 LLM 调用满足项目硬约束：**独立 timeout + fallback**；prompt 精简、系统提示稳定以吃 DeepSeek 前缀缓存省 token。

**非目标（YAGNI）**
- 不支持炼金工坊 `/workshop`（全局模块库无所属剧本、无大纲可参考）。
- 不做「编辑已有条目」的补全，仅「新增」。
- 不做整条剧情线生成、不做逐字段单独采纳、不做预览确认弹层（直接填入表单）。
- 不碰主回合链路 / 不动 gameplay Agent。

## 3. 现状复用点（实现依据）

- `api/app/services/deepseek_client.py` —— 现有 LLM client。
- `api/app/services/module_adapter.py` —— **可直接仿照的模板**：单次 LLM 调用 + 独立 timeout（`MODULE_ADAPT_TIMEOUT_SECONDS`）+ 多重 fallback（失败/超时/解析失败/结构漂移 → 退化）。
- `api/app/services/story_settings.py` —— 剧本设定字段定义（生成"目标字段清单"的来源）。
- `api/app/routers/games.py` —— 已有 `/api/games/{id}/settings-guide-export` 等游戏维度端点，新端点并入此处。
- 前端：`web/lib/generatorBoard.ts` 的 `ITEM_FIELD_SPECS`（每类数组要补的字段）、`newItemBlock`、`BlockDetailModal`、`SettingsBoard`、`PlotMasterDetail`、`web/lib/api.ts`。

## 4. 设计

### 4.1 各数组的「身份字段」与「待补字段」

身份字段（用户必填，AI 不覆盖）；待补字段 = 该类 `ITEM_FIELD_SPECS` 去掉身份字段后的其余字段：

| array_key | 身份字段（必填） | 待补字段（AI 生成） |
|---|---|---|
| `core_characters` | `name` | role/identity/aliases/description/appearance/desire/fear/leverage/relationship_arc/dramatic_function/public_limit/portrait_prompt/visibility |
| `act_plan` | `title` | objective/dramatic_question/must_hit_beats/allowed_reveals/forbidden_reveals/completion_anchors/transition_to_next_act |
| `main_quest_path` | `title` | objective/act_id/player_visible/completion_signal/optional |
| `core_mechanics` | `name` | rule/visibility |
| `action_style_rules` | `name` | triggers/rule/priority/enabled |
| `story_material_library` | `title` | type/keywords/triggers/priority/always_on/visibility/public_info/gm_secret/content/usage/enabled |

> `act_plan`/`main_quest_path` 的内部 `id` 不在补全范围（仍由 `generateItemId` 自动生成）。`main_quest_path.act_id` 由前端用当前选中幕预填，AI 不必动（若 AI 返回则忽略，以前端预填为准）。

### 4.2 后端

新服务 `api/app/services/item_suggester.py`（仿 `module_adapter.py`）：

- 输入：`array_key`、用户 `draft`（含身份字段）、game 的 `story_settings`（从 `game.config` 取）。
- **精简大纲**（控制 token）：拼装一段简短文本，仅含
  - `game_profile`：title / genre / tone
  - `story_core`：premise / central_mystery / main_goal / emotional_arc / narrative_style
  - `worldview.summary`（截断到一句）
- **目标字段清单**：按 `array_key` 取 4.1 的待补字段，附每字段一句话中文说明（来源：`story_settings.py` 字段定义 / 一份精简字段说明常量）。
- 调 `deepseek_client`，要求返回严格 JSON `{字段: 值}`；**系统提示固定**（吃前缀缓存）。
- **独立 timeout** `SUGGEST_ITEM_TIMEOUT_SECONDS`（~40s）。
- **fallback**：超时 / 调用失败 / JSON 解析失败 / 返回结构漂移（非 dict、字段越界）→ 返回空 `{}`（不抛错），前端据空结果提示"AI 补全失败，请手动填写"。
- **过滤**：返回值剔除身份字段与不在待补清单里的键，保证不覆盖用户输入、不写脏字段。

新端点 `POST /api/games/{game_id}/settings/suggest-item`：
- body：`{ "array_key": str, "draft": {…} }`
- 校验 `array_key` 合法（在 6 类内）、game 存在。
- 返回：`{ "fields": {…} }`（补全字段，可能为空）。
- 失败兜底走 service 的 fallback（端点本身不 500，除非 game 不存在）。

### 4.3 前端

- `web/lib/api.ts`：加 `suggestItem(gameId, arrayKey, draft) → Promise<{ fields: Record<string, unknown> }>`。
- `BlockDetailModal`：当传入可选 `aiSuggest` 回调 prop 时才显示「✨ AI 补全」按钮（不传则不显示——天然实现"仅游戏设定页有、工坊没有"）；
  - 仅当身份字段非空时可点；点击 → loading → 调 `aiSuggest(drafts)` → 把返回 `fields` 合并进 `drafts`（**用户已填值优先，不被覆盖**）。
  - 失败 → 行内提示文案，不影响继续手动填写与保存。
- 接入点：`SettingsBoard` 与 `PlotMasterDetail` 在游戏设定页渲染新增弹窗时，把 `aiSuggest` 回调（内部调 `suggestItem(gameId, …)`）传给 `BlockDetailModal`。**仅游戏设定页传该回调**；工坊页不传 → 按钮不显示。

### 4.4 数据流

```
新增弹窗(填 name/title) --点击--> aiSuggest(gameId, arrayKey, draft)
  --> POST /settings/suggest-item
  --> item_suggester: 精简大纲 + 待补字段清单 + draft --DeepSeek--> {fields}
       (超时/失败/漂移 → {})
  --> 前端 merge 进 drafts(用户值优先) --> 用户可改 --> 保存(原有 onAddItem 链路)
```

## 5. 文件清单

- 新增 `api/app/services/item_suggester.py` —— 补全 service（含大纲组装、字段清单、LLM 调用、timeout/fallback、结果过滤）。
- 修改 `api/app/routers/games.py` —— 加 `POST /games/{id}/settings/suggest-item`。
- 修改 `api/app/schemas/`（相应 schema 文件）—— 请求/响应模型。
- 新增 `api/tests/test_item_suggester.py` —— service 单测（mock LLM client）。
- 修改 `web/lib/api.ts` —— `suggestItem`。
- 修改 `web/components/board/BlockDetailModal.tsx` —— 「✨ AI 补全」按钮 + loading/失败态。
- 修改 `web/components/board/SettingsBoard.tsx` / `PlotMasterDetail.tsx` —— 传 `aiSuggest` 回调（仅游戏设定页）。

## 6. 测试

- 后端（**容器内 pytest**，本地无 Postgres）：
  - 正常：mock LLM 返回合法 JSON → service 返回过滤后的字段。
  - fallback：超时 / 调用异常 / 非 JSON / 非 dict / 含越界字段 → 返回 `{}` 或剔除越界键，不抛错。
  - 大纲组装：只含约定的精简字段，不泄漏全量 settings。
  - 不覆盖身份字段：draft 的 name/title 不被返回值覆盖。
- 前端：逻辑轻（触发 + merge + loading），无 RTL，靠手动验证。

## 7. 风险与注意

- **prompt 文件 / 规则新增**：本功能新增一段系统提示，需在 `OPTIMIZATION_PLAN.md` 记录（新 prompt 名称/用途）。
- **token 控制**：大纲必须精简、系统提示固定；避免把全量 story_settings 塞进 prompt。
- **fallback 不阻断**：AI 失败绝不能挡住用户手动新增；按钮失败仅提示，不影响保存链路。
- **隐私**：测试与文档一律用占位剧本数据，严禁真实剧本入仓。
- 完成后在 `OPTIMIZATION_PLAN.md §1` 追加 Round 条目。
