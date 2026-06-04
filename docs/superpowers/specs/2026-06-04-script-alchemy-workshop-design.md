# 剧本炼金工坊（特性2）

- 日期：2026-06-04
- 范围：后端（新表 + 模块库服务 + AI 适配器 + 路由）+ 前端（工坊页 + 看板「存为模块」+ 共享并入面板）
- 状态：设计已与用户逐块确认（含 HTML 示意图），待写实现计划
- **依赖**：复用特性1的看板（`buildBoardModel`/`BoardBlock`/`writeBlockFields`，已在 main）。

## 1. 背景与目标

用户精修剧本（如「光湮末世」）费时费力。希望把优秀设定**提炼成可复用模块**，存进个人「工坊」，再用到别处——并入时可选 AI **「本地优化」** 把模块改写得贴合目标剧本。

**核心闭环**：提取（从看板 block）→ 模块库 → 并入（到新剧本生成草稿 / 已有剧本设定页）。

## 2. 已确认决策（避免反复）

- **模块粒度**：单 block（一个看板 block = 一个模块）。
- **提取**：P1 只做「单个提取」——看板 block 弹窗加「⚗ 存为模块」。批量提取留 P2。
- **模块库**：后端 Postgres 表 `setting_modules`，**纯本地/个人**；通过**文件导入/导出**共享（支持导入第三方「个人工坊」文件）；**绝不上传/进 GitHub**（模块含剧本数据，仅存 Postgres）。
- **并入入口（P1 两个都做）**：🅱 已有剧本设定页 + 🅰 新剧本生成页草稿。
- **AI 本地优化**：P1 就做，作为「直接并入」之上的一层 + 预览门；独立 timeout + 失败回退直接并入。
- **冲突处理**：字符串桶静默去重；身份条目（同名角色/机制/同 id 幕）冲突 → 用户选 **改名(默认)/覆盖/跳过**；并入前**预览**；落地**存版本快照可回滚**。
- **非目标（P1 不做）**：批量提取、模块内部版本史、跨设备云同步、把模块组合成「设定包」。

## 3. 数据模型

新表 `setting_modules`（Postgres，迁移新增）：

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PK | |
| `name` | str | 模块名（默认取 block 标题）|
| `description` | text? | 可选描述 |
| `module_type` | str | 看板分类：`world/characters/plot/mechanics/constraints/materials`（UI 分类标签）|
| `payload` | JSONB | **最小 story_settings 片段**（见 §4），并入逻辑只认这个结构 |
| `tags` | JSONB(list[str]) | 标签，便于筛选/搜索 |
| `source_game_id` | UUID? FK→games ON DELETE SET NULL | 溯源；删剧本不删模块 |
| `created_at`/`updated_at` | timestamptz | |

> 隐私：`payload` 多来自精修剧本，仅存 Postgres，严禁进仓库/测试/文档（占位符）。索引 `module_type`。

## 4. 模块 payload = 最小 story_settings 片段

为让「提取」和「并入」对称、并入逻辑统一，模块 `payload` 存成一个可直接深合并进 story_settings 的最小片段。由看板 `BoardBlock.address` + `fields` 还原：

| BoardBlock.address.kind | 还原的 payload 片段 |
|---|---|
| `settingsItem{arrayKey,idKey,idValue}` | `{ <arrayKey>: [ <完整条目 dict> ] }`（角色/机制/行动风格/幕/素材/主线）|
| `settingsStringList{path}` | 嵌套 `{ ...path: [strings] }`（hard_rules.* / story_core.canon_terms 等）|
| `settingsScalar{path}` | 嵌套 `{ ...path: value }`（story_core.central_mystery 等单值；或整对象如 game_profile）|

`module_type` 由 `BoardBlock.category` 推出。提取是**拷贝快照**（深拷贝 block 当前数据），来源剧本日后变更不影响已入库模块。

## 5. 并入引擎（`module_library` 服务）

`merge_modules_into_settings(target_settings, module_payloads, conflict_resolutions) -> MergeResult`

- 深合并每个 payload 进 `target_settings` 的副本：
  - **字符串桶**（hard_rules.* / story_core.canon_terms/forbidden_drift/must_not_become/must_preserve / worldview.public_facts/hidden_facts）：逐条比对，完全相同 → 跳过（去重），新 → 追加。**不打扰**，计入摘要。
  - **列表条目**（core_characters[name] / core_mechanics[name|id] / action_style_rules[name|id] / act_plan[id]+anchor唯一 / story_material_library[id|title] / main_quest_path[id]）：按身份去重；**身份冲突**时按 `conflict_resolutions[module_id]` 处理——`rename`（自动 `名 (2)`，两者共存，默认）/ `overwrite`（替换现有）/ `skip`（不并入）。
- 合并后 **必过 `validate_story_settings`**（防同名/同 id/同 anchor 漏网）。
- 返回 `MergeResult{ settings, report }`，`report` 列出每个模块：added / renamed(→新名) / overwritten / skipped / deduped(N 条) / conflict(待用户决断)。

> 复用特性1 的 `story_settings` 归一/校验既有能力（`normalize_story_settings`/`validate_story_settings`）。

## 6. AI 本地优化（`module_adapter` 服务）

`adapt_module(payload, target_context) -> adapted_payload`

