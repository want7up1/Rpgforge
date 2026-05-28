# RPGForge 优化路线图

本文档是项目当前优化工作的"驾驶舱"。Claude 接手任何后续工作前应**先读本文档**，避免重复决策、避免推翻已落地的方案。

约定：
- 已落地工作在"已完成"区追加，不修改历史条目。
- 路线图条目用 `[ ]` / `[x]` 跟踪；新增条目从"路线图"末尾追加。
- 重大决策（特别是"不做某事"）落在"决策记录"，避免被反复推翻。

---

## 0. 状态速览

| 项 | 状态 |
|---|---|
| 最近一轮 | Round 1 — AI Agent 链路重构 |
| 完成日期 | 2026-05-28 |
| 文档卫生 | 2026-05-28 完成：归档 `PROJECT_GUIDE.md` / 补 CHANGELOG / 加文档现状索引（§5.3） |
| 当前阶段 | Round 1 完成；阶段 0（止血）待启动 |
| 下一步建议 | 阶段 0 三件小事 → 阶段 1.1 trace 落表 |

---

## 1. 已完成

### Round 1 (2026-05-28) — AI Agent 链路重构

13 项改动全部落地、全部 `py_compile` 通过。完整 diff 横跨主回合 + 维护任务 + 数据库迁移 + 前端可见字段。

**改动清单**（按问题编号）：

| # | 主题 | 关键文件 |
|---|---|---|
| 1 | `TurnRuntimeContext` 缓存 `state_v2` / `runtime_story_full` / `runtime_story_bare` | gameplay.py |
| 2 | Director `active_material_titles` 真正过滤 GM 输入 | gameplay.py::`_filter_materials_by_director` |
| 3 | DriftValidator 重写改为带 `previous_gm_output` 局部修订 | gameplay.py, prompt_builder.py, gm_runtime.md(第 27 条) |
| 4 | 显式 `on_stage` 回调，删除中文文案反推断 | gameplay.py, turn_jobs.py |
| 5 | 每个 Agent 独立 timeout | story_director.py, drift_validator.py, state_extractor.py, context_compressor.py, gameplay.py |
| 6 | TurnJob 加 5 个 telemetry 列 | 迁移 20260528_0025 |
| 7 | gameplay 层收集 `TurnTelemetry` 并写库 | gameplay.py, turn_jobs.py |
| 8 | StateExtractor 接收 `director_hints` / `drift_hints` | state_extractor.py, extract_state_delta.md(规则 14、15) |
| 9 | `forbidden_reveals` 代码层硬注入 | gameplay.py::`_enforce_hard_forbidden_reveals` |
| 10 | Director 输入精简（`gm_output_excerpt`） | story_director.py |
| 11 | GM 重写 `max_tokens` 下调到 8000 | gameplay.py |
| 12 | DriftValidator fallback 不再静默放行（`approved=False`） | drift_validator.py |
| 13 | 全项目交叉检查、TurnJobRead 字段补全 | routers/gameplay.py |

**改动文件**：

```
新增:
  api/migrations/versions/20260528_0025_turn_job_telemetry.py
  docs/OPTIMIZATION_PLAN.md (本文件)

修改 (服务层):
  api/app/services/gameplay.py
  api/app/services/story_director.py
  api/app/services/drift_validator.py
  api/app/services/state_extractor.py
  api/app/services/context_compressor.py
  api/app/services/prompt_builder.py
  api/app/services/turn_jobs.py
  api/app/services/turn_maintenance_jobs.py

修改 (数据/路由):
  api/app/models/generator_job.py
  api/app/schemas/turn.py
  api/app/routers/gameplay.py

修改 (Prompt):
  api/app/prompts/gm_runtime.md
  api/app/prompts/extract_state_delta.md
```

**部署须知**（Docker 内执行）：

```bash
docker compose exec api alembic upgrade head
docker compose restart api worker
```

旧 TurnJob 行的新列由 server_default 自动填 `false`/`null`，无需手工回填。

---

## 2. 当前 AI Agent 链路速查

详细架构见 `ARCHITECTURE.md` 与 `AI_STORY_RUNTIME_GUIDE.md`。此处只放速查表。

### 2.1 主回合链路（`turn_jobs.run_turn_job`，玩家等待）

