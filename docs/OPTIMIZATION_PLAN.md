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
| 最近一轮 | Round 39 — 看板成为完整设定编辑面：字段数据派生全覆盖（home_base/worldview facts/完成锚点等）+ 字段类型系统(number/bool/objectList/keyValue/json) + 空块折叠开关 + 手动新增数组项（纯前端） |
| 完成日期 | 2026-06-04 |
| 游戏方向 | 2026-06-02 新开「游戏方向」专项（可玩性/机制/叙事/体验，区别于 GAME_SYSTEM_AUDIT 审的状态正确性）。核心判断：剧情遵循已过度投入，缺**博弈/失败/结局**三大根本，继续加固防跑偏为负收益。路线图见 [`GAME_DIRECTION_AUDIT.md`](GAME_DIRECTION_AUDIT.md) §4 |
| 文档卫生 | 2026-05-29 更新：§0/§3/§7/§9 对齐到 Round 24 现状（此前停在 Round 1–15）。架构蓝图见 `PROMPT_ARCHITECTURE_REDESIGN.md` |
| 当前阶段 | **2026-06-04 一轮大型前端建设（Round 36–39）**：围绕「story_settings 可视化编辑」建了一套**设定看板**子系统，并落地三件事——① 生成页重设计（Round 36）② 设定页 + 信息架构去重（Round 37）③ **剧本炼金工坊**（Round 38，setting_modules 模块库 + 提取/并入 + AI 本地优化）④ 看板成为完整设定编辑面（Round 39，全字段数据驱动 + 字段类型系统 + 手动新增项）。详见各 Round 与下方「设计文档」。 |
| 前端子系统（新） | **设定看板** = `web/lib/generatorBoard.ts`（buildBoardModel/字段派生/writeBlockFields）+ `web/components/board/*`（SettingsBoard/BoardFieldEditor/BlockDetailModal/Tabs/Grid）。三处复用：生成页 `app/games/new`、设定页 `app/games/[id]/settings`、工坊并入面板。**工坊** = `/workshop` + `web/components/workshop/*` + 后端 `setting_modules` 表/`/api/modules`/`module_library`/`module_adapter`。**导航**：顶栏「工坊」；游戏内「设定」页。 |
| 设计文档（必读） | 今天 4 个特性的 spec/plan 全在 [`docs/superpowers/specs/`](superpowers/specs/) 与 [`docs/superpowers/plans/`](superpowers/plans/)（2026-06-04-*：generation-ui-redesign / game-settings-board / script-alchemy-workshop / board-complete-settings-editor）。接手前端工作前应读对应 spec。 |
| ✅ 验证状态 | 后端容器内 **231 pytest** 全过 + `ruff check .` 干净；前端 `npm run lint` 0/0 + **vitest 36** + `tsc` + `next build` 全过；CI（push main 触发）全绿。三个特性合并自 PR #3/#4/#5（已 merge），看板编辑面经本地合并（Round 39），串台 bug 修复 PR #6。 |
| 下一步建议（P2 待办） | 均为本轮明确留到 P2 的项：① 生成页接入「手动新增数组项」（设定页已做，共用组件 onAddItem 回调即可）② objectList 子卡拖拽排序 ③ 工坊「批量提取」「单块 AI 重生成」「模块版本史」④ 同名条目编辑按索引精确定位（现按 name 取首个，见 [`board-complete-settings-editor-design.md`] §8）⑤ AI 本地优化、并入闭环的真实游玩验证。**注意**：以下「游戏方向/文档卫生」两行为 2026-06-02/05-29 的历史背景，非当前焦点。 |

---

## 1. 已完成

### Round 52 (2026-06-22) — 剧本遵循护栏：高压锚点停滞监控 + 导入剧本 required 锚点警告

承接 Round 51 的 `act_pacing`：本轮不新增 LLM、不自动补锚点、不恢复同步 drift，只做两条确定性监控/护栏，防止"信号已经进 Director/GM，但真实运行仍看不到推进"和"弱剧本导入后天然缺转幕抓手"静默发生。

**① 高压锚点停滞监控（post-state，低误报）**：
- `act_pacing.py` 新增 `ANCHOR_PACING_STALL_TURNS_AFTER_HIGH = 3` 与 `observe_act_pacing_stall()`。当 `pressure=high` 后再持续 3 回合仍无 required 锚点进展，返回 `act_pacing_stalled` flag；只读 state/runtime_story，不做文本语义判断、不写状态。
- `turn_maintenance_jobs._apply_delta` 在状态提取、应用、rebuild 之后计算停滞观测，并合并进 `turn_runtime_inputs.output_observation.flags` 与 `output_observation.act_pacing`。选择 post-state 是为了避免误报"本回合其实完成锚点但 extractor 尚未入库"。
- 前端本回合详情已展示 `observation.flags`，无需新增 UI 即可看到停滞告警。

**② 导入/生成剧本结构警告（不阻断旧兼容）**：
- `story_settings.py` 新增 `story_settings_warnings()`：当 `act_plan` 中某幕没有任何 `required=true` 完成锚点时，返回作者可见 warning；`validate_story_settings` 仍保持只 log 不 raise，避免破坏旧存档/手动空剧本兼容。
- `GeneratorFinalizeResponse` / `GeneratorFinalizeJobRead` 增加 `warnings`。`/api/generator/import-script`、同步 finalize、异步 finalize job snapshot/read 都透出 warnings。
- `games/new` 页面新增 `scriptWarnings` 展示区，导入或生成完成后在看板上方显示结构提示；不阻止继续编辑或创建。

**验证中顺手修复**：`web/Dockerfile` 给 Next 运行时 `.next/cache` 预建并授权给 `node`，避免 web 容器在页面资源缓存时出现 `EACCES` 日志。

**验证**：TDD RED→GREEN；容器内目标后端测试 **19 passed**（`test_act_pacing`、`test_act_pacing_wiring`、`test_import_script`、维护集成用例）；全量后端 `pytest tests/` **268 passed**；`ruff check app tests` 干净。前端 `eslint .`、`tsc --noEmit`、`vitest` **52 passed**、`next build` 通过。Docker 已重建并重启 api/worker/web，api/web/worker 状态与日志正常；浏览器验证 `/games/new` 导入弱剧本会显示 `剧本结构提示`。

### Round 51 (2026-06-20) — 锚点驱动节奏压力：治"不跟剧本 / 推不动 / 选项全是原地打转"

**实证诊断（用户反馈"剧本遵循性差 + 剧情推进有问题"）**：查真实存档 agent_traces（某真实存档一局约 28 回合，剧本内容脱敏不复述），铁证——第一幕 4 个 required 锚点**只完成 1 个**，`ready_for_next_act` 始终 false、**从未转幕**；导演 scene_objective 连续十几回合反复设"准备型 / 训练型 / 加固型"小目标，**从不真正触发当幕的关键锚点戏**（甚至出现"避免提前触发"的目标）；crisis 全程满血 100（危险从未兑现）。排除两个误区：剧本内容**完整进了 GM payload**（Round 48 重构没丢）、抽查 GM **严格跟了导演指令**。根因落在**导演层缺节奏压力**——它每回合只反应式服务玩家当下行动、无"本幕停留多久 / 距上次锚点进展多久"信号，于是在玩家不断选择停留型行动时被"再准备一次"无限拖住。**且 GM 给的 A/B/C/D 也全落在"准备"框里**（连续 5 回合实测，无一可推进），死循环自我强化。

**为什么"修改之后"才明显（钟摆过度矫正）**：Round 44/46/49 为治"生硬/像规则报告"集中松绑了所有向前驱动——Round 44 把 gm_instruction/scene_objective 降成软提示+删素材清单、Round 46 删同步"拽回主线"、Round 49 删锚点文本兜底（转幕 100% 靠 LLM 显式上报）。一个旁证：更早一局（Round 44 前）能逐幕推进、触发过转幕；本轮诊断的那局（Round 44 后）28 回合困在第一幕。**Round 49 §"已知中间态"里早埋的 TODO**（"停留超 M 回合无锚点进展→给 Director 软提示"）本轮兑现。

**改动（纯导演 + GM 选项层，确定性信号、零新增 state、rebuild 安全、无迁移）**：
- **新增 `app/services/act_pacing.py`**：`compute_act_pacing(state_v2, runtime_story)` 纯函数。用现成字段算 `turns_since_anchor`（`current_turn − last_anchor_update_turn`，缺省回退 `last_advance_turn`/0）→ `pressure`：无未完成 required→`ready`；`≥ANCHOR_PACING_HIGH_TURNS(8)`→`high`；`≥ANCHOR_PACING_RISING_TURNS(4)`→`rising`；否则`low`。`next_required_anchor` = 当幕第一条未完成 required 锚点 `{id,title,completion_signal}`（`required` 默认 True，与 story_settings/state_applier 对齐）。回合号读 `state_v2_view` 的 `active_scene.turn`（兼容裸 state 的 `current_turn`）。
- **注入两处 payload**：`story_director._payload` 顶层加 `act_pacing`；`prompt_builder.build_runtime_messages` 在**尾段**（`current_act_open_anchors` 旁、缓存断裂点之后）加 `act_pacing`——**不破 Round 48 的 prefix cache**（字节前缀测试仍过）。
- **`story_director.md` 新增规则 13**：按 pressure 调 scene_objective——`high` 时**必须**把戏推到 `next_required_anchor.completion_signal` 兑现的临界点（锚点本回合就发生/启动，不再"准备一次"），仍承接玩家行动；`ready` 不硬推。
- **`gm_runtime.md` 新增规则 36**：pressure 为 rising/high 时，A/B/C/D **至少一条**是推向 `next_required_anchor` 的前进选项，**禁止四个全是休整/加固/原地重复**；其余仍可谨慎/探索/关系向（不与规则 5/6 冲突、仍是建议非强制）。

**明确不做（避免把"生硬"请回来）**：不改 GM 文笔/字数、不重启同步 drift。pacing 只走导演决策与"选项至少留一条出路"，HOW 写仍由 GM 自主。

**已知局限（诚实记录）**：① Round 44 把 gm_instruction 降为软提示——若上线后监控到 high 压力下 GM 仍拖延（导演已要求收束、GM 仍只回应玩家小动作），下一轮再给 GM 加一条呼应规则。② `turns_since_anchor` 在完成任一锚点时重置——多 required 锚点的幕里，完成一个会给喘息再爬升，属预期设计。③ 阈值 8/4 为 observation-driven 初值，待上线看真实 pressure 分布再调。

**验证（TDD：RED→GREEN）**：容器内 `ruff check` 干净 + `pytest tests/` **264 passed**（+8：`test_act_pacing` 6 个纯函数 low/rising/high/ready/开局边界/required默认 + `test_act_pacing_wiring` 2 个导演&GM payload 注入）。**部署**：api/worker 镜像已重建重启（无 web、无迁移）。**行为效果待真实游玩验证**（LLM 是否在 high 压力下真把戏推向锚点、是否真给出前进选项）——纯函数与信号注入已测，规则遵守度只能实机观察。

### Round 50 (2026-06-19) — 导入自定义剧本（外部 AI 写 → 粘贴 JSON → 看板预览 → 建游戏）

新功能：玩家在外部 AI（Claude/ChatGPT）里按 RPGForge 结构写好剧本，粘贴 JSON 即可新建一个"契合自己想法"的可玩游戏。设计 spec 见 `docs/superpowers/specs/2026-06-19-import-custom-script-design.md`。

**复用为主、零新增 LLM 链路**：`games/new` 现有流水线本就是 `generatedConfig → buildBoardModel → SettingsBoard 分块预览 → create-game`；本轮只给它加一个"喂入口"，下游预览/编辑/建游戏/开场白全复用。

**后端**（2 端点，`api/app/routers/generator.py`）：
- `GET /api/generator/authoring-kit`：下载"剧本创作包" Markdown = 现成 v2 指南（`export_settings_guide_markdown`）+ 完整范例剧本 + AI 指令。新模块 `app/services/authoring_kit_exporter.py`，范例 `AUTHORING_KIT_EXAMPLE`（全新编写的侦探题材，**不碰任何真实存档**）由测试守护必须能过 `validate_story_settings`。
- `POST /api/generator/import-script`：吃粘贴 JSON → `build_imported_game_config`（`game_creator.py`）校验+归一化 → 返回 `GeneratorFinalizeResponse`（与 finalize 同构，`model_used="import"`）；不建游戏、不落库。

**关键坑 + 兜底**：① 给 AI 的指南必须用 **story_settings v2** 真实 schema，`docs/AI_STORY_RUNTIME_GUIDE.md` 那份旧结构（script_outline/campaign_contract）**不可导入**。② `normalize_story_settings` 会把任意输入静默纠成合法空壳（title 缺省「未命名游戏」、format_version 纠回），故 `validate` 挡不住垃圾粘贴 → 新增 `_story_has_content` 防线：标题/世界观/角色/幕/故事核心全空则 400。③ `_extract_story_settings` 兼容裸对象 / settings-export 包裹体 / 前端再包一层。

**前端**（`web/app/games/new/page.tsx` + `web/lib/api.ts`）：顶部加「AI 访谈生成 | 导入剧本」模式切换；导入面板 = 下载创作包 + 粘贴 textarea + `.json` 上传 + 解析预览；解析成功 `setGeneratedConfig` → 复用现成看板预览 → 「确认并开始冒险」。

**过 Round 44 前端门**：这不是给冻结的 SettingsBoard/工坊加作者便利新功能，而是**给玩家核心循环加一条创建入口**——让玩家直接得到契合自己想法的可玩游戏（"读剧情→做选择→看后果"的前置）。触点是 `games/new` 创建流，非冻结看板。

