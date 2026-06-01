# RPGForge 游戏系统审查报告（2026-06-01）

> 本文档是「游戏系统」专项审查的产出与修复驾驶舱。审查方法：将游戏系统切成 5 个互不重叠分区，并行多 Agent 深度审查 + 真实存档（`[示例剧本]`，15 回合）只读验证。所有 P0/P1 结论均已用真实数据或可复现脚本坐实。
>
> 配套：`OPTIMIZATION_PLAN.md` 是全项目驾驶舱，本文件是游戏系统专题。修复落地后在本文件路线图打 `[x]`，并在 OPTIMIZATION_PLAN.md §1 追加对应 Round。

## 0. 健康度总评

| 子系统 | 健康度 | 说明 |
|---|---|---|
| event-sourcing 重放 | ✅ 优 | 重放幂等已实证（persisted==rebuild#1==rebuild#2，MD5 一致）。**改 apply 逻辑后跑一次 rebuild 即自动修存量，无需迁移脚本** |
| 数值结算（xp/技能/等级） | ✅ 良 | 公式/clamp/level-up/乘数表边界全部正确 |
| 剧本生成主路径 | ✅ 良 | 真实剧本 5 幕/17 主线/46 锚点字段契约逐一对齐；`normalize_story_settings` 幂等 |
| 转幕控制 `_can_advance_to_act` | ✅ 逻辑本身严密 | 防跳幕 + required 锚点全完成；但**信任的 `completed_anchors` 上游被污染** |
| 状态提取契约 | 🔴 差 | LLM 输出键名与代码身份键断裂（总根因 R1） |
| 任务/线索/锚点/推进 | 🔴 差（重灾区） | 脆弱中文字符串匹配泛滥（总根因 R2）+ 证据池黑名单漏（R3） |
| 结算状态机 | 🟠 有 P0 软锁 | `failed` delta 无人工出口可卡死存档 |
| 关系/投影/前端 | 🟡 中 | 子串误判分桶、关系合并丢信息、前端信息缺失 |

## 1. 三大总根因（贯穿多数问题）

- **R1 字段契约断裂**：`extract_state_delta.md` 对 `quest_updates`/`open_thread_updates`/`faction_updates`/`new_lore_candidates` **零规则、无 item 模板**（而 `xp_events`/`skill_events`/`condition_updates` 有完整示例，那几块就健康）。LLM 遂自创键名 `quest_id`/`thread_id`/`progress_update`/`description`，而代码身份键 `_identity_candidates`(`state_applier.py:679`)/`_thread_key`(`:576`)/`_existing_quest_statuses`(`:1917`) 只认 `id/name/title/key/npc` → **显式状态全部丢失、产生僵尸记录、resolve 跨回合失效**。
  - 真实数据：`{'source':'explicit','status':'active','quest_id':'main_quest_2','progress_update':'已精确定位角色D位置…'}`、`{'thread_id':'bai_xiaoyu_rescue','status':'active','description':'…'}`。
- **R2 脆弱中文字符串匹配泛滥**：Round 16 已明令回退「未来幕短语滑动窗口子串黑名单」，但同类逻辑仍**完整存活**于锚点完成推断、线索分桶、任务状态判定、活动证据匹配中（滑窗片段/子串/否定句误判）。
- **R3 证据池用黑名单天然会漏**：`STATE_EVIDENCE_EXCLUDED_KEYS`(`state_applier.py:135`) 用排除式，已漏 `open_threads`（未解线索=未完成目标，却被当成「锚点已完成的证据」）和 `known_facts`。应改白名单。

## 2. 问题清单（按严重度）

### P0 — 崩溃 / 数据损坏 / 软锁

- **[P0-1] `failed` 状态 delta 无人工出口，可永久卡死存档** —— 根因 `routers/states.py:20-21`（`EDITABLE`/`REJECTABLE` 均不含 `failed`）+ `state_settlement.py:67`（failed 每次 `ensure_settled` 重新提取，烧 3 次 LLM）。若某回合 `gm_output` 确定性触发提取失败 → 玩家续玩拿 409 → 既不能自动结算、又不能人工编辑/拒绝跳过。**修复方向**：`failed` 加入 `REJECTABLE_STATUSES`（允许以空 delta 跳过该回合状态变更）；给 StateDelta 加 `attempt_count` 上限，超限自动降级为空 approved delta 并告警。

### P1 — 可见错误（已实锤）