```
prepare_context → retrieve_memory → story_director → gm_runtime
                                                       ↓
                              [drift 触发条件满足?] ← runtime_output
                                ↓ 是          ↓ 否
                          drift_validation    ↓
                                ↓             ↓
                          [should_rewrite?]   ↓
                            ↓ 是    ↓ 否     ↓
                          gm_runtime (重写)   ↓
                                ↓             ↓
                              persist_turn ←──┘
                                ↓
                              completed → enqueue maintenance job
```

### 2.2 维护任务链路（`turn_maintenance_jobs`，异步）

```
state_extract (读 TurnJob.turn_runtime_inputs 拿 director/drift hints)
  ↓
apply_delta (纯代码 StateApplier)
  ↓
[turn_number % 4 == 0?] → memory_summary → completed
                 ↓ 否
              skipped
```

### 2.3 Agent 表

| Agent | 模型 | reasoning | max_tokens | timeout | 失败行为 |
|---|---|---|---|---|---|
| StoryDirector | Flash | high | 1800 | 90s | 本地 fallback（`used_fallback=True`） |
| GM (首次) | Pro | high | 12000 | 360s | 抛 `GameplayValidationError`，回合失败 |
| DriftValidator | Flash | high | 1600 | 90s | `approved=False, severity="unknown"`，不重写但 telemetry 标记 |
| GM (重写) | Pro | high | 8000 | 360s | 同首次 |
| StateExtractor | Flash | None | 4096 | 150s | 抛 `StateExtractorValidationError`，maintenance 标 failed，下回合 settle 重试 |
| ContextCompressor | Flash | high | 3000 | 180s | fallback 拼接纯代码摘要 |

### 2.4 Telemetry 字段 → 数据库列对照

| 内存字段 (`TurnTelemetry`) | 数据库列 (`turn_jobs`) | 写入时机 |
|---|---|---|
| `director_used_fallback` | `director_used_fallback` BOOL | Director 调用后 |
| `drift_severity` | `drift_severity` VARCHAR(32) | DriftValidator 调用后 |
| `rewrite_triggered` | `rewrite_triggered` BOOL | 决定重写时 |
| `extractor_failed` | `extractor_failed` BOOL | maintenance 失败时 |
| `director_decision` + `drift_validation` | `turn_runtime_inputs` JSONB | persist_turn 后 |

### 2.5 Stage 常量（前端进度条对照）

```
prepare_context(1) → retrieve_memory(2) → story_director(3) → gm_runtime(4)
  → drift_validation(5) → persist_turn(6) → completed(7)
```

`stage_total=7`。新增 stage 必须同步前端。常量定义在：
- `gameplay.py::STAGE_*`
- `turn_jobs.py::TURN_JOB_STAGES`

两处保持顺序一致。

---

## 3. 路线图

### 阶段 0 — 止血（建议一周内）

Round 1 落地后立刻暴露的 3 个尾巴。改动量小、风险低、价值明确。

- [ ] **0.1 TurnJob 整体 timeout 对齐**：当前 `TURN_JOB_TIMEOUT_SECONDS = 14*60 = 840s`，但单回合最坏情况 `Director(90) + GM(360) + Validator(90) + GM重写(360) = 900s` > 840s。要么把整体提到 18 min，要么把 GM 单次降到 300s。文件：`turn_jobs.py:18`。

- [ ] **0.2 `must_hit_beats` 从硬注入中拆出**：当前 `_enforce_hard_forbidden_reveals` 把 `current_act.must_hit_beats`（"必须发生的剧情节点"）也当成 forbidden_reveals merge 进去，语义错误，会误杀正常剧情。只保留 `forbidden_reveals + forbidden_drift + must_not_become`。文件：`gameplay.py::_enforce_hard_forbidden_reveals`。

- [ ] **0.3 turn_jobs 的 SessionLocal 合并**：当前 `turn_jobs.py` 内开了 19 次 `SessionLocal()`，每次 stage 切换/progress 更新都新开。改成显式划阶段后合并到 ~5 次。注意 RQ 异步任务不能跨 await 复用同一 session，所以是"段内合并"不是"全任务复用"。文件：`turn_jobs.py`。

### 阶段 1 — AI 质量基础设施（2-4 周）

**这是当前项目的命脉。没有这一阶段，所有后续 AI 优化都是凭感觉。**

- [ ] **1.1 LLM 调用 trace**
  - 新表 `agent_traces`：`id, turn_job_id, agent, model, prompt_messages JSONB, output_text, tokens_input, tokens_output, latency_ms, telemetry JSONB, created_at`
  - 每个 Agent 内部钩子写入（在 `asyncio.wait_for` 包之外，包含 fallback 的情况）
  - `/api/admin/traces?turn_job_id=...` 返回该回合所有 Agent 的完整 trace
  - 注意：不要把 trace 写到 `turn_jobs.turn_runtime_inputs` —— 那个字段是 maintenance 用的小载荷

