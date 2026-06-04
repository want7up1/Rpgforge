# 已有剧本设定看板 + 信息架构去重（特性1）

- 日期：2026-06-04
- 范围：前端 `web/`（游戏内「概览/资料」页重整 + 新增「设定」页）；后端零改动（复用既有端点）
- 状态：设计已与用户逐块确认（含 HTML 示意图），待写实现计划
- **依赖**：本特性复用「创建冒险页重设计」（PR #3）落地的看板组件（`buildBoardModel`/`SettingsBoard` 等）。**应在 PR #3 合并后，从更新的 `main` 切分支实现**（或基于 `feat/generation-ui-redesign` 叠加）。

## 1. 背景与问题

游戏内导航现为：概览 / 剧情(play) / **资料(/memory)** / 状态(/status) / 角色(/characters) / 历史(/history)。

排查发现「概览」与「资料(/memory)」在 **story_settings 的展示/编辑**上严重重复：

- **概览** `app/games/[id]/page.tsx`：蓝图摘要（`buildGameBlueprint`）、剧本素材库前 6 条、高级诊断里的 story_settings 原始 JSON（`JsonBlock`）。
- **资料** `app/games/[id]/memory/page.tsx`（已是「巨无霸」≈800 行）：story_settings 分区只读展示、**完整 JSON 编辑器**（`updateGameConfig`）、导入/导出/填写说明（`importGameSettings`/`getGameSettingsExport`/`getGameSettingsGuideExport`）、**版本恢复**（`getSettingVersions`/`restoreSettingVersion`）、外加旅程记忆/摘要、重建摘要（`rebuildGameSummaries`）、运行诊断。

`story_settings` 是该剧本「唯一主设定源」，却被切到两页、各有一套展示/编辑入口。

## 2. 目标与非目标

**目标**
- 给已有剧本一个**专属的「设定」页**：用「创建冒险页」同款 6 分类 Tab 看板浏览全部 story_settings，可点 block 编辑/删除。
- **去重重整信息架构**（方案 A）：碰 story_settings 的一切集中到「设定」页；「概览」回归落地页；「资料」瘦身为运行记忆页。
- 复用既有后端端点，**后端零改动**。

**非目标**
- 不做「剧本炼金工坊」（特性2，另开 spec）——但本页的看板将是其「从已有剧本提取/并入」的载体。
- 不动「状态/角色/历史/剧情」页。
- 不新增后端端点、表或 LLM 调用。

## 3. 信息架构（方案 A：三页职责划清）

导航新增「设定」：概览 / 剧情 / **设定(新)** / 资料 / 状态 / 角色 / 历史。

| 页 | 职责 | 内容 |
|---|---|---|
| **概览** `[id]/page.tsx` | 落地页 | 设定概览（各分类条数）+「查看/编辑全部设定 →」入口；进度存档；旅程记忆预览（→资料）；导出剧本(MD)；删除游戏 |
| **设定（新）** `[id]/settings/page.tsx` | story_settings 唯一的家 | 6 分类看板（可编辑）+ 折叠：① 原始 JSON（直接编辑保存）② 导入/导出 JSON + 下载填写说明 ③ 版本历史 + 一键恢复 |
| **资料** `[id]/memory/page.tsx` | 运行记忆 | 旅程记忆/上下文摘要、重建摘要、运行诊断 |

**迁移清单**
- 概览 **移除**：`buildGameBlueprint` 大段摘要、素材库前 6、高级诊断 `JsonBlock`。
- 资料 **移除并迁到设定页**：story_settings 分区展示、JSON 编辑器（`updateGameConfig`）、导入/导出/填写说明、版本历史/恢复。
- 资料 **保留**：`getGameMemory` 记忆/摘要、`rebuildGameSummaries`、运行诊断。

## 4. 「设定」页设计

### 4.1 看板（主体）
- 加载 `game.config.story_settings` → `buildBoardModel({ source: "settings", settings })` → 渲染 `SettingsBoard`。
- **不需要**生成页的「改动闪烁 / 锁定」（这里不涉及 AI 重推导）。看板隐藏角标/闪烁/解锁。
- 顶部一句提示：「这里是该剧本唯一主设定源。修改只影响后续回合，不改写已发生的剧情/状态。」

### 4.2 编辑数据流
- 页面本地持有一份 `story_settings`（来自 `game.config.story_settings`）。
- 点 block → `BlockDetailModal` 查看/编辑/删除 → 复用 `writeBlockFields`/`deleteBlock`（Phase A 纯函数）得到新的整份 `story_settings`。
- 保存 → `updateGameConfig(gameId, { story_settings_json: merged })`（既有端点：后端 `validate_story_settings` + `_save_setting_version` 自动存版本快照）。
- 成功后用返回的 `GameDetail` 刷新本地 settings + 看板。

### 4.3 编辑护栏
- 后端 `_assert_settings_editable` 在有进行中回合任务时对 `PATCH /config` 返回 409 → 前端捕获，提示「回合生成中，稍后再改」并保留用户输入。
- 顶部常驻「只影响后续回合」提示（见 4.1）。