- **[P1-1] 字段契约断裂：`quest_id`/`thread_id` 不被识别**（总根因 R1 的直接后果）—— 根因见 §1 R1。后果：① 真实存档 4 条 `id/title=None` 僵尸任务永久显示且无法清理；② LLM 写的进度文本（`progress_update`）全部丢失，主线任务 `progress` 恒 null；③ 线索 resolve 跨回合 key 漂移失效；④ 显式 quest 状态完全进不来 → 主线任务全靠脆弱推断。**修复方向**：prompt 补 item 模板（统一用 `id`）+ `_identity_candidates`/`_thread_key`/`_thread_identity_values`/`_existing_quest_statuses` 纳入 `quest_id`/`thread_id` 归一。
- **[P1-2] 完成的任务/锚点对应的长句线索永不 resolve**（用户最初报的 bug）—— 根因 `_quest_thread_topic`(`state_applier.py:1631`) 要求主题词 2-12 字，LLM 写的整句线索（27 字）→ 空主题 → 匹配交集永空；叠加 `thread_id` 不被身份路径识别（`_thread_identity_values:609`）→ id 关联也废。实测：任务「营救角色D」已完成，线索「[地点]…角色D发出求救信号，被困第七天」永远 active。**修复方向**：优先靠稳定 id 关联（`thread_id`↔锚点/quest `id`），子串兜底（已完成项主题词 ≥3 字作为子串命中线索标题）。
- **[P1-3] 已 resolve 的线索可被同标题 active 更新「复活」** —— 根因 `_merge_thread_record`(`state_applier.py:618`) 无条件覆盖 `status`，LLM 再次提及线索（不带 resolve action）即把已关闭线索翻回 active。**修复方向**：`status` 单调保护（已 resolved/closed 不被非 resolve 更新降级）。
- **[P1-4] `_thread_is_resolved` 子串误判 → 活跃线索被错误隐藏** —— 根因 `state_v2.py:286` 用 `"完成" in text`：「调查未完成的仪式」→ resolved、「解决粮食危机」→ resolved。被错分到 resolved 桶 → 前端 `open_threads.active` 不显示。**修复方向**：分桶只看显式 `status`/`action` 字段，不对 title 子串判定；或加否定词排除。
- **[P1-5] 库存删除按 `name` 键，真实库存用 `item` 键 → 删除静默失效** —— 根因 `_remove_inventory_item`(`state_applier.py:322`) 取 `item.get("name")` 只比对 `existing.get("name")`，而真实库存是 `{"item":"压缩干粮"}`。**修复方向**：复用 `_inventory_key`/identity 归一（兼容 `item/name/title`），支持按数量部分扣减。
- **[P1-6] 完成/失败/隐藏任务对玩家完全不可见** —— 根因前端 `status/page.tsx:362` 只渲染 `quest_log.active`。实测存档 completed:3、hidden:12 全不显示。**修复方向**：任务面板加「已完成」分组（`completed_titles` 现成）；`hidden` 是否展示需与剧情防剧透权衡。
- **[P1-7] act_plan 分区空返回时回退 outline，锚点字段错位 → 全局机械完成判定失效** —— 根因 `game_generator.py:475`：outline 用 `completion_anchor_plan`（字符串数组），运行时读 `completion_anchors`（对象数组，需 `id`/`required`/`completion_signal`）。回退后每幕 `required_anchor_ids=[]` → `_computed_ready_for_next_act` 恒 None → 自动进幕兜底全失效，幕推进降级为完全依赖 Director LLM。**修复方向**：空分区视为失败触发重试；回退时把 `completion_anchor_plan` 映射成 `completion_anchors` 骨架。
- **[P1-8] main_quest_path 空分区回退 outline，缺 id/title → 标题全「未命名主线节点」** —— 根因 `game_generator.py:477`，outline 节点无 `id`/`title`。`id` 会合成（唯一，运行时不错乱），但玩家可见标题全是占位符。**修复方向**：同 P1-7；回退路径用 `objective` 截断兜底 title。

### P2 — 隐患（机制危险，当前数据未必爆发）