**安全验证**：TDD（6 个新测试，含空剧本拒绝走 RED→GREEN）；容器内 `ruff` 干净 + **pytest 255 passed**；前端 `eslint`/`tsc`/`vitest 52` 全过；重建 api/worker/web 后**真实端点冒烟**：范例→200、垃圾→400、极简真实剧本→200。

**部署**：api/worker/web 镜像已重建重启（无迁移）。

### Round 49 (2026-06-19) — T2 外科拆 state_applier Phase A：删锚点文本推断 backstop

承接架构审计"state_applier 是全项目最烂巨石"的客观结论（2150 行、184 行脆弱中文子串匹配、Round 16/26/27/28/29/30/33/34 八轮返工同一病灶）。本轮做 Phase A——**外科式删掉锚点文本推断 backstop**（最易误判、最该砍的一层）。

**删除**：`_inferred_completed_anchors`（原在 `_sync_story_progress_and_quests` 调用，用 narrative 证据整串/整短语匹配反推锚点完成）+ `_anchor_completion_reason`，共 **-67 行**（2150→2083）。共享 helper（`_completion_anchor_records_for_act`/`_meaningful_phrases`/`_evidence_units`）保留（任务推断等仍用）。

**新契约**：锚点完成**只剩 LLM 显式 `completed_anchors`**（`extract_state_delta` 规则 10，经 `_apply_story_progress` 白名单校验入库）。转幕（`_computed_ready_for_next_act`）/通关（`campaign_complete`）本就只读 `completed_anchors` 列表、从不调被删函数 → 链路自洽。

**安全验证**：① 容器内 `ruff` 干净 + `pytest tests/` **250 passed**（2 个断言推断的测试改成新契约：一个显式上报两锚点→转幕+派生；一个空 delta+证据→锚点不完成）；② **3 个真实存档 rebuild 零回退**（act/anchors/campaign_complete 完全不变）；③ **全存档扫描 0 条"推断来源锚点"**（`anchor_history.reason` 无"根据当前状态证据补全"）→ 删推断对所有现有数据零回退、**无需迁移**。

**2-Agent 对抗性审查 + 采纳**（无 critical/high，2 minor-nits）：确认 `game.status=completed` 仅由 `campaign_complete`（末幕锚点）驱动、与 main_quest 零耦合 → **不会假通关**。采纳：① 修正注释（原写"确定性转幕兜底"代码里不存在，已改为明示"无文本兜底、漏报即卡幕"）；② `does_not_infer` 测试补回 `main_quest_10==completed` 断言，钉死"任务-锚点解耦"契约。

**已知中间态 / 取舍（诚实记录）**：
- **任务-锚点解耦**：`_quest_completion_evident`（任务文本推断）属 Phase B 未删 → main_quest 可经文本推断 `completed`，但其锚点不进 `completed_anchors`（玩家可能看到"主线任务已完成、剧情却不前进"）。Phase B 删任务推断后消解。
- **转幕单点依赖**：删 backstop 后，有 required 锚点的幕转幕 **100% 依赖 LLM 显式上报**，无文本兜底——LLM 漏报锚点即卡幕。这是审计认可的取舍（"别用代码猜中文语义"），但属高敏感单点。**已做第一道缓解**：`extract_state_delta.md` **规则 10** 从被动（"只有…才…"）改为**主动逐条核对**——对当前幕每个未完成锚点判断 GM 本回合是否达成其 completion_signal，并明示"这是唯一来源、漏报即卡幕"（非脆弱、纯 LLM 语义判断，正是审计认可的层）。**仍待**：上线后监控漏报率（如"narrative 含某锚点整串 completion_signal 但 N 回合未上报"占比）；若偏高，再设计**确定性**转幕兜底（如停留超 M 回合无锚点进展→给 Director 软提示，是提示不是自动完成）。

**Phase B（未做，更险）**：删任务/线索文本推断（`_quest_completion_evident`/`_activity_text_matches`/`_completed_topic_in_thread`，184 行里的大头）——synthesis 要求"先加 LLM 显式 resolve 路径，否则 un-fix Round 26 的线索 bug"。

**部署**：api 镜像已重建重启（无 web 改动、无迁移）。

### Round 48 (2026-06-19) — T1 prefix cache 多段切分（可缓存前缀 33%→84%）

承接 Round 22c 的"宪法层字节固化"。审计指出 GM 上下文 prefix cache 命中率仅 ~4.5%——逐回合变化的内容混进了稳定前缀。本轮做真正的"多段切分"：把逐回合内容移出可缓存前缀。纯 GM payload 改动，drift/state-ops 各自 `build_runtime_story` 不受影响。

**根因**：`build_runtime_story` 把 `current_act.completion_anchors` 过滤为"未完成项"（随完成逐回合缩短），它同时进了 ① system 幕级简报（断裂点）② user 的 `runtime_story`。且 `runtime_story` 还含逐回合的 `story_progress`、`selected_action_style`、`related_story_materials`——这一大块（含整局静态的 story_core/worldview/角色/机制/主线）因此被钉在断裂点之后、永不缓存。

**改动**：
- **system 幕内稳定**（`gm_hard_constraints`）：从幕级简报移除逐回合的未完成锚点，只留 objective/dramatic_question（幕内静态）。
- **runtime_story 拆分**（`prompt_builder._split_runtime_story_for_cache`）：把 GM 的 runtime_story 拆成「静态」+「`current_act_open_anchors`」；抽走 `story_progress`（GM 从 current_state_v2 读）/`selected_action_style`/`related_story_materials`（尾段已单列）/`current_act.completion_anchors`。
- **user payload 重排**：`game → generation_parameters → runtime_story(静态)` 进可缓存前缀；`current_act_open_anchors → current_state_v2 → 风格/素材/记忆/导演/recent_turns/player_input` 放逐回合尾段。
- **`gm_runtime.md`**：规则 21（runtime_story 现为「静态设定视图」）、23（priority_order 是逻辑阅读序、非字面键路径）、30（锚点引用改指 `current_act_open_anchors`）。

**实测**（真实存档）：可缓存稳定前缀 = system(9111) + game/gen + 静态 runtime_story(13500) = **84.0%** 总输入（改前仅 system ~33%；更早还断在锚点处）。按 ~1/10 缓存计价，命中时 input 成本约降 76%。缓存幕内有效、随幕推进（每~10回合）断一次。**注**：GM 流式调用不回 usage，无法直接测 live 命中；字节稳定前缀长度是命中的决定性代理指标（已用字节级测试钉死）。

**3-Agent 对抗性审查 + 采纳**（1 OK + 2 minor-nits，无 critical/high）：确认无悬空引用（story_director/extractor/drift 仍引用 runtime_story.current_act.completion_anchors 是对的——它们各自 build 完整未拆分版）、稳定前缀纯净、无别处消费方。采纳 LOW：规则30 删掉对 GM 不可见的"静态定义"措辞、`_split` 加 `isinstance(list)` 守卫、payload 测试升级为**字节前缀相等**、规则23 澄清 priority_order。

**验证**：容器内 `ruff check app/` 干净 + `pytest tests/` **250 passed**（+3：拆分纯函数 / 静态前缀字节稳定 / system 字节稳定）。**部署**：api/worker 镜像已重建重启（无 web 改动、无迁移）。

### Round 47 (2026-06-19) — T1 属性 seeding：让 d20 判定真实生效（角色 build 影响成败）

承接 T0 的「行动后果卡」——审计发现开局 `protagonist.attributes` 多为空 → `_compute_modifier` 的 attribute 加成恒 0 → 前中期判定纯靠运气、角色 build 不影响成败、后果卡的 `+modifier` 永远是 0。本轮让属性真正进入判定。纯后端，无迁移。

**统一六维**：力量/敏捷/体质/智力/感知/魅力（D&D 式，10=常人均值，加成 `(值-10)//2`）。判定层 `_attribute_bonus` 大小写+子串匹配 `action_check.attribute`；Director（`story_director.md` 规则12）被要求"用 current_state_v2 里已有的名字"填 attribute → 同名即匹配，**属性名对齐天然成立**（六维或自定义属性都行）。

- **生成侧**（`generate_config_section.md`）：`initial_state.protagonist.attributes` 模板由 `{}` 改为填满六维示例 + 规则"数值 8–16、按主角设定分配明显强弱（强项 13–16/弱项 8–9），不要全填 10 或留空"。→ 新游戏开局就有 build 差异。
- **初始化兜底**（`game_creator`）：新增 `DEFAULT_PROTAGONIST_ATTRIBUTES`（六维全 10，定义在 `state_v2`）；`_fill_protagonist_from_story_settings` 在 configured 早返回**之前**，属性空则填默认（AI 未产出/手动建档也不空）。
- **老存档零迁移**（`state_v2._protagonist_sheet`）：投影时属性仍空则懒注入默认六维。不动存档、rebuild 可复现。**注意**：仅影响后端 `state_v2_view`（判定层/Director/GM 投影）；前端 `getStateV2FromGame` 是独立客户端归一、读原始 state——故空属性老存档"判定用中性六维生效、但前端状态页仍显示空"，属轻微展示侧不一致、非 bug（新游戏两端一致）。
- **DC**：本轮**不动**（观察驱动）。中性默认让老存档/非专长行动难度不变；专长行动变易是"build 该起作用"的正确表现；hard(16)/extreme(20) 在典型 +3~+5 修正下仍有真实不确定性（hard 需 roll≥11~13）。盲目通胀 DC 会变 grindy——上线后看真实掷骰分布再定。
- **可见度**：行动后果卡（Round 44）已在阅读流展示 outcome_label + 骰面；只露结果不露 breakdown（防泄露关系/隐藏值）。

**验证**：容器内 `ruff check app/` 干净 + `pytest tests/` **247 passed**（+4：懒投影默认/真值保留/game_creator 填充/填充不覆盖生成值）；真实老存档 rebuild 实测属性原样保留、空属性投影得默认六维。**部署**：api/worker 镜像已重建重启（无 web 改动、无迁移）。

### Round 46 (2026-06-18) — T1 Drift 改异步事后审计（去延迟尖峰 + 不再压制能动性）

承接路线图 T1，把"偏离校验(drift)"从玩家同步路径改成异步事后审计。**§2.1/§2.3/§2.5 链路表已变，下次维护文档时同步**（玩家路径少一层、stage_total 7→6）。

**玩家路径（gameplay.py）**：删 `_should_run_drift_validation`（旧：首回合+每3回合+高风险词/forbidden 命中触发）与 `_validate_and_maybe_rewrite`（major/critical → 二次 Pro 重写）、`STAGE_DRIFT_VALIDATION`、gameplay 的 `DriftValidator` 依赖/构造参数。GM 写完 → 观测 → 返回。**净效果**：去掉每3回合的 90s 同步校验尖峰 + 命中重写的 360s 二次等待 + "偏离→重写拽回主线"对玩家发散探索的压制。

**唯一事后剧透兜底（新增 `_redact_forbidden_reveals_if_hit`）**：读 `output_observer` 已算的 `forbidden_reveal_hits`（当前幕 `forbidden_reveals` **整串命中**、高精度低召回、零额外 LLM）；命中（罕见）才做一次定向重写"仅删提前揭露、其余保留"，重写失败/超时保留原稿。重写后复检残留命中 → `logger.warning` 告警；观测失败置 `output_observation={"observe_error":True}`，避免防线静默塌陷。

**异步审计（turn_maintenance_jobs `_audit_drift`）**：observe-only，回填 `turn_jobs.drift_severity` 供 admin 看板监控"去同步控制后跑偏趋势"，**不触发任何重写**；任何异常只 `logger.exception`、绝不拖垮维护。session 内 eager-load（selectinload config/state）+ 重建 `GMRuntimeOutput`（需正好 4 个 A/B/C/D 选项，失败跳过）→ session 外调 `DriftValidator.validate`。

**stage**：`TURN_JOB_STAGES` 去 drift 项 → `TURN_JOB_STAGE_TOTAL` 7→6；前端 `stageTotal` 读后端动态值（顺手把 `turnJobStream.ts:58` / `play/page.tsx` 两处陈旧 `|| 7` fallback 改 6）。

**4-Agent 对抗性审查 + 采纳**（无 critical/high，3 minor-nits + 1 needs-fix=缺测试）：① **时序修正**：`_audit_drift` 从 `_apply_delta` 之后**移到之前**——否则幕转换回合 state 已推进、用新幕 runtime_story 配旧幕 director 判定 → drift_severity 在最高风险回合系统性误判；前移后用 pre-turn state、与旧同步链一致。② **稀疏采样**：审计加 `DRIFT_AUDIT_INTERVAL_TURNS=3`（首回合+每3回合），不每回合烧 Flash（剧透安全已由同步整串门负责）。③④ 见上（残留告警 / observe_error）。⑤ 前端陈旧 fallback。

**已知取舍（诚实记录）**：① 运行时剧透防护收敛为**整串命中**——换措辞的概念性剧透不再被同步拦，交由异步 `drift_severity` 趋势监控（看板可对 `forbidden_reveals` 为空的幕 + severity 升高告警）。② `rewrite_triggered` 口径变为"仅剧透兜底重写"。③ `StateExtractor` 的 `drift_hints` 通道对当前回合失效（extract 先于异步审计跑）；审计结果只服务看板、不回流本回合 state 提取。

