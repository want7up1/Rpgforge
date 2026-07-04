# Review Findings

本文件记录代码审查发现的有效问题。状态说明：`Open` 待处理，`Done` 已修复并验证，`Ignored` 明确暂不处理。

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
