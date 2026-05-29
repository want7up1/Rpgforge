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
| 最近一轮 | Round 19 — 按需注入：StateExtractor/Compressor 用精简投影省 input token |
| 完成日期 | 2026-05-29 |
| 文档卫生 | 2026-05-28 完成：归档 `PROJECT_GUIDE.md` / 补 CHANGELOG / 加文档现状索引（§5.3） |
| 当前阶段 | AI 质量闭环完整 + 全链路测试覆盖。Round 1–15 本地 pgvector 实测 **102 tests pass** |
| ✅ 验证状态 | 本地 pgvector 实测：迁移 head、102 pytest、trace 端到端、admin JSONB 查询全 OK。详见 §9 |
| 下一步建议 | **方案已敲定**，见 [`PROMPT_ARCHITECTURE_REDESIGN.md`](PROMPT_ARCHITECTURE_REDESIGN.md) §11（2026-05-29 头脑风暴）。北极星=遵守剧本质量；验证器只观测不重写；遵守与省 token 并行。**下一步 Round 20：验证器观测层 v1（canon/越界/提前揭露，只写 telemetry）**；Round 21 GM 场景投影；Round 22 接 DeepSeek 缓存 |

---

## 1. 已完成

### Round 19 (2026-05-29) — 按需注入：状态运算类 agent 用精简 runtime_story 投影

用户需求：从架构上减少 input token 浪费——"该注入什么的时候再注入什么"，而非所有 agent 每回合无脑塞同一份巨型全量 payload。

**诊断（trace 实测每回合 input token）**：story_director ~27.5k / gm ~26k / state_extractor ~31.4k / drift ~25.3k / compressor ~34.9k。input:output ≈ 30:1，成本几乎全在输入端，且当前**零 prompt caching**。核心浪费：每个 agent 每回合全量重发 `runtime_story`（~17.5k 字符），其中 worldview/core_mechanics/hard_rules/角色内幕(fear/leverage/appearance/desire) 等**写作向字段**对"状态运算类" agent 完全无用。

**本轮范围（保守起步，用户选定）**：只改职责最窄、最不需要写作向字段的 **StateExtractor（每回合必跑）+ ContextCompressor（每 4 回合）**。GM/Director/Drift 暂不动。

**实现**：

- `story_settings.py::project_runtime_story_for_state_ops`：精简投影。保留 `current_act`(含锚点) / `story_core` / `story_progress` / `main_quest_path`；`next_act` 瘦成 id+title；`core_characters` 瘦成 `name/id/aliases/role` 索引（够认人、归类关系事件）。砍掉 worldview / core_mechanics / hard_rules / home_base / game_profile / generation_parameters / priority_order。
- `state_extractor.py` / `context_compressor.py`：payload 里用投影包裹 `build_runtime_story`。

**安全性**：核对 `extract_state_delta.md` / `compress_context.md`，两个 prompt 只引用 `current_act.completion_anchors` / `next_act` / 主线 / `director_hints` / `current_state.v2`，**完全不引用被砍字段**——投影保留集与 prompt 需求精确吻合，不破坏功能。

**实测节省（真实游戏）**：这两个 agent 的 runtime_story **17564 → 5989 字符，省 65.9%（~5.8k tokens/次）**。extractor 每回合必跑，等于每回合直接省 ~11.6k 字符 input。

**改动文件**：`api/app/services/story_settings.py`、`api/app/services/state_extractor.py`、`api/app/services/context_compressor.py`、`api/tests/test_gameplay.py`（+投影回归测试）。

**部署**：`docker compose up -d --build api worker`。**验证**：容器内 `pytest tests/` **142 passed**，ruff 通过。

> 后续可选（未做）：①Director/Drift 同样按需投影（中等风险，需逐个验证不影响决策/偏离判定）；②GM 的 state_v2(占 user 41%) 精简（高风险）；③确认后端是否支持 prompt caching——若支持，把稳定前缀缓存化是更大杠杆。

### Round 18 (2026-05-29) — 用真实 trace 定位"强约束在剧情里看不到"，把全部强约束提进 system prompt

承接 Round 17。用户反馈："剧本里的强约束，游戏中大部分没见到，从第一回合就有。"先做**架构 + 真实 trace 双向诊断**，再对症修复（用户明确要求"解决传递/执行，而非只做事后校验"）。

**诊断（dump 数据库 79 条旧 gm_runtime trace 的真实 prompt）**：

- 无独立"开场"路径：第一回合也走 `run_turn → generate_turn_runtime_output → build_runtime_messages`，全回合统一。
- 旧代码下 GM 实际收到：**SYSTEM 仅 3063 字符纯通用规则，本剧本强约束一条没有**；**USER 高达 60869 字符**。
- USER 6 万字符构成实测：`current_state_v2` **24937（41%）** ← 最大淹没源（随回合累积）、`runtime_story` 19467（32%）、`memory_summaries` 11.4%、`recent_turns` 10.7%。`hard_rules`+`story_core` 约束合计仅 ~2300 字符（**<4%**）。
- 根因（全在传递/执行层，非校验层）：①强约束占比 <4% 被淹没；②最高权重的 system prompt 对强约束零强化；③`current_state_v2` 独占 41% 是压倒性噪声。第一回合 state 小，所以"第一回合也没见到"主要是 ①②。
- 关键缺口：Round 17 的 system 注入**只放了"禁止类"（must_not/forbidden_*）**，而玩家"想看却没看到"的是**"必须类"**——`hard_rules.must_follow`（实测 12 条，如"[剧情规则]""[剧情规则]""[剧情规则]""[剧情规则]"）、`reveal_rules`/`continuity_rules`/`gm_output_rules`、当前幕 `objective`+未完成锚点、`core_mechanics` 规则。这些**全没进 system**。

