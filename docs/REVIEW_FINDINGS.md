# Review Findings

本文件记录代码审查发现的有效问题。状态说明：`Open` 待处理，`Done` 已修复并验证，`Ignored` 明确暂不处理。

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