- [ ] **1.2 Golden 用例集 + replay 脚本**
  - `tests/golden/turns/` 目录存 N 个固化输入（game config + state + player_input + 真实 LLM 输出）
  - `scripts/replay_traces.py --prompt <branch>` 用任意 prompt/model 版本跑一遍，输出 diff
  - 评估指标：narrative embedding cosine（用本地小模型）+ option 集合 Jaccard

- [ ] **1.3 LLM-as-Judge 自动评分**
  - 用 Pro 模型对 GM 输出按维度打分：剧本一致性 / 状态一致性 / 节奏 / 文采 / 新意 / 安全性
  - 异步触发（maintenance 之后），结果存 `agent_evaluations`
  - 与 telemetry 关联：能回答"重写率上升时 GM 文采是否下降"

### 阶段 2 — 架构层重构（3-6 周）

- [ ] **2.1 Agent 抽象**：抽 `Agent[InputT, OutputT]` 基类，封装 timeout/fallback/trace/重试。让 Director/Validator/Extractor/Compressor 都基于它。新增 Agent 只需写 prompt + schema + fallback。

- [ ] **2.2 maintenance 状态机**：当前用 string `maintenance_stage` 切换，扩展性差。用 enum + transition table 重构，便于以后插入新 Agent（character_arc_tracker、faction_pressure_updater 等）。

- [ ] **2.3 AgentContextBundle 跨进程复用**：把主回合构造好的 `runtime_story_bare` / `state_v2` 序列化进 `TurnJob.turn_runtime_inputs`，maintenance 阶段反序列化复用，避免重复 `build_runtime_story`。

### 阶段 3 — 前端 + UX（穿插进行）

- [ ] **3.1 telemetry dashboard**：`/admin` 页面展示最近 100 回合的 director_fallback / drift_severity / rewrite / extractor_failed 分布；P50/P95 时长；当前模型路由配置。

- [ ] **3.2 玩家可见回溯**：当 `drift_severity ∈ {major, critical}` 或玩家不满意时，让玩家"回到上一回合"或"切换到 v2 版本"。需要在 `persist_runtime_turn` 时保留所有版本（带原稿改写就是 v1/v2）。

- [ ] **3.3 流式 UX 改造**：去掉 `turn_jobs` 里 DB poll fallback 路径，纯走 Redis pub/sub + SSE；progress_message 不再写 DB。单回合 DB 写入次数从 ~50 降到 ~5。

### 阶段 4 — 可选

- [ ] **4.1 Prompt 版本管理**：`app/prompts/*.md` 改成 `(version, content)` 表 + 文件双源，支持 A/B。**仅在 1.1 + 1.2 完成后启动**，否则 A/B 测不出结论。

- [ ] **4.2 模型路由策略**：按 act / 玩家 / 时段动态路由。需要 telemetry 支撑。

- [ ] **4.3 i18n**：prompts 和 UI 文案的多语言支持。视产品方向决定。

---

## 4. 决策记录（不做的事）

**这些选项已经评估过，主动放弃。重新提出前请说明新证据。**

| 不做的事 | 原因 |
|---|---|
| 大规模重写 `story_settings.py` | 700 行 normalize 在做的事天然丑陋；ROI 低，bug 风险高 |
| 引入 LangChain / LlamaIndex / Agent 框架 | 当前 5 个 Agent 用 Pydantic schema + asyncio.wait_for 已经够灵活；框架反而难 debug |
| 上 Kubernetes / 微服务 | 单机 Docker Compose 可支撑预估 1000 DAU；过早架构化 |
| 把 StateApplier 重构成 event sourcing | 当前"LLM 提案 + 代码应用"分层已经够清晰 |
| 堆单元测试覆盖率 | 真正的"测试"是阶段 1.2 golden replay；Python 单测不能反映 AI 质量 |
| 给每个 Agent 加重试 | DriftValidator 已经在 fallback 中放行，重试只会增加成本；除非 trace 显示真实重试收益 |

---

## 5. 关键文件 + 关键常量索引

### 5.1 文件定位

