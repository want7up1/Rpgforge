# 看板成为完整设定编辑面（特性3）

- 日期：2026-06-04
- 范围：前端 `web/`（看板字段层重构 + 新增 block）；后端零改动（复用 `PATCH /games/{id}/config` + validate + 版本快照）
- 状态：设计已与用户逐块确认（含 HTML 示意图），待写实现计划
- **依赖**：特性1/2 已在 main（`generatorBoard.ts` 看板 + `BlockDetailModal` + 设定页 + 工坊）。

## 1. 背景与目标

当前看板的 block 是**手写白名单**（`buildFromSettings` 逐字段硬编码），导致：① 覆盖不全——`home_base`（整块）、`worldview.public_facts/hidden_facts`、`act_plan.completion_anchors` 等看不到也改不了；② 易漂移——schema 加字段需手动同步（同 Round 35 的"填写说明"漂移）。

**目标**：让看板成为**完整的设定编辑面**——所有 story_settings 项都能以 block 形式**清晰展示 + 编辑**，并支持在已有剧本里**手动新增数组项**（新角色/机制/幕/素材/主线/行动风格）。

**非目标**：不改后端 schema；不改 block 的分类归属与粒度（保持 story_core 标量逐项、红线桶逐桶等，以免打乱已用的"按块提取模块"细粒度）；不做 JSON-only 编辑（要友好控件）。

## 2. 已确认决策

- 字段层改**数据驱动**：字段从实际数据自动派生（数据里有的键都出控件）+ 一份 placement 配置（title/icon/分类/类型提示）。自动全覆盖、不漂移。
- **字段类型系统**（P1 全做友好控件，json 仅兜底）。
- 嵌套结构 P1 就做友好子编辑器（objectList/keyValue），不是 JSON 兜底。
- 空固定块**默认折叠**；看板顶部「显示空设定项」开关打开后灰显可填。
- 「新增」= 数组项；固定项靠编辑（含空块）。
- 块粒度**保持现状**；补齐缺口（home_base / worldview facts / 各 item 缺失字段 / completion_anchors 等）。
- 主场景设定页；①② 改共用组件，生成页看板自动受益。

## 3. 字段类型系统

`BoardFieldType` 扩展为：

| type | 数据形态 | 控件 |
|---|---|---|
| `text` | 短字符串 | 单行输入 |
| `textarea` | 长字符串 | 多行输入 |
| `number` | 数值 | 数字输入 |
| `bool` | 布尔 | 勾选框（如 anchor.required / enabled / always_on） |
| `stringList` | `string[]` | 可增删的条目（每行/每 chip 一条） |
| `objectList` | `Record[]`（对象数组） | 可增删的**子卡**，每张卡是该对象的子字段表单（带 `itemFields` 子字段规格）|
| `keyValue` | 开放对象（无固定 schema，如 `home_base`/`transition_to_next_act`） | 可增删的「键→值」行 |
| `json` | 兜底：识别不了的结构 | 带解析校验的 JSON 文本框 |

`BoardField.value` 放宽：`string | string[] | number | boolean | Record<string,unknown> | Record<string,unknown>[]`。
`BoardField` 增加可选 `itemFields?: SubFieldSpec[]`（仅 objectList 用，描述每个子对象渲染哪些子字段及其类型）。

**字段类型推断**（数据驱动）：对一个值——string→text/textarea（按长度/已知键）、number→number、boolean→bool、`string[]`→stringList、`object[]`→objectList、已知开放对象→keyValue、其余对象/异形→json。已知键（如 completion_anchors 的子字段、character 的字段）由 placement 配置给出更精确的 label/type。

## 4. 数据驱动的 block 生成

`buildFromSettings` 重构为：placement 配置（声明每个顶层键/桶 → 分类、title、icon、是否数组、item 身份键、已知字段规格）驱动遍历，**字段从实际数据派生**（配置只决定归类与精修，不决定"有没有"——数据里出现的键一律出字段，杜绝遗漏）。

- 块粒度不变：game_profile/worldview/home_base/generation_parameters 各一块（多字段对象）；story_core 标量逐项块；hard_rules/story_core 红线各桶一块（stringList）；core_characters/act_plan/main_quest_path/core_mechanics/action_style_rules/story_material_library 每项一块。
- 补齐：`home_base` 块（advanced 或 world，见 §7 待定→定为 world 末尾）、worldview 块加 public_facts/hidden_facts 字段、各 item 块补齐缺失字段、act 块加 completion_anchors(objectList)/allowed_reveals/forbidden_reveals(stringList)/transition_to_next_act(keyValue)/must_hit_beats(stringList)。
- **id/address 兼容**：沿用现有 `block.id`（`${arrayKey}:${idValue}` / `${parent}.${key}` / 顶层键）与 address 规则不变（保护生成页 diff 与模块提取）。延续特性1 修复的"同分类内 id 去重"。

