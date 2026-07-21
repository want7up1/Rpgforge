# RPGForge AI 开发驾驶舱

> 最后更新：2026-07-21（Round 60，文档整理）。本文件只保留当前目标、执行边界、下一步队列和最近完成摘要；Round 1–59 的完整旧驾驶舱已归档到 [`history/OPTIMIZATION_PLAN_ARCHIVE_THROUGH_ROUND_59.md`](history/OPTIMIZATION_PLAN_ARCHIVE_THROUGH_ROUND_59.md)。文档与代码冲突时以代码为准。

## 0. AI 接手摘要

| 项目 | 当前状态 |
|---|---|
| 产品方向 | 自托管、纯叙事向 AI 文字 RPG；状态以 conditions、relationships、quests、open threads、known facts、幕进度等文字结构延续，不恢复玩家可见的等级、属性、技能、骰点或危机数值。 |
| 运行形态 | Docker Compose：Next.js `web` → FastAPI `api` → Redis/RQ `worker`，PostgreSQL + pgvector 持久化；公开入口只应指向 Web。 |
| 主回合 | 玩家行动 → 6 阶段 TurnJob → StoryDirector → GM 流式正文 → 持久化回合 → 异步状态提取/应用、偏离审计、结局判断和周期性记忆维护。 |
| 前端 | Round 58 已重做为像素磷光绿终端风；Round 59 已修复 320px 窄屏右侧溢出和记忆页帮助气泡越界，远端实页已验收。 |
| 当前任务 | **没有进行中的业务代码任务。** 下一轮必须先由用户从 §2 选择范围，再修改代码或运行环境。 |
| 审查台账 | [`REVIEW_FINDINGS.md`](REVIEW_FINDINGS.md) 当前记录均为 `Done`，没有已登记的 `Open` 项。 |
| 最近验证 | Round 59：前端 lint、TypeScript、52 项 vitest、生产构建通过；远端服务、健康接口、真实存档响应式与浏览器控制台通过。后端未来有改动时仍须重新跑当前测试，不沿用旧轮次数。 |

接手顺序：

1. 读本文件 §0–§8，确认目标、边界和验证方式。
2. 有代码审查或修复任务时读 [`REVIEW_FINDINGS.md`](REVIEW_FINDINGS.md)，避免重复问题。
3. 改 AI 运行链路前读 [`AI_STORY_RUNTIME_GUIDE.md`](AI_STORY_RUNTIME_GUIDE.md) 和实际代码；改前端看板/工坊前读对应 [`superpowers/specs/`](superpowers/specs/) 设计稿。
4. 先看 `git status` / `git diff`，保留用户已有改动；部署前确认代码、私有配置和持久数据边界。

## 1. 当前目标与边界

### 当前目标

- 保持已上线的纯叙事运行链路、长局状态一致性和移动端 UI 稳定。
- 下一阶段优先使用真实存档、trace、judge 和可复现 UI 状态决定投入方向，不凭感觉继续增加 prompt 或校验层。
- 驾驶舱维持轻量：只放当前判断；完整过程写入 `docs/history/`，有效审查问题写入 `docs/REVIEW_FINDINGS.md`。

### 不可突破的边界

- 不恢复已删除的玩家可见数值机制，除非用户明确重新决策产品方向。
- 不大改 `story_settings.py` 的规范化结构；新增字段必须兼容旧存档、导入剧本和 `rpgforge.story.v2`。
- 不以删除、重建或覆盖方式处理数据库、上传头像、音频、私有配置和其他持久数据。
- 不在可提交文件中写真实服务器、路径、域名、SSH 别名、密钥、cookie 或 token。
- 不把 AI 输出质量判断等同于单元测试通过；prompt/模型行为变更必须同时设计 trace、真实回合或 judge 证据。
- 不顺手处理本轮范围外的问题；发现后只记录或提醒。

## 2. 当前执行队列

> 这里是候选队列，不代表已授权实施。除文档维护外，进入任何代码项前先给出涉及文件、步骤和验证方式，等待确认。

| 状态 | 候选事项 | 价值与边界 |
|---|---|---|
| Now | 无进行中事项 | Round 59 已发布；Round 60 仅整理文档。 |
| Ready | Round 57 真实游玩复验 | 用真实模型回合确认“失败/代价 → 非数值状态”能稳定落库并在后续承接，同时观察 `alternative_group` 是否生成、展示和推进合理。只在用户同意消耗模型额度后执行。 |
| Ready | 生成页补“手动新增数组项” | 设定页已经把 `onAddItem` 接入 `SettingsBoard`，生成页尚未接入；可复用既有 `appendItem`，范围较小。 |
| Candidate | 看板 objectList 拖拽排序 | 需要定义地址/索引稳定性，不能破坏 `block.id`、`address`、diff、锁定字段和模块提取。 |
| Candidate | 工坊批量提取、单块 AI 重生成、模块版本史 | 拆成独立小项，不一次扩成大型工坊重构；AI 调用必须有 timeout、结构护栏和原 payload fallback。 |
| Candidate | 同名条目按索引精确编辑 | 当前部分路径按 name 取首项；需先覆盖重复名称 fixture，再调整定位规则并验证旧地址兼容。 |
| Candidate | API 文档与 router 对照 | `docs/API.md` 历史上可能滞后；先只读生成差异清单，再决定是否更新。 |
| Conditional | Maintenance 状态机、SSE/DB 写入收敛 | 只有真实性能/维护成本证据支持时再做；属于核心链路重构，需单独方案和回归环境。 |
| Conditional | Agent 基类、Prompt 版本管理、动态模型路由 | 新增第 6 个 Agent、需要正式 A/B 或 telemetry 显示明确收益时再启动。 |

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
| 状态提取、应用、重建 | `state_extractor.py`、`state_applier.py`、`state_rebuilder.py` |
| Story settings 与 runtime 投影 | `api/app/services/story_settings.py` |
| 幕节奏与替代锚点 | `api/app/services/act_pacing.py`、`state_applier.py` |
| 长期记忆 | `api/app/services/context_compressor.py` |
| Trace / Judge | `api/app/services/agent_traces.py`、`turn_judge.py`、`api/app/routers/admin.py` |

