# RPGForge AI 开发驾驶舱

> 最后更新：2026-11-07（Round 62：替换部署验收通过；A/B 重构完成，B4 延后）。本文件只保留当前目标、执行边界、下一步队列和最近完成摘要；Round 1–59 的完整旧驾驶舱已归档到 [`history/OPTIMIZATION_PLAN_ARCHIVE_THROUGH_ROUND_59.md`](history/OPTIMIZATION_PLAN_ARCHIVE_THROUGH_ROUND_59.md)。文档与代码冲突时以代码为准。

## 0. AI 接手摘要

| 项目 | 当前状态 |
|---|---|
| 产品方向 | 自托管、纯叙事向 AI 文字 RPG；状态以 conditions、relationships、quests、open threads、known facts、幕进度等文字结构延续，不恢复玩家可见的等级、属性、技能、骰点或危机数值。 |
| 运行形态 | Docker Compose：Next.js `web` → FastAPI `api` → Redis/RQ `worker`，PostgreSQL + pgvector 持久化；公开入口只应指向 Web。 |
| 主回合 | 玩家行动 → 6 阶段 TurnJob → StoryDirector → GM 流式正文 → 持久化回合 → 异步状态提取/应用、偏离审计、结局判断和周期性记忆维护。 |
| 前端 | Round 58 已重做为像素磷光绿终端风；Round 59 已修复 320px 窄屏右侧溢出和记忆页帮助气泡越界，远端实页已验收。 |
| 当前任务 | A1–A4、B1–B3、C1–C5 已完成合并重构与性能对比；经用户授权，Round 62 已替换旧 TaleForge 部署并验收，旧专属代码和存档按要求删除。B4 延后，模型配置待用户填写；发布记录以本轮 Git 提交为准。 |
| 审查台账 | [`REVIEW_FINDINGS.md`](REVIEW_FINDINGS.md) 保留 A/B 原始复现与本轮修复证据；异步晚写、隐藏人物关系和通关投影有专门回归用例。 |
| 最近验证 | Round 62：远端实际镜像隔离数据库 312 项全过、生产构建通过；真实代理/SSE/存读档/回退/重开/RQ worker/卷可写/源码摘要通过。Round 61 的本地 92 项前端与旧档兼容、移动端模拟验收保留。未调用真实模型。 |

接手顺序：

1. 读本文件 §0–§8，确认目标、边界和验证方式。
2. 有代码审查或修复任务时读 [`REVIEW_FINDINGS.md`](REVIEW_FINDINGS.md)，避免重复问题。
3. 改 AI 运行链路前读 [`AI_STORY_RUNTIME_GUIDE.md`](AI_STORY_RUNTIME_GUIDE.md) 和实际代码；改前端看板/工坊前读对应 [`superpowers/specs/`](superpowers/specs/) 设计稿。
4. 先看 `git status` / `git diff`，保留用户已有改动；部署前确认代码、私有配置和持久数据边界。

## 1. 当前目标与边界

### 当前目标

- 保持已上线的纯叙事运行链路、长局状态一致性和移动端 UI 稳定。
- 将 A/B 优化按共同职责合并实施：统一状态应用、时间线恢复、进度计算、结算回执与流式连接，清理已确认的重复和未使用代码；不按发现位置分别堆叠补丁。
- 保留正常业务能力与旧档兼容；缺陷修复、展示改善、生成策略变化和玩法新增分别验收。性能收益使用相同输入测量，不以拆文件或减少行数代替。
- 下一阶段优先使用真实存档、trace、judge 和可复现 UI 状态决定投入方向，不凭感觉继续增加 prompt 或校验层。
- 驾驶舱维持轻量：只放当前判断；完整过程写入 `docs/history/`，有效审查问题写入 `docs/REVIEW_FINDINGS.md`。

### 不可突破的边界

- 不恢复已删除的玩家可见数值机制，除非用户明确重新决策产品方向。
- 不大改 `story_settings.py` 的规范化结构；新增字段必须兼容旧存档、导入剧本和 `rpgforge.story.v2`。
- 原有数据库、头像、音频及其他项目持久数据默认保护；本轮仅按用户明确授权删除旧 TaleForge 独占部署目录与存档。当前 RPGForge 的新持久卷继续保护。
- 不在可提交文件中写真实服务器、路径、域名、SSH 别名、密钥、cookie 或 token。
- 不把 AI 输出质量判断等同于单元测试通过；prompt/模型行为变更必须同时设计 trace、真实回合或 judge 证据。
- 不顺手处理本轮范围外的问题；发现后只记录或提醒。

