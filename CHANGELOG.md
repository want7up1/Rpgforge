# Changelog

All notable changes to RPGForge will be documented in this file.

详细工作记录见 [docs/OPTIMIZATION_PLAN.md](docs/OPTIMIZATION_PLAN.md)。

## Unreleased

### Round 14 — context_compressor + state_extractor 测试 (2026-05-28)

**Added**

- `tests/test_state_pipeline.py`：compressor `_trim_text` / `_fallback_summary`、extractor hints 注入与省略。全套 91 passed。

### Round 13 — DriftValidator + StoryDirector 测试 (2026-05-28)

**Added**

- `tests/test_turn_agents.py`：fake router 测 drift 重写判定 + fallback、director 解析 + fallback。全套 86 passed。

### Round 12 — TurnJudge 测试 (2026-05-28)

**Added**

- `tests/test_turn_judge.py`：fake router 测 JudgeResult overall 平均值 fallback、显式 overall、evaluate_turn 成功落库、LLM 失败时落 error 行。本地 pgvector 全套 81 passed。

### Round 11 — admin 集成测试 + 修序列化 (2026-05-28)

**Added**

- `tests/test_admin.py`：8 个 TestClient 集成测试覆盖 /api/admin/* endpoint。

**Fixed**

- `admin.TurnEvaluationRead.overall_score` 由 Decimal 改 float，使 JSON 返回 number（与前端类型一致），原本返回字符串 `"4.17"`。

**Verified**：本地 pgvector 全套 77 passed。

### Round 10 — 容器验证 + 修复 P0 部署 bug (2026-05-28)

**Fixed**

- `app/routers/progress.py`：`delete_game_progress_save` 移除 `-> None` 返回注解。该模块的 `from __future__ import annotations` 使 `-> None` 变字符串，FastAPI 0.115.x 误判为 response_model，导致 204 endpoint 在 import 时崩溃、整个 app 无法启动。既有 bug，非本次优化引入。

**Verified**（本地 pgvector pg16 实测）

- `alembic upgrade head` 成功（含迁移 0025/0026/0027）。
- `pytest tests/` 全套 69 passed。
- trace 写入→读出端到端、admin 聚合 + JSONB 查询 OK。

### Round 9 — dashboard 评分查询视图 (2026-05-28)

**Added**

- `/admin` 新增 Judge 评分查询区块：输入 game id 查看该游戏所有回合评分（overall + 6 维 + 状态）。
- `web/lib/api.ts`：`fetchGameEvaluations` / `triggerTurnEvaluation` 及 `TurnEvaluationRead` 类型。

纯前端，复用 Round 5 的 `GET /api/admin/games/{id}/evaluations`。

### Round 8 — 纯函数单元测试 (2026-05-28)

**Added**

- `tests/test_agent_infra.py`：覆盖 `extract_usage` / `JudgeResult` clamp / `_filter_materials_by_director` / `_enforce_hard_forbidden_reveals`（含 must_hit_beats 回归）/ `_director_hints` / `_drift_hints`。不依赖 DB。

### Round 7 — stage 常量统一 + dashboard trace 详情 (2026-05-28)

**Changed**

- `turn_jobs` 复用 `gameplay.STAGE_*` 常量构造 `TURN_JOB_STAGES`，stage id 单一来源；裸字符串替换为常量（不含 status / event_type）。纯重构。

**Added**

- `/admin` dashboard：点击 trace 行展开完整 prompt_messages / reasoning / output（复用 `GET /api/admin/traces/{id}`）。

### Round 6 — 阶段 3.1 Telemetry Dashboard (2026-05-28)

**Added**

- 后端 `GET /api/admin/stats/recent-turns`：聚合最近 N 个 completed turn job 的 telemetry（fallback / rewrite / extractor 失败率、drift severity 分布、各 agent 平均 latency、评分均值）。
- 前端 `web/app/admin/page.tsx`：管理监控页，聚合卡片 + 最近 30 条 trace 表，阈值超标高亮。
- `web/lib/api.ts`：admin API 客户端函数与类型。

**Access**：浏览器 `/admin`，使用与设置页相同的 `SETTINGS_ADMIN_TOKEN`。

### Round 5 — 阶段 1.3 LLM-as-Judge (2026-05-28)

**Added**

- 迁移 `20260528_0027`：`turn_evaluations` 表，6 维评分（canon_fidelity / state_consistency / pacing / prose_quality / freshness / safety）+ overall_score + rationale + 关联到原始 trace。
- `app/services/turn_judge.py` + `app/prompts/turn_judge.md`。
- admin endpoints：`POST /turns/{turn_id}/evaluate`、`GET /turns/{turn_id}/evaluations`、`GET /games/{game_id}/evaluations`。
- `api/scripts/judge_turn.py`：CLI 触发（单 turn / 最近 N / 全部）。

**Notes**

- 评分本身消耗 Pro LLM 调用。**默认不自动跑**，必须显式触发（admin API 或 CLI）。
- judge 调用归到 `agent_traces.job_kind="judge"`，不污染主回合的 trace 视图。

### Round 4 — 阶段 1.2 Golden replay 工具 (2026-05-28)

**Added**

- `api/scripts/replay_trace.py`：按 trace_id / turn_job_id / agent 重放历史 LLM 调用，比对旧/新输出。
- `api/scripts/diff_traces.py`：纯比对两条历史 trace（不发请求）。
- `api/scripts/label_trace.py`：把 trace 标记为 golden（`extras.label` + `extras.note`）。
- `GET /api/admin/golden`：列已标记的 golden 集合。

### Round 3 — 阶段 1.1 LLM trace 落表 (2026-05-28)

**Added**

- 迁移 `20260528_0026`：新建 `agent_traces` 表，弱关联 `(job_kind, job_id)` 存所有 LLM 调用的完整 prompt / output / token usage / latency / status。
- `app/models/agent_trace.py`、`app/services/agent_traces.py`、`app/routers/admin.py`。
- ContextVar 在 RQ 任务入口设置，下游 `ModelRouter` 自动归属当前 job。

**Changed**

- `ModelRouter` 所有调用方法包装 trace 钩子；流式/非流式都覆盖。trace 写入失败被吞掉，不影响主回合。
- `app/main.py` 注册 `admin` router。

**Endpoints**（需 `X-Settings-Admin-Token`）

- `GET /api/admin/traces` — 列表（轻量，不含 prompt/output 全文）
- `GET /api/admin/traces/{id}` — 单条完整内容
- `GET /api/admin/turn-jobs/{job_id}/traces` — 一个回合的所有 LLM 调用

### Round 2 — 阶段 0 止血 (2026-05-28)

**Changed**

- `TURN_JOB_TIMEOUT_SECONDS` 从 14min 提到 18min（最坏情况 Director + GM + Validator + GM重写 = 900s + IO 开销）；超时文案改用常量插值。
- `_enforce_hard_forbidden_reveals` 拆出 `must_hit_beats`——它是"必须发生"语义，不能并入 forbidden_reveals 黑名单。
- `turn_jobs.on_stage` 不再写 DB，只 publish broker。DB 持久化交给紧随的 `on_progress` / `on_update`，单回合 SessionLocal 数减半。

### Round 1 — AI Agent 链路重构 (2026-05-28)

**Added**

- `TurnTelemetry` 数据结构与 5 个 `turn_jobs` 表列（`director_used_fallback`、`drift_severity`、`rewrite_triggered`、`extractor_failed`、`turn_runtime_inputs`），迁移 `20260528_0025`。
- `TurnRuntimeContext` 一次性缓存 `state_v2` / `runtime_story_full` / `runtime_story_bare`，供 Director / Validator / PromptBuilder 复用。
- 每个 LLM Agent 独立 timeout（Director 90s / Validator 90s / GM 360s / Extractor 150s / Compressor 180s）。
- 显式 `on_stage` 回调驱动主回合进度阶段。
- `_enforce_hard_forbidden_reveals` 把剧本写死的 `forbidden_reveals` / `forbidden_drift` / `must_not_become` 强制 merge 进 Director 输出。
- StateExtractor 接收 `director_hints` / `drift_hints`，prompt 增加规则 14、15。
- GM 重写改为"带原稿局部修订"，`max_tokens` 从 12000 下调到 8000。

**Changed**

- Director 真正裁剪 GM 输入：按 `active_material_titles` 过滤 `related_materials`，空集回退全集。
- Director 输入精简：`recent_turns` 用 320 字符 `gm_output_excerpt` 替代完整 `gm_output`。
- DriftValidator fallback 改为 `approved=False, severity="unknown"`，不再静默放行（telemetry 真实反映降级）。
- `turn_jobs._publish_turn_snapshot` 与 router 同步暴露 telemetry 字段到 `TurnJobRead`。

**Removed**

- `turn_jobs._infer_turn_stage` 中文文案反推断（被显式 stage emit 取代）。

**Docs**

- 新增 `docs/OPTIMIZATION_PLAN.md` 作为工作驾驶舱。
- 新增项目根 `CLAUDE.md`，引导 Claude 优先读 OPTIMIZATION_PLAN。
- 归档 `docs/PROJECT_GUIDE.md` 到 `docs/_archive/`（与当前实现严重脱节）。

## 0.1.0 - 2026-05-11

Initial public preview.

### Added

- Docker-first FastAPI, Next.js, PostgreSQL/pgvector, Redis, and worker stack.
- DeepSeek-backed rule interview and game configuration generation.
- Streaming generation progress for setup and turn jobs.
- Turn-based AI RPG runtime with structured actions and free-form input.
- Story director, drift validation, state extraction, and state v2 foundations.
- Worldbook retrieval and context summaries.
- Character archive and user-uploaded portrait support.
- Mobile-friendly play UI, history/status/memory pages, theme switching, and Markdown story rendering.