**决策**：不砍 `current_state_v2`（实测构成是 skills/relationship_tracks/quest_log 等合理当前状态，非历史垃圾，砍它高风险低收益）。正解是**把强约束提到 system 顶部，使其根本不进被淹没的 user 水域**。（见 §4 新增决策）

**修复**：

- `story_settings.py::gm_hard_constraints` 扩展：在原"禁止类"基础上，新增 `must_follow` / `reveal_rules` / `continuity_rules` / `gm_output_rules` / 当前幕 `objective`+未完成锚点 / `core_mechanics` 规则（结构化字段转可读行）。
- `prompt_builder.py::_build_system_content` 重构为**三组渲染**：`## 本回合/本幕必须落实`（必须类，置顶）→ `## 绝对禁止`（禁止类）→ `## 命名与一致性`（canon_terms）。文案明确"必须类不是可选风格，每个相关回合都要在 narrative 真实体现"。

**实测效果（同一真实游戏）**：SYSTEM 3063 → **6598** 字符，强约束块 3522；must_follow 全部强约束（含"[剧情规则]""[剧情规则]""[剧情规则]"等）确认进入 system 顶部；next_act 仍 1493→32、main_quest 未来节点已裁。

**改动文件**：`api/app/services/story_settings.py`、`api/app/services/prompt_builder.py`、`api/tests/test_gameplay.py`（扩充 system 断言覆盖正向约束）。

**部署**：api/worker 不挂源码，**必须重建镜像**：

```bash
docker compose up -d --build api worker
```

**验证**：重建后容器内 `pytest tests/` **141 passed**。

> 遗留观察（未做，留待真实 trace 验证）：`current_state_v2` 占 user 41%，虽未淹没已提进 system 的强约束，但仍可能稀释 GM 对当前状态细节的注意力。若后续 trace 显示状态遵守仍差，再评估 state_v2 瘦身（高风险，需先看内容）。

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

### Round 2 (2026-05-28) — 阶段 0 止血

紧接 Round 1 完成"必修尾巴"。无新增 DB 迁移、无新增依赖。

**改动清单**：

| # | 主题 | 关键文件 |
|---|---|---|
| 0.1 | `TURN_JOB_TIMEOUT_SECONDS` 14 min → 18 min；超时文案改用常量计算 | turn_jobs.py |
| 0.2 | `_enforce_hard_forbidden_reveals` 拆出 `must_hit_beats`（语义错误，是"必须发生"不是"禁止揭露"） | gameplay.py |
| 0.3 | `on_stage` 不再写 DB，只 publish broker；DB 持久化交给紧随其后的 on_progress / on_update。单回合 SessionLocal 数减半 | turn_jobs.py |

**部署须知**：纯代码改动，重启 api + worker 即可。

```bash
docker compose restart api worker
```

### Round 17 (2026-05-29) — 从源头治理"提前揭露"与"约束不被遵守"

承接 Round 16：滑动窗口黑名单回退后，从**数据流源头**而非事后字符串拦截来治理两个核心痛点。先用数据库里真实剧本（`[示例剧本]`，5 幕 / 15 主线节点 / canon_terms 14 / must_not 10）量化、再改、再验证。

**痛点 1：GM 提前揭露未来剧情 —— 源头是"把未来幕全文喂给 GM"**

- 实测：游戏在 act_4，但每回合 `runtime_story.next_act` 把 **act_5（终局幕）完整 1493 字符**（objective「[剧情]…[剧情]」、dramatic_question「主角是实验体」、allowed_reveals 6 条、completion_anchors 9 条）直接喂给 GM；`main_quest_path` 15 个节点（含未来幕的 player_visible/objective/completion_signal）也全给。等于把答案递给模型再用 prompt 求它装不知道。
- 修复：`story_settings.py::redact_runtime_story_for_gm`——**仅对 GM 输入**裁剪：`next_act` 只留 `id`+`title`（供 rule 29/32 柔和转场方向，1493→32 字符）；`main_quest_path` 非当前幕节点只留 `id/title/act_id`，剥掉 player_visible/objective/completion_signal。**不动** hard_rules/story_core/current_act/worldview。
- 关键：裁剪只作用在 `prompt_builder.build_runtime_messages`（GM 提示词唯一咽喉点）。**DriftValidator 仍收到未裁剪的 `runtime_story_bare`**，才能识别"GM 提前揭露 next_act"——这正是 Round 16 保留的 drift prompt 第 5 条要判的偏离。Director 也仍看全量（需规划转场）。