## 2. 当前执行队列

本轮已获授权的范围为 A1–A4、B1–B3、C1–C5；具体实现、测量方法和兼容边界见 [`history/OPTIMIZATION_LOG_2026-11.md`](history/OPTIMIZATION_LOG_2026-11.md)。用户随后明确授权 Round 62 的替换部署、旧 TaleForge 专属代码/数据删除和 GitHub 发布；这不授权模型费用或清理其他项目。

| 状态 | 事项 | 当前边界 |
|---|---|---|
| Done | Round 62 替换部署 | 新栈接管原入口，5 项服务运行，迁移 0032，实际代理/队列/状态与 312 项远端回归通过；其他服务和反代配置未改。 |
| Done | Round 61 A/B 合并重构 | 本地验收完成；500 回合续玩准备 373→122ms、SQL 1009→5，读档 305→160ms、SQL 1013→19；新快照约增大 4%，保存略慢。未保留永久双实现。 |
| Deferred | B4：承诺、期限、离屏推进 | 用户明确延后；新增玩法需要另定创建、到期、后果、可见性与回退语义。 |
| Ready | 配置模型与真实多回合复验 | 新实例模型 API Key 尚未填写，设置保存需要私有管理令牌。有效配置后再确认连续性、实际代价、替代路线与文风；模型费用需要独立授权。 |
| Candidate | 生成页手动新增数组项、同名条目精确编辑 | 原有工坊/看板候选，不属于本轮。 |
| Candidate | API 文档与 router 对照 | 先只读核对，不以本轮优化扩大为全项目文档审查。 |
| Conditional | Agent 抽象、Prompt 版本管理、动态模型路由 | 有新增 Agent 或可靠测量证明收益时再设计。 |

### 2.1 A/B/C 完成映射

| 编号 | 实现职责 | 兼容和验收重点 |
|---|---|---|
| A1 | `timeline.py`、进度存档/回退/摘要维护 | 独立初始种子、快照 v2、重试计数、清除未来摘要；尾声只属于当前时间线；保留旧快照读取。 |
| A2 | `jobStream.ts` + 回合/生成器适配 | 前台恢复、online、心跳 watchdog、轮询降级；generation/revision/seq 拒绝旧流，较短新生成可替换。 |
| A3 | 短事务时间线锁、请求 ID/hash、revision | 同请求返回原任务/正文，异输入冲突；旧后台结果无效；正文与任务结果原子提交，模型期间不持锁。 |
| A4 | `context_continuity.py`、PromptBuilder | 近期正文保持原 1800 字符预算，保留首尾；既有连续观测形成事实反馈，不增加模型调用。硬约束不因窗口丢失。 |
| B1 | `ProgressRules` | 必需要求、替代路线、转幕与 pacing 共用规则；只裁可选项，不裁必需项；可选进展不清除主线停滞。保持组内 OR/组间 AND 及原自动转幕时机。 |
| B2 | StateV2、`NarrativeState`、手账/状态页 | 常驻文字摘要、持久物品/证物、最新关系；旧物品别名/小数/单位兼容，隐藏内容不进入玩家展示。 |
| B3 | `settlement_receipts.py`、Turn 回执 | 比较实际应用前后状态；区分 pending/confirmed/failed/rejected/skipped，旧空回执标未核验；失败上限续玩出口保留。 |
| B4 | 未实施 | 不作为本轮完成条件。 |
| C1 | 历史批量读取、请求内规则复用、顺序尾部结算 | 消除 N+1 delta 查询；无变化不写回；历史插入仍完整重放，后续提取读取正确中间状态。 |
| C2/C4 | 公共连接生命周期、共享任务监视 | 提交与恢复复用监视，保持各自输入/错误反馈；离页取消监听，网络不确定重试保留请求 ID 和原 revision。 |
| C3 | 删除未引用 blueprint/contract 链 | 保留实际使用的 settlement/chapter view 和旧档读取；不按旧名称误删仍承接文字状态的服务。 |
| C5 | StoryMarkdown memo/useMemo、角色列表缓存 | 固定输入不重复解析/构造匹配器；有半截 Markdown、别名、点击测试；未引入全局缓存。 |

### 2.2 当前共同职责与保留决策

