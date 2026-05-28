# Changelog

All notable changes to RPGForge will be documented in this file.

详细工作记录见 [docs/OPTIMIZATION_PLAN.md](docs/OPTIMIZATION_PLAN.md)。

## Unreleased

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