**痛点 2：剧情不遵守剧本约束 —— 根因是约束埋在巨型 user JSON 深层、且零代码兜底**

- 根因 A：硬红线（hard_rules.must_not / story_core.canon_terms / must_not_become / forbidden_drift / 当前幕 forbidden_reveals）全塞在 user message 的 `runtime_story` JSON 里，与 worldview/materials/recent_turns 等"参考信息"平级混着，模型遵守度低。
- 修复 A：`story_settings.py::gm_hard_constraints` 抽出这些红线，`prompt_builder._build_system_content` 把它们格式化成显式分节**追加到 system prompt 末尾**（"=== 本剧本不可违反的硬约束（最高优先级）==="），凌驾于其他风格/节奏要求。
- 实测确认：上述真实剧本的 must_not 10 条、forbidden_reveals 4 条、canon_terms 14 个、must_not_become 等已逐条出现在 GM 的 system prompt。
- 痛点 2 的②确定性 canon 校验、③drift 每回合跑 + 逐条核对——**本轮未做**，留作后续按真实 trace/judge 数据决定（避免重蹈 Round 16"凭感觉加拦截"覆辙）。

**改动文件**：`api/app/services/story_settings.py`（+2 函数）、`api/app/services/prompt_builder.py`（system 拼装 + 裁剪接入）、`api/tests/test_gameplay.py`（+2 回归测试）。`drift_validator.md` 第 5 条 prompt 沿用 Round 16 保留版。

**部署须知**：api/worker **不挂载源码**（`docker-compose.yml` 仅挂 data 卷），代码改动必须**重建镜像**才生效：

```bash
docker compose up -d --build api worker
```

**验证**：重建后容器内 `pytest tests/` **141 passed**（含 2 个新回归：`test_gm_prompt_redacts_future_act_spoilers` / `test_gm_system_prompt_elevates_hard_constraints`）；并用真实剧本实跑 `build_runtime_messages` 确认 next_act 1493→32、红线进 system prompt。

### Round 16 (2026-05-29) — 回退"未来幕短语滑动窗口黑名单"误杀方案

**背景**：在 c4b488b 之后的 working-tree 里，曾尝试用代码层硬拦截"GM/Director 提前揭露未来幕剧情"。实现方式是把 `next_act` / `main_quest_path` / `forbidden_drift` 等**未来幕全文**切成 4/6/7/8 字滑动窗口子串，组成黑名单，再用"子串 in 文本"判断 GM 输出 / Director 决策是否违规（gameplay.py `_blocked_story_boundary_phrases` 系列 + `_sanitize_director_free_text`；drift_validator.py `_precheck_story_boundary` 系列）。

**为何回退**（容器内实测验证）：

- 一个典型 next_act objective「进入[地点]营救角色C」生成 **57 个**黑名单片段，全是 `营救角色C`/`核心设施`/`[组织]核`/`被囚禁在` 这类通用词组。
- 4 个**当前幕完全合法**的句子（"听说该地点的传闻""被囚禁在城南""角色擦肩而过""玩家内心想法营救念头"）全部被误判为 major 偏离。
- 连续剧情里角色/地点必然跨幕复现，子串匹配必然大量误杀。命中后链路：`_should_run_drift_validation` 强制 True → drift `_precheck` 强制 `approved=False/major` → **强制重写**（多烧一次 GM Pro 8000 token）→ Director 合法指令被清空替换成模板套话。等于稳定剧情每回合都被无谓重写、叙事退化、成本翻倍。
- 用脆弱的字符串子串匹配做语义判断 → 每修一次误杀就加白名单/调窗口，永远修不完（死循环根因）。
- 该逻辑还在 gameplay.py 与 drift_validator.py 里复制成两份（~80 行各一）。

**处置**：

- `git checkout HEAD -- gameplay.py drift_validator.py tests/test_gameplay.py`，三个文件回退到 c4b488b。
- **保留** `prompts/drift_validator.md` 第 5 条新增 prompt（"story_director 不是豁免凭证：若其指令本身要求 GM 提前揭露 next_act / 未来主任务 / 未来锚点 / 当前幕 forbidden_reveals，仍按 runtime_story 判偏离"）。把"防剧透"交回 **DriftValidator 的 LLM 语义判断** + 已有的精确 `forbidden_reveals` 硬注入（Round 1 #9 `_enforce_hard_forbidden_reveals`，整串匹配人工指定禁忌词）。

**结论性决策**（见 §4 新增）：代码层防剧透只能基于**人工精确指定的整串** forbidden_reveals，**禁止**把未来幕全文切成滑动窗口子串黑名单。

**验证**：容器内 `pytest tests/test_gameplay.py tests/test_turn_agents.py` **46 passed**；已 `docker compose restart api worker`。

### Round 15 (2026-05-28) — 流式 JSON 解析测试

`tests/test_stream_parse.py`（11 个，纯函数无需 DB）：`extract_partial_json_string_field` 的完整/未闭合/转义引号/换行/unicode/字段缺失/非字符串/unicode 转义中途断裂等。这是流式回合实时显示 narrative 的核心。本地全套 **102 passed**。

**测试加固线完成**：从会话开始的 ~50 个测试增长到 102 个，覆盖所有新增基础设施 + 核心 agent 链路 + 流式解析。