**验证**：容器内 `ruff check app/` 干净 + `pytest tests/` **243 passed**（+3 守护：stage_total=6 不含 drift / 剧透门无命中零 LLM 不置 rewrite_triggered / `_audit_drift` 缺 job 不抛）；前端 `eslint .` 0 + `tsc` 0 + `next build` 通过。**部署**：api/worker/web 三镜像均已重建重启（无迁移）。

### Round 45 (2026-06-18) — T1 叙事工艺层 + recent_turns 梯度 + 叙事连续性摘要轨（再上一个台阶）

承接 Round 44 T0，落地审计路线图 T1 中"最对症文笔"的两条（用户拍板「开始做这一轮」）。纯后端，无迁移，旧存档兼容（无 `type="narrative"` 摘要时优雅降级）。

**① 叙事工艺层 → 提进 system 稳定前缀**：新增 `prompt_builder._narrative_craft_directives(runtime_story)`，从 `runtime_story.story_core` 抽**整局静态**的 `narrative_style`/`core_fantasy`/`emotional_arc`/`tone_do`/`tone_dont`/`pacing_rules`，渲染"=== 本剧本叙事工艺 ==="，在 `_build_system_content` 里插在「宪法层」与「篇幅指引」之间（稳定前缀、不碎裂 prefix cache；全空则 no-op）。`gm_runtime.md` 顶部新增**正向工艺锚点段**（承接优先/演而非讲/对白推进/节奏呼吸/人称一致）+ **新增规则 35**（`narrative_recap` 框定：前情提要、非复述清单）。不改负向规则 12/13/16/20。

**② recent_turns 梯度**：`_turn_payload` 加 `full` 参数，最近 `_RECENT_FULL_TURNS=2` 回合下发 `gm_output` 完整正文（截 `_RECENT_FULL_CHARS=1800`）、不再发 `gm_output_excerpt`；更早回合仍只发 excerpt。让 GM 真能看到上一回合结尾去承接，根治"同地点每回合从头重述"。

**③ 叙事连续性摘要轨**：`ContextCompressionOutput` 新增 `narrative_recap`；`compress_context.md` **新增规则 8** + 输出字段（承接语气的"前情提要"，≤300字软目标、不剧透、append-then-condense）；`update_after_turn` 在非空时 upsert `type="narrative"` 单行摘要；`load_prompt_summaries` 带出 `narrative_recap` → GM `memory_summaries`；`_fallback_summary` 维护它（保留尾部最近节拍、永不空白）。治"长局走味"。

**对抗性审查（4-Agent 工作流）+ 采纳**：审查结论无 critical/high（2 OK + 2 minor-nits），确认 prefix-cache 中性偏改善、回归边界安全、剧透无新增风险、对文笔净正向。采纳其真问题：① 工艺 6 字段从 GM **user payload story_core 剥掉**（`_strip_craft_from_story_core`，原本 system+user 重复下发、费 token 且把基调显性化成清单）；② full 回合去掉冗余的 `gm_output_excerpt` 前缀子串；③ fallback recap 截断改保留尾部（原 `_trim_text` 截前缀会丢最新→长局停更）；④ 常量命名 + 本条记账。

**验证**：容器内 `ruff check app/` 干净 + `pytest tests/` **240 passed**（+1 工艺层 no-op/渲染测试 + 更新 recent_turns 断言 + 工艺段排序/去重断言）。**部署**：api/worker 镜像已重建重启。**Telemetry 待观测**：recent_turns 完整正文每回合净增约 2×min(正文,1800) 字（不缓存），承接效果稳定后可评估收档到 `_RECENT_FULL_TURNS=1` 或更低 `_RECENT_FULL_CHARS`。

### Round 44 (2026-06-18) — 架构级审计（35-Agent 工作流）+ T0 后端「去配额化/去清单化」止血叙事生硬

**背景**：用户反馈实机输出"生硬、生搬硬套剧情和设定，不像小说"。先对真实存档做实证诊断（同地点反复重述/凑配额假加粗/低事件回合注水/机械塞素材/义务复述线索），再用多 Agent 工作流（8 维度并行审计 → 对抗性压力测试 → 战略综合，35 Agent / 250 万 token）做架构级审视。用户明确授权"重构到任何程度"。

**审计核心结论**（详见个人记忆 `rpgforge-architecture-audit-2026-06`）：43 轮力气投在"防跑偏/防剧透"防御轴，地基（数据/迁移/队列/event-sourcing/防剧透宪法层）健康，但把唯一玩家可见产物 narrative 建模成"约束满足问题"而非"语言艺术"，GM 退化成履约机器=生硬。根因在**传递层**：`prompt_builder.py:122-147` 把合规+篇幅配额固化进 system 最高优先级，voice/情绪弧丢进被 state_v2 淹没的 user JSON；`gm_runtime.md` 34 条规则约 26 条是负向禁令。**对抗性压测点破**：DeepSeek `thinking=enabled` 时结构性丢弃 temperature（`deepseek_client.py:216`）→ 调温度松绑文笔无效，把"换正文模型"推到前台。

**T0 落地（本轮，纯 prompt/参数 + 纯 UI，零安全风险，已验证部署）**——用户选定「T0三件套 + 后果卡」（模型盲测后弃），三件套全部落地。**后端（prompt/参数）**：
- **软化字数下限 + 删 emphasis 配额**：`prompt_builder._generation_parameter_directives` 把"【硬下限】narrative 不少于 N 字、字数不足视为偷工"改为"【篇幅·按信息量自然成文】事件少可短而精、不为凑字数注水复述，仅 <~250 字地板防敷衍"；emphasis 从"min–max 配额"改"宁缺毋滥、没有就不加"。`gm_runtime.md` 规则 7/13 同步改写。（遗留小瑕疵：保留的【优先级】块尾部仍有"不得低于硬下限"措辞，因该块含敏感词无法安全 Edit，语义无害，下轮顺手清。）
- **去清单化**：新增 `prompt_builder._gm_facing_director`，从 **GM payload** 删 `continuity_notes`/`active_material_titles`（最易被 GM 当"必须逐条用上并加粗"的填空清单）；这两项仍保留在 StateExtractor 的 director_hints（异步维护）。`gm_runtime.md` 规则 22（scene_objective/gm_instruction 降级为软提示，forbidden_reveals/pacing_limit 仍硬）、规则 24（素材改"私有一致性知识底座，不是填空题"）。
- **裁判对齐**：`turn_judge.md` prose_quality 改"节奏自适应：短回合不扣分；为凑字数注水/堆砌/凑数加粗才扣分"，防 Judge 反向奖励凑配额。
- **测试同步**：`test_gameplay.py` 篇幅断言由"不少于 700 字"改"按信息量自然成文"。

**前端（纯 UI/信息架构，不碰防剧透/状态/schema/存档）**：
- **bold 去亮金**：`globals.css` `.story-markdown strong` 由 `--gold`+`font-weight:850`（假加粗放大器）改正文同色 `--foreground`+`650`。
- **判定后果卡提进阅读流**：新增 `gameExperience.ActionOutcomeView` + `extractActionOutcome`（从 `state_delta_json.action_outcome` 取 outcome_label/action/roll/modifier/dc，tone 映射 critical/success/partial/failure→great/good/partial/fail）；`TurnSettlementCard` 顶部渲染彩色「行动结果 · X」卡（掷骰明细次要），**无判定回合不显示（不伪造成功）**；从 `TurnInsightsPanel` debug 抽屉移除重复判定块；篇幅标签去掉"未达硬下限"（短回合不再标失败）。
- **冻结设定编辑器**：项目 `CLAUDE.md` 工作约束加「前端工作门」——新前端工作须先服务玩家循环「读→选→看后果」或修正确性/可访问性，冻结看板/工坊作者便利新功能（投入轴纠偏）。

**验证**：后端 `ruff check app/` 干净 + `pytest tests/` **239 passed**；前端 `eslint .` 0、`vitest` **52**、`tsc --noEmit` 0、`next build` 全路由通过。**部署**：api/worker/web 三镜像均已 `build`+`up -d`（纯 prompt+UI 改动，旧存档无需迁移）。

**本轮未做（待续）**：① 模型盲测（DeepSeek vs Claude）——用户试玩后认为后端改动后文笔可接受，**决定跳过**（环境也无 Anthropic key）。② T1/T2（叙事工艺层提 system、Drift 改异步事后审计、属性 seeding+判定可见、prefix cache 多段切分、外科拆 state_applier、记忆层叙事连续性轨、锚点多路径+结局变体）见个人记忆 `rpgforge-architecture-audit-2026-06` 路线图，待用户逐层拍板。

### Round 43 (2026-06-05) — 前端 UI 审查 + P0 可访问性修复

承用户「这两天改了很多前端」做的一轮 UI/UX 审查（用 ui-ux-pro-max 技能，按 web 规则）。结论：工程底子很好（语义化 token 体系、响应式断点系统、移动端适配、文字 break 兜底齐全），问题集中在**可访问性**与最近新增看板组件的细节。本轮只落地用户选定的 **P0（影响最广、风险最低，纯前端）**：

- **全站按钮键盘焦点环**：`web/app/globals.css` 此前仅 `.app-input:focus` 有反馈，`.app-button`/tabs/卡片按钮（全是裸 `<button>`）键盘 Tab 时无焦点指示（违反 CRITICAL 级 `focus-states`）。新增 `:where(button, a, summary, [role="button"]):focus-visible` + checkbox/radio 焦点环（`outline: 2px var(--accent-strong)`；`:focus-visible` 鼠标点击不触发，不影响视觉）。
- **BlockDetailModal 补无障碍**：`web/components/board/BlockDetailModal.tsx` 是看板/工坊/剧情主从视图到处复用的核心弹窗，此前缺 Esc/aria/焦点管理（旧 `CharacterModal` 反而有，属退化）。照搬 CharacterModal 已验证模式——`role="dialog"`/`aria-modal`/`aria-label`、Esc 关闭、打开聚焦关闭按钮、关闭恢复原焦点、Tab 焦点陷阱、背景按钮点击关闭（替掉原 `onClick`+`stopPropagation`）。
- **prefers-reduced-motion 降级**：`globals.css` 追加全局 reduced-motion 媒体查询，弱化 pulse/hover 位移/过渡，照顾前庭敏感用户。

**审查留存的待办（本轮未做，用户选择只修 P0）**：P1 ——「新增」弹窗取消按钮误写「🗑 删除」（`SettingsBoard.tsx:120`/`PlotMasterDetail.tsx:225` 把 `onDelete` 当取消用）、保存校验静默失败无反馈（`SettingsBoard.tsx:116`）、PlotMasterDetail 变更态仅靠红边色传达无文字标记（与 BoardBlockGrid「刚更新」药丸不一致，违反 `color-not-only`）、14 处硬编码状态色（`#e0533d`变更/`#e0a23d`选中/`#4a9a6f` 应进 token）；P2 ——原生 checkbox 未定制、BoardTabs 触控偏小（28px<44px）、stringList/keyValue 编辑摩擦。

**验证**：`npm run lint` 0/0、`tsc --noEmit` 0、vitest **52 passed**、`next build` 全路由通过。纯前端、后端零改动、无需迁移。

### Round 42 (2026-06-05) — 看板新增设定体验增强：字段统一 + id 自动生成 + AI 补全

承接 Round 41，同 PR #7。两部分：

**① 新增表单与编辑共用完整字段规格 + id 自动生成（纯前端）**
- 抽 `web/lib/generatorBoard.ts` 的 `ITEM_FIELD_SPECS`（6 类数组项完整字段规格），`buildFromSettings` 与 `newItemBlock` 共用 → 新增表单字段不再比编辑面少（此前 `newItemBlock` 只用 `ARRAY_SPECS.keys` 的 2-3 个最小字段）。
- 新增 `generateItemId(arrayKey, existingIds)` / `itemIdsOf(model, arrayKey)`：幕/主线节点的 `id` 自动生成唯一值（`act_N`/`quest_N`），新增表单不再要求手填 id；`SettingsBoard`/`PlotMasterDetail` 新增保存处对 idKey="id" 数组注入自动 id。

**② 新增设定 AI 补全（前后端）**
- 新 prompt `api/app/prompts/suggest_item.md`（固定系统提示，吃前缀缓存）。
- 新 `api/app/services/item_suggester.py`（`ItemSuggester`）：`use_flash` + `reasoning_effort=None` + `SUGGEST_ITEM_TIMEOUT_SECONDS=40s`；失败/超时/解析/漂移 → 空 dict fallback；`build_outline` 仅取 game_profile + story_core + worldview 概要省 token；结果过滤（剔身份字段/越界字段，不覆盖用户输入）。
- 新端点 `POST /api/games/{id}/settings/suggest-item`。
- 前端 `BlockDetailModal` 新增态「✨ AI 补全」按钮（传 `aiSuggest` 回调才显示）：用户填标题 → AI 补其余字段（**用户已填值优先**）；仅游戏设定页注入 `onSuggestItem`，工坊不启用。
- 测试：`api/tests/test_item_suggester.py`（5 绿）+ `test_games.py` 端点用例；前端 tsc/lint/build 通过。
- 设计/计划：`docs/superpowers/specs|plans/2026-06-05-ai-suggest-item*` 与 `2026-06-05-plot-line-masterdetail*`。

### Round 41 (2026-06-05) — 看板「剧情结构」升级为主从视图（纲领总览 + 幕大纲 + 幕详情）

纯前端，后端零改动。此前剧情线（`act_plan` 幕 + `main_quest_path` 主线节点）与其它设定共用通用卡片网格 `BoardBlockGrid`，看不清「幕 → 节点」从属与走向。本轮在看板「剧情结构」标签页换成专门的主从视图：