### 4.4 三个折叠（高级，从概览/资料迁来）
- **原始 JSON**：textarea 直接编辑整份 story_settings → `updateGameConfig({ story_settings_json })`（与看板编辑同端点，互为补充；power user 兜底）。
- **导入/导出**：导出 JSON（`getGameSettingsExport`）、下载填写说明（`getGameSettingsGuideExport`）、导入 JSON（`importGameSettings`）。
- **版本历史**：列出 `getSettingVersions`，每条「恢复」→ `restoreSettingVersion`，恢复后刷新看板。

## 5. 组件复用与归位

当前看板组件在 `web/components/generator/`，但「已有剧本设定」与「生成」复用同一看板，放在 `generator/` 命名不准确。

- **归位**：把可复用的看板组件 `SettingsBoard` / `BoardTabs` / `BoardBlockGrid` / `BlockDetailModal` / `ChangeSummaryBar` 从 `components/generator/` 移到 `components/board/`；生成专属的 `ChatDock` / `ChatHistorySheet` / `GenerationProgress` 留在 `components/generator/`。更新生成页 import。
- **可选化 props**：`SettingsBoard` 的生成专属 props 改为可选——
  - `diff?: BoardDiff`（缺省视为「无改动」，等价 `EMPTY_DIFF`）
  - `lockedIds?: string[]`（缺省 `[]`）
  - `onUnlockBlock?: (block) => void`（缺省时 `BlockDetailModal` 不显示「解锁」按钮）
  - `ChangeSummaryBar` 在 `diff` 缺省/无改动时不渲染（现已是 `changed.length === 0 → null`，天然兼容）。
- 设定页调用 `SettingsBoard` 时只传 `model` / `loading` / `onEditBlock` / `onDeleteBlock`（不传 diff/lock/unlock）。

## 6. 概览页改动

- 删除 `buildGameBlueprint` 大段、`featuredMaterials`(前6)、高级诊断 `JsonBlock`、相关 import。
- 新增「设定概览」区块：用 `buildBoardModel(story_settings)` 取各分类 `blocks.length` 渲染条数 pill + 「查看/编辑全部设定 →」`Link` 到 `/games/{id}/settings`。
- 保留：进度存档（新建/读取/删除）、旅程记忆预览（→资料）、导出剧本(MD)、删除游戏。

## 7. 资料页改动

- 删除：story_settings 分区展示、JSON 编辑器、导入/导出/填写说明、版本历史/恢复 及其 import（`updateGameConfig`/`getGameSettingsExport`/`getGameSettingsGuideExport`/`importGameSettings`/`getSettingVersions`/`restoreSettingVersion`）。
- 保留：`getGameMemory` 记忆/摘要展示、`rebuildGameSummaries`、运行诊断。
- 页面体量从 ≈800 行大幅瘦身。

## 8. 数据流与 API（全部既有，无后端改动）

| 操作 | 端点 / 函数 |
|---|---|
| 读剧本 | `getGame` → `game.config.story_settings` |
| 看板编辑保存 / 原始 JSON 保存 | `updateGameConfig(id, { story_settings_json })`（`PATCH /api/games/{id}/config`）|
| 导出设定 / 填写说明 | `getGameSettingsExport` / `getGameSettingsGuideExport` |
| 导入设定 | `importGameSettings` |
| 版本历史 / 恢复 | `getSettingVersions` / `restoreSettingVersion` |
| 记忆 / 重建摘要 | `getGameMemory` / `rebuildGameSummaries` |

## 9. 组件拆分（高内聚）

- `web/app/games/[id]/settings/page.tsx`：设定页容器，管 story_settings 本地态 + 三个折叠 + 编辑保存/409 处理。
- `web/components/board/*`：归位后的复用看板（见 §5）。
- 复用 Phase A 纯函数 `web/lib/generatorBoard.ts`（`buildBoardModel`/`writeBlockFields`/`deleteBlock`）——**不改其逻辑**，仅作消费方。
- 概览/资料页：删减，不新增大组件。

## 10. 测试

- **vitest（纯逻辑）**：已有 `buildBoardModel`/`writeBlockFields`/`deleteBlock` 覆盖。新增：从 `game.config.story_settings` 构建看板后编辑某 block → 提交给 `updateGameConfig` 的是「整份合并后 settings」（可对 handler 抽出的纯函数测）；概览「设定概览」条数计数。
- **类型/构建**：`cd web && npx tsc --noEmit` + `npm run build`。
- **手动走查**：① 概览不再有 JSON 大坨、点入口进设定页；② 设定页看板可浏览、改一个角色保存后刷新、版本里能看到新快照并可恢复；③ 回合生成中保存得到 409 提示；④ 资料页只剩记忆/摘要/诊断，导入导出/版本已不在此。

## 11. 决策记录（避免反复）

- 方案 **A**：三页职责划清（概览=落地 / 设定=唯一主源 / 资料=运行记忆），去重不减页。
- 设定页**可编辑**，走既有 `updateGameConfig` + 自动版本快照；编辑只影响后续回合；生成中 409 拦截。
- 看板的「改动闪烁/锁定」生成专属，设定页**不启用**（通过可选化 props 实现）。
- 复用组件**归位**到 `components/board/`。
- 原始 JSON / 导入导出 / 版本恢复**集中到设定页折叠区**（从概览+资料迁来）。
- 后端**零改动**。