### 前端

| 关注点 | 文件 / 入口 |
|---|---|
| 全局设计系统、响应式规则 | `web/app/globals.css` |
| 核心游玩页 | `web/app/games/[id]/play/page.tsx` |
| 回合 SSE / polling fallback | `web/lib/turnJobStream.ts` |
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

- [ ] `git status --short` / `git diff --stat` 确认范围，用户已有改动完整保留。
- [ ] `git diff --check` 无空白错误、冲突标记或意外大范围格式化。
- [ ] 公开内容通过项目脱敏检查，不含真实部署信息或密钥。
- [ ] 目标问题有可复现前后对照；无法验证的部分明确写出原因。

### 7.2 后端改动

```bash
cd api
python3 -m ruff check .
python3 -m pytest
```

- 涉及数据库时在可连接 PostgreSQL 的容器环境运行测试，并检查 Alembic head、schema/default 和旧数据读取。
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

- [ ] 仅同步本轮目标文件，不使用 `--delete`，不覆盖私有配置或持久数据。
- [ ] 只重建受影响服务；Docker/数据库/Redis 变更另行评估数据风险。
- [ ] 检查 compose 服务状态、API health、关键日志、Web 路由和真实业务读写。
- [ ] 需要时核对本地/远端目标文件哈希；文档-only 改动不触发镜像重建。
- [ ] 验证完成后更新当月 history、驾驶舱摘要和审查台账，再提交/推送。

## 8. 遗留疑点与风险

| 项目 | 当前判断 / 下一步证据 |
|---|---|
| Round 57 非数值代价闭环 | Prompt 与目标测试已通过，但长期稳定性仍依赖真实模型遵守；需要多回合检查 delta 落库及后续承接。 |
| `alternative_group` 实际使用 | 运行时代码和目标测试已覆盖；仍需检查新剧本生成是否会合理配置、看板表达是否清晰、玩家路线是否自然推进。 |
| WebKit 移动端验收 | Round 59 使用现有 Chrome 的 iPhone 模拟；本机未安装 Playwright WebKit 组件，尚无 Safari 引擎自动化证据。 |
| 生成页数组新增 | 设定页已接入、生成页未接入，属于已定位的小功能缺口；是否做由用户决定。 |
| 同名设定条目 | 部分编辑路径按 name 找首项，重复名称的精确定位仍需专门 fixture 和兼容方案。 |
| API 文档漂移 | `docs/API.md` 可能未覆盖所有历史 router 增量，尚未做当前版本逐路由核对。 |
| 架构候选的 ROI | Maintenance 状态机、SSE/DB 写入收敛、Agent 抽象均没有新的性能或维护证据，保持候选而不主动重构。 |

## 9. 最近完成摘要

只保留最近 5 条；详细内容进入 history。

1. **Round 60（2026-07-21）— 驾驶舱归档与接手信息重整**：完整保留旧驾驶舱，主文档从 1500+ 行历史堆栈重构为当前目标、队列、规则、关键文件和验证清单；修正旧文档中与代码不一致的阶段总数与超时信息。详见 [`history/OPTIMIZATION_LOG_2026-07.md`](history/OPTIMIZATION_LOG_2026-07.md)。
2. **Round 59（2026-07-21）— 移动端右侧溢出修复**：为 `.game-screen` 显式建立可收缩 Grid 列；移动端帮助气泡改为视口安全定位；远端真实存档多宽度验收通过。详见 [`history/OPTIMIZATION_LOG_2026-07.md`](history/OPTIMIZATION_LOG_2026-07.md) 和 [`REVIEW_FINDINGS.md`](REVIEW_FINDINGS.md)。
3. **Round 58（2026-07-18）— 像素磷光绿终端 UI 重做**：重组信息架构、核心游玩页和全局设计系统，并完成移动端补充复查。详见当月 history 与完整归档。
4. **Round 57（2026-07-06）— 非数值代价闭环 + 替代锚点组**：强化失败后果的状态承接，支持同组 required 锚点任一完成即可推进。详见当月 history 和 [`REVIEW_FINDINGS.md`](REVIEW_FINDINGS.md)。
5. **Round 56（2026-07-03）— 纯叙事契约部署验证**：保数据部署 Round 55，完成 migration、服务健康、关键 API 与目标测试验证。详见当月 history与完整归档。

## 10. 历史归档索引

| 范围 | 位置 | 说明 |
|---|---|---|
| Round 1–59 完整旧驾驶舱 | [`history/OPTIMIZATION_PLAN_ARCHIVE_THROUGH_ROUND_59.md`](history/OPTIMIZATION_PLAN_ARCHIVE_THROUGH_ROUND_59.md) | 冻结历史快照，含旧 Round 全文、路线图、查询样例、常量和验证清单；部分信息已过时，不作为当前实现依据。 |
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