- 新增 `web/lib/plotView.ts`（纯函数 `derivePlotView` + `actKeyOf`）：从 `BoardModel` 派生 `{ overview, acts, unassignedNodes }`。纲领 = world 分类里 `settingsScalar` 且 `path=["story_core", k]` 的 6 个标量块；幕 = plot 分类 `arrayKey==="act_plan"`；节点 = `arrayKey==="main_quest_path"`，按 `act_id` 分组到幕，`act_id` 空或指向不存在幕 → `unassignedNodes`（孤儿不丢失）。配 4 个 vitest 用例。
- 新增 `web/components/board/PlotMasterDetail.tsx`：顶部剧情纲领总览（镜像 story_core，与世界观 tab 同源），左幕大纲（选中高亮 + ＋新增幕），右幕详情（目标/转场 + 该幕节点列表 + ＋新增节点，新增节点 `act_id` 预填当前幕）。编辑/删除/新增全复用 `BlockDetailModal` 与 `SettingsBoard` 既有 `onEditBlock/onDeleteBlock/onAddItem` 回调，diff/写回/后端零改动。
- `web/components/board/SettingsBoard.tsx`：`activeTab === "plot"` 时渲染 `PlotMasterDetail` 替换 `BoardBlockGrid`（其它 tab 不变），plot tab 隐藏「显示空设定项」开关（主从视图自管空态）。
- **不做**：节点拖拽重排/跨幕改归属（顺序与归属靠字段）、后端 schema/`story_blueprint` 运行时改动。
- 设计与计划文档：`docs/superpowers/specs|plans/2026-06-05-plot-line-masterdetail*`。
- 验证：`npm run test`（含 plotView 4 绿）/ `npm run lint` / `npm run build` 全通过；**UI 手动验证待在带数据环境跑**（本地需 API + Postgres + 已有游戏）。

### Round 40 (2026-06-04) — 「下载填写说明」改为通用模板（去剧本痕迹 + 去游戏依赖）

`api/app/services/settings_guide_exporter.py`。此前导出文档结构已通用，但仍有两类"非通用"：① 字段表「示例」列硬编码了一套具体剧本（雁回镇/沈砚/义庄/黑伞会/不要修仙）；② 头部含 `game.title`/`game.id`/导出时间，「当前 JSON 结构概览」按当前游戏输出条目计数。本轮改成纯通用模板：

- `export_settings_guide_markdown(game)` → 无参 `export_settings_guide_markdown()`，不再读 `game.config`；标题固定 `# RPGForge 设定填写说明`；头部删导出时间/游戏 ID，`format_version` 改用常量 `STORY_SETTINGS_FORMAT_VERSION`；删除 `_append_current_summary`/`_summary_line`/`_text`。
- 字段表「示例」列：剧本专名 → `[占位符]`（如 `[游戏标题]`/`[角色名]`/`[地点名]`），保留结构性枚举值（`act_1`/`true`/`protagonist`/数字/系统四选项契约等通用值）。
- **接口不变**：`/api/games/{id}/settings-guide-export` 路由与文件名（仍带 `game.title`）保持原样；router 改调无参函数。
- 同步护栏测试 `test_settings_guide_documents_every_normalized_field`（去 game 依赖、改无参调用，字段路径列未动→护栏仍有效）。
- 验证：本地 `py_compile` + `ruff check` 干净；本地复现护栏断言 `missing=[]`；本地渲染确认 雁回镇/沈砚/义庄/修仙 痕迹全部清除。**容器内 pytest 待跑**（本地无 Postgres）。

### 修复 (2026-06-04, PR #6) — 看板「玩法机制」分类内容串台

真实精修剧本暴露的 React 渲染 bug：设定页反复切到「玩法机制」时卡片内容串台。根因——看板 block 的 React `key` 用 `${arrayKey}:${name|title}`，而 `core_mechanics`/`action_style_rules`/`story_material_library` 的 name/title **没有唯一性校验**（不像 core_characters.name / act_plan.id 有 validate 唯一）；「玩法机制」合并 `core_mechanics ∪ action_style_rules` 两数组，精修剧本里常有同名条目 → block.id 重复 → React key 撞 → DOM 复用错位、内容串台。修复：`buildBoardModel` 末尾对每分类内 block.id 去重（撞了追加 `#2/#3`，唯一 id 不变、不影响生成页 diff），加 vitest 覆盖。教训：多 Agent 并行开发时，纯函数测试只用了唯一名占位数据，没覆盖"同名条目"边界，真实剧本才触发。

### Round 39 (2026-06-04) — 看板成为完整设定编辑面（数据驱动全覆盖 + 字段类型系统 + 空块折叠 + 手动新增数组项）

纯前端，后端零改动。

- **字段数据派生全覆盖**：`generatorBoard.buildFromSettings` 由「手写白名单」改为「FIELD_SPEC 精修 + 实际数据派生兜底」（`deriveFields`/`inferType`），补齐此前看不到/改不了的字段——`home_base`（新块）、`worldview.public_facts/hidden_facts`、`act_plan.completion_anchors`(objectList)/`allowed_reveals`/`forbidden_reveals`/`transition_to_next_act`、各 item 全字段（角色 dramatic_function/portrait_prompt 等、素材 type/triggers/gm_secret 等）。固定块无条件建块。block.id/address 规则不变（护住生成页 diff 与模块提取）。
- **字段类型系统**：`BoardFieldType` 扩为 text/textarea/number/bool/stringList/objectList/keyValue/json；新增 `BoardFieldEditor` 按类型渲染（objectList 子卡增删、keyValue 键行、bool 勾选、json 兜底校验）；`BlockDetailModal` 改类型化 drafts；`writeBlockFields` 无损回写各类型（`fieldsToRecord` 直接赋值，天然支持）。
- **空块折叠**：`isEmptyBlock` + `SettingsBoard` 顶部「显示空设定项」开关（默认折叠空的固定块，灰显可填）。
- **手动新增数组项**：`ARRAY_SPECS`/`createEmptyItem`/`appendItem`/`newItemBlock`；`BoardBlockGrid` 分类底部「＋新增角色/机制/幕/素材/主线/行动风格」；复用 BlockDetailModal 空白表单（身份必填，重名由后端 validate 兜底）；设定页 `onAddItem`→`appendItem`→`PATCH config`(+版本快照)。生成页手动新增留 P2（展示/编辑增强两边共享）。
- **验证**：web `npm run lint` 0/0、vitest **36 passed**（+12：全字段覆盖/无损往返/新增项）、tsc 干净、`next build` 通过；web 镜像已重建。

### Round 38 (2026-06-04) — 剧本炼金工坊（setting_modules 表 + module_library 合并引擎 + module_adapter AI 优化 + /api/modules 路由 + /workshop 页 + 存为模块 + 并入面板）

**背景**：剧本设定（story_settings）由 AI 生成但难以跨剧本复用，每次创建新剧本都要从头提炼素材。本轮引入「剧本炼金工坊」，将剧本设定片段提炼为可复用模块，支持库管理、合并预览、AI 本地优化后并入，覆盖后端存储 → 合并逻辑 → AI 适配 → API → 前端工坊页 → 看板存为模块 → 设定/生成页接入整条链路。

**后端（Task 1–4）**：
- **`setting_modules` 表**：新增 `api/migrations/versions/20260604_0029_add_setting_modules.py`——`setting_modules`（id/name/description/module_type/payload JSON/tags/source_game_id/created_at/updated_at）；Alembic HEAD = `20260604_0029`。
- **`module_library.py` 合并引擎**：`merge_modules_into_settings(items, target, resolutions)` 将模块 payload 深合并进 story_settings——列表字段去重追加（同 id/name 身份键比较）、冲突 rename（`名 (2)` 后缀）/ overwrite / skip 三策略；字典字段（settingsScalar）列表子键去重追加、标量/对象子键覆盖；返回 `(settings, MergeReport)`。
- **`module_adapter.py` AI 本地优化**：`adapt_module_for_game(fragment, target_settings, game_context)` 调用 DeepSeek 按目标剧本风格小幅调整模块内容；新增 prompt `api/app/prompts/adapt_module.md`（输入输出 JSON schema + 约束：仅微调措辞/数值，禁止改结构/增删字段）；独立 `MODULE_ADAPT_TIMEOUT_SECONDS = 120` + fallback（返回原始 fragment 不抛出）。
- **`/api/modules` 路由**：新增 `api/app/routers/modules.py`——`GET /api/modules`（列表+搜索）、`POST /api/modules`（创建）、`GET /api/modules/{id}`（详情）、`PUT /api/modules/{id}`（更新）、`DELETE /api/modules/{id}`（删除）、`POST /api/modules/{id}/export`（导出 JSON）、`POST /api/modules/import`（导入 JSON）、`POST /api/modules/merge-preview`（预览合并）。

**前端（Task 5–10）**：
- **`moduleFragment.ts` 类型层**：`ModuleFragment` / `SettingModule` / `MergePreview` / `MergeStrategy` 类型定义；`fragmentToModule` / `moduleToFragment` 互转工具函数；`lib/moduleFragment.test.ts` 4 个 vitest 覆盖转换逻辑。
- **`api/modules.ts`**：封装全部 `/api/modules` 端点（list/get/create/update/delete/export/import/mergePreview）+ SWR key 常量。
- **`/workshop` 工坊页**：`app/workshop/page.tsx`——模块列表（分类筛选/搜索/排序）+ 模块详情侧边栏（查看 fragment/标签/来源）+ 导入/导出/删除操作；响应式布局。
- **看板「存为模块」**：`components/board/SettingsBoard` 右上角「存为模块」按钮 → `SaveAsModuleDialog`（选分类/填名称描述/预览 fragment → POST /api/modules）。
- **`ModuleMergePanel` 共享并入面板**：`components/workshop/ModuleMergePanel.tsx`——选模块 → AI 优化开关（调 module_adapter）→ 预览合并差异（added/renamed/skipped/conflicts）→ 确认并入；targetSettings 变更清预览防陈旧覆盖。
- **设定页/生成页接入**：`/games/[id]/settings` 看板区新增「并入模块」入口（挂 ModuleMergePanel）；`/games/new` 生成页草稿看板新增「并入模块」入口（并入后刷新 confirmed_requirements）。

**验证**：
- 迁移 HEAD = `20260604_0029`；三镜像真实重建（api/worker: 2026-06-04T05:00:54Z，web: 2026-06-04T05:21:37Z）。
- 后端 `pytest tests/` **229 passed**；`ruff check app/` 全过。
- 前端 eslint 0 error/0 warning；vitest **23 passed**（lib/moduleFragment.test.ts 4 + lib/generatorBoard.test.ts 19）；tsc --noEmit 0 error；`next build` 含 `/workshop` 路由通过。
- Step 4 手动浏览器端到端走查留给用户人工验证。

### Round 37 (2026-06-04) — 已有剧本「设定」页 + 信息架构去重

**背景**：已有剧本的 story_settings 展示/编辑/导入导出/版本历史散落在「概览」和「资料」两页，信息重复、职责不清。本轮将上述功能统一到新设定页，同时对概览/资料两页做减法。

**主要改动（前端，纯前端，无后端改动）**：
- **看板组件归位**：`components/generator/SettingsBoard` 等 5 个看板组件 `git mv` 到 `components/board/`，生成页路径同步更新；`diff`/`lockedIds`/`onUnlockBlock` 改可选（默认值 `EMPTY_DIFF`/`[]`），`EMPTY_DIFF` 从 `generatorBoard.ts` 导出。
- **`GamePageHeader` 加「设定」导航**：`GameSection` 新增 `"settings"`，`gameNavItems` 插入「设定 → /games/[id]/settings」。
- **`SettingsAdvanced` 组件**：新增 `components/settings/SettingsAdvanced.tsx`，封装原始 JSON 编辑 + 导入/导出/填写说明 + 版本历史三个高级折叠区。
- **新「设定」页**：新增 `app/games/[id]/settings/page.tsx`，看板（六分类可查看/编辑/删除）+ 高级折叠，409 回合生成中友好提示。
- **概览页瘦身**：新增 `components/settings/SettingsOverviewCard.tsx`（各分类条数 + 设定入口）；删除 `ScriptLockSection`/`BlueprintCard`/`DiagnosticsPanel`、「剧本素材库」section、「高级诊断」details，及 `buildGameBlueprint`/`JsonBlock`/`asList`/`pickString` 等已无引用的 import/函数。
- **资料页瘦身**：删除 tab 机制、`CoreSettingsSection`/`UnifiedSettingsSection`/`StorySettingsOverview`/`StorySettingsEditor`/`StorySettingsStructureGuide`/`SettingsImportExportSection`/`VersionHistorySection` 七个组件、`STORY_SECTION_GUIDE`/`emptyValueForSection`/`currentActFromSettings` 等常量和辅助函数、`versions` 数据流；资料页只剩记忆/摘要 + 重建摘要 + 运行诊断。

**验证**：vitest 19 passing；eslint 干净；tsc/build 通过；web 容器已重建（2026-06-04T03:57:53Z）。

### Round 36 (2026-06-04) — 创建冒险页重设计 + 后端锁定字段支持

**背景**：创建冒险页（`/games/new`）原实现采用单栏问答式 UI，字段抽取结果不可视、不可编辑，用户无法手动调整已确认设定，也无法告诉 AI「我改过这个，别动它」。本轮完成前端完整重设计 + 后端配套最小改动。