- 状态应用统一复用 `ProgressRules`；完整重建继续作为回退、历史编辑与正确性基准。
- 时间线操作统一短事务校验；快照独立保存 replay seed，旧种子中的结局污染仅在种子兼容路径清理。
- GM/完整存档保留权威信息；玩家投影与变化回执按玩家可见性过滤。变化回执比较完整集合，避免 UI 预算导致假丢失。
- 回执服务落账与展示，没有改成不可变事件源；中途改设定后仍沿既有规则重放。读档保留当前剧本配置的原合同不变。
- 沿用 FastAPI、SQLAlchemy/PostgreSQL、Redis/RQ、Next.js；未引入管理器大类、重型框架或永久双路径。
- B1 的“达标后等待自然转场”、B4 新玩法、真实模型质量与生产延迟优化均不混入保功能重构结论。

### 2.3 验收与发布边界

- 确定性回归覆盖旧档、失败降级、替代路线、17+ 锚点、历史重建、回退/重开、幂等与旧后台晚写。
- 临时数据库实际演练 `0030 → 0031 → 0032`、旧档加载/再保存、`0032 → 0030 → 0032`；降级保留旧业务行，但会移除新增元数据，不能代替备份。
- 内置浏览器使用真实 FastAPI/数据库结算链路，模型/队列/SSE 为本地模拟；检查 320/360/375/390/430px、刷新不重复、旧空回执、0.5 单位物品和通关。没有真实 Safari 引擎或断电证据。
- 性能必须注明测量边界：固定 fixture CPU、实际 SQL/保存加载与渲染纯计算，均不代表真实模型首字、全回合延迟或浏览器 FPS。
- 新增可靠性/兼容代码与删除冗余分别统计；不以总行数或文件拆分冒充性能收益。
- Round 61 仅做本地重构；Round 62 已获明确替换部署/删除旧 TaleForge 数据/提交推送授权并完成上线验收。没有删除其他项目的数据；实际部署信息留在私有记录。

## 3. 下一轮实施方案模板

每个候选项按以下顺序闭环：

1. **只读基线**：确认真实页面/接口/数据库/日志或 trace，写出可复现条件；检查工作树和相关历史问题。
2. **方案确认**：列需求理解、涉及文件、实现步骤、数据/部署风险和验证矩阵；等待用户确认。
3. **最小修改**：只改目标文件，不做无关格式化或架构升级；兼容旧数据和现有调用方。
4. **本地验证**：先目标测试，再 lint/类型检查/构建或后端全量测试；模型调用默认不自动消耗额度。
5. **远端闭环**：仅同步必要文件，不使用删除式同步；只重建受影响服务，随后检查状态、健康接口、日志和真实页面/API。
6. **记录与发布**：有效问题更新审查台账；详细过程进当月 history；驾驶舱只留摘要；脱敏检查通过后再提交和推送。

## 4. 当前运行链路速查

### 4.1 服务与数据流

```text
Browser
  → Next.js web（页面、API 代理、SSE + polling fallback）
  → FastAPI api（业务接口、持久任务记录）
  → Redis/RQ → worker（生成、回合、维护任务）
  → PostgreSQL + pgvector（游戏、回合、状态、记忆、trace、配置）
```

### 4.2 玩家回合

```text
prepare_context → retrieve_memory → story_director
→ gm_runtime → persist_turn → completed
```

- `TURN_JOB_STAGE_TOTAL = 6`，来源是 `api/app/services/turn_jobs.py::TURN_JOB_STAGES`。
- Stage id 的单一来源是 `api/app/services/gameplay.py::STAGE_*`；改阶段时必须同步后端默认值、schema、migration（如需要）和前端进度显示。
- 单回合总超时当前为 18 分钟；GM 单次调用另有独立超时和重写兜底。

### 4.3 异步维护

```text
state_extract
  → drift audit（每 3 回合稀疏采样，只观测）
  → apply/rebuild canonical state
  → campaign completion / epilogue
  → memory summary（每 4 回合）
```

- 状态提取失败会记录失败 delta，并在下次继续前重试；不能假装维护成功。
- 偏离审计不在玩家同步路径阻断正文；精确禁止揭露仍由同步整串护栏负责。
- Maintenance 总超时当前为 10 分钟。

## 5. 业务规则与已定决策

