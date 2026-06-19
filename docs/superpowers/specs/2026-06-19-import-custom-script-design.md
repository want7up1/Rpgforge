# 导入自定义剧本（Approach C）设计

- 日期：2026-06-19
- 分支：feat/narrative-quality-overhaul
- 状态：设计已确认，待写实现计划

## 1. 背景与目标

用户希望「自己导入自定义剧本」：拿到 RPGForge 的**剧本结构 + 填写指南**，在外部 AI（Claude / ChatGPT）里结合自己的想法产出一份剧本，再导入 RPGForge 直接新建一个游戏，使这个游戏「十分契合自己的想法」。

关键决策（已与用户确认）：

- **AI 在外部写剧本，应用只管导入** —— 不在应用内新增任何 LLM 链路。
- **采用 Approach C：导入前有「试运行预览」**，且预览**复用现有「创建完成后的设定看板」分块视图**，可逐块查看/编辑后再正式建游戏。

## 2. 现状（已存在的底座）

本功能大部分底座已存在，无需重建：

- `GET /games/{id}/settings-guide-export` → 现成的 v2 权威填写指南（`export_settings_guide_markdown()`，`api/app/services/settings_guide_exporter.py`，**无 game 相关入参，是静态内容**）。
- `GET /games/{id}/settings-export` → 可再导入的 `story_settings v2` JSON。
- `POST /games/{id}/settings-import` → 把 JSON 导入**已存在的游戏**（替换设定+角色，校验，存版本）。**本功能不动这条路。**
- `create_game_from_config()`（`api/app/services/game_creator.py:78`）→ **已能只凭一份 `story_settings` 拼出完整游戏**：自动补 `initial_state`、从 `game_profile` 取标题/题材/简介、填主角、`initial_story_progress` 设初始幕、同步 `core_characters`。
- `POST /generator/create-game`（`api/app/routers/generator.py:260`）→ 吃 `GeneratedGameConfig` → `create_game_from_config` + 生成开场白（`_generate_opening_scene`）。
- 前端 `app/games/new/page.tsx` **已是 Approach C 的形态**：`generatedConfig` → `buildBoardModel({source:"settings", settings})` → `SettingsBoard` 分块预览（`handleEditBlock/DeleteBlock/UnlockBlock` 可逐块编辑）→ `handleCreateGenerated` → `createGeneratedGame` → 进游戏。

**结论**：本功能 = 给 `games/new` 这条已存在的「config → 预览 → 建游戏」流水线，**加一个新的喂入口**（粘贴外部 AI 写的 JSON），下游全部复用。

## 3. 数据格式约定

- 唯一可导入格式：`story_settings v2`（`STORY_SETTINGS_FORMAT_VERSION = "rpgforge.story.v2"`，定义见 `api/app/services/story_settings.py` 的 `validate_story_settings` / `normalize_story_settings`）。
- **重要坑**：`docs/AI_STORY_RUNTIME_GUIDE.md` 描述的是旧结构（`script_outline`/`campaign_contract`/`truth_map`），**不是**导入器接受的格式。给外部 AI 的「创作包」必须基于 v2 真实 schema（即 `settings_guide_exporter` 的内容），不能基于那份旧文档。
- 标题/题材/简介来自 `story_settings.game_profile`（`game_profile(settings)`），不是顶层字段；外部 AI 只需产出一份完整的 `story_settings` 对象。
- 导入应**兼容**两种粘贴：① 裸 `story_settings` 对象；② `settings-export` 的包裹体（若含 `story_settings` 键则取该键）。创作包指导 AI 产出 ① 即可。

## 4. 端到端流程

```
下载「创作包」(结构 + 指南 + 范例 + 指令)  ── 用户拿去 Claude/ChatGPT
        ↓ 喂入自己的想法
外部 AI 产出 story_settings JSON
        ↓ 粘贴 / 上传到 games/new「导入剧本」模式
POST /generator/import-script  → 校验 + 归一化 → 返回 GeneratedGameConfig（不建游戏）
        ↓
setGeneratedConfig(config) → SettingsBoard 分块预览（复用现成看板，逐块可编辑/删/改）
        ↓ 满意
「确认并开始冒险」→ createGeneratedGame（复用 create-game）→ 建游戏 + 开场白 → 进游戏
```

## 5. 后端改动（2 个端点，零新增 LLM 链路）

### 5.1 `GET /generator/authoring-kit`

- 返回**不绑游戏**的「创作包」Markdown（`text/markdown`，可下载）。
- 内容四段：
  1. **字段指南**：复用 `export_settings_guide_markdown()`（v2 权威）。
  2. **JSON 骨架**：`story_settings v2` 的精确空骨架（含 `game_profile`），标注必填/选填、枚举取值（如 `role`/`visibility`）。骨架应由代码从规范派生或维护为常量，避免与 `validate_story_settings` 漂移。
  3. **完整范例剧本**：一份**从头编写的通用范例**（如侦探或低魔奇幻题材），可直接导入成功。**严禁使用任何真实存档/剧本**（守 `script-data-privacy`）。
  4. **AI 指令**：硬性要求——只输出合法 JSON、用 v2 字段名、秘密放 `hidden_facts`/`gm_secret`/`forbidden_*`、不要编造顶层字段。