### Round 14 (2026-05-28) — context_compressor + state_extractor 测试

`tests/test_state_pipeline.py`：compressor `_trim_text` / `_fallback_summary`（幕后信息进 hidden_summary 不混入可见）；extractor 把精简后的 director_hints/drift_hints 注入 payload、无 hints 时不加 key。本地 pgvector 全套 **91 passed**。

测试加固线收尾：6 个核心 agent（director/gm 间接/drift/extractor/compressor/judge）+ telemetry/trace/admin 均有覆盖。

### Round 13 (2026-05-28) — DriftValidator + StoryDirector 测试

`tests/test_turn_agents.py`（fake router）：drift approved 不重写 / major 触发重写 / LLM 失败 fallback 不重写；director 正常解析（used_fallback=False）/ LLM 失败 fallback（used_fallback=True）。本地 pgvector 全套 **86 passed**。

### Round 12 (2026-05-28) — TurnJudge 测试

`tests/test_turn_judge.py`（fake router，不发真实 LLM）：overall 平均值 fallback、显式 overall、`evaluate_turn` 成功落库、LLM 失败落 error 行。本地 pgvector 全套 **81 passed**。

### Round 11 (2026-05-28) — admin endpoint 集成测试 + 修 overall_score 序列化

利用 Round 10 拿到的本地测试能力，给 Round 3-6 零覆盖的 admin endpoint 补集成测试，并修一个序列化不一致。

**新增**

- `tests/test_admin.py`（8 个 TestClient 集成测试）：stats 空库、trace 列表/详情/404、agent 过滤、golden label 过滤、turn-job 聚合排序、game evaluations、token 鉴权。

**修复**

- `admin.TurnEvaluationRead.overall_score`：`Decimal` → `float`。原来 FastAPI 把 `Numeric(3,2)` 序列化成 JSON 字符串 `"4.17"`，与前端 `lib/api.ts` 声明的 `number` 不一致。改 float 后 JSON 返回 number。（集成测试发现）

**验证**：本地 pgvector 全套 **77 passed**。顺带验证了 `turn_evaluations` 的 FK 约束生效（测试插假 turn_id 被拒，改用真实 game+turn）。

### Round 10 (2026-05-28) — 容器验证 + 修复 P0 部署阻断 bug

用本地 docker pgvector Postgres 第一次真实验证 Round 1-9 全部后端工作，并顺带发现+修复一个会让 app 起不来的既有 bug。

**修复（P0，既有 bug，非本次优化引入）**

- `app/routers/progress.py` 的 `delete_game_progress_save`：移除 `-> None` 返回注解。
  - 根因：该模块顶部 `from __future__ import annotations` 把 `-> None` 变成字符串 `"None"`，FastAPI 0.115.x 将其 eval 成 `NoneType` 并误判为 response_model，触发 `Status code 204 must not have a response body`，**import 阶段直接崩溃，整个 app 起不来**。
  - 影响面：用 `fastapi>=0.115`（requirements 范围 + uv.lock 为空不锁版本）构建的容器都会中招。本次优化新增的 admin endpoint 也因此连带不可用。
  - 全项目仅此一处（future annotations + 204 endpoint 的唯一组合）。

**验证结果（本地 pgvector pg16）**

- `alembic upgrade head` 成功，含新迁移 0025/0026/0027。
- `pytest tests/` **全套 69 passed**（含 5 个 TestClient 集成模块 + test_gameplay 向后兼容 + test_agent_infra 19 个新测试）。
- trace 端到端：`record_trace` 写入 → `list_traces` / `get_trace` / `get_turn_job_traces` 读出 OK。
- admin 查询：`stats_recent_turns`（聚合）、`list_golden_traces`（JSONB `extras[label]` 表达式）实测 OK。

**说明**：验证用的 psycopg/redis/rq/pgvector/fastapi 是装在本地全局环境，**未改 `requirements.txt` / `uv.lock`**。

> 附带建议（未做，留给后续）：`uv.lock` 当前是空的（只有 version 头），意味着依赖未真正锁定。考虑 `uv lock` 生成真实锁文件，避免 fastapi 等再次漂移到不兼容版本。

### Round 9 (2026-05-28) — dashboard 评分查询视图

`/admin` 加 Judge 评分查询：输入 game id → 该游戏所有回合评分表（overall + 6 维）。纯前端，复用 `GET /api/admin/games/{id}/evaluations`。`web/lib/api.ts` 加 `fetchGameEvaluations` / `triggerTurnEvaluation`。tsc + lint 通过。

至此 AI 质量闭环在 UI 上完整可见：概览 stats → trace 列表+详情 → judge 评分。

### Round 8 (2026-05-28) — 纯函数单元测试

给 Round 1-7 新增的 correctness-critical 纯函数补回归测试。零生产代码改动。

- `tests/test_agent_infra.py`（不依赖 DB，不用 db_session fixture）覆盖：
  - `agent_traces.extract_usage`：token usage 抽取的各分支
  - `turn_judge.JudgeResult` clamp：1-5 边界 + 非法值
  - `gameplay._filter_materials_by_director`：空集退全集语义、部分匹配、空白清理
  - `gameplay._enforce_hard_forbidden_reveals`：merge / 去重 / **must_hit_beats 不被并入（回归保护）**
  - `state_extractor._director_hints` / `_drift_hints`：字段抽取与空值丢弃