| 决策 | 当前约束 |
|---|---|
| 纯叙事产品方向 | 状态继续结构化，但玩家侧不展示等级、XP、属性、技能熟练度、骰点、危机条等数值系统。 |
| 状态是权威连续性 | 不为了省 token 随意砍 `state_v2`；应优先做稳定前缀、场景投影和相关性注入。 |
| 约束先传递再观测 | 强约束进入高优先级 prompt；Drift/Judge 是审计和度量层，不作为修复传递失败的主手段。 |
| 禁止未来幕滑窗黑名单 | 不用短子串做语义剧透判断；代码同步兜底只认剧本人工精确配置的整串禁止揭露。 |
| 剧本优先于全局篇幅上限 | 段落、强调和字数上限在与剧本详细描写要求冲突时让位；下限可用于防止偷工减料。 |
| 数据驱动 AI 调优 | material 过滤、director hints、drift 阈值等必须先看 trace/真实样本/judge，不凭感觉改。 |
| 不统一每个 Agent 的重试 | 各 Agent fallback 语义不同；只有 trace 证明重试有收益时才增加。 |
| Agent 抽象暂缓 | 当前差异化 fallback 更清晰；新增第 6 个 Agent或具备可靠核心回归环境时再评估。 |
| 不引入重型框架 | 不引入 LangChain/LlamaIndex、Kubernetes、微服务或 event sourcing；当前 Compose + Pydantic 服务结构足够。 |
| 设定规范化保持稳定 | 不大规模重写 `story_settings.py`；优先小型适配、字段级测试和向后兼容。 |
| 持久数据优先 | 部署默认保留 `.env`、数据库和上传/音频数据；禁止删除 volume 或删除式同步。 |
| 公开仓库脱敏 | 真实部署信息只放 gitignore 的本机私有文件；公开文档和脚本只用通用占位。 |

## 6. 关键文件

### 后端

| 关注点 | 文件 / 入口 |
|---|---|
| HTTP 回合入口、状态查询、回退 | `api/app/routers/gameplay.py` |
| TurnJob 队列编排、进度与持久化 | `api/app/services/turn_jobs.py` |
| 主回合上下文与 GM 生成 | `api/app/services/gameplay.py` |
| 异步状态/审计/记忆维护 | `api/app/services/turn_maintenance_jobs.py` |
| Director | `api/app/services/story_director.py` |
| Prompt 拼装 | `api/app/services/prompt_builder.py`、`api/app/prompts/` |
| 状态提取、应用、重建 | `state_extractor.py`、`state_applier.py`、`state_rebuilder.py`、`progress_rules.py` |
| 时间线与实际回执 | `timeline.py`、`turn_job_access.py`、`settlement_receipts.py` |
| Story settings 与 runtime 投影 | `api/app/services/story_settings.py` |
| 幕节奏与替代锚点 | `api/app/services/act_pacing.py`、`state_applier.py` |
| 长期记忆 | `api/app/services/context_compressor.py` |
| Trace / Judge | `api/app/services/agent_traces.py`、`turn_judge.py`、`api/app/routers/admin.py` |

### 前端

| 关注点 | 文件 / 入口 |
|---|---|
| 全局设计系统、响应式规则 | `web/app/globals.css` |
| 核心游玩页 | `web/app/games/[id]/play/page.tsx` |
| 回合 SSE / polling fallback | `web/lib/jobStream.ts`、`turnJobStream.ts`、`generatorJobStream.ts` |
| 文字状态、物品与请求恢复 | `web/components/NarrativeState.tsx`、`web/lib/turnRequest.ts` |
| 记忆与帮助气泡 | `web/app/games/[id]/memory/page.tsx` |
| 游戏创建 | `web/app/games/new/page.tsx` |
| 设定看板逻辑 | `web/lib/generatorBoard.ts`、`web/components/board/` |
| 设定页与版本恢复 | `web/app/games/[id]/settings/page.tsx` |
| 工坊 | `web/app/workshop/page.tsx`、`web/components/workshop/` |
| API client / 类型 | `web/lib/api.ts`、`web/lib/types.ts` |

### 文档

| 用途 | 文档 |
|---|---|
| 当前驾驶舱 | 本文件 |
| 有效审查问题 | [`REVIEW_FINDINGS.md`](REVIEW_FINDINGS.md) |
| 架构与 AI runtime | [`ARCHITECTURE.md`](ARCHITECTURE.md)、[`AI_STORY_RUNTIME_GUIDE.md`](AI_STORY_RUNTIME_GUIDE.md) |
| Prompt/context 历史设计 | [`PROMPT_ARCHITECTURE_REDESIGN.md`](PROMPT_ARCHITECTURE_REDESIGN.md) |
| 产品与系统专项审查 | [`GAME_DIRECTION_AUDIT.md`](GAME_DIRECTION_AUDIT.md)、[`GAME_SYSTEM_AUDIT.md`](GAME_SYSTEM_AUDIT.md) |
| 具体功能设计 | [`superpowers/specs/`](superpowers/specs/)、[`superpowers/plans/`](superpowers/plans/) |