- **[P2-1] 证据池漏排除 `open_threads`/`known_facts` → 锚点误判完成证据** —— `STATE_EVIDENCE_EXCLUDED_KEYS`(`:135`)。实测把锚点 `description`（目标文本）喂给 `_anchor_completion_reason` 即返回「已完成」。**方向**：加入 `open_threads`；评估 `known_facts`；长期改白名单（见 P3-2）。
- **[P2-2] 锚点完成阈值过低** —— `_anchor_completion_reason`(`:1107`) 任一 ≥6 字短语整串命中、或 ≥2 个短语命中即判完成。
- **[P2-3] Round 16 已禁的滑窗子串匹配仍存活** —— `_anchor_key_terms`(`:1195`)+`_term_fragments`(`:1245`) 对 >8 字词生成 3-4 字滑动窗口片段，`_anchor_key_term_evident`(`:1222`) 做模糊匹配。实测 `act_1_bai_xiaoyu_devotion` 完成理由全是「念力控制/力控制+/米念力控」碎片。**方向**：删 `_term_fragments`+模糊匹配；锚点完成只信 LLM 显式 `completed_anchors` + 整串 `completion_signal` 高精度命中。
- **[P2-4] `_quest_status_bucket` 否定句误判** —— `:1960` 用 `"完成" in text`：「未完成」「无法完成」→ completed，「放弃抵抗」→ failed。修好 R1 后此 bucket 立即成新误判源。**方向**：精确状态枚举 + 否定词前置检测。
- **[P2-5] 未来幕「活动证据」靠 2 字片段 + 当前角色名误触发** —— `_act_activity_evident`(`:1703`)/`_activity_markers`(`:1861`)。实测 `act_2` 因当前角色「角色D」+ 通用词片段被判「世界中已在发生」。**方向**：排除当前已登场角色名；去 2-3 字后缀片段。
- **[P2-6] `_sync_current_act_from_completed_anchors` 绕过转幕校验 + `completed_anchors` 只增不减** —— `:1017` 按 act 索引直接跳幕，不走 `_can_advance_to_act` 的 required 校验；`:828` 只增。一旦误判一个未来幕锚点完成即跳幕。**方向**：跳幕也走 required 校验；重放时 `completed_anchors` 由当回合证据重算。
- **[P2-7] extractor JSON 截断（max_tokens=4096）无兜底** —— `state_extractor.py:172` + `json_utils` 全有或全无解析。高密度回合截断 → 整回合状态丢失 → 可能进 P0 死锁。（注：`json_mode=True` 已落地，畸形/散文包裹实际不会发生，只剩截断风险。）**方向**：提高 max_tokens / reason 限长 + 尾部修补尽力解析。
- **[P2-8] 库存数量非数值静默丢弃 + 可为负** —— `_merge_inventory_record`(`:370`)。「若干」「一把」等非数值被跳过；负累加得负库存。**方向**：保留量词或并列；`max(0, total)`。
- **[P2-9] NPC 场景定位字符串匹配脆弱** —— `_narrative_places_npc_in_changed_scene`(`:287`) 单字命中（`林`→`主角`）、名+地点共现即判在场（「角色D困在 3km 外」误绑到基地）。触发面窄但条件满足即误绑。**方向**：要求显式移动模式 + 名称边界。
- **[P2-10] relationship 未命中轴默认 `trust`** —— `quantified_state.py:255`。未知轴（`romance` 等）误加 trust 并污染 stage。**方向**：未命中跳过该事件。
- **[P2-11] 关系别名合并数值轴取 max → 丢失「关系下降」** —— `_merge_relationship_record`(`:718`)。和解后的低 conflict 被旧高值覆盖。**方向**：取最新（带 turn）而非 max。
- **[P2-12] relationship_events 用别名 → 同一 NPC 分裂成两条记录** —— `_apply_relationship_event`(`quantified_state.py:256`) `_upsert_named` 不查 aliases；`_merge_relationship_aliases` 兜底只认 `npc.aliases`，记不全则永久分裂。**方向**：事件应用前也走别名归一。
- **[P2-13] `validate_story_settings` 无最小基数校验** —— `story_settings.py:586`。空 act_plan、零锚点幕均放行，是 P1-7/P1-8 静默劣化的放大器。**方向**：act_plan 至少 1 幕、每幕 required 锚点 ≥1。
- **[P2-14] act_plan/main_quest_path 空返回不触发重试** —— `game_generator.py:432` 仅校验类型，空数组合法 → 滑向 outline 回退。**方向**：关键 list 分区空数组也抛错触发既有重试。
- **[P2-15] 线索卡向中文玩家直显英文 status** —— `status/page.tsx:393`。**方向**：status 中文映射或回退展示。

### P3 — 轻微 / 可维护性