- 纯静态，无 LLM、无 DB 依赖。

### 5.2 `POST /generator/import-script`

- 入参：`{ story_settings: <粘贴的 JSON 对象> }`（兼容裸对象或带包裹体，见 §3）。
- 逻辑：
  1. 解析 JSON（语法错 → 400，错误信息可读）。
  2. `validate_story_settings`（缺必填/`game_profile.title` 空 → 400，结构化错误）。
  3. `normalize_story_settings`（静默纠偏：补缺省、限长、去重 id）。
  4. 包成 `GeneratedGameConfig`：`story_settings` = 归一化结果；`title/genre/description` 由 `game_profile` 派生；`initial_state` 走默认（`create_game_from_config` 会再处理一次，保持一致）；`voice_profiles=[]`。
  5. 返回 `{ config: GeneratedGameConfig, model_used: "import" }`（与 `GeneratorFinalizeResponse` 同构，前端可当 finalize 结果处理）。
- **不建游戏、不落库**。建游戏仍由用户在预览后点「确认」走现成 `create-game`。
- 复用 `validate_story_settings`/`normalize_story_settings`/`game_profile`，不重复造轮子。

## 6. 前端改动（`app/games/new/page.tsx` 为主，复用为主）

- 顶部加模式切换：**「AI 访谈生成」｜「导入剧本」**。
- 「导入剧本」面板：
  - `下载创作包` 按钮（`GET /generator/authoring-kit`，触发文件下载）。
  - 粘贴 `textarea`（主输入）+ 可选 `.json` 文件上传（次）。
  - `解析预览` 按钮 → `POST /generator/import-script`。
- 解析成功 → `setGeneratedConfig(config)`（同时重置 `confirmed`/`lockedIds`，复用 `handleFinalize` 尾部的 `buildBoardModel`+`diffBoard` 逻辑）→ **现成 `SettingsBoard` 渲染分块预览** → 逐块可编辑 → `确认并开始冒险` 照常建游戏。
- 解析失败 → 用现成 `error` 状态清晰回显，便于一键复制错误丢回外部 AI 修。
- 入口放 `games/new` 模式切换（非独立新页），复用面最大；输入以粘贴为主、文件为辅。

## 7. 过 Round 44 前端门 + 隐私

- **过门理由**：这不是给冻结的 SettingsBoard/工坊加「作者便利新功能」（objectList 拖排、批量抽取、单块重生、模块版本史），而是**给玩家核心循环加一条创建入口**——让玩家直接得到一个契合自己想法的可玩游戏（「读剧情 → 做选择 → 看后果」的前置）。落地时在 `docs/OPTIMIZATION_PLAN.md` 写明此理由。
- **隐私**：创作包范例剧本全新编写，绝不碰任何真实存档/剧本（`script-data-privacy`）。

## 8. 不做（YAGNI）

- 不做应用内 AI 写剧本（已选外部 AI）。
- 不做 Markdown 剧本反向导入（只认 JSON；`script-export` 的 markdown 仅供人读，不可往返）。
- 不改既有「导入到已有游戏」（`settings-import`）逻辑——那是另一条路，本功能只新增「从剧本新建游戏」。

## 9. 验收标准

1. 在 `games/new` 切到「导入剧本」，下载到的创作包能让外部 AI 一次产出可导入的 JSON。
2. 粘贴合法 JSON → 预览看板正确分块渲染 worldview / story_core / acts / core_characters 等。
3. 预览中编辑/删除某 block 后，确认建游戏，落库内容与预览一致。
4. 粘贴非法 JSON（语法错 / 缺 `game_profile.title`）→ 明确错误，不建游戏。
5. 建成的游戏可直接进入并游玩，含开场白。
6. 全程无新增 LLM 调用；既有 `settings-import` 行为不变。

## 10. 测试

- 后端（api 容器内 `pytest`）：
  - `import-script`：合法 JSON → 返回归一化 config；语法错 / 缺必填 → 400。
  - `authoring-kit`：返回非空 markdown，含字段指南 + 骨架 + 范例；范例 JSON 自身能过 `validate_story_settings`（防止范例腐烂）。
- 前端：导入模式切换、解析成功进预览、解析失败显错（按现有测试风格）。

## 11. 关键文件索引

- 后端校验/归一化：`api/app/services/story_settings.py`（`validate_story_settings` / `normalize_story_settings` / `game_profile`）
- 落库：`api/app/services/game_creator.py`（`create_game_from_config`）
- 现成指南导出：`api/app/services/settings_guide_exporter.py`（`export_settings_guide_markdown`）
- 生成器路由：`api/app/routers/generator.py`（`create-game` 在 260；新增 `authoring-kit` / `import-script`）
- schema：`api/app/schemas/generator.py`（`GeneratedGameConfig` / `GeneratorFinalizeResponse`）
- 前端新建页：`web/app/games/new/page.tsx`
- 前端看板：`web/components/board/SettingsBoard.tsx`、`web/lib/generatorBoard.ts`（`buildBoardModel`）