**注意**：本地无 psycopg 无法跑，仅 `py_compile` 通过 + 人工逐条对齐实现。容器内 `pytest tests/test_agent_infra.py` 是首次真实验证（已纳入 §9.2）。

### Round 7 (2026-05-28) — 收尾：stage 常量统一 + dashboard trace 详情

两件低风险、可静态验证的收尾。**刻意不动需要 trace 数据才能决策的 AI 行为项**（§7.2/§7.5）。

- **§7.8 stage 常量统一**：turn_jobs import gameplay 的 `STAGE_*` 构造 `TURN_JOB_STAGES`，裸字符串全替换为常量（保留非 stage 的 `job.status` / `event_type`）。纯重构。
- **3.1c dashboard trace 详情**：`/admin` 点击 trace 行展开完整 prompt_messages / reasoning / output（复用 `GET /api/admin/traces/{id}`）。纯前端，tsc + lint 通过。

**部署**：重新构建 web（后端 turn_jobs 改动需重启）。

```bash
docker compose up -d --build api worker web
```

### Round 6 (2026-05-28) — 阶段 3.1 Telemetry Dashboard

让 trace + telemetry + 评分**可视化**。AI 质量基础设施从"可查询"升级到"可一眼看"。

**新增**

- 后端：`GET /api/admin/stats/recent-turns?limit=` 聚合 endpoint（`RecentTurnStats`）。
- 前端：`web/app/admin/page.tsx` —— token 输入（复用 `rpgforge.settingsAdminToken`）+ 聚合卡片 + 最近 30 条 trace 表。
- `web/lib/api.ts`：新增 `fetchRecentTurnStats` / `fetchRecentTraces` / `fetchTraceDetail` / `fetchTurnJobTraces` 及类型。

**部署**：前端 + 后端都改了，需重新构建。

```bash
docker compose up -d --build api web
```

**访问**：浏览器打开 `/admin`，填入 `SETTINGS_ADMIN_TOKEN`（与设置页同一个）。

**阈值高亮**：director_fallback > 10% / rewrite > 20% / extractor_failed > 5% 卡片变琥珀色，便于一眼发现异常。

### Round 5 (2026-05-28) — 阶段 1.3 LLM-as-Judge

**新增**

- 迁移 `20260528_0027_turn_evaluations.py`：`turn_evaluations` 表，6 维评分 + overall + rationale + trace_id 回链 + status。
- `app/models/turn_evaluation.py`、`app/services/turn_judge.py`、`app/prompts/turn_judge.md`。
- `api/scripts/judge_turn.py`：CLI 触发，支持单 turn / 最近 N 个 / 全部。
- admin endpoints：`POST /turns/{turn_id}/evaluate`、`GET /turns/{turn_id}/evaluations`、`GET /games/{game_id}/evaluations`。

**保守 opt-in**：不在 maintenance 中自动跑——judge 自身消耗 Pro quota。任何评分都需要显式调用（CLI 或 admin API）。

**部署**

```bash
docker compose exec api alembic upgrade head    # 创建 turn_evaluations 表
docker compose restart api worker
```

**典型用法**

```bash
# 评最近一个回合
python -m scripts.judge_turn --game-id <UUID> --last 1

# 看一个游戏的评分趋势
curl -H "X-Settings-Admin-Token: $TOKEN" \
  http://localhost:8000/api/admin/games/$GAME_ID/evaluations
```

### Round 4 (2026-05-28) — 阶段 1.2 Golden replay 工具

第一版 golden 工作流：不引入新表，复用 `agent_traces` 当快照源。

**新增**

- `api/scripts/replay_trace.py`：按 trace_id / turn_job_id / agent 重发历史调用，对比旧/新输出。`job_kind="replay"` 隔离 trace。
- `api/scripts/diff_traces.py`：纯比对两条历史 trace（不发请求）。改 prompt 前后跑两轮，diff 即评估。
- `api/scripts/label_trace.py`：把 trace 标记为 golden（`extras.label` + `extras.note`）。
- `GET /api/admin/golden?label=&agent=`：列已标记的 golden。

**部署**：纯脚本和 router 改动，重启 api 即可（worker 不依赖）。

```bash
docker compose restart api
```

**典型用法**

```bash
# 进 api 容器
docker compose exec api bash

# 列最近 trace 找候选
curl -s -H "X-Settings-Admin-Token: $TOKEN" \
  http://localhost:8000/api/admin/traces?agent=gm_runtime&limit=10

# 把好回合标记为 golden
python -m scripts.label_trace <TRACE_ID> --label good --note "经典调查回合"

# 改 prompt 后跑一遍新回合，再对比新旧
python -m scripts.diff_traces --agent gm_runtime --last 2 --show-prompt

# 重放历史回合，看当前代码会怎么写
python -m scripts.replay_trace --turn-job-id <UUID> --agent gm_runtime
```

### Round 3 (2026-05-28) — 阶段 1.1 LLM trace 落表