## 7. 验证清单

### 7.1 所有改动

- [x] Round 61：`git status --short` / `git diff --stat` 确认范围，用户已有改动完整保留。
- [x] Round 61：`git diff --check` 无空白错误、冲突标记或意外大范围格式化。
- [x] Round 61：项目已跟踪文件脱敏检查和本轮新增文件扫描通过；没有凭据或本机项目绝对路径进入新记录。
- [x] Round 61：有测试、状态等价摘要和性能前后对照；真实模型/生产/真实设备边界见当月日志。

### 7.2 后端改动

```bash
cd api
python3 -m ruff check .
python3 -m pytest
```

- 涉及数据库时在隔离 PostgreSQL 测试环境运行测试，并检查 Alembic head、schema/default 和旧数据读取。
- 涉及 AI 行为时另看完整 trace、fallback、timeout、结构校验和真实回合；Judge/replay 会消耗额度的操作必须单独确认。
- 涉及 stage 时验证后端常量、ORM/schema 默认、SSE snapshot 和前端进度总数一致，当前基线为 6。

### 7.3 前端改动

```bash
cd web
npm run lint
npx tsc --noEmit
npm test
npm run build
```

- 移动端至少覆盖 320/360/375/390/430px；检查文档宽度、`.game-screen`、模态框、抽屉、命令行、帮助气泡和局部滚动容器。
- 对真实存档和动态状态做几何检查、截图与控制台检查；不能只测空页面或首屏。
- 交互变化验证键盘、触屏、focus-visible、reduced-motion 和 iOS 输入框不自动缩放。

### 7.4 部署与实机

- [x] Round 62：源文件逐项哈希核验，未覆盖其他项目私有配置或数据；旧 TaleForge 独占目录按明确授权删除。
- [x] Round 62：独立新栈、全新持久卷；切换仅重建 web，其他 10 个容器保持原 ID 与状态。
- [x] Round 62：5 项服务运行、0032、API/代理/SSE/RQ 与定向实际状态读写通过；真实模型待配置。
- [x] Round 62：上传源清单与运行 API 源码摘要一致；文档更新不触发镜像重建。
- [x] Round 62：更新当月 history、驾驶舱及私有部署记录；随本轮重构提交发布。

## 8. 遗留疑点与风险

| 项目 | 当前判断 / 下一步证据 |
|---|---|
| Round 57 非数值代价闭环 | Prompt 与目标测试已通过，但长期稳定性仍依赖真实模型遵守；需要多回合检查 delta 落库及后续承接。 |
| `alternative_group` 实际使用 | 运行时代码和目标测试已覆盖；仍需检查新剧本生成是否会合理配置、看板表达是否清晰、玩家路线是否自然推进。 |
| WebKit 移动端验收 | Round 59 使用现有 Chrome 的 iPhone 模拟；本机未安装 Playwright WebKit 组件，尚无 Safari 引擎自动化证据。 |
| 生成页数组新增 | 设定页已接入、生成页未接入，属于已定位的小功能缺口；是否做由用户决定。 |
| 同名设定条目 | 部分编辑路径按 name 找首项，重复名称的精确定位仍需专门 fixture 和兼容方案。 |
| API 文档漂移 | `docs/API.md` 可能未覆盖所有历史 router 增量，尚未做当前版本逐路由核对。 |
| 本轮已确认缺陷 | 已按共同职责实现并覆盖隔离数据库与前端回归；本地模拟链路不等于生产网络、真实设备或断电验收。详见审查台账与当月日志。 |
| 本轮代码精简与性能 | 已移除未使用派生链与重复连接逻辑，提供固定输入的 CPU/SQL/渲染对照；新增可靠性与展示功能使生产代码总量增加，不能宣称全仓净缩减。真实模型耗时未测量。 |
| 生成策略与新增玩法 | A4 保持字符预算并保留正文尾部，连续观测反馈会影响模型提示，尚无真实质量结论；B4 与自然转场明确延后。 |

## 9. 最近完成摘要

只保留最近 5 条；详细内容进入 history。