- 新 LLM 调用（`ModelRouter.use_pro`，JSON 模式），**独立 `MODULE_ADAPT_TIMEOUT_SECONDS`**，失败/超时/解析失败 → **回退返回原 payload**（即退化为直接并入）。
- 输入 context（目标剧本投影，控 token）：`story_core`(基调/核心)、`worldview.summary`、`canon_terms`、`core_characters` 的 name+role 索引、`game_profile`(题材/tone)。
- 新 prompt `adapt_module.md`（全新文件，无既有规则编号）：**保留模块机制内核/功能**，**改写**专名、基调、出身、与现有角色的关系，使其贴合目标剧本；**输出与输入同结构的 JSON 片段**，不得改变 payload 顶层键集合。
- 仅在用户开「AI 本地优化」时逐模块调用；改写结果进预览的「前后对比」。

## 7. API（路由 `modules.py`，前缀 `/api/modules`）

| 端点 | 作用 |
|---|---|
| `GET /api/modules?type=&tag=&q=` | 列表/筛选/搜索 |
| `POST /api/modules` | 从 block 提取创建：`{name, description, module_type, payload, tags, source_game_id}` |
| `PATCH /api/modules/{id}` | 改名/描述/标签 |
| `DELETE /api/modules/{id}` | 删除 |
| `GET /api/modules/export?ids=` | 导出选中为「工坊文件」JSON（含 format_version）|
| `POST /api/modules/import` | 导入工坊文件 → 批量入库（按 name 可重名共存或跳过，见下）|
| `POST /api/modules/merge-preview` | 核心：`{ target_settings, module_ids, adapt: bool, conflict_resolutions }` → `{ merged_settings, report, adapted: [{module_id, before, after}] }`。**算合并 + 可选 AI 改写，返回预览不落地。** |

**落地（不新增端点）**：
- 🅱 已有剧本：前端拿预览的 `merged_settings` → `PATCH /api/games/{id}/config`（既有，自动存版本快照、可回滚）。
- 🅰 生成草稿：前端把本地 `GeneratedGameConfig.story_settings` 置为 `merged_settings`，照常 finalize/create。

> `merge-preview` 用 `target_settings`（原始整份）而非 game_id，使生成草稿（尚无 game）与已有剧本走同一端点。导入重名策略：默认共存（导入不去重，用户自行在工坊页清理），保持简单。

## 8. 前端

- **工坊页 `web/app/workshop/page.tsx`**：模块库管理——搜索框 + 类型/标签筛选 + 模块卡（名/类型/来源/标签）+ 改名/标签/删除 + ⬆导入文件 / ⬇导出所选。
- **提取入口**：`BlockDetailModal`（`components/board/`）加「⚗ 存为模块」按钮 → 小表单（名默认 block 标题 / 描述 / 标签）→ `POST /api/modules`（payload 由 §4 从 block 还原）。需要把当前 game_id 传进看板/弹窗以记 `source_game_id`（设定页有 game_id；生成页 source 置空）。
- **共享并入面板 `web/components/workshop/ModuleMergePanel.tsx`**：勾选模块 + AI 优化开关 → `merge-preview` → 渲染预览（新增/去重摘要、身份冲突的 改名/覆盖/跳过 选择、AI 前后对比）→ 确认 → 调用方提供的 `onApply(mergedSettings)`。
  - 设定页 `[id]/settings`：`onApply` = `updateGameConfig(id,{story_settings_json})` + 刷新。
  - 生成页 `games/new`：`onApply` = 置本地草稿 settings。
- 纯逻辑可放 `web/lib/`（如 payload 还原、export 文件名）。

## 9. 组件/服务拆分（高内聚）

- 后端：`models/setting_module.py`、`services/module_library.py`（合并/去重/冲突，纯函数为主、可单测）、`services/module_adapter.py`（AI，含 timeout/fallback）、`routers/modules.py`、`prompts/adapt_module.md`、迁移。
- 前端：`app/workshop/page.tsx`、`components/workshop/ModuleMergePanel.tsx`、`components/board/BlockDetailModal.tsx`(加按钮)、`lib/api.ts`(新函数)、`lib/types.ts`(模块类型)。

## 10. 错误处理与边界

- AI 适配失败/超时 → 回退原 payload（直接并入），预览标注「AI 优化未生效，已用原始内容」。
- 并入后 `validate_story_settings` 失败（极端：冲突解析后仍非法）→ 拒绝落地、报错、保留预览。
- 已有剧本回合生成中 → `PATCH config` 返回 409 → 复用设定页的友好提示。
- 导入文件 `format_version` 不符 → 拒绝并提示。

## 11. 测试

- **后端 pytest（容器内，占位符数据）**：`module_library` 合并——字符串桶去重、身份冲突三种解析（rename/overwrite/skip）、合并后 validate 通过、payload 还原各 address 形态；`module_adapter` fallback（mock LLM 失败→返回原 payload）；路由 CRUD/import/export/merge-preview 正/负例。
- **前端**：`npm run lint`(含测试文件) + tsc + `next build`；若加纯逻辑（payload 还原）用 vitest。
- 迁移：`alembic upgrade head`；Docker 改后端必重建镜像（含 worker）。

## 12. 遵 CLAUDE.md

- 新 LLM 调用（`module_adapter`）：独立 timeout + fallback ✓。
- 新 prompt（`adapt_module.md`）：在 OPTIMIZATION_PLAN 记录（全新文件）。
- 未新增 TurnJob 字段。新表走迁移；隐私 [[script-data-privacy]]：模块仅 Postgres、导入导出走本地文件、测试用占位符、不进仓库。

## 13. 分期

- **P1（本次）**：表 + 模块库合并引擎 + AI 适配 + CRUD/导入导出/merge-preview + 工坊页 + 看板「存为模块」+ 两个并入点（设定页/生成页）+ 冲突/预览/回滚。
- **P2+**：批量提取、模块组合成「设定包」、模块版本史。