第一次让 AI 链路"可观察"。代码改动量适中、新增一张表 + 一个 admin 路由前缀。

**新增**

- 迁移 `20260528_0026_agent_traces.py`：`agent_traces` 表 + 3 个索引（job / agent+created / status+created）。
- `app/models/agent_trace.py`：`AgentTrace` ORM。
- `app/services/agent_traces.py`：`TraceContext` + ContextVar + `record_trace()` + DeepSeek usage 提取。**所有 trace 写入失败都被吞掉，不影响主回合。**
- `app/routers/admin.py`：`/api/admin/traces` 列表、单条详情、按 turn_job 聚合三个 endpoint，受 `X-Settings-Admin-Token` 保护。

**修改**

- `app/services/model_router.py`：所有四个调用方法（`use_flash` / `use_flash_stream` / `use_pro` / `use_pro_stream`）都改走内部 `_call_chat` / `_stream_chat`，包装 trace 钩子。
- `app/services/turn_jobs.py` / `turn_maintenance_jobs.py` / `generator_jobs.py` / `generator_chat_jobs.py`：每个 RQ 任务入口调用 `set_trace_context()`。
- `app/main.py`：注册 admin router。

**部署须知**

```bash
docker compose exec api alembic upgrade head    # 创建 agent_traces 表
docker compose restart api worker
```

**用法**

```bash
# 列表
curl -H "X-Settings-Admin-Token: $TOKEN" http://localhost:3000/api/admin/traces?limit=20

# 单回合所有 LLM 调用
curl -H "X-Settings-Admin-Token: $TOKEN" \
  http://localhost:3000/api/admin/turn-jobs/$JOB_ID/traces
```

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

- [x] **0.1 TurnJob 整体 timeout 对齐**：`TURN_JOB_TIMEOUT_SECONDS` 已提到 `18 * 60 = 1080s`，覆盖最坏情况 900s + IO 开销。超时文案同步使用常量计算。文件：`turn_jobs.py:18`。

- [x] **0.2 `must_hit_beats` 从硬注入中拆出**：`_enforce_hard_forbidden_reveals` 只 merge `forbidden_reveals + forbidden_drift + must_not_become`，注释中说明 `must_hit_beats` 是"必须发生"语义，不能并入禁止列表。

- [x] **0.3 turn_jobs SessionLocal 优化**：审计后实际只有 9 个 SessionLocal 入口（之前 19 是把 turn_maintenance_jobs 算进去了）。机械合并风险高（长事务锁），收益低。改为单点优化：`on_stage` 只 publish broker、不再写 DB —— 紧随其后的 `on_progress` 会写一遍 DB，删除冗余写入。单回合 SessionLocal 次数减半。文件：`turn_jobs.py::on_stage`。

### 阶段 1 — AI 质量基础设施（2-4 周）

**这是当前项目的命脉。没有这一阶段，所有后续 AI 优化都是凭感觉。**

- [x] **1.1 LLM 调用 trace**（Round 3, 2026-05-28）
  - 新表 `agent_traces`（迁移 `20260528_0026`）：弱关联 `(job_kind, job_id)` 到上游 job；存完整 `prompt_messages JSONB` + `output_text` + `reasoning_text` + token usage + latency + status + extras。
  - `ModelRouter._call_chat` / `_stream_chat` 包装层统一写 trace；每次调用结束（成功/失败/empty）都同步落 1 条记录；写入失败被吞掉不影响主回合。
  - ContextVar 在 RQ worker 任务入口（`run_turn_job` / `run_turn_maintenance_job` / `run_chat_job` / `run_finalize_job`）set 一次，下游 LLM 调用自动归属。
  - 新增 `/api/admin/*` 路由（受 `X-Settings-Admin-Token` 保护）：
    - `GET /api/admin/traces?job_id=&agent=&status=&limit=` — 列表（不带 prompt/output 全文）
    - `GET /api/admin/traces/{trace_id}` — 单条完整内容
    - `GET /api/admin/turn-jobs/{job_id}/traces` — 一个回合的所有 trace 按时间正序
  - 已知边界：流式调用 DeepSeek 默认不返回 usage，所以 GM 流式的 tokens_* 会是 None。可接受。

- [x] **1.2 Golden 用例集 + replay 脚本**（Round 4, 2026-05-28）
  - **第一版**：复用 `agent_traces` 表作为 golden 数据源，不引入新表/新 fixture。每条历史 trace 自带完整 prompt + 输出，天然是"快照"。
  - `api/scripts/replay_trace.py`：按 trace_id / turn_job_id / agent 重发当前 ModelRouter，对比旧/新 output（unified diff + latency + token）。replay 的新 trace 归到 `job_kind="replay"` 不污染生产视图。
  - `api/scripts/diff_traces.py`：不发请求，纯比对两条历史 trace（手动 ID 或按 agent 取最近 N 条）。CI 友好。
  - `api/scripts/label_trace.py`：把 trace 升级为 golden，标签写入 `extras.label` (good/bad/neutral) + `extras.note`，不需要新加表列。
  - `GET /api/admin/golden?label=&agent=&limit=`：列出已标记的 golden 集合。
  - 评估指标：当前只用 unified diff + 长度/latency/token 对比。embedding cosine / Jaccard 等量化指标留给后续——先看人工标注规模有多大再决定是否需要自动化指标。

