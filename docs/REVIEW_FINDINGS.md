# Review Findings

本文件记录代码审查发现的有效问题。状态说明：`Open` 待处理，`Done` 已修复并验证，`Ignored` 明确暂不处理。

## 2026-07-21 — 移动端横向溢出修复

### Done — 游玩页隐式 Grid 列会被内容撑出窄屏右边界

- 位置：`web/app/globals.css` `.game-screen`
- 影响：在 320–330px 窄屏、已有回合且顶部操作较多的存档中，游玩页唯一的隐式 Grid 列会被内容最小宽度撑到约 342px。`html` / `body` 的 `overflow-x: hidden` 会掩盖文档级滚动，使问题表现为右侧内容偶发推出或裁切。
- 修复：为 `.game-screen` 显式设置 `grid-template-columns: minmax(0, 1fr)`，让顶部、剧情卷轴和命令行三行始终按视口宽度收缩；在场角色姓名条仍保留自己的局部横向滚动。
- 验证：本地 `git diff --check`、`npm run lint`、`npx tsc --noEmit`、vitest 52 项、`npm run build` 全过；远端只重建 `web` 后，Playwright 复验 65 组初始路由、4 个真实存档 × 7 档宽度（28 组）及菜单/手账/命令行/角色弹窗 4 个动态状态，均无文档级或 `.game-screen` 横向溢出。

### Done — 记忆页帮助气泡在移动端会越过视口边缘

- 位置：`web/app/games/[id]/memory/page.tsx` `HelpMark`
- 影响：帮助气泡固定为 `w-72` 并相对 20px 图标居中；图标靠近内容边缘时，气泡在 320–430px 视口会向左越界并被裁切。
- 修复：移动端改为固定在视口底部安全区内，左右各保留 0.75rem；`sm` 以上仍使用图标下方居中的原桌面布局。
- 验证：远端实页在 320/360/390/430px 下逐一聚焦 5 个帮助入口，共 20 次几何检查均位于视口内；320px 截图确认气泡完整可读，浏览器控制台 0 error。

## 2026-07-06 — 游玩方向审查后续修复

### Done — 失败/代价缺少稳定状态闭环

- 位置：`api/app/prompts/gm_runtime.md`、`api/app/prompts/extract_state_delta.md`
- 影响：纯叙事化后，GM 可以写出失败或代价，但如果提取器没有把这些后果落入 `conditions` / `relationships` / `open_threads` / `quests`，后续回合容易把受伤、追捕、失信、任务受阻等压力当作一次性气氛，游玩张力会变软。
- 修复：强化 GM 与状态提取合同：risk/cost 明确发生时必须写成可持续承接的具体后果；提取器只在 GM 输出明确写出代价时，把它落成非数值状态、关系、线索或任务变化，不因 risk_note/cost_if_fails 本身虚构代价。
- 验证：`cd api && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_markdown_contracts.py tests/test_act_pacing.py tests/test_games.py::test_settings_guide_documents_every_normalized_field tests/test_gameplay.py::test_runtime_story_filters_satisfied_alternative_anchor_group tests/test_gameplay.py::test_state_delta_advances_after_alternative_anchor_group_and_required_anchor`；`cd api && python3 -m ruff check app tests`。

### Done — 转幕只能 all-of 完成 required 锚点，缺少多路径推进

- 位置：`api/app/services/story_settings.py`、`api/app/services/state_applier.py`、`api/app/services/act_pacing.py`
- 影响：同一幕内如果有多条合理主线进入方式或解决路线，系统仍要求所有 `required=true` 锚点全部完成；玩家选了一条路线后，另一条替代路线仍可能阻塞转幕或继续显示为开放锚点。
- 修复：为 completion anchor 增加可选 `alternative_group`。同一幕内多个 required 锚点填相同组名时，完成任意一个即可满足该组；运行时投影会隐藏已满足组的兄弟锚点，转幕、当前幕进度、fallback anchor quest、act_pacing 均按“要求组”而不是原始锚点数计算。未配置 `alternative_group` 的旧剧本保持原 all-of 行为。
- 验证：同上；新增回归覆盖 runtime_story 过滤已满足替代组、state_delta 转幕门槛、act_pacing 计数。

## 2026-07-04 — feat/narrative-quality-overhaul vs origin/main

### Done — 剧透兜底重写接口错误会中断玩家回合

- 位置：`api/app/services/gameplay.py` `_redact_forbidden_reveals_if_hit`
- 影响：命中 `forbidden_reveal_hits` 后，如果 `gm_runtime_rewrite` 模型/API 调用抛出 `DeepSeekError`，同步回合会失败，而不是按函数注释保留已生成原稿。
- 修复：兜底重写 catch 增加 `DeepSeekError`，并新增回归测试覆盖模型/API 失败时返回原稿。
- 验证：`cd api && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_gameplay.py::test_redact_forbidden_reveals_no_hit_is_zero_cost tests/test_gameplay.py::test_redact_forbidden_reveals_keeps_original_on_deepseek_error`

### Done — 导入剧本后“重新生成”会退回示例设定

- 位置：`web/app/games/new/page.tsx`
- 影响：导入剧本后会清空 `confirmed`，但生成结果工具栏仍显示调用 `handleFinalize` 的“重新生成”；点击后会用硬编码 `sampleIdea` 替换导入剧本。
- 修复：记录 `generatedConfig` 来源；只有 AI 访谈生成的配置显示“重新生成”，导入剧本只保留“确认并开始冒险”。
- 验证：`cd web && npm run lint && npx tsc --noEmit`