## 5. 编辑与无损回写

`BlockDetailModal` 按 `BoardField.type` 渲染对应控件（含 objectList 子卡增删、keyValue 键行增删、bool 勾选、json 校验）。
`writeBlockFields` 扩展为按类型把 `BoardField.value` 写回 source 对应位置：
- 现有 confirmedField/settingsScalar/settingsStringList/settingsItem 路径不变；
- 新类型的 value（number/bool/对象/对象数组）直接作为该字段值写入（`fieldsToRecord` 已是按 key 赋值，天然支持）；
- **无损契约**：只写该块涉及的字段，源对象其余键原样保留（深拷贝 + 按 key 覆盖）。
- 保存 → `updateGameConfig(story_settings_json)` → 后端 validate（同名/同 id/anchor 唯一）失败则 400 → 前端提示并保留编辑。

## 6. 空块折叠 + 手动新增

**空块折叠**：`SettingsBoard` 加 `showEmpty` 状态（默认 false）+ 顶部「显示空设定项」开关。默认 `BoardBlockGrid` 过滤掉"全字段空"的固定块；开关打开则灰显空块（点击进入编辑/填写）。数组项的「＋新增」始终显示。

**手动新增数组项**：
- 每个含数组的分类底部渲染「＋新增X」入口：角色（core_characters）、素材（story_material_library）各 1；剧情（act_plan / main_quest_path）、机制（core_mechanics / action_style_rules）各 2。约束/世界/高级无数组项 → 无新增。
- 点击 → 复用 `BlockDetailModal` 的**空白表单**（按该数组 item 的字段规格生成空字段；身份字段必填：name 或 id/title）。
- 提交 → 校验身份非空 + 不与现有同名/同 id 冲突（冲突提示）→ 追加进对应数组 → 调用方落地：设定页 `updateGameConfig`(+版本快照)；生成页改本地 `generatedConfig`。
- 新增由调用方传入回调（`onAddItem(arrayKey, item)`），`SettingsBoard` 不直接持久化（与现有 onEditBlock/onDeleteBlock 一致的受控模式）。

## 7. 组件/接口

- `web/lib/generatorBoard.ts`：重构 `buildFromSettings`（placement 配置 + 字段推断）；扩 `BoardFieldType`/`BoardField`；扩 `writeBlockFields`；新增 `createEmptyItem(arrayKey)`（按字段规格产空 item）与 `appendItem(settings, arrayKey, item)`。纯函数，vitest 覆盖。
- `web/components/board/BlockDetailModal.tsx`：按类型渲染控件（新增 number/bool/objectList/keyValue/json 渲染器；objectList/keyValue 子组件可拆到 `components/board/fields/`）。
- `web/components/board/BoardBlockGrid.tsx`：空块过滤 + 「＋新增」入口（接 onAdd 回调）。
- `web/components/board/SettingsBoard.tsx`：`showEmpty` 开关 + `onAddItem` 透传 + 新增表单（复用 BlockDetailModal 的空白态）。
- 设定页 `app/games/[id]/settings/page.tsx`：接 `onAddItem`（appendItem → persist）。生成页可后续接（P1 设定页为主，生成页因共用组件，新增入口默认开但回调改本地草稿；若工作量大可 P1 仅设定页接 onAddItem，生成页只享受展示/编辑增强）。

## 8. 风险与边界

- **共用 `generatorBoard.ts`**：保持 block.id/address 规则兼容，避免破坏生成页改动闪烁 diff（id 稳定）与模块提取（`buildModulePayload` 按 address 读数）。
- **无损回写**：新类型回写必须不丢源数据其余键；objectList 改 anchors 不得产生重复 anchor id（靠 validate 兜底 + UI 提示）。
- **新增项身份**：必填 + 重名校验，避免 validate 400。
- **空块判定**：固定块"空"= 全字段为空/空数组；判定要稳定（用于折叠）。
- **json 兜底**：解析失败不落地、提示。

## 9. 测试

- vitest（纯函数）：`buildBoardModel` 对各形态字段（含 number/bool/objectList/keyValue）的覆盖与类型推断；`writeBlockFields` 各类型**无损往返**（改一个字段其余键不变）；`createEmptyItem`/`appendItem` 追加正确；空块判定。
- 组件层靠 `tsc --noEmit` + `next build` + `npm run lint`（0 error/0 warning）。
- 后端无改动；现有 `updateGameConfig` 路径与 validate 复用。
- 手动走查：空块开关、各类型编辑无损保存、新增角色/机制/幕/素材、completion_anchors 子卡增删、重名/非法提示、版本回滚。

## 10. 分期

- **P1（本次）**：数据驱动全覆盖 + 全部字段类型友好控件（objectList/keyValue/number/bool）+ 空块折叠开关 + 设定页手动新增数组项。
- **P2+**：生成页接入手动新增；字段级校验提示精修；objectList 拖拽排序。