- [x] **1.3 LLM-as-Judge 自动评分**（Round 5, 2026-05-28）
  - **保守 opt-in**：不在 maintenance 自动跑（避免偷烧 quota）；通过 admin endpoint 或 CLI 手动触发。
  - 新表 `turn_evaluations`（迁移 `20260528_0027`）：6 维评分（canon_fidelity / state_consistency / pacing / prose_quality / freshness / safety）+ overall_score + rationale + trace_id 回链。
  - `app/services/turn_judge.py::evaluate_turn(db, turn_id)`：一次评分 = 一次 Pro 调用（task_type=`turn_judge`，可路由）。失败仍落库（status="error"）。
  - prompt：`app/prompts/turn_judge.md`，每维 1-5、必须给 rationale。
  - `POST /api/admin/turns/{turn_id}/evaluate` — 手动触发
  - `GET /api/admin/turns/{turn_id}/evaluations` — 历史评分（一个 turn 可多次评）
  - `GET /api/admin/games/{game_id}/evaluations` — 按游戏聚合
  - `api/scripts/judge_turn.py`：CLI 批量评分（`--turn-id` / `--game-id --last N` / `--game-id --all`）。
  - 与 trace 关联：judge 调用本身归到 `agent_traces.job_kind="judge", job_id=turn_id`，不污染主回合视图。

### 阶段 2 — 架构层重构（3-6 周）

- [ ] **2.1 Agent 抽象**：抽 `Agent[InputT, OutputT]` 基类，封装 timeout/fallback/trace/重试。让 Director/Validator/Extractor/Compressor 都基于它。新增 Agent 只需写 prompt + schema + fallback。

- [ ] **2.2 maintenance 状态机**：当前用 string `maintenance_stage` 切换，扩展性差。用 enum + transition table 重构，便于以后插入新 Agent（character_arc_tracker、faction_pressure_updater 等）。

- [ ] **2.3 AgentContextBundle 跨进程复用**：把主回合构造好的 `runtime_story_bare` / `state_v2` 序列化进 `TurnJob.turn_runtime_inputs`，maintenance 阶段反序列化复用，避免重复 `build_runtime_story`。

### 阶段 3 — 前端 + UX（穿插进行）

- [x] **3.1 telemetry dashboard**（Round 6, 2026-05-28）：后端 `GET /api/admin/stats/recent-turns` 聚合最近 N 个 completed turn job 的 director_fallback / rewrite / extractor_failed 率 + drift severity 分布 + 各 agent 平均 latency + 评分均值；前端 `web/app/admin/page.tsx` 展示聚合卡片（阈值超标变琥珀）+ 最近 30 条 trace 表。直接访问 `/admin`。未做 P50/P95 和图表（先用数字表，等真实数据）。

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
| 堆单元测试覆盖率 | 真正的"测试"是阶段 1.2 golden replay；Python 单测不能反映 AI 质量。**例外**：correctness-critical 的纯函数（telemetry 抽取、硬底线 merge、must_hit_beats 回归、hints 抽取）值得测——它们是数据正确性的基础，且能锁定回归。见 `tests/test_agent_infra.py`。区别在于"测数据正确性"而非"刷覆盖率" |
| 给每个 Agent 加重试 | DriftValidator 已经在 fallback 中放行，重试只会增加成本；除非 trace 显示真实重试收益 |
| 阶段 2.1 Agent 抽象基类（暂缓，非永久放弃） | 当前没有要新增的 agent，抽象的唯一收益"加新 agent 省事"无处兑现。各 agent 的 fallback 差异大（Director 本地决策 / Validator 放行 / Extractor 抛错 / Compressor 拼接），强行统一反而降低可读性。在"无法本地跑测试 + 自主无人审查"下做核心链路大重构 ROI 为负。**触发条件**：真要加第 6 个 agent，或能在容器里跑回归测试时，再做 |
| 凭感觉改 AI 行为（material 过滤强度 / director hints / drift 阈值，§7.2/7.5/7.3） | trace 基础设施刚建好、还没有真实数据。这些都标注为"等数据再定"。先收集 trace + judge 评分，用数据驱动，而不是继续猜 |
| 用"未来幕全文切滑动窗口子串黑名单"在代码层拦截剧透（Round 16 已回退） | 子串匹配做语义判断必然大量误杀：跨幕复现的角色/地点会让当前幕合法叙述被判 major 偏离 → 无谓强制重写 + Director 指令被擦成套话 + 成本翻倍。每修一次误杀就加白名单/调窗口 = 修不完的死循环。**正路**：防剧透交 DriftValidator 的 LLM 语义判断；代码层兜底只用**人工精确指定的整串** `forbidden_reveals`（`_enforce_hard_forbidden_reveals`），绝不自动从未来幕文本生成黑名单 |
| 砍 `current_state_v2` 体积来给约束让位（Round 18 评估后不做） | 实测 state_v2 24915 字符构成是 skills/relationship_tracks/quest_log/protagonist_sheet 等合理的当前状态，非历史垃圾；砍它直接威胁状态一致性，高风险低收益。正解是把强约束提进 system prompt（最高权重、不进被 state 淹没的 user 水域），而非缩小噪声。仅当后续 trace 显示状态遵守仍差时再重评 |
| 靠事后校验（DriftValidator/Judge）解决"约束不被遵守"（Round 18 明确否决为主手段） | 用户洞察：校验是亡羊补牢，执行/传递没做好时校验只是补漏。根因是强约束没被有效传给 AI（占 user <4% + system 零强化），应先在**传递层**把强约束提进 system prompt 确保 AI 一定看到；校验作为补充而非主手段 |

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