| 关心的事 | 文件 | 入口符号 |
|---|---|---|
| 主回合编排 | `api/app/services/gameplay.py` | `GameplayService.generate_turn_runtime_output` |
| RQ 任务入口 | `api/app/services/turn_jobs.py` | `run_turn_job` |
| Maintenance 入口 | `api/app/services/turn_maintenance_jobs.py` | `run_turn_maintenance_job` |
| Director Agent | `api/app/services/story_director.py` | `StoryDirector.plan` |
| GM prompt 拼装 | `api/app/services/prompt_builder.py` | `PromptBuilder.build_runtime_messages` |
| Drift Agent | `api/app/services/drift_validator.py` | `DriftValidator.validate` |
| Extractor Agent | `api/app/services/state_extractor.py` | `StateExtractor.extract` |
| Compressor Agent | `api/app/services/context_compressor.py` | `ContextCompressor.update_after_turn` |
| 状态应用（纯代码） | `api/app/services/state_applier.py` | `apply_state_delta` |
| Runtime view 构造 | `api/app/services/story_settings.py` | `build_runtime_story` |
| TurnJob 模型 | `api/app/models/generator_job.py` | `TurnJob` |
| TurnJob 对外 schema | `api/app/schemas/turn.py` | `TurnJobRead` |

### 5.2 关键常量

| 常量 | 文件:行 | 当前值 | 说明 |
|---|---|---|---|
| `TURN_JOB_TIMEOUT_SECONDS` | turn_jobs.py:18 | 840 (14 min) | **见 0.1 待修** |
| `GM_RUNTIME_TIMEOUT_SECONDS` | gameplay.py:39 | 360 | 单次 GM 调用上限 |
| `GM_REWRITE_MAX_TOKENS` | gameplay.py:41 | 8000 | 重写局部修订 token 上限 |
| `STORY_DIRECTOR_TIMEOUT_SECONDS` | story_director.py | 90 | |
| `DRIFT_VALIDATOR_TIMEOUT_SECONDS` | drift_validator.py | 90 | |
| `STATE_EXTRACTOR_TIMEOUT_SECONDS` | state_extractor.py | 150 | |
| `CONTEXT_COMPRESSOR_TIMEOUT_SECONDS` | context_compressor.py | 180 | |
| `TURN_MAINTENANCE_TIMEOUT_SECONDS` | turn_maintenance_jobs.py:23 | 600 (10 min) | maintenance 整体兜底 |
| `MEMORY_SUMMARY_INTERVAL_TURNS` | turn_maintenance_jobs.py:24 | 4 | 每 4 回合压缩一次 |
| `DIRECTOR_RECENT_TURN_EXCERPT_CHARS` | story_director.py | 320 | Director 看到的 gm_output 截断长度 |

### 5.3 文档现状（权威 / 参考 / 归档）

文档质量良莠不齐，Claude 接手时需要知道**哪些可信、哪些已过时**。

**权威信息源**（与代码同步、可放心据此写代码）：

| 文档 | 范围 |
|---|---|
| 代码本身（`api/app/`、`api/migrations/`） | 终极权威 |
| `docs/AI_STORY_RUNTIME_GUIDE.md` | AI 剧情生成依据，与代码对应度高 |
| `docs/ARCHITECTURE.md` | 宏观架构，简短准确 |
| `docs/OPTIMIZATION_PLAN.md`（本文件） | 工作驾驶舱、路线图、决策记录 |
| `docs/API.md` | 当前 HTTP API 接口（小幅可能滞后，写代码前对 router 实地核对） |
| `docs/CONFIGURATION.md` | 环境变量与设置 |
| `docs/DEPLOYMENT.md` | Docker 部署 |
| `README.md` | 项目概览 |
| `CHANGELOG.md` | 版本日志（Round 1 已记录） |
| `CLAUDE.md`（项目根） | Claude 工作约束 |

**礼节性文档**（对 Claude 工作无直接影响）：

- `CODE_OF_CONDUCT.md`、`SECURITY.md`、`CONTRIBUTING.md`

**已归档（请勿据此写代码）**：

| 路径 | 归档原因 |
|---|---|
| `docs/_archive/PROJECT_GUIDE_2026-05-11_DRAFT.md` | 项目启动期初稿。`lore_entries` / `modes` 表已被 drop、`/api/games/{id}/lore` 等路由不存在、`pending → 人工确认`流程已自动化、MiMo TTS 从未实现、状态结构不一致。文件顶端已加警告横幅。 |

**接手原则**：

1. 写代码前先看代码 + AI_STORY_RUNTIME_GUIDE.md，再看其他文档。
2. 任何文档与代码冲突时，**以代码为准**，并把冲突点记到本节"已知文档/代码偏差"（如有，下追加）。
3. 大规模工作完成后，回头同步更新本节 + 涉及的权威文档。