- **[P3-1]** 显式 `completed_anchors` 无白名单校验（`_apply_story_progress:793`），LLM 误报未来幕 anchor_id 直接 append → 配合 P2-6 跳幕。
- **[P3-2]** 证据池应改**白名单**（当前混入 `npcs`/`location`/`relationships` 的描述性文本，对「是否完成」语义无关，扩大误命中面）。
- **[P3-3]** 条件以裸字符串存储时无法被 `resolved` 移除（`quantified_state.py:231`）。
- **[P3-4]** `_apply_location`(`:187`) 跨地点残留陈旧非事件属性（`danger`/`district`）。
- **[P3-5]** `_merge_mapping`(`:456`) 对 protagonist/variables 无 `_has_value` 守卫，空值可覆盖好数据。
- **[P3-6]** `total_xp` 非纯重放场景会低估且不自愈（`quantified_state.py:117`）。
- **[P3-7]** xp/skill `reason` 对 dict 直接 `str()`（`quantified_state.py:360`），污染日志展示。
- **[P3-8]** 技能与能力可同名（实测「星域」既是 skill 又是 ability），投影层不去重。
- **[P3-9]** `_merge_recent_events`(`:737`) 按 dict 全等去重，模板化交互被误合并。
- **[P3-10]** `_merge_relationship_aliases` 在 apply 流程被调用两次（`:170`+`:172`），170 冗余。
- **[P3-11]** `FAILED_SETTLEMENT_STATUSES`(`state_settlement.py:26`) 为死常量，无引用。
- **[P3-12]** `project_state_for_scene`(`state_v2.py:604`) 丢弃 hidden 任务桶。**决策（用户 2026-06-01）：hidden 任务应保留给 GM 看、用于剧情铺垫**——GM 需要知道隐藏目标的存在以提前埋线，hidden **不是**对 GM 的防剧透对象（防剧透由 next_act 裁剪 / forbidden_reveals 等机制负责）。→ 待实现，见 §4 阶段 8.1。
- **[P3-13]** `core_mechanics_outline` 未列入 outline 截断重试的必保字段（`game_generator.py:351`）。

## 3. 已验证健康（放心清单，无需改动）

- **event-sourcing 重放幂等**：实证 MD5 一致，`delta_json` 只存 LLM 原生输出（无 derived 回写），quests 整体覆盖、anchors `not in` 去重累加。→ 改 apply 逻辑后 rebuild 自动修存量。
- **数值公式**：xp/skill 乘数表、`_clamp`（xp 1-90、skill 1-35、relationship 0-100）、level-up while 循环、`mastery` 边界全部正确。
- **生成主路径契约**：`completion_anchors`/`main_quest_path`/`act` 标识/`transition_target`/`initial_state` 根 key 生成与消费逐一对齐；`normalize_story_settings` 幂等；硬失败路径干净（畸形 JSON 抛错不落库）。
- **转幕控制 `_can_advance_to_act` 逻辑本身严密**（问题在喂进来的 `completed_anchors` 被污染）。
- **前端 `getStateV2` 二次归一化兜底强**，后端字段缺失/类型漂移难击穿到 UI。

## 4. 分阶段修复路线图

> **进度（Round 26-28）**：✅ 已完成 19 项（阶段 1-2 全 + 3.1-3.3 + 4.1 + 5.1/5.3 + 6 前端 + 7）+ dead code 已清理（Round 28）。⏳ 未勾项（3.4/4.2/5.2/5.4/6.1/6.4 + P3）均评估后暂缓，理由见 §2 各条与 OPTIMIZATION_PLAN Round 27/28。真实续玩已验证新回合线索/任务状态正确流转（角色I线索：已了结 resolved、对应未完成锚点的保持 active）。

> 排序原则：先治根因与止血（阶段 1），再修用户可见 bug（阶段 2），再彻底落实 Round 16 教训（阶段 3），最后健壮性与体验。每阶段可独立交付、独立验证。改 apply 逻辑后**必须对真实存档跑一次 rebuild diff 回归**（重放幂等是前提）。

### 阶段 1 — 止血与契约根治（最高优先，最廉价、影响面最大）
- [x] **1.1 字段契约**：`extract_state_delta.md` 补 `quest_updates`/`open_thread_updates`/`faction_updates` item 模板（新增规则）；统一用 `id`。→ P1-1、R1
- [x] **1.2 身份键归一**：`_identity_candidates`/`_thread_key`/`_thread_identity_values`/`_existing_quest_statuses` 纳入 `quest_id`/`thread_id`。→ P1-1
- [x] **1.3 P0 软锁**：`failed` 加入 `REJECTABLE_STATUSES`；StateDelta 加 `attempt_count` 上限自动降级。→ P0-1
- [x] **1.4 截断兜底**：extractor 提高 max_tokens / reason 限长 + 尾部尽力解析。→ P2-7