8. ~~**`TURN_JOB_STAGES` 与 `gameplay.py::STAGE_*` 重复定义**~~（已解决 Round 7, 2026-05-28）：turn_jobs 现在 import gameplay 的 `STAGE_*` 常量构造 `TURN_JOB_STAGES`，stage id 单一来源在 gameplay.py，turn_jobs 只补中文 label。turn_jobs 内所有裸 stage 字符串也替换为常量（保留 `job.status="completed"` 和 `event_type="completed"`，它们不是 stage）。

---

## 8. 文档维护规则

- 每完成一轮工作（不论大小），在 §1 追加 `### Round N (日期)` 子节，列出改动清单。**不要修改历史 Round 的内容**。
- 路线图条目落地后，在原位打 `[x]`，不要删除。
- 新发现的"不做"决策追加到 §4。
- 关键常量调整后同步 §5.2 的值。
- 本文件本身的目录结构（编号章节）保持稳定，方便 Claude 用章节号引用。

---

## 9. 容器验证清单

> ✅ **Round 10 已用本地 docker pgvector(pg16) 实测通过**：迁移 upgrade head、全套 69 pytest、trace 端到端、admin 查询全部 OK。
> 下面清单保留给**生产环境首次部署**复核（生产用 docker-compose 的真实 redis + worker，本地验证未覆盖 RQ worker 实际消费和真实 LLM 调用）。

### 9.1 迁移 + 启动

```bash
docker compose up -d --build api worker web
docker compose exec api alembic upgrade head     # 应升到 20260528_0027
docker compose exec api alembic current           # 确认 head
```

预期新增 3 张表：`agent_traces`、`turn_evaluations`，以及 `turn_jobs` 上 5 个新列。

```bash
docker compose exec postgres psql -U rpg -d rpgforge -c "\d agent_traces"
docker compose exec postgres psql -U rpg -d rpgforge -c "\d turn_evaluations"
docker compose exec postgres psql -U rpg -d rpgforge -c "\d turn_jobs" | grep -E "director_used_fallback|drift_severity|rewrite_triggered|extractor_failed|turn_runtime_inputs"
```

### 9.2 后端测试

```bash
docker compose exec api pytest tests/ -x -q
```

重点确认 `test_gameplay.py` 全过（Round 1 改了 PromptBuilder / StoryDirector / DriftValidator 的签名，但都向后兼容）。

### 9.3 trace 落库（玩一回合后）

```bash
# 玩一回合，然后：
docker compose exec api python -c "
from app.db.session import SessionLocal
from app.models.agent_trace import AgentTrace
from sqlalchemy import select, func
with SessionLocal() as db:
    n = db.scalar(select(func.count(AgentTrace.id)))
    print('agent_traces rows:', n)
    for t in db.scalars(select(AgentTrace).order_by(AgentTrace.created_at.desc()).limit(6)):
        print(t.agent, t.status, t.latency_ms, 'ms', t.model)
"
```

预期：一回合产生 story_director / gm_runtime（可能 + gm_runtime_rewrite）/ drift_validator / state_extractor 等多条 trace。

### 9.4 telemetry 字段

```bash
docker compose exec postgres psql -U rpg -d rpgforge -c \
  "SELECT director_used_fallback, drift_severity, rewrite_triggered, extractor_failed FROM turn_jobs ORDER BY created_at DESC LIMIT 5;"
```

### 9.5 admin API（需要 SETTINGS_ADMIN_TOKEN）

```bash
TOKEN=<你的 token>
curl -s -H "X-Settings-Admin-Token: $TOKEN" http://localhost:3000/api/admin/stats/recent-turns | python -m json.tool
curl -s -H "X-Settings-Admin-Token: $TOKEN" "http://localhost:3000/api/admin/traces?limit=5" | python -m json.tool
```

浏览器打开 `http://localhost:3000/admin`，填 token，确认卡片和 trace 表渲染。

### 9.6 LLM-as-Judge（消耗 quota，可选）

```bash
GAME_ID=<某个游戏 id>
docker compose exec api python -m scripts.judge_turn --game-id $GAME_ID --last 1 --yes
curl -s -H "X-Settings-Admin-Token: $TOKEN" \
  http://localhost:3000/api/admin/games/$GAME_ID/evaluations | python -m json.tool
```

### 9.7 验证后

全部通过后，把本节标题改为"Round 1–6 已验证（日期）"，并在 §0 移除待验证警告。
若发现问题，记录到 §7 已知遗留疑点或新开 Round 修复。