**前端重设计（Phase A–C，Task 1–14）**：
- **看板主体 + 底部 ChatDock 布局**：左侧六分类 Tab 看板展示 `confirmed_requirements` 各字段（世界与基调/核心前提/必须出现/禁止内容/玩法偏好/风格偏好）+ `initial_state`/`story_settings` 各分区（角色/剧情/机制/素材）；底部 ChatDock 可拖拽调高，历史上滑可见完整对话。
- **改动指示（diff/+N/闪烁/摘要条）**：每轮对话后对比前后 Board 状态，变更 block 闪烁、对应 Tab 角标 +N、底部摘要条常驻本轮、下次重算。
- **Block 详情弹窗**：查看 / 编辑 / 删除 / 解锁四个操作；编辑保存后 block 标「✏ 已改」（锁定）。
- **锁定语义**：锁定 block 的字段名通过 `createGeneratorChatJob` 的 `locked_fields` 发给后端；客户端发新轮时把锁定值覆盖回 `confirmed_requirements`（兜底防止后端改回）；「🔓 解锁/恢复 AI 原值」可撤销锁定并恢复 baseline 值。
- **进度点亮 + 思考收起**：`GenerationProgress` 组件六类进度点亮（P1 粗粒度，与后端 `progress_message` 前缀匹配）；reasoning 可折叠。
- **新增前端 vitest**：`lib/generatorBoard.test.ts` 覆盖 `buildBoardModel` / `diffBoard` / 锁定工具函数共 19 个纯逻辑测试用例。

**后端锁定支持（Phase D，Task 15）**：
- `api/app/schemas/generator.py`：`GeneratorChatRequest` 新增 `locked_fields: list[str] = Field(default_factory=list)`。
- `api/app/services/game_generator.py`：`_build_interview_messages` 在「当前已确认需求」之后、历史消息之前，注入 system 消息「用户已锁定以下字段…必须原样保留其值、不得改写或还原成旧值；但仍要读取这些值作为上下文，让新生成的内容与之保持联动一致：[字段列表]」。
- `api/app/prompts/generator_interview.md`：新增规则 7「若系统消息标注了『用户已锁定』的字段，对这些字段必须原样输出用户给定的值，禁止改写、补充或还原为更早的版本；其它字段照常抽取，并保证与锁定字段在设定上一致、不矛盾。」
- 新增 `api/tests/test_generator_locked_fields.py`：4 个 pytest 覆盖 schema 字段存在/默认值、注入逻辑有无锁定指令。

**验证**：容器内重建镜像后 `pytest tests/` **214 passed**（+4 新增）；前端 vitest 19/19 + `next build` 通过；Task 16 Step 3 手动浏览器端到端走查留给用户人工验证。

### Round 35 (2026-06-03) — 修「下载填写说明」文档与 schema 漂移

- **背景**：`settings_guide_exporter.py` 的字段说明表是手工硬编码的，schema（`story_settings.py` 的 `normalize_story_settings`）后续加字段后没人同步，导致导出的填写说明文档漏掉了 14 个规范化字段。
- **补全字段**（导出文档 `_append_field_reference` 已对齐 schema）：
  - `story_core`：`emotional_arc`、`narrative_style`
  - `core_characters[]`：`aliases`、`relationship_arc`、`portrait_prompt`
  - `act_plan[]`：`must_hit_beats`；`completion_anchors[]` 的 `title`/`required`/`description`
  - `main_quest_path[]`：`optional`
  - `action_style_rules[]`：`name`
  - `story_material_library[]`：`priority`（影响 `_material_score` 召回打分）、`visibility`、`enabled`
- **加护栏测试**：`test_games.py::test_settings_guide_documents_every_normalized_field` —— 用满数组样例过 `normalize_story_settings`，递归收集所有产出字段名，断言每个都在导出 Markdown 里以独立词出现；以后 schema 加字段忘了同步文档会直接报红。
- 容器内 `pytest -k "guide or normalized_field"` 2 passed。未改 LLM 链路 / prompt 规则编号。

### Round 34 (2026-06-03) — 游戏方向第二梯队落地（A1 判定层 + A2 数值反哺 + B3/A3 压力与失败 + B5 松绑校验 + C5/C6 重roll与回退）

承接 Round 33，落地 [`GAME_DIRECTION_AUDIT.md`](GAME_DIRECTION_AUDIT.md) §4 **第二梯队全部 5 簇**——把项目从「带强约束的 AI 叙事生成器」推向「真正的游戏」（博弈/失败/能动性）。