### 阶段 2 — 线索/任务/锚点 resolve 与分桶修正（含用户最初报的 bug）
- [x] **2.1 线索匹配靠 id 关联**（`thread_id`↔锚点/quest `id`），子串兜底（已完成项主题词 ≥3 字）。→ P1-2
- [x] **2.2 `_thread_is_resolved` 不子串判 title**，只看显式 status/action。→ P1-4
- [x] **2.3 `_merge_thread_record` status 单调保护**。→ P1-3
- [x] **2.4 证据池排除 `open_threads`**。→ P2-1

### 阶段 3 — 砍脆弱字符串匹配（Round 16 教训彻底落地）
- [x] **3.1 删 `_term_fragments` 滑窗 + `_anchor_key_term_evident` 模糊匹配**；锚点完成只信显式 + 整串 signal。→ P2-2、P2-3
- [x] **3.2 `_quest_status_bucket` 精确枚举 + 否定词检测**。→ P2-4
- [x] **3.3 `_act_activity_evident` 排除当前角色名 + 去片段**。→ P2-5
- [ ] **3.4 证据池改白名单**（只收成果性字段）。→ P3-2

### 阶段 4 — 状态机与推进健壮性
- [x] **4.1 显式 `completed_anchors` 白名单校验**（拒绝未来幕/非法 anchor_id）。→ P3-1
- [ ] **4.2 `_sync_current_act_from_completed_anchors` 走 required 校验**；重放时 anchors 可重算。→ P2-6

### 阶段 5 — 基础字段与数值
- [x] **5.1 库存删除键归一 + 部分扣减 + 防负 + 非数值保留**。→ P1-5、P2-8
- [ ] **5.2 NPC 场景定位收紧匹配**（显式移动模式 + 名称边界）。→ P2-9
- [x] **5.3 axis 未命中跳过（不默认 trust）**。→ P2-10
- [ ] **5.4 `_merge_mapping`/`_apply_location`/`total_xp`/条件裸串/reason dict** 健壮化。→ P3-3~P3-7

### 阶段 6 — 关系 / 投影 / 前端
- [x] **6.1 关系合并取最新（带 turn）而非 max + 事件前别名归一**。→ P2-11、P2-12
- [x] **6.2 前端显示已完成任务**。→ P1-6
- [x] **6.3 线索 status 中文映射**。→ P2-15
- [ ] **6.4 技能/能力同名处理 + recent_events 带 turn 去重 + 删冗余别名归一调用**。→ P3-8~P3-10

### 阶段 7 — 生成侧防线
- [x] **7.1 `validate_story_settings` 最小基数校验**（act_plan 非空、每幕 required 锚点 ≥1）。→ P2-13
- [x] **7.2 act_plan/main_quest_path 空分区触发重试**。→ P2-14
- [x] **7.3 outline 回退字段映射**（`completion_anchor_plan`→`completion_anchors`，补 title）。→ P1-7、P1-8

### 阶段 8 — 投影补充（按用户决策）
- [x] **8.1 `project_state_for_scene` 保留 hidden 任务桶给 GM**（用户 2026-06-01 决策：hidden 用于 GM 剧情铺垫，非防剧透对象）。当前 GM 投影把 `quest_log` 重建为仅 `{active, completed_titles}`、**丢弃 hidden**；改为保留 hidden（至少标题/objective）传给 GM，使其能提前为隐藏目标埋线。与 next_act 裁剪等既有防剧透机制不冲突——那针对「未来幕剧情」，hidden quest 是「当前局已存在、玩家尚未激活的目标」。→ P3-12

## 5. 验证与部署约定

- 后端测试必须在容器内：`docker compose exec api pytest tests/`。
- 改 `api/app/services/*` / prompt 后**必须重建镜像**（不挂源码）：`docker compose up -d --build api worker web`。
- 每阶段新增回归用例（如长句线索 resolve、quest_id 归一、否定句不误判完成、证据池不含线索）。
- 改 apply/state_applier 逻辑后：**对真实存档跑 `rebuild_game_state` 并 diff，确认存量自动修复且无意外漂移**。
- prompt 改动记录规则编号到 OPTIMIZATION_PLAN.md。
