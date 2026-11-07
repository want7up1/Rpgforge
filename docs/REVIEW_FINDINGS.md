# Review Findings

本文件记录代码审查发现的有效问题。状态说明：`Open` 待处理，`Done` 已修复并验证，`Ignored` 明确暂不处理。

## 2026-11-07 — A/B 优化评估中的已定位问题

以下问题已在 Round 61 的共同职责重构中修复。范围见 [`OPTIMIZATION_PLAN.md` §2](OPTIMIZATION_PLAN.md#2-当前执行队列)，详细测试与性能记录见 [`history/OPTIMIZATION_LOG_2026-11.md`](history/OPTIMIZATION_LOG_2026-11.md)。证据包括隔离 PostgreSQL、模拟模型任务与内置浏览器；不等同于真实模型长局、生产断电或实体手机验收。

### Done — A1：回退后保留已删除回合的摘要

- 位置：`turn_rewind.py::rewind_game_to_turn`、`context_compressor.py::load_prompt_summaries`。
- 影响：回退删除 Turn 并重建状态，但未失效 Summary/状态摘要；后续上下文仍读取覆盖未来回合的记忆。
- 证据：实际服务函数配合内存 fake DB，从第 3 回合退到第 1 回合，状态回合变为 1，摘要与前情提要仍引用第 3 回合。
- 验收：回退到 0、跨摘要周期、同回合重写后，所有注入记忆均属于当前有效时间线；后台晚到结果也不能重新写入未来摘要。
- 验证：`test_timeline_invariants.py` 覆盖回退/摘要范围与晚到压缩；generation/config 校验在模型调用后执行，读档亦筛除超范围摘要。

### Done — A1：尾声污染初始种子，影响重开与较早读档后的重建

- 位置：`turn_maintenance_jobs.py::_persist_campaign_ending`、`progress_saves.py::_initial_state_for_restart` / `_restore_state`。
- 影响：生成非空尾声后把结局写入 `initial_state_json`；重开复制该种子，较早读档也不恢复原种子，下次重建可能重新带回旧结局。并非所有读档均触发。
- 证据：纯函数复现 `current_turn=0` 同时带有 `campaign_complete=True` 与旧尾声；恢复早期 live state 后种子仍保留结局。
- 验收：有结局局的回退、重开、早期读档、继续后重建正确；兼容已有污染种子，不清除有效已完成存档的结局。
- 验证：`test_timeline_invariants.py`、`test_async_timeline_fencing.py`、`test_terminal_progress.py` 覆盖种子清理、早期读档/重开、旧尾声写入失效和有效结局保留。

### Done — A1：进度快照遗漏结算重试计数

- 位置：`progress_saves.py::_state_delta_snapshot` / `_restore_state_deltas`。
- 影响：失败 delta 的 `attempt_count` 不随快照保存/恢复，读档后默认归零，削弱跨续玩的失败重试上限。
- 证据：已有 `attempt_count=8` 的对象生成快照时字段缺失，恢复路径也未读取该字段。
- 验收：新快照计数往返保持，旧快照缺字段有兼容默认，不增加自动模型重试额度。
- 验证：旧 schema 真实数据迁移、旧快照加载/再保存通过；timeline 回归验证计数 8 往返保持，旧缺字段默认 0。

### Done — A2：流已收首帧后静默中断无法自愈，短新快照可能保留旧内容

- 位置：`web/lib/turnJobStream.ts::waitForTurnJobWithStream` / `mergeTurnJobSnapshot`。
- 影响：首帧清除连接计时器后仅依赖 `onerror`，静默半开连接没有心跳超时恢复；running 快照按字符串长度保留较长内容，不能识别新一轮较短结果。
- 证据：执行实际函数配合假 EventSource/时钟，收到首帧后静默 65 秒仍未轮询或结束；较短的新快照未替换旧正文。
- 验收：锁屏/回前台、漏完成帧、较短新生成、重复帧、回退后旧流等场景均恢复服务器权威结果，并保留轮询降级。
- 验证：`jobStream.test.ts`、`turnJobReplay.test.ts` 覆盖静默连接、前台/online、重复/丢帧、短新生成、取消与低落盘序号的权威终态恢复；同 job 的直接 GET 终态可结束，旧 SSE 仍拒绝。

### Done — B1：模型锚点投影与实际完成门槛不一致

- 位置：`story_settings.py::build_runtime_story`、`state_applier.py` 必需要求组计算、`act_pacing.py::compute_act_pacing`。
- 影响：运行时只保留前 16 个未完成锚点，实际门槛按全量计算；必需项位于截断范围外时模型看不到，pacing 还可能误报 ready。
- 证据：16 个可选项加第 17 个必需项的纯函数复现，实际未达标、模型未见必需项、pacing 为 ready。
- 验收：必需条件与替代路线不因投影截断丢失，模型、节奏和玩家进度使用一致的完整计算来源。
- 验证：`test_progress_rules_refactor.py` 以 16 个 optional + 第 17 个 required 及多条替代路线验证统一计算；必需路线不参与可选预算。

### Done — B1：可选锚点完成重置主线停滞计时

- 位置：`state_applier.py::_apply_story_progress`、`act_pacing.py::compute_act_pacing`。
- 影响：任一新锚点均更新最近进展回合，optional 进展可以清除仍未推进的必需门槛压力。
- 证据：12 回合无必需进展后只完成可选项，仍有必需门槛，停滞归零且 pressure 回到 low。
- 验收：主线停滞按必需要求组的实际进展计算；可选内容正常记录，不虚报完成或自动强制转幕。
- 验证：ProgressRules 与 act_pacing 回归验证 optional 不重置主线进展时间，同组替代项完成后的行为及原自动转幕时机保留。

### Done — B2：持久物品未进入当前状态视图与面板

- 位置：`state_v2.py::normalize_state_v2`、`web/lib/stateV2.ts`、状态页、`prompt_builder.py`。
- 影响：后端 `inventory` 已保存，变化卡也能显示获得/失去，但当前 StateV2 未投影持久物品；状态面板和 GM 的 `current_state_v2` 缺少这份权威清单。其他正文/摘要可能提到物品，不代表物品本身未保存。
- 证据：给含“仓库钥匙”的真实纯函数输入，原状态保留物品，派生 StateV2 无 inventory 字段。
- 验收：新旧存档的随身物品/证物持续可查，获得和失去与回执一致，相关物品进入 GM 状态，可见性符合玩家知识范围。
- 验证：`test_runtime_views.py`、`narrativeInventory.test.ts` 和移动端手账/状态页验证；字符串、item 别名、0.5 单位与私有可见性兼容。

### Done — B3：本回合变化摘要忽略故事进度更新

- 位置：`web/lib/gameExperience.ts::buildTurnSettlement`、游玩页 `TurnSettlementCard`。
- 影响：摘要未处理 `story_progress_update`；仅完成主线锚点或转幕的回合可能显示“暂无结构化结算”。
- 证据：实际函数输入仅含合法进度更新，结果 `hasChanges=false`、sections 为空。
- 验收：已落账的锚点、幕和结局变化有对应玩家反馈；结算中、确无变化与失败后跳过可区分，回执不直接等同于模型提取申请。
- 验证：`test_state_settlement_refactor.py`、`test_player_receipt_review.py`、`settlementView.test.ts` 验证真实前后状态、主线、跳过/失败与旧空回执；浏览器验证转幕和通关反馈。

### Done — C1：读档按回合逐条查询

- 位置：`progress_saves.py::_clear_runtime_progress` / `_restore_state_deltas`。
- 影响：删除回合触发关联 delta 的逐条懒加载；恢复 delta 时逐条 `db.get(Turn)`，500 回合实际读档超过 1000 条 SQL。
- 修复：关联批量预载，恢复使用同游戏 Turn map；保留 ORM 删除、原有 delta 状态、回执与计数语义。
- 验证：10/50 回合混合 approved/rejected/failed 的真实 PostgreSQL 回归均限制 SELECT 数量且状态/计数往返保持；最终 500 回合 SQL 与耗时见当月性能表。

### Done — 异常与终局的状态投影不同步

- 位置：`routers/gameplay.py::create_turn`、`turn_maintenance_jobs.py::_with_epilogue`、游玩页 `CampaignEndingCard` / `StoryPanel`。
- 影响：同步正文持久化后出现非预期维护异常，会留下 pending 回执；尾声只写根状态会导致 v2/UI 读不到，末幕未计入通关幕数，结束后仍显示行动选项。
- 修复：只对尚 pending 的持久回合标 failed，已确认 delta 不覆盖；结局同步 v2，前端兼容旧根尾声、计入当前末幕并隐藏终局行动。
- 验证：`test_inline_atomic_turns.py` 的真实服务故障重试、`test_terminal_progress.py`、`settlementView.test.ts` 和实际两幕模拟通关页面通过。

### Done — 隐藏人物通过显式关系及旧投影泄露

- 位置：`state_v2.py`、`settlement_receipts.py::_view`、`web/lib/stateV2.ts`。
- 影响：关系自带 known/default，但引用隐藏 NPC 的姓名、别名或 ID 时，只检查关系自身 visibility 会显示隐藏态度；旧 v2 还可能缺人物可见性元数据。
- 修复：共享隐藏人物引用规则，玩家关系与回执继承更严格可见性；canonical NPC 补齐旧投影元数据，GM 保留正文；隐藏条目仍参加差异匹配，避免误报关系失去。
- 验证：姓名/别名/ID × default/known、旧投影、visibility 变化、正常已知关系均有定向回归；前端同时过滤原始 NPC 别名和在场/同行名单。

### Done — 离页晚到请求重开监听、崩溃终态序号落后

- 位置：`turnRequest.ts::TurnMonitorScope`、游玩页 submit/monitor、`turnJobStream.ts`。
- 影响：getTurnJob 在离页后完成可能新开旧监听或取消新游戏的监听；已发送 delta 但未落盘序号时进程崩溃，终态快照序号偏小会被拒绝。
- 修复：挂载、创建请求、详情请求和流共用 AbortController 作用域，所有 continuation 先校验；只允许同 job 直接 GET 的权威终态恢复低序号，仍拒绝旧时间线和迟到 SSE。
- 验证：`turnRequest.test.ts`、`turnJobReplay.test.ts` 新增取消和终态恢复回归，TypeScript/lint/构建通过。

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