**A1 轻量判定层 + A2 数值反哺（P0，地基）**：玩家行动现在有成败之分。
- 新增 `action_resolver.py`：StoryDirector 标注 `action_check`（难度/相关属性/技能/社交对象，见 `story_director.md` 规则 12 + 输出结构新增 action_check）→ 后端按「等级 + 技能 + 属性 + 关系」算修正、roll d20 vs 难度 DC → outcome（critical/success/partial/failure，nat20 必大成功/nat1 必失败）。**A2 即修正来源**：等级、技能 level+mastery、属性(D&D 式 (attr-10)//2)、关系(trust/affection 相对 50 的 ±5)全部进判定。
- 接入：`gameplay.generate_turn_runtime_output` 新增 `_resolve_action_outcome`——解析 action_check，把 `build_outcome_instruction` 的硬约束句追加进 gm_instruction，结果存 `StoryDirectorDecision.resolved_outcome` + telemetry `action_outcome`。
- GM 硬约束：`gm_runtime.md` 新增规则 33——resolved_outcome 非空时必须按既定结果叙事（failure 写受阻/代价、partial 写部分+代价），narrative 不得出现机制词。纯对话/叙述无 action_check → 跳过判定。
- 观测：`TurnInsights` 新增 `action_outcome`，前端「本回合详情」展示「行动判定 · 成功（掷骰…）」。

**B3 压力时钟兑现 + A3 危机条/失败出口（P0/P1）**：拖延有代价、「输」有出口。
- `pressure_clock` 此前只是展示文本、从不兑现——新增 `survival_clock.py`，在 `apply_state_delta` 每回合确定性推进：① 压力时钟每回合 +1，到阈值(默认 10)触发 → 侵蚀危机条 + 重置；② **危机条 crisis(0–100)** 受「判定失败 -12/部分 -5」「活跃状态严重度(high -6/medium -3/low -1)」「压力触发 -12」侵蚀，平静回复 +4；归零 → 置 `story_progress.defeat`。
- 失败结局复用 B1 闭环：`turn_maintenance_jobs._finalize_campaign_if_complete` 泛化为胜利/失败两种——victory→`game.status="completed"`、defeat→`"defeated"`，`EpilogueGenerator` 按 `ending_type` 写不同基调结局（`generate_epilogue.md` 增 victory/defeat 分支）。
- 判定结果经 `_apply_delta` 并入 `turn.state_delta_json`（持久化、rebuild 可复现）→ survival_clock 据失败侵蚀。`game_creator` 初始化 crisis/pressure_clock，`state_v2` 投影二者（GM 规则 34 据此让危险可感）。
- 前端：play 页 `CrisisBar`（绿/黄/红三档）；`game.status==="defeated"` → 「败局」结局卡（`CampaignEndingCard` 加 outcome 参数）。

**B5 松绑校验器（P1）**：`drift_validator.md` 新增规则 4b「玩家来源豁免」——玩家主动驱动的剧本外发散探索，只要不提前剧透 forbidden_reveals/hidden_facts，不再判 major。把「忠于剧本」收窄到「不提前剧透真相」。纯 prompt 改动。

**C5 重 roll（P1）**：`web/app/games/new` 生成结果区加「重新生成」按钮——复用已确认采访(`idea/history/confirmed`)重跑 finalize，不满意可换一个世界。纯前端。

**C6 后悔药（P1）**：新增 `turn_rewind.py::rewind_game_to_turn` + `POST /api/games/{id}/turns/rewind`——删除第 N 回合之后的回合（StateDelta 经 FK CASCADE + ORM cascade 一并删），rebuild 从 initial_state 重放剩余 delta（危机/压力/结局全确定性重算），跨过结局则复位 `game.status="active"`。生成进行中拒绝(409)。前端 play 页顶栏「撤销上一回合」(回退到 latest-1)。

**遵 CLAUDE.md**：A1 判定层的 LLM 调用沿用 Director（已有 timeout/fallback），未新增裸 LLM 调用；prompt 改动记录规则编号（story_director 规则12+action_check、gm_runtime 规则33/34、drift_validator 规则4b、generate_epilogue victory/defeat 分支）；新增 state 字段(crisis/pressure_clock/defeat/action_outcome)走 state JSON + 投影，未动 TurnJob 列。crisis/pressure 对**旧存档**：rebuild 时从 initial_state(无该字段)默认 100/0 起算，确定性重放、无需迁移。

**验证**：容器内 `pytest tests/` **209 passed**（+21：`test_action_resolver` 9 / `test_survival_clock` 9 / `test_turn_rewind` 3）、`ruff check` 全过；web `next build`（tsc+lint）通过。**部署**：`docker compose up -d --build api worker web`。

> 待真实游玩验证：① 撬锁/说服等行动是否真的可能失败、失败是否被 GM 写成受阻而非顺利；② 高等级/高技能是否明显更稳；③ 拖延/受创时危机条是否下降、归零是否触发败局结局；④ 玩家发散探索是否不再被 drift 拽回；⑤ 重 roll / 撤销上一回合是否如期工作。第三梯队（B2 结局变体 / B4 多路通关 / A4-A6 / B6-B8 / C7-C9）见审查文档 §4，未动。

### Round 33 (2026-06-03) — 游戏方向第一梯队落地（B1 结局闭环 + C1 开局序章 + C2 目标条 + C3 引导卡）

承接 Round 32 [`GAME_DIRECTION_AUDIT.md`](GAME_DIRECTION_AUDIT.md) §4，落地第一梯队全部 4 项（低成本、立竿见影）。执行顺序：C2/C3（纯前端速赢）→ B1（核心链路）→ C1（生成管线）。

**B1 结局闭环（P0，最刺眼）**：补齐「打通后无结局」。
- 末幕检测：`state_applier._sync_story_progress_and_quests` 末尾——`current_act` 是 `act_plan` 最后一幕且 `_computed_ready_for_next_act` 为 True（末幕 required 锚点全完成）→ 幂等置 `story_progress["campaign_complete"]=True`（随 state 持久化、rebuild 时确定性重算）。
- 尾声生成：新增 `epilogue_generator.py::EpilogueGenerator`（Pro 自由文本，独立 `EPILOGUE_TIMEOUT_SECONDS=180`，失败/超时返回空串走 fallback）+ 新 prompt `generate_epilogue.md`。
- 触发与置状态：`turn_maintenance_jobs._finalize_campaign_if_complete`（`_apply_delta` 后调用）——检测 campaign_complete 且 `game.status!="completed"` → 生成 epilogue → 置 `game.status="completed"`，epilogue 写入 **live state + initial_state**（后者保证 rebuild 重放不丢，尾声不随 delta 重算）。LLM 调用在 session 之外，避免长事务。`game.status` 从此首次被赋予「通关」语义（此前恒为 `draft`/`active`，B1 勘误见 Round 32）。
- 前端：`game.status==="completed"` → play 页切 `CampaignEndingCard`（尾声正文 + 旅程回顾 + 开新档），停用输入框。`GameRead.status` 既有，无需改 schema。

**C2 play 页目标条（P0）**：主界面看不到目标 → 修。
- 后端：`_sync_story_progress_and_quests` 派生 `current_act_title`/`current_act_objective`（`_act_record_for` 取自 `act_plan`）写入 story_progress；`state_v2._story_progress` 投影带出（连同 `campaign_complete`/`epilogue`）。
- 前端：story 列顶部固定 `ObjectivePanel`（当前幕目标 + 本幕锚点进度 + active 任务前 2 条 + 首条未解线索），数据全取自 stateV2。

**C3 首次引导卡（P0）**：零新手引导 → 修。
- 前端：首次进 play 弹一次性 `OnboardingCard`（`localStorage` key `rpgforge.onboarding.play.v1` 记忆），解释四种输入模式 +「你可以尝试任何行动」；四模式说明抽成共享 `MODE_GUIDE`，模式按钮加 `title` tooltip。

**C1 开局序章（P0，最重，触及生成管线）**：空白冷启动 → 修。
- 新增 `opening_scene_generator.py::OpeningSceneGenerator`（Pro 自由文本，独立 `OPENING_TIMEOUT_SECONDS=150`，fallback 空串）+ 新 prompt `generate_opening.md`。
- `routers/generator.py::generator_create_game` 改 `async`，建游戏后 `_generate_opening_scene` 生成开场写入 **turn 0**（display-only：`state_delta_json={}`、不产生 StateDelta、不参与 rebuild 重放；`_next_turn_number` 仍从 1 起）。失败静默跳过保持原空开局。**仅 AI 生成流程接入**，手动建游戏（`games.py`，空白 config）不接。
- 前端：turn 0 特判——隐藏「玩家行动」块/结算卡/insights，GM 块标签显示「序章」。

**新增 LLM 调用（遵 CLAUDE.md）**：epilogue / opening 两处均设独立 timeout + fallback。新增 prompt 两个（`generate_epilogue.md` / `generate_opening.md`，全新文件无既有规则编号）。

**验证**：容器内 `pytest tests/` **188 passed**（+8：新增 `tests/test_round33_features.py` 覆盖 campaign_complete 正/负例、非末幕不误判、title/objective 派生、两生成器 fallback/成功）、`ruff check` 全过；web `next build`（tsc+lint）通过。**部署**：`docker compose up -d --build api worker web`。

> 待真实游玩验证：① 打通末幕后是否如期出现「剧终」卡 + 尾声；② 新建 AI 游戏进 play 是否直接看到序章而非空白框；③ 目标条/引导卡展示。第二梯队（A1 判定层等）见审查文档 §4，未动。

### Round 32 (2026-06-02) — 游戏方向审查（多 Agent 并行，只审查不改码）

用户从「游戏开发项目经理」视角要求：只看游戏方向（可玩性/机制/叙事/体验），不看工程/安全/部署/多人/商业化，审查缺失、不完善、不合理处。用 3 个 general-purpose Agent 并行深审（① 机制深度/挑战性 ② 叙事能动性/闭环 ③ 玩家全周期体验），分区不重叠 + 代码逐条核实。**本轮只审查、未改代码**，产出 [`GAME_DIRECTION_AUDIT.md`](GAME_DIRECTION_AUDIT.md)。

**核心判断**：项目在工程/AI 链路/剧情遵循上已投入过度（31 轮），但作为「游戏」缺三样立身之本——**博弈、失败、结局**。当前更像「带强约束的 AI 叙事生成器」而非 RPG。

**三条主线**：① **无判定层**（全库 dice/roll/检定/成功率/概率零命中）→ 属性/技能/等级全是只写不读的装饰；② **只能前进**（无 game over、`pressure_clock` 代价从不兑现、末幕完成后无结局流程，`game.status` 恒为 `draft`）；③ **防跑偏用力过猛压制能动性**（DriftValidator/StoryDirector 把玩家发散探索、慢节奏扮演拉回主线）。

**问题分布**：机制层 6 条（A1–A6）、叙事层 8 条（B1–B8）、体验层 9 条（C1–C9），共 **8 个 P0 / 9 个 P1 / 6 个 P2**。

**优先级裁决**：第一梯队（低成本、立竿见影）= B1 结局闭环 + C1/C2 开场序章与目标条 + C3 首次引导；第二梯队（价值最大、需架构）= A1 判定层（做完带动 A2–A5 全部获得意义）+ B3/A3 压力兑现与失败出口 + B5 松绑校验器 + C5/C6 重 roll 与后悔药；第三梯队 = B2 结局变体 + B4 多路通关 + 经济/地图/氛围。

**勘误（诚实记录）**：多 Agent 初稿误称「`Game` 模型无 `status` 字段」，主线复核为：字段存在但**恒为默认 `"draft"`**、全库无任何 `game.status=` 赋值（`api/app/models/game.py:31`），从未用于通关语义——B1 结论不变、证据更精确（死字段，无需建表即可启用通关态）。

**重要提醒**：B5/B7 表明剧情遵循已到拐点，继续加固为负收益。后续重心应从「让 AI 更听话」转向「让游戏更好玩」。

**下一步**：按 `GAME_DIRECTION_AUDIT.md` §4 路线图，与用户确认后从第一梯队落地。本轮无代码改动、无需部署。

### Round 31 (2026-06-01) — 移除任务系统增强设计稿（用户决定不做）

用户决定不做任务系统增强（主线/支线/奖励整套），移除 `GAME_SYSTEM_AUDIT.md` §6 设计稿（M1-M6 待实现模块，本就未实现，纯文档）。

**保留不动**：Round 29 的 8.1（GM hidden 投影铺垫）/ 6.1（关系合并取最新）、Round 30（锚点进度展示修复 + hidden 投影越界修复）——均为已落地功能与独立 bug 修复，与"任务系统增强"无关。本轮无代码改动。

### Round 30 (2026-06-01) — 修两个 bug：8.1 hidden 投影越界 + 锚点进度展示

用户续玩 act_2 第 22 回合发现：① 女主名字提前出现 ② 状态页「幕完成锚点 5个已完成·未满足过渡条件」自相矛盾。查实为**两个独立问题**。

**A（真 bug，8.1 副作用）hidden 投影越界**：Round 29 的 8.1 给 GM 投影了**全部** hidden（含 act_4/5 远期女主：角色B/角色C…），GM 据此把还没到的女主提前抛出。修：`project_state_for_scene` 的 hidden 只投影**当前幕 + 下一幕**（`current_act` + 新增派生 `next_act`）。实测真实存档 hidden 10→5 条，act_4/5 远期女主被挡。

**B（展示 bug，既有）锚点进度算错**：前端 `formatAnchorProgress` 用全局 `completed_anchors.length`（含历史 act_1 的 5 个）显示"5个已完成"，但当前幕 act_2 实际 0/7。"未满足过渡条件"本身**正确**（act_2 required 锚点未完成、不该过渡）。修：`story_progress` 新增派生 `current_act_anchor_progress`（当前幕 done/total），前端改显示「本幕 0/7」。

**实现**：`_sync_story_progress_and_quests`（当前幕最终确定后）存 `next_act` + `current_act_anchor_progress`；`state_v2._story_progress` 投影带出（+ `_anchor_progress` 规整）；`project_state_for_scene` 用 `near_acts={current_act,next_act}` 过滤 hidden；前端 `stateV2.ts` 类型/归一 + `formatAnchorProgress` 展示。

**验证**：容器内 `pytest tests/` **180 passed**（+2 用例）、ruff + tsc 全过；真实存档 rebuild 实测 `next_act=act_3`、`anchor_progress={done:0,total:7}`、hidden 限 act_2/3。**部署**：`docker compose up -d --build api worker web`。

> A 的铺垫范围取"当前幕 + 下一幕"（GM 可为即将到来的 act_3 埋线）；若需更严（只当前幕、连下一幕都不提前），改 `near_acts` 一处即可。

### Round 29 (2026-06-01) — 实现计划第一批：GM hidden 投影 + 关系合并取最新（8.1 + 6.1）

按 [`GAME_SYSTEM_AUDIT.md`](GAME_SYSTEM_AUDIT.md) §4 实现计划第一批（玩法价值项）落地。

**8.1（P3-12，用户决策）**：`state_v2.project_state_for_scene` 给 GM 的 quest_log 投影增加 `hidden` 桶（标题 + objective）。**用户决策：hidden 任务给 GM 看、用于剧情铺垫，非防剧透对象**（防剧透由 next_act 裁剪负责；hidden 是"当前局已存在、玩家未激活的目标"）。实测真实存档 GM 投影现含 12 条 hidden（首次收服俘虏 / 角色D异能觉醒 / 救援角色F…），GM 可提前埋线。

**6.1（P2-11）**：`_merge_relationship_record` 数值轴 `max` → 取较新（incoming 是 relationships 列表中较后/较新回合的同人记录）。修复别名合并后"关系只升不降"（和解后降低的 conflict 被旧高值覆盖）。**P2-12 分裂**：现有 `_merge_relationship_aliases`（事件后用 `npc.aliases` 归一）已尽力，根治缺口在 LLM 提取的 `npc.aliases` 完整性，代码层无法无中生有关联缺失别名——保持现状（诚实记录，6.1 勾选表 P2-11 落地 + P2-12 评估为现状已尽力）。

**验证**：容器内 `pytest tests/` **178 passed**（+2 用例：GM 投影保留 hidden、关系合并取较新）、ruff 全过；真实存档 rebuild 回归正常（关系数值不变、GM 投影 hidden 实测 12 条生效）。**部署**：`docker compose up -d --build api worker`。

> 顺带发现：角色G关系 `trust=None`（既有小数据问题，非本轮引入，未处理）。剩余第二批（库存防负 / `_merge_mapping` 守卫 / 技能能力同名去重，可选）+ 第三批（脆弱匹配加固，ROI 递减建议结案）见 §4。

### Round 28 (2026-06-01) — 游戏系统修复收尾：死代码清理 + 路线图对齐 + 真实续玩验证

承接 Round 26/27，清理阶段 3 砍脆弱匹配后遗留的 dead code，对齐审查文档路线图勾选。

**死代码清理**：删除 `state_applier.py` 中阶段 3 砍掉调用后已无引用的 8 个脆弱匹配函数（`_semantic_completion_matches`/`_anchor_action_terms`/`_anchor_action_evident`/`_anchor_key_terms`/`_anchor_key_term_evident`/`_term_fragments`/`_ordered_completion_match`/`_useful_anchor_fragment`）+ 4 个仅它们引用的常量（`ANCHOR_ACTION_TERMS`/`ANCHOR_ACTION_EQUIVALENTS`/`ANCHOR_TERM_SPLIT_RE`/`ANCHOR_TERM_STOPWORDS`），约 200 行。保留仍被引用的 `_compact_text`/`_activity_markers`/`_meaningful_phrases`/`THREAD_QUEST_TOPIC_PREFIXES`/`ACTIVITY_MARKER_STOPWORDS`。用字符串边界 + assert 精确删除，`ruff` 确认无未使用 import 残留。

**真实续玩验证（意外收获）**：用户合并部署后续玩数回合，产生新剧情（角色I线索）。rebuild 实测新回合状态正确流转——4 条线索中 3 条已了结 `resolved`、"角色I的囚徒"对应**未完成**锚点 `act_1_first_captive`（首次收服俘虏）正确保持 `active`，v2 投影前端显示 1 条未解线索。**证明 Round 26-27 修复（id 归一管理线索、锚点联动 resolve、prompt 规则 20/21）在真实新回合工作正常**。

**路线图对齐**：`GAME_SYSTEM_AUDIT.md` §4 勾选 19 个已完成项（阶段 1-2 全 + 3.1-3.3 + 4.1 + 5.1/5.3 + 6 前端 + 7）。

**诚实 nuance**：个别勾选项只落地核心——5.1 做了"删除键归一"(P1)，"部分扣减/防负/非数值保留"(P2-8) 暂缓；3.3 做了"去碎片"(P2-5 主因)，"排除当前角色名"额外加固暂缓。

**验证**：容器内 `pytest tests/` **176 passed**、`ruff check` 全过；真实存档 rebuild 回归无异常漂移。**部署**：`docker compose up -d --build api worker`。

### Round 27 (2026-06-01) — 游戏系统修复第二批：砍脆弱字符串匹配 + 状态机 + 基础字段（阶段 3-5）

承接 Round 26，串行落地剧情核心改动（`state_applier`，高风险区，逐阶段 rebuild 回归）。

**阶段 3 砍脆弱字符串匹配（Round 16 教训彻底落地）**：① 锚点完成 `_anchor_completion_reason` 删第③层 `_semantic_completion_matches`（滑窗碎片/字符级模糊/字符顺序匹配），只保留整串(≥6字)+整短语(≥2)高精度命中 + LLM 显式 `completed_anchors`；② 任务完成 `_quest_completion_evident` 删 semantic + 碎片 marker 兜底；③ 活动证据 `_activity_markers` 去掉 2-3 字后缀碎片（保留完整词/去动词前缀），消除"角色D"等在场角色名把未来幕误判为"已在发生"；④ `_quest_status_bucket` 加否定词检测（"未完成/无法解决/进行中"不再判 completed）。
> `_semantic_completion_matches` 及其依赖（`_anchor_action_*`/`_anchor_key_*`/`_term_fragments`/`_ordered_completion_match`/`_useful_anchor_fragment`）已无引用、成 dead code，待清理轮删除（测试已确认无引用）。

**阶段 4 状态机**：`_apply_story_progress` 加白名单校验（`_anchor_ids_for_acts`）——LLM 显式 `completed_anchors` 只接受"当前幕/已完成幕"的合法 anchor，拒绝未来幕 anchor_id，防 `_sync_current_act_from_completed_anchors` 据此直接跳幕、跳过中间幕 required 校验。

**阶段 5 基础字段数值**：① 库存删除 `_remove_inventory_item` 改按归一名称(item/name/title 跨 str/dict)匹配（修删除指令用 name、库存存 item 键时静默失效，P1）；② `_apply_relationship_event` 未知轴跳过（不默认计入 trust，P2）。

**rebuild 回归验证（真实存档）**：current_act=act_1 不跳幕、completed_acts 空、completed_anchors 3 个不漂移（base_secured 靠整串"建立[地点]"、另两个靠 LLM 显式，砍 semantic 无影响）、线索仍正确 resolved。**诚实权衡**：`main_quest_2`「营救角色D」由 completed→active——它原靠脆弱 semantic 判完成（角色D已救，但 quest completion_signal 与锚点文案仅语义相似、非整串），砍 semantic 后改靠 LLM 显式(规则21)/act 完成兜底；这是"消除脆弱误判"的合理代价，强行加 quest↔anchor 字符串联动会重蹈 Round 16 覆辙，**不做**。

**验证**：容器内 `pytest tests/` **176 passed**（`test_gameplay` 两处旧 semantic 用例已更新为整短语命中/整词活动匹配；新增 `test_game_system_fixes` 否定词/库存/axis 用例）。**部署**：`docker compose up -d --build api worker`。

**评估后暂缓（非遗漏，见 [`GAME_SYSTEM_AUDIT.md`](GAME_SYSTEM_AUDIT.md)）**：阶段 6 后端关系合并取max/分裂（P2，真实数据未暴露，根治需 npc.aliases 完整性）、阶段 3.4 证据池白名单（砍 semantic 后边际收益低、漏收卡幕风险高）、NPC 场景定位收紧（P2，触发面窄）、P3 项、dead code 清理。

### Round 26 (2026-06-01) — 游戏系统修复第一批：契约根治 + 线索 resolve（阶段 1-2 + 泳道）

按 [`GAME_SYSTEM_AUDIT.md`](GAME_SYSTEM_AUDIT.md) §4 路线图落地前两阶段 + 三条独立泳道。**执行方式（用户选定）**：剧情核心主线（state_applier，重灾区）亲自串行改；**结算状态机 / 前端 / 生成侧 3 条无文件冲突的泳道用 background Agent 并行**（提速且互不污染），最后统一重建 + 全量测试 + rebuild 回归。

**阶段 1 止血与契约根治**：① prompt `extract_state_delta.md` 补 `quest_updates`/`open_thread_updates`/`faction_updates` 的 item 模板 + 规则 20/21/22（从源头让 LLM 用标准 `id`）；② `state_applier._normalized_upsert_update`/`_clean_thread_record` 把 LLM 的 `quest_id`/`thread_id`/`npc_id` 归一到 `id`，`_apply_upserts` 丢弃无身份空壳（根治僵尸记录）；③【泳道】`failed` delta 加入可拒绝/可编辑 + `attempt_count` 列（迁移 0028）超 9 次自动降级跳过（修 P0 软锁）；④【泳道】extractor `max_tokens` 4096→8000 + `parse_json_object(repair_truncated=)` 参数化截断兜底（仅 state_extractor 启用，generator 保持严格重试）。

**阶段 2 线索 resolve 与分桶**：① 新增 `_completed_topic_in_thread`，已完成任务/锚点专名主题词（≥3 字）作子串命中线索文本即判关联（解长句线索永不 resolve）；② `state_v2._thread_is_resolved` 只看 status 不拿 title 子串误判；③ `_merge_thread_record` status 单调保护（防已 resolve 线索被 active 更新复活）；④ `STATE_EVIDENCE_EXCLUDED_KEYS` 排除 `open_threads`；⑤ `_thread_identity_values` 纳入 description（修 **rebuild 回归暴露**的"同一线索 id-form 与 title-form 分裂"）。

**泳道**：前端（任务面板加「已完成」折叠分组 + 线索 status 中文映射 + 修 React key）；生成侧（关键 list 空分区触发重试 + outline 回退字段映射 `completion_anchor_plan`→`completion_anchors`/补 title + `validate_story_settings` 最小基数校验 warn）。

**验证**：容器内 `pytest tests/` **173 passed**（含新 `test_game_system_fixes.py` 13 用例）；**真实存档 rebuild 回归实证**：用户报的「营救角色D完成但线索仍在未解线索」彻底修复（角色D线索 active→resolved）、僵尸任务 4→0、线索不再分裂。**部署**：`docker compose up -d --build api worker web` + `alembic upgrade head`（迁移 0028）。

> 剩余阶段 3、4、5、6后端 待办（见 §4）。**阶段 3（砍脆弱字符串匹配）高风险**：动锚点完成推断逻辑，须对真实存档跑 rebuild diff 回归（现存档 act_1_base_secured 是 inferred 补全的，改判定逻辑可能让重放结果漂移）。

### Round 25 (2026-06-01) — 游戏系统全面审查（多 Agent 并行，只审查不改码）

用户转入「游戏系统」专项优化。用 5 个 general-purpose Agent 并行深审（① 提取管线 ② 应用+数值 ③ 任务/线索/锚点/剧情 ④ 关系+投影展示 ⑤ 生成侧），分区互不重叠 + 真实存档（`[示例世界]`，15 回合）只读验证。**本轮只审查、未改代码**，产出游戏系统修复驾驶舱 [`GAME_SYSTEM_AUDIT.md`](GAME_SYSTEM_AUDIT.md)。

**三大总根因**：① **字段契约断裂**——`extract_state_delta.md` 对 `quest_updates`/`open_thread_updates` 无 item 模板，LLM 遂用 `quest_id`/`thread_id`/`progress_update`，而代码身份键（`_identity_candidates`/`_thread_key`）只认 `id/title/key` → 显式状态丢失、僵尸记录、resolve 失效（实测存档 4 条 `id=None` 僵尸任务 + 进度文本全丢）；② **脆弱中文字符串匹配泛滥**——Round 16 已回退的「滑窗子串黑名单」同类逻辑仍存活于 `_term_fragments`/`_anchor_key_term_evident`（锚点完成）、`_thread_is_resolved`（线索分桶）、`_quest_status_bucket`（"未完成"→completed）；③ **证据池黑名单天然漏**——`STATE_EVIDENCE_EXCLUDED_KEYS` 已漏 `open_threads`/`known_facts`，未解线索（=未完成目标）被当「锚点完成证据」。

**问题分布**：1 P0（`failed` delta 无人工出口、可卡死存档 + 烧 LLM）、8 P1（含用户报的「长句线索永不 resolve」、库存删除键不匹配静默失效、生成空分区回退致锚点字段错位）、15 P2、13 P3。**关键好消息**：event-sourcing 重放幂等已实证（persisted==rebuild MD5 一致）→ 改 apply 逻辑后跑一次 rebuild 即自动修存量，无需迁移脚本。数值结算 / 生成主路径契约 / 转幕控制逻辑本身均健康。

**修复路线图**：7 阶段（1 止血契约根治 → 2 线索 resolve → 3 砍字符串匹配 → 4 状态机 → 5 基础字段数值 → 6 关系投影前端 → 7 生成防线），勾选框见审查文档 §4。**下一步落地阶段 1**。

### Round 24 (2026-05-29) — 修复 LLM-as-Judge + 优化后遵循度量化基线（收尾）

收尾轮：用 turn_judge 给整轮优化一个量化总结。**结果先暴露了一个真 bug**：judge 从 Round 5 起**一直是坏的**——`turn_judge` 用 `use_pro(max_tokens=1200)` 且默认 `reasoning_effort="high"`，reasoning 吃光 token 导致输出 JSON 全部截断（unterminated string）或空内容，所以 `turn_evaluations` 表一直是 0 条（从未成功评过一次）。

**修复**：`turn_judge` 调用改 `max_tokens=3000` + `reasoning_effort=None`（judge 是结构化评分，不需要 reasoning）。修复后 judge 正常评分。

**优化后遵循度量化基线**（当前游戏 14 回合全为 Round 16–23 代码生成，评最近 5 回合）：

| 维度 | 评分 /5 |
|---|---|
| canon_fidelity（剧本设定一致） | **5** |
| safety（无泄露/提前揭露） | **5** |
| state_consistency（状态一致） | **5** |
| prose_quality / freshness | 5 |
| pacing（节奏） | 4 |
| overall | **4.83** |

**诚实局限**：① 5 回合分数完全一致，可能含 LLM judge 评分趋同/宽松偏差；② 旧存档已删，**无严格"改前"对照**，这是"优化后绝对水平"而非"提升了多少"。但 canon/safety/state 满分至少佐证：当前**遵循剧本设定、不提前揭露、状态一致**都处于高水平——与本轮优化目标一致。

**改动文件**：`api/app/services/turn_judge.py`。**部署**：`docker compose up -d --build api worker`。**验证**：`pytest tests/` **159 passed**、ruff 通过；judge 实跑 5 回合全部成功落库（此前全失败）。

> 这是 Round 16–24 大优化的收尾。省 token（cache 固化 + 场景投影）+ 遵循类（防剧透/强约束/重述/字数）+ 可观测（observer/面板/judge）均已落地验证。后续若需，按 `PROMPT_ARCHITECTURE_REDESIGN.md` §7 收尾候选（dashboard 跨回合趋势）。

### Round 23 (2026-05-29) — GM 场景投影（支柱 2，省 user token）

设计文档支柱 2 落地。**先用真实数据校准预期**：当前游戏（28 回合）state_v2 仅 6135 字符、占 user 13%（不是之前 97 回合老存档的 25k/41%）；且 state 在 user 末段、不在 system 稳定前缀，**投影只省 token、不提 cache 命中**。当前 ROI 中等、长期游戏（state 膨胀）才大——用户决策"做保守投影"。

**`state_v2.project_state_for_scene`**（保守，仅 GM 用；drift/extractor 仍用全量）：

- 全保留场景/主角必需：active_scene / protagonist_sheet / abilities / conditions / skills / open_threads / story_progress / party。
- 精简明确噪声：`progression` 砍 `xp_log`（GM 规则 20 不输出 XP）；`quest_log` active 全留、completed 压成 `completed_titles`；`npc_registry` 只留在场（present_npcs ∪ party）；`relationship_tracks` 只留在场角色、`recent_events` 留最近 1 条。
- **兜底**：present 名单为空时不过滤 NPC/关系（避免砍光）。
- 接入：`prompt_builder` GM payload 的 `current_state_v2` 用投影。

**实测**：当前游戏 state_v2 **6135 → 2502 字符，省 59%**（长期游戏省更多：非在场 NPC + 大量 completed quest + 关系历史）。

**改动文件**：`api/app/services/state_v2.py`、`api/app/services/prompt_builder.py`、`api/tests/test_scene_projection.py`（新，6 用例）。

**部署**：`docker compose up -d --build api worker`。**验证**：容器内 `pytest tests/` **159 passed**、ruff 通过。

### Round 22c (2026-05-29) — 宪法层字节固化（提升 DeepSeek prefix cache 命中）

**诊断**：Round 22b 实测 cache 命中率仅 ~4.5%。逐字节比对两相邻回合 GM 请求发现：system 前 **3467 字符**字节一致，**第 3467 字符开始 diff —— 那是"当前幕未完成锚点列表"**（锚点逐个完成 → 列表每变一次，前缀就在此断裂，后面 4 万字符全 miss）。根因：Round 18 把"当前幕目标/未完成锚点"放进了 system 强约束块，而它会随幕推进变化。

**原理**：DeepSeek prefix cache 按"最长公共前缀"自动命中，从第 1 个 token 起逐 token 比对，**一遇不同 token，后面全部 miss**，命中部分 input 计费约 1/10。所以稳定内容必须尽量长、尽量靠前、逐回合字节一致。

**修复（把会变的移出稳定前缀）**：

- `prompt_builder`：`_HARD_CONSTRAINT_LABELS` 拆成 `_CONSTITUTION_LABELS`（整局不变：must_follow / reveal_rules / continuity_rules / gm_output_rules / core_mechanics / must_not / must_not_become / forbidden_drift / canon_terms）+ `_ACT_BRIEF_LABELS`（随幕变：current_act 目标+锚点 / current_act_forbidden_reveals）。
- `_build_system_content` 分层顺序：模板 → **宪法层**（稳定）→ **篇幅指引**（generation_parameters 整局不变，稳定）→ **幕级简报**（变化，放最末尾）。新增 `_render_constraint_groups` 复用渲染。

**实测**：可缓存前缀 **3467 → 8510 字符**（宪法+篇幅全进前缀，锚点列表已挪到末尾），前缀长度 ×2.4。GM/director/drift/extractor/compressor 都吃 system，稳定前缀命中对每个 agent 每回合生效。

**改动文件**：`api/app/services/prompt_builder.py`。

**部署**：`docker compose up -d --build api worker`。**验证**：容器内 `pytest tests/` **153 passed**、ruff 通过；system 分层结构实测正确（宪法<篇幅<幕简报，前缀不含锚点列表）。

> 待玩家续玩验证：在"本回合详情"面板看 cache 命中率是否从 ~4.5% 明显上升（同幕连续回合应能命中到幕简报之前）。

### Round 22b (2026-05-29) — 游戏界面"本回合详情"折叠面板（把观测搬到前端）

用户要求：把 token/cache/字数/observer 直接显示在游戏界面，兼顾桌面/移动。决策（头脑风暴）：**每回合折叠面板**（`<details>`，默认收起，不伤沉浸；原生响应式，桌面移动统一），显示全部四类。

**后端**：

- `GET /api/games/{game_id}/turns/{turn_id}/insights`（`gameplay.py`）：聚合该回合 observation（`turn_job.turn_runtime_inputs.output_observation`）+ 各 agent token/cache（`agent_traces` where job_kind='turn' job_id=turn_job.id）+ 总计/命中率。schema `TurnInsights` / `TurnAgentCost`（`schemas/turn.py`）。
- 链路：Turn → TurnJob(turn_id) → AgentTrace。

**前端**：

- `lib/api.ts`：`fetchTurnInsights` + `TurnInsights`/`TurnAgentCost` 类型。
- `play/page.tsx`：`TurnInsightsPanel` 组件——最新回合结算卡下方的 `<details>`，**展开时才按需拉取**（onToggle，避免每回合请求）；显示本回合 token、缓存命中率、篇幅（字数/达标/段落）、canon 使用、各 agent token、质量观测 flags。

**实测发现（首次端到端看见）**：真实回合 insights —— GM 流式 token 终于有数（in≈24k）；**全回合总 token≈70k，cache 命中率仅 ~4.5%**。→ 命中率低，印证设计文档"宪法层字节固化"（仍未做）值得做：当前 system 虽稳定但实际命中少，固化前缀可大幅提升。

**改动文件**：`api/app/routers/gameplay.py`、`api/app/schemas/turn.py`、`web/lib/api.ts`、`web/app/games/[id]/play/page.tsx`。

**部署**：`docker compose up -d --build api worker web`。**验证**：后端 `pytest tests/` **153 passed**、ruff 通过；web `next build`（含 tsc+lint）通过；endpoint 真实回合实测数据正确。

### Round 22 (2026-05-29) — 接通 DeepSeek prefix cache 观测（省 token 杠杆的度量前提）

**背景**：设计文档阶段 2 的省 token 最大杠杆是 DeepSeek 官方自动 prefix cache（命中部分 input 计费约 1/10）。但"没有度量不优化"——GM 是流式调用，DeepSeek 流式默认不返回 usage，导致 GM 真实 token 与 cache 命中**一直看不见**（agent_traces 里 GM tokens 全是 None）。本轮先打通观测。

**改动**：

- `deepseek_client._build_payload`：stream=True 时加 `stream_options={"include_usage": True}`。
- `deepseek_client.chat_completion_stream`：`ChatCompletionStreamChunk` 加 `usage` 字段；正确处理末尾 usage chunk（choices 为空、只带 usage，原代码会 IndexError）。
- `agent_traces.extract_cache_usage`：抽 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`。
- `model_router`：`_stream_chat` 捕获 usage chunk → 补全 GM 流式 `tokens_input/output/reasoning`（过去缺失）；`_call_chat` 与 `_stream_chat` 都把 cache 命中/未命中并入 `agent_traces.extras`（`cache_hit_tokens`/`cache_miss_tokens`）。

**意义**：DeepSeek 自动 prefix cache 本就在工作（Round 18 起 system 已是稳定前缀）；本轮先**量化现状命中率**。续玩几回合后看 trace：① GM 流式终于有 token 数；② cache 命中率。命中率高 → 前缀够稳，省 token 已生效；命中率低 → 再做"宪法层字节固化"提升。

**改动文件**：`api/app/services/deepseek_client.py`、`api/app/services/model_router.py`、`api/app/services/agent_traces.py`、`api/tests/test_deepseek_cache.py`（新，4 用例）。

**部署**：`docker compose up -d --build api worker`。**验证**：容器内 `pytest tests/` **153 passed**，ruff 通过。

> 待玩家续玩后拉数据：GM 流式 token 数 + cache 命中率（`extras.cache_hit_tokens` / `prompt_tokens`）。

### Round 21 (2026-05-29) — 字数治理：篇幅指引提进 system（下限硬、上限让位于剧本）

**背景**：Round 20 观测层暴露 GM 字数长期不达硬下限（约 70%）。根因同 Round 18：`generation_parameters` 埋在 user JSON 里被淹没。把篇幅约束提到 system 顶部。

**关键修正（用户指出的冲突）**：初版把段落/强调/字数**上限**也作为硬指标写进 system，结果与剧本 `must_follow`/`core_mechanics` 的"详细描写要求"**直接冲突**——该剧本明确要求"[剧情规则]完整描写""战斗色情化着重刻画性征""[剧情规则]完整流程""俘虏完整性征档案"等，这些场景天然需要大篇幅、多段、多强调；而 generation_parameters 是**全局单一上限**（target_max 2500 / paragraph_max 8 / emphasis_max 4），详细场景必然超。即 system 自相矛盾：一边要详细、一边限上限。这是继 Round 16 滑窗、canon 冷落之后**第三次把机械指标当违规**。

**最终方案（用户决策：上限让位于剧本）**：

- `prompt_builder._generation_parameter_directives`：分三层——【硬下限】不少于 N 字（防偷工，与详细描写一致）；【软参考，可被剧本覆盖】段落/标题/强调一般范围；【优先级】凡剧本要求"完整/详细描写"的场景，段落数/强调数/篇幅上限一律让位于剧本，不受软参考限制（但不得低于硬下限）。
- `output_observer._observe_generation`：**移除**段落/标题/强调"超上限"的违规 flag（详细场景误报）；保留字数不足、段落 < 下限（挤成一坨）、行动选项数≠4。各项 count 仍记录在 generation 指标里供观察。

**实测**：真实剧本 system 末尾篇幅指引按"硬下限 / 软参考 / 让位剧本"三层呈现，消除与 must_follow 的矛盾。

**改动文件**：`api/app/services/prompt_builder.py`、`api/app/services/output_observer.py`、`api/tests/test_gameplay.py`、`api/tests/test_output_observer.py`（+详细场景不误报用例）。

**部署**：`docker compose up -d --build api worker`。**验证**：容器内 `pytest tests/` **149 passed**，ruff 通过。

> 教训补充（§4）：generation_parameters 的**上限**类约束（段落/强调/字数上限）不可作为硬指标凌驾于剧本 must_follow 的详细描写要求——剧本优先级最高。只有**下限**（防偷工）是安全的硬约束。

> 待玩家续玩验证：observer 的字数不达标 / 段落越界 / 强调越界 flag 频次是否下降（同 Round 20b 的闭环验证法）。

### Round 20b (2026-05-29) — 修"新回合带上一回合内容"（同场景重述）

**用户反馈现象**："有的时候新回合会带有上一回合的内容。"

**诊断（数据驱动，非代码 bug）**：

- 数据库最终 narrative 干净（difflib 检测无大段相邻重复）、前端流式用 `narrative_buffer` 全量替换、`streamTurnJob` 的 `latestJob` 每回合从空初始化——**流式/存储链路没有粘连 bug**。
- 真正根因是 **GM 行为**：同一场景连续回合，GM 每回合用**逐字相同的 `### 场景标题` + 开场环境描写句**起头，而非承接上一回合推进。实测该游戏 19 回合中 6→7、7→8、13→14、18→19 的新回合开头与上一回合逐字重复 18–25 字（如反复用 `### [地点]厨房\n\n发电机低沉的嗡鸣声`）。`gm_runtime.md` 规则 12 只禁"无切换乱用标题"，没禁"同场景重复标题/开场"。

**修复（治本 prompt + 观测验证，符合敲定方案，不重写不改形态）**：

- `gm_runtime.md` 规则 12 追加：本回合与 recent_turns 最近一回合同场景（未明显切换）时，**不要重复上一回合的 `###` 场景标题和开场环境描写**，直接承接结尾与玩家行动推进。
- `output_observer.observe_gm_output` 加 `previous_narrative` 参数 + `_observe_opening_repeat`：比较两回合开头窗口（各 60 字）的公共前缀，≥12 字则 flag（`opening_repeat`）。
- `gameplay._record_output_observation` 把 `recent_turns[-1].gm_output` 作为 previous_narrative 传入——这样能用 telemetry 验证 prompt 改动是否真减少了重述。

**改动文件**：`api/app/prompts/gm_runtime.md`、`api/app/services/output_observer.py`、`api/app/services/gameplay.py`、`api/tests/test_output_observer.py`（+2 用例）。

**部署**：`docker compose up -d --build api worker`。**验证**：容器内 `pytest tests/` **148 passed**，ruff 通过。

### Round 20 (2026-05-29) — 验证器观测层 v1（敲定方案线 B 起步：只观测不重写）

按 `PROMPT_ARCHITECTURE_REDESIGN.md` §11 敲定方案，遵守剧本为北极星、验证器**只观测不重写**（度量先行，避免 Round 16 过度重写）。每回合 GM 输出后用代码做确定性校验，结果写 telemetry 供 dashboard/调优，**不干预生成**。

**新增 `app/services/output_observer.py::observe_gm_output`**（纯函数，整串匹配，失败被吞不影响主回合）：

- **generation_parameters 达标**：字数/段落/场景标题/强调/行动选项数（=4）——纯机械 100% 可靠。
- **forbidden_reveals 整串命中**：仅取 current_act.forbidden_reveals（会被揭露的实体/概念），整串匹配（绝不滑动窗口，Round 16 教训）。高精度低召回。
- **canon_terms 使用度**：每个专名是否出现，统计被冷落的专名（canon 一致性弱代理）。
- **核心角色提及**：core_characters 的 name+aliases 整串匹配统计。
- 不做（v1）：在场一致性（state.present_npcs 数据常空，噪声大，留 v1.1）。

**接入**：`gameplay.py` 两个 GM 输出 return 点前调用 `_record_output_observation`；`TurnTelemetry` 加 `output_observation` 字段并纳入 `to_runtime_inputs` → 随 `TurnJob.turn_runtime_inputs` JSONB 落库（**免迁移**，复用 Round 1 telemetry 链路）。

**真实数据立刻暴露两个之前不可见的系统性问题**（拿数据库 79 回合 trace 实跑观测）：

1. **GM 每回合字数严重不达标**：硬下限 1200 字，实际仅 831/872 字（约 70%）。
2. **canon 14 个专名每回合只用 2-3 个**，"[地点]""[异能]""[能量]"等核心专名长期冷落——对应"设定没体现"。

→ 这正是观测层的价值：把违规可观测化，为后续数据驱动治理（升级分级重写 / 调 prompt）提供依据。

**改动文件**：`api/app/services/output_observer.py`（新）、`api/app/services/gameplay.py`、`api/tests/test_output_observer.py`（新，4 用例）。

**部署**：`docker compose up -d --build api worker`。**验证**：容器内 `pytest tests/` **146 passed**，ruff 通过。

> 后续：Round 20b 给 admin dashboard 加观测违规率展示（读 turn_runtime_inputs.output_observation 聚合）。

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

> **现状（2026-05-29）**：本节是 Round 1 时的早期路线图。阶段 0–1（止血 + AI 质量基础设施）已全部落地（见 §1 Round 1–15）。**省 token + 遵循剧本的后续优化已由 Round 16–24 落地，其权威路线图与剩余项见 [`PROMPT_ARCHITECTURE_REDESIGN.md`](PROMPT_ARCHITECTURE_REDESIGN.md) §7。** 本节阶段 2–4 中：2.1 Agent 抽象基类已决策暂缓（见 §4）；2.2/2.3 未做；3.1 已做（telemetry dashboard）、3.2/3.3 未做；4.x 未做。下方条目保留作历史，不再单独推进。

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
| 把 generation_parameters 的**上限**（段落/强调/字数上限）作为硬约束（Round 21 修正） | 与剧本 `must_follow`/`core_mechanics` 的"详细描写要求"（[剧情规则]、战斗色情化、[剧情规则]、性征刻画等）直接冲突——这些场景天然需要大篇幅、多段、多强调，而 generation_parameters 是全局单一上限。剧本优先级最高，上限须让位。只有**字数下限**（防偷工）是安全的硬约束。observer 不再把"超上限"当违规。这是第三次"机械指标误判"（前两次：Round 16 滑窗、canon 冷落） |

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

### 5.4 前端：设定看板 / 工坊 / 设定页（2026-06-04 Round 36–39 新建）

> 这套是今天大建设的核心。改前端设定编辑/工坊前，先读对应 `docs/superpowers/specs/2026-06-04-*`。

| 关心的事 | 文件 | 入口符号 / 说明 |
|---|---|---|
| **看板纯逻辑**（无 React，vitest 覆盖） | `web/lib/generatorBoard.ts` | `buildBoardModel`（settings/confirmed 两源）、`deriveFields`/`inferType`（字段数据派生）、`writeBlockFields`（无损回写）、`appendItem`/`createEmptyItem`/`newItemBlock`/`ARRAY_SPECS`（新增项）、`isEmptyBlock`、`diffBoard`、锁定工具。**block.id/address 规则不可乱改**（护住生成页 diff 与模块提取） |
| 看板容器 | `web/components/board/SettingsBoard.tsx` | Tab + 网格 + 弹窗 + 「显示空设定项」开关 + onAddItem |
| 字段编辑器（8 类型） | `web/components/board/BoardFieldEditor.tsx` | text/textarea/number/bool/stringList/objectList/keyValue/json |
| 块详情/编辑/新增弹窗 | `web/components/board/BlockDetailModal.tsx` | 类型化 drafts |
| Tab / 网格(空块折叠+＋新增) | `web/components/board/BoardTabs.tsx` / `BoardBlockGrid.tsx` | |
| 生成页（看板+对话停靠+手改锁定） | `web/app/games/new/page.tsx` | 锁定 locked_fields → 后端 interview |
| 设定页（看板编辑+高级折叠+并入） | `web/app/games/[id]/settings/page.tsx` + `web/components/settings/*` | 保存走 `updateGameConfig`(PATCH config)+版本快照 |
| 工坊页 | `web/app/workshop/page.tsx` | 模块库：分类分组/搜索/改名/删除/编辑内容/导入导出 |
| 工坊组件（提取/并入） | `web/components/workshop/*` | `ModuleMergePanel`(并入预览/AI优化/冲突)、`SaveAsModuleDialog`(存为模块) |
| 模块 payload 还原 | `web/lib/moduleFragment.ts` | `buildModulePayload`（按 BoardBlock.address 取数据） |
| 前端 API | `web/lib/api.ts` | `listModules`/`createModule`/`mergePreviewModules`、`updateGameConfig` 等 |
| **后端工坊** | `api/app/models/setting_module.py`、`services/module_library.py`（合并引擎）、`services/module_adapter.py`（AI 本地优化，独立 timeout+fallback）、`routers/modules.py`、`prompts/adapt_module.md` | merge-preview 统一服务"已有剧本/生成草稿"两个并入点 |
| 前端测试 | `web/lib/generatorBoard.test.ts`、`web/lib/moduleFragment.test.ts` | `cd web && npm test`（vitest，纯函数）。**CI 跑 `eslint .` 全量含 tests，改前端推送前必跑 `npm run lint`** |

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

> **现状（2026-05-29）**：本节是 Round 1 落地时的遗留清单，多数已被后续 Round 处理或被新架构覆盖——疑点 1（重写局部修订）、3（drift 触发阈值）相关逻辑已在 Round 16 重构防剧透时调整；trace/observer 基础设施（Round 3/20）已让这些"等数据再定"的项可观测。下方保留作历史参考，新疑点请记到对应 Round 条目或 §4 决策记录。

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

> ✅ **持续在容器内验证**：截至 Round 24，`docker compose exec api pytest tests/` 全套 **159 passed**（Round 10 时为 69）；迁移 head、trace 端到端、admin 查询、judge 实跑均 OK。Round 16–24 每轮均 `docker compose up -d --build api worker` 重建 + 真实游玩验证。
> 下面清单保留给**生产环境首次部署**复核（生产用 docker-compose 的真实 redis + worker）。

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
