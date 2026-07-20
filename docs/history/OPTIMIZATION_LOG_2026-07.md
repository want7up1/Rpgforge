# Optimization Log 2026-07

## 2026-07-06 — Round 57：非数值代价闭环 + 替代锚点组

### 背景

游玩方向审查指出两项优先问题：

- 纯叙事化后，失败、受伤、暴露、失信、追捕等代价可能只停留在 GM 正文里，未稳定进入后续状态。
- 幕推进要求所有 `required=true` 锚点全部完成，无法表达“潜入/说服/绕路任选一条也能推进”的多路径主线。

本轮只修这两项，不恢复骰子、属性、技能或数值资源。

### 改动

- `gm_runtime.md`：要求 GM 把风险/代价写成后续能被状态提取器承接的具体剧情后果。
- `extract_state_delta.md`：新增非数值代价闭环规则。GM 输出明确发生代价时，提取器必须落到 `condition_updates`、`relationship_events`、`open_thread_updates` 或 `quest_updates`；不得只因 risk/cost hint 存在就虚构代价。
- `story_settings.py`：新增 `completion_anchors[].alternative_group` 规范化字段；runtime_story 会过滤已满足替代组的兄弟锚点。
- `state_applier.py`：ready/advance/current_act_anchor_progress/fallback anchor quest 改按“required requirement group”计算。同组 required 锚点任一完成即满足该组；未分组锚点仍单独必达。
- `act_pacing.py`：open_required_count 和 next_required_anchor 支持替代组，避免同一替代路线组被算成多个必达项。
- `settings_guide_exporter.py`、`authoring_kit_exporter.py`、`generate_config_section.md`：同步作者可见字段说明。
- 测试新增覆盖 prompt 合同、替代组 runtime 投影、替代组转幕、act_pacing 计数和填写说明字段。

### 验证

- `cd api && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_markdown_contracts.py tests/test_act_pacing.py tests/test_games.py::test_settings_guide_documents_every_normalized_field tests/test_gameplay.py::test_runtime_story_filters_satisfied_alternative_anchor_group tests/test_gameplay.py::test_state_delta_advances_after_alternative_anchor_group_and_required_anchor`
  - 结果：15 passed。
- `cd api && python3 -m ruff check app tests`
  - 结果：All checks passed。
- 远端运行环境：
  - 最小同步后重建 `api` / `worker`。
  - `docker compose ps`：`api` healthy，`worker` running，依赖服务 healthy。
  - `GET /health`：`status=ok`。
  - 容器内目标 pytest：15 passed。
  - `api` / `worker` 启动日志无异常。

### 未完成

- 本机带 `db_session` 的旧目标测试仍因本地 Postgres `postgres:5432` 连接被关闭而无法跑通；需在容器或远端运行环境复验。
- 代价闭环是 prompt + 状态提取合同，仍需真实模型回合验证是否稳定按合同落库并被后续回合承接。