1. **Round 62（2026-11-07）— 替换部署与发布**：按用户要求删除旧 TaleForge 专属资源，当前项目接管原入口；远端 312 项及真实代理/SSE/状态/RQ 通过，其他服务与反代配置不变。模型 Key 待填写。详见 [`history/OPTIMIZATION_LOG_2026-11.md`](history/OPTIMIZATION_LOG_2026-11.md)，私有地址和命令不进入 Git。
2. **Round 61（2026-11-07）— A/B 合并重构**：统一进度规则、实际回执、时间线恢复/幂等与连接生命周期，删除重复派生链并缓存 Markdown 计算；保留旧档，B4 延后。312 后端/92 前端回归及本地模拟通关通过，性能与兼容成本见 [`history/OPTIMIZATION_LOG_2026-11.md`](history/OPTIMIZATION_LOG_2026-11.md)。未部署。
3. **Round 60（2026-07-21）— 驾驶舱归档与接手信息重整**：完整保留旧驾驶舱，主文档从 1500+ 行历史堆栈重构为当前目标、队列、规则、关键文件和验证清单；修正旧文档中与代码不一致的阶段总数与超时信息。详见 [`history/OPTIMIZATION_LOG_2026-07.md`](history/OPTIMIZATION_LOG_2026-07.md)。
4. **Round 59（2026-07-21）— 移动端右侧溢出修复**：为 `.game-screen` 显式建立可收缩 Grid 列；移动端帮助气泡改为视口安全定位；远端真实存档多宽度验收通过。详见 [`history/OPTIMIZATION_LOG_2026-07.md`](history/OPTIMIZATION_LOG_2026-07.md) 和 [`REVIEW_FINDINGS.md`](REVIEW_FINDINGS.md)。
5. **Round 58（2026-07-18）— 像素磷光绿终端 UI 重做**：重组信息架构、核心游玩页和全局设计系统，并完成移动端补充复查。详见当月 history 与完整归档。

## 10. 历史归档索引

| 范围 | 位置 | 说明 |
|---|---|---|
| Round 1–59 完整旧驾驶舱 | [`history/OPTIMIZATION_PLAN_ARCHIVE_THROUGH_ROUND_59.md`](history/OPTIMIZATION_PLAN_ARCHIVE_THROUGH_ROUND_59.md) | 冻结历史快照，含旧 Round 全文、路线图、查询样例、常量和验证清单；部分信息已过时，不作为当前实现依据。 |
| 2026-11 月度日志 | [`history/OPTIMIZATION_LOG_2026-11.md`](history/OPTIMIZATION_LOG_2026-11.md) | Round 61 的合并重构、兼容/迁移、性能方法和本地验收。 |
| 2026-07 月度日志 | [`history/OPTIMIZATION_LOG_2026-07.md`](history/OPTIMIZATION_LOG_2026-07.md) | Round 55–60 的背景、改动、验证、部署与边界。 |
| 审查台账 | [`REVIEW_FINDINGS.md`](REVIEW_FINDINGS.md) | 有效问题及 `Open` / `Done` / `Ignored` 状态。 |
| 产品/系统审查 | [`GAME_DIRECTION_AUDIT.md`](GAME_DIRECTION_AUDIT.md)、[`GAME_SYSTEM_AUDIT.md`](GAME_SYSTEM_AUDIT.md) | 历史专项判断；遇到纯叙事化后的冲突时，以本驾驶舱、Round 53+ 和代码为准。 |
| Prompt/context 重构 | [`PROMPT_ARCHITECTURE_REDESIGN.md`](PROMPT_ARCHITECTURE_REDESIGN.md) | Round 16–24 的设计、度量与已明确不做项。 |

## 11. 文档维护规则

- 本文件只写当前状态、下一步、规则、关键文件、验证和最近 3–5 条完成摘要，不再追加完整 Round 正文。
- 每轮详细背景、变更、部署、失败尝试、回滚与验证写入 `docs/history/OPTIMIZATION_LOG_YYYY-MM.md`。
- 审查发现只进入 `docs/REVIEW_FINDINGS.md`；已修复仍保留并标为 `Done`，明确不修标为 `Ignored`。
- 用户提出新方向时更新 §2；形成长期决策时更新 §5；证据改变判断时更新 §8。
- 关键常量不在文档里硬编码行号；值变更时同步 §4 和验证清单。
- 主驾驶舱超过约 1000 行、完成摘要超过 5 条或历史再次淹没当前队列时，先归档再继续。