**已知文档/代码偏差**：

- `docs/API.md` 未与最新 router 100% 对齐（Round 1 没改 router 路径，但历史增量可能有遗漏）。优先级低，等阶段 1.1 trace 上线后顺便核对。
- `CONTRIBUTING.md` 中 "Include tests for backend behavior changes" 与 §4 决策"不堆单元测试"有轻微冲突；AI 链路回归测试方案见 §3 阶段 1.2。

---

## 6. Telemetry 查询样例

近 100 回合降级率：

```sql
SELECT
  COUNT(*) AS total,
  SUM(CASE WHEN director_used_fallback THEN 1 ELSE 0 END) AS director_fallback,
  SUM(CASE WHEN rewrite_triggered THEN 1 ELSE 0 END) AS rewrites,
  SUM(CASE WHEN extractor_failed THEN 1 ELSE 0 END) AS extractor_fail,
  COUNT(*) FILTER (WHERE drift_severity IS NOT NULL) AS drift_judged,
  COUNT(*) FILTER (WHERE drift_severity = 'unknown') AS drift_unknown
FROM (
  SELECT * FROM turn_jobs
  WHERE status = 'completed'
  ORDER BY created_at DESC LIMIT 100
) t;
```

按游戏维度看：

```sql
SELECT
  game_id,
  COUNT(*) AS turns,
  AVG(CASE WHEN rewrite_triggered THEN 1.0 ELSE 0 END) AS rewrite_rate,
  AVG(CASE WHEN director_used_fallback THEN 1.0 ELSE 0 END) AS director_fallback_rate
FROM turn_jobs
WHERE status = 'completed'
GROUP BY game_id
HAVING COUNT(*) >= 10
ORDER BY rewrite_rate DESC;
```

---

## 7. Round 1 已知遗留疑点

落地时识别但**没有修**的事项。逐一审视后决定是否进入路线图。

1. **重写能否真的"局部修订"**：完全靠 `gm_runtime.md` 第 27 条让模型自觉。Round 1 没法验证，要等阶段 1.1 trace 上线后看 rewrite 后 narrative 与 previous_gm_output 的相似度。

2. **`active_material_titles` 过滤可能过激**：Director 是 Flash 模型，可能挑错。当前 fallback 仅"过滤为空时退全集"。可以加 `min_materials=3` 兜底。等 1.1 trace 看真实选择情况再定。

3. **`_should_run_drift_validation` 字面匹配长度阈值 4**：会漏掉"灭世""神明"这类 2 字关键词。已在代码里，可调小到 2 但要防止短词误命中。

4. **`StoryDirectorDecision.used_fallback` 字段可能被 LLM 返回值覆盖**：Pydantic 默认 `extra="ignore"`，但 `used_fallback` 是定义字段，如果模型 JSON 里恰好包含 `"used_fallback": true` 会覆盖。当前显式 `decision.used_fallback = False` 在成功路径中重置，已安全；但属于"易踩坑"。

5. **`director_hints` 信息冗余**：传给 StateExtractor 的 hints 里同时有 `forbidden_reveals` 和 `scene_objective`，但 extractor 只关心"已发生的变化"。可以精简到 `continuity_notes + state_conflicts`。

6. **maintenance 读旧 TurnJob 的兼容性**：迁移 0025 前的回合 `turn_runtime_inputs = NULL`，extractor 看不到 hints 但仍能跑。已验证安全。

7. **Stage 数量与前端约定**：`stage_total=7`。未来加 stage 需要同步 `gameplay.py::STAGE_*` + `turn_jobs.py::TURN_JOB_STAGES` + 前端进度条。

8. **`TURN_JOB_STAGES` 与 `gameplay.py::STAGE_*` 重复定义**：两处字符串必须保持同步。理想做法是把 STAGE_* 提到一个公共模块，gameplay 和 turn_jobs 都引入。

---

## 8. 文档维护规则

- 每完成一轮工作（不论大小），在 §1 追加 `### Round N (日期)` 子节，列出改动清单。**不要修改历史 Round 的内容**。
- 路线图条目落地后，在原位打 `[x]`，不要删除。
- 新发现的"不做"决策追加到 §4。
- 关键常量调整后同步 §5.2 的值。
- 本文件本身的目录结构（编号章节）保持稳定，方便 Claude 用章节号引用。
