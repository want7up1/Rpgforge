# Optimization Log 2026-11

## 2026-11-07 — Round 63：创作包同步与模型自动探测

### 授权与实现

用户明确要求更新创作包、取消管理 TOKEN、根据 Base URL 和 Key 能列出的模型自动识别槽位，完成后提交推送并部署。

- 更新导出器和填写指南，生成根目录 `RPGForge-剧本创作包.md`。补全 A AND (B OR C) 加可选项范例、公开幕标题/目标的秘密边界、结算后自动转幕、condition 非独立程序门、generation_parameters 和外部设定不接 initial_state/回执的边界。维持 `rpgforge.story.v2`，不扩展导入 schema。
- 设置页和遥测管理台共用的 TOKEN 输入、请求头、后端依赖、配置项及生产空 TOKEN 拦截全部移除。旧 `settings_protected` 响应字段保留为 false；旧客户端多传请求头不影响接口。
- 新增 `POST /api/settings/deepseek/models`，只读取服务的模型列表，不保存配置、不执行聊天生成。接受草稿 Base URL/Key，未输入 Key 可复用当前同源服务的有效 Key；切换源必须重新输入 Key，保存端也执行该边界。
- URL 校验、禁止跟随重定向、12 秒网络超时、2 MiB 响应上限；只返回可保存的模型 ID，去重并排除明确非聊天类型。错误不回传 Key、上游错误正文或请求 URL。
- 槽位从实际返回 ID 推荐，保留有效已选项，单模型可用两槽。设置页 600ms 防抖自动探测，提供重试/取消；输入变化、离页与请求版本隔离迟到结果。失败不覆盖已保存配置，新服务不能用旧列表保存。
- 保留任务级快速/高质量分配、清空已存 Key、旧配置只改职责的路径；API Key 不写浏览器持久存储，旧 Token localStorage 仅清除。

### 验证

- 候选 Docker 镜像在独立测试数据库全量 **355 passed，2 warnings**；测试库已删除，正式数据库未用于 pytest schema 重建。
- 前端全量 **102 passed**；ruff、ESLint、TypeScript、本地生产构建及 Linux Docker 生产构建通过。
- 创作范例从实际 Markdown 提取 JSON 再导入；两条 OR 路线、optional 不阻塞、condition 非额外门槛、内部状态不注入均通过。
- 模型探测覆盖有效/无权限/不存在/重定向/超时/畸形/空/过大响应，ID 128 字符上限、已选保留、单模型双槽、保存 Key 跨源拒绝与生产无 Token。
- 内置浏览器使用独立预览数据库、API/Web 和仅提供模型列表的模拟服务：输入后自动出现两模型并推荐双槽；无需 Token 保存；刷新后保留已选，双槽可用同一模型；上游错误有安全中文提示，修改服务失效旧列表；慢响应不会覆盖新结果；清空 Key 可保存。
- 320/430px 设置页无文档或 body 横向溢出。预览只使用测试 Key，正式模型配置与存档没有被验收数据覆盖，没有真实聊天调用。

### 发布边界

功能提交 `0260806` 已推送并部署；只更新现有 API/worker/web，原监听地址与端口、PostgreSQL、Redis 和持久卷保留。私有环境与本地旧管理 Token 文件已清除，发布前保留一份私有数据库备份供必要恢复。

线上核验：五项服务运行；迁移仍为 `20261107_0032`；worker 注册正常；无需 Token 的设置 PATCH 与管理台读取成功；设置有效值保持；未填写 Key 的探测返回安全 400；下载创作包与根目录文件哈希一致。内置浏览器确认线上无 Token 输入、两个模型选择控件及 430px 无横向溢出，截图保留在本地验收产物中。

预览容器、专用网络、独立数据库、模拟供应商、临时端口/SSH 转发和脚本全部清理。真实 Key 未提供，不把模拟服务验收写成真实供应商或聊天能力验收。

## 2026-11-07 — Round 62：替换旧 TaleForge 部署并发布

### 授权与范围

用户明确要求：卸载目标 Docker 服务器上的 TaleForge，当前 RPGForge 沿用旧入口的宿主地址和端口部署，然后提交并推送到 GitHub；随后明确旧 TaleForge 的代码和存档数据均不保留。清理仅限已确认独占的旧容器、命名镜像、网络和部署目录，不清理其他项目或全局 Docker 缓存。

真实 SSH 信息、目录、端口与操作命令保存在 Git 忽略的私有 `DEPLOY.local.md` 及服务器私有配置，公开记录不包含这些值。

### 发布过程与结果

- 按工作树实际文件制作源包，上传后逐文件核验 SHA256；没有上传本地依赖、构建产物、凭据或 Git 私有元数据。
- 在独立 Compose project 构建 API/worker 和 Web 镜像，使用新的 PostgreSQL、Redis、音频和头像存储；没有复用旧 TaleForge 数据。
- 私有生产配置只发布 web:3000 对应的原宿主入口，数据库、Redis 与 API 均不发布宿主端口；生成随机数据库密码与设置管理令牌，私有文件权限 0600。
- 先保留旧服务运行，在临时本机端口验收新栈；确认通过后停止旧服务、仅重建 web 切到原入口，再删除旧专属资源。没有为旧应用额外创建备份。
- API 启动执行所有 Alembic 迁移，最终为 `20261107_0032`；API/worker 使用同一运行镜像，Web 由服务器按现有锁文件重新构建。
- 已核验只有 web 发布了原宿主地址/端口，临时端口已移除；原反向代理文件摘要未变，其他 10 个容器的 ID 与运行状态未变。

### 验证

- 远端实际镜像中，在独立一次性测试数据库运行后端全量：**312 passed，2 warnings**。测试库已删除，未对正式 schema 运行 pytest 的重建逻辑。
- 首次测试与 Compose 补齐 web 依赖发生重叠，数据库依赖容器重建造成两项临时连接错误；改为依赖稳定后测试、切换时仅更新 web，重新完整运行后全部通过。
- Linux Docker Web 生产构建及 TypeScript 通过；沿用本轮本地 92 项前端回归、lint、类型检查与构建证据。
- 真实 Next 同源代理、API、PostgreSQL 和 Redis 通路通过；用唯一 UUID 标识的合成游戏注入一条实际 Turn/approved delta，由真实重建器生成 confirmed 回执，核验 0.5 ml 证物与事实落账。
- 实际 SSE 初始终态快照、event id、no-cache/no-transform 与禁止代理缓冲响应头通过。
- 通过 HTTP 完成保存 → 回退 → 读档 → 重开，核验回合 ID、物品、事实、回执与世代变化；验收游戏已定向删除。
- 真实 RQ worker 成功执行无模型的 `builtins.sum` 任务，结果为 6；仅该验收任务的记录已清理。
- 原入口 `/health`、`/api/games` 正常；生产环境、设置令牌保护、未带令牌保存返回 401、API 镜像源码摘要、迁移 head、音频和头像卷可写均已核验。
- 仅用 Codex 内置浏览器，经 SSH 通道读取远端真实实例，确认冒险页和设置页正常显示。没有使用用户 Chrome。

### 当前边界

新实例尚未填写模型 API Key，设置页已启用管理令牌保护。此轮没有调用真实模型，也没有真实模型生成与文风验收结论；用户可在设置页完成配置后开始游玩。

临时源码压缩包、独立测试库、合成游戏、队列验收任务和临时端口均已清理。已安装的运行栈和持久卷属于当前 RPGForge，不属于旧 TaleForge 清理范围。部署记录与本轮重构一并发布；提交 SHA 以 Git 记录为准。

## 2026-11-07 — Round 61：时间线、进度、回执与前端共同职责重构

### 范围与保留行为

用户确认将两轮评估的 A1–A4、B1–B3 与 C1–C5 合并实施，保留功能和旧档兼容，提供优化前后测量。B4（承诺、期限、离屏推进）明确延后。参考项目只用于识别职责与取舍，没有直接替换现有产品或引入外部运行依赖。

- 保持纯叙事产品、组内 OR/组间 AND、达标后既有自动转幕时机、状态失败累计上限及续玩出口。
- 读档沿用当前剧本配置的既有合同；没有改成不可变事件源，也没有改变历史设定编辑后的重放语义。
- 没有修改生产数据、部署、重启、调用真实模型、提交或推送。

### 实现

| 范围 | 共同职责与结果 |
|---|---|
| A1 | 时间线恢复统一失效旧任务；新快照 v2 包含独立初始种子、游戏状态、重试计数与回执。回退失效跨未来的 Summary 和状态摘要；结局只写 live state，兼容清理旧种子中的结局污染。摘要模型调用后重新核对 generation/config。 |
| A2/A3 | 请求 ID/hash、revision、timeline generation 贯通入口与后台；相同请求重取原结果，异输入拒绝。正文与任务关联原子提交，模型期间不持时间线锁，超时/旧任务不能复活写回。流增加 generation/revision/seq 和 SSE id。 |
| A4 | 近期正文保持原 1800 字符预算，以首尾摘要保留落点；连续开场重复观测形成事实反馈，正常后消退。没有额外模型调用或语义质量裁判。GM 规则 36 同步多条替代路线，新增规则 37 说明观测反馈；Director 规则 13 同步候选路线。 |
| B1/C1 | 新 `ProgressRules` 统一要求组、开放锚点、进度与 pacing；只限制可选投影，所有必需路线均保留；可选完成不重置主线停滞。一次结算复用规则，历史用 outer join 批量读取，顺序尾部逐条应用，历史中途插入仍重放。 |
| B2 | StateV2 纳入持续物品/证物；常驻处境摘要、手账与状态页复用文字组件。兼容字符串、`item` 别名、数字字符串、小数和单位。隐藏人物姓名/别名/ID继承可见性，GM 与完整存档仍保留内容。 |
| B3 | 回执比较真实应用前后状态，涵盖主线、处境、关系、物品、任务、线索、场景和新事实；区分 pending/confirmed/failed/rejected/skipped，空旧回执标为未核验。完整集合差异不受 UI 线索预算影响，变为隐藏不会误报失去。 |
| C2/C4 | 提取窄范围 `jobStream.ts`，保留回合与生成器业务适配；统一 watchdog、online、前台同步、清理和降级。提交与恢复共用监视，网络不确定时保留请求 ID 与原 revision，409 刷新状态和正文。 |
| C3/C5 | 删除没有调用方的 blueprint/contract 派生链，保留实际 settlement/chapter view。StoryMarkdown 缓存正文解析和角色匹配器，角色在场推导也按输入复用。 |

收尾复核另修：旧终局 writer 的根状态尾声与 v2 不同步、通关计数漏最后一幕、结束后仍出现选项、同步维护意外失败一直 pending、离页后迟到请求重开监听，以及隐藏人物的显式关系回执泄漏。新终局 writer 同步 v2；前端仍保持 v2 优先，仅兼容覆盖明确存在的旧根状态尾声。

### 功能与兼容验证

- 原始基线 `573d69a` 的 254 项后端测试在独立 PostgreSQL 16.2 + pgvector 上通过。
- 最终后端 **312 passed**（8 条原有 Pydantic/pytest 配置警告）、前端 **92 passed**；`ruff check .`、ESLint、TypeScript、Next 生产构建全部通过。模型调用均为确定性模拟。
- 用旧版 API 和 schema `20260703_0030` 创建真实旧游戏/回合/approved delta/物品/事实/存档，升级 `0031 → 0032` 后用新版加载、重建、继续保存为 v2；回合 ID、物品与已知事实保持，旧空回执可重新生成。
- 独立迁移库演练 `0032 → 0030 → 0032`，games/turns/state_deltas/存档行数保持 1/1/1/2。降级会丢弃新增列的元数据，应回退应用版本并恢复发布前备份，不能把此测试当作无损业务回滚保证。
- 已有存档确实没有初始种子时，无法恢复当时自定义的原始内容；继续使用旧版已有默认种子回退，不冒充已恢复未知历史。
- 测试包含同请求重试、异输入/旧 revision 冲突、旧 worker 及摘要/尾声晚写、重复维护、维护超时、旧快照、计数往返、回退和重开、必需锚点超过 16 项、可选进展与替代路线、真实 before/after 回执、隐藏关系/物品/线索、0.5 单位物品和终局投影。

### 浏览器验收

仅使用 Codex 内置浏览器和独立临时数据库。FastAPI、状态应用、回执与持久化为真实代码；模型、RQ 和 SSE 传输采用本地模拟，无模型费用。

- 从第 1 回合推进、转幕、刷新后继续，正文与状态无重复；实际打通两幕并显示生成尾声，终局无可点击行动选项。
- 旧空回执显示“旧记录·未核验”；手账保留旧格式物品与 `0.5 ml` 数量；隐藏 fixture 未进入玩家视图。
- 320/360/375/390/430px 下文档、body 与 game-screen 无横向溢出；430px 抽屉宽度 352px，长中文物品说明可读；状态页同样通过几何检查。最终浏览器控制台无 error。
- 截图为本地模拟验收证据，不代表真实模型质量、生产网络可靠性、实体 iPhone 或 Safari 引擎验收。

### 性能方法与结果

基线固定为 `573d69a`。同机器、同依赖、同 fixture，各版本用独立进程和独立临时数据库顺序执行；不调用模型。完整样本、SQL 分类、摘要与方法见 [`round61-benchmarks.json`](round61-benchmarks.json)，脚本位于 `api/scripts/` 与 `web/scripts/`。最终 SQL 测量期间业务源码摘要不变。

实际数据库样本为 1 幕 × 1 锚点，三次中位数，包含游戏关系加载、服务操作及 commit/rollback，排除建库、预热、JSON 统计与哈希计算：

| 回合 | 续玩准备 ms | 续玩 SQL | 读档 ms | 读档 SQL | 保存 ms | 保存 SQL |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 9.905 → 3.176 | 29 → 5 | 10.352 → 10.165 | 33 → 19 | 5.021 → 6.468 | 9 → 12 |
| 100 | 66.409 → 14.337 | 209 → 5 | 62.043 → 34.853 | 213 → 19 | 14.321 → 16.725 | 9 → 12 |
| 500 | 372.750 → 122.033 | 1009 → 5 | 304.639 → 159.768 | 1013 → 19 | 73.059 → 81.731 | 9 → 12 |

无新 delta 时，续玩准备五次 SELECT、零写入；其中四次为游戏及已有关系加载，另一次为历史查询。已有加载的服务目标回归仅需一条历史 SELECT。500 回合续玩准备约减少 67%，读档约减少 48%；保存新增时间线锁与完整安全快照，约增加 8.7ms，不能宣称所有路径都更快。

完整重建 CPU 样本为 8 幕 × 每幕 6 个锚点，10/100/500 回合，7 次中位数。canonical state（不含允许扩展的派生 v2）摘要相等。SQL/保存加载另用真实数据库脚本测量，不能把内存 fake repository 读次数称为 SQL。

| 回合 | 原完整重建 CPU ms | 新完整重建 CPU ms | 设定规范化次数 |
|---:|---:|---:|---:|
| 10 | 4.456 | 0.909 | 40 → 1 |
| 100 | 44.557 | 9.894 | 400 → 1 |
| 500 | 268.896 | 107.943 | 2000 → 1 |

canonical 状态、共同存档语义、内存重放和多幕重放摘要全部相等。快照 JSON 为 `207239→210705`、`698916→722274`、`2886116→2998674` 字节，分别增加 1.67%/3.34%/3.90%，来自初始种子、计数及回执等元数据；不是 PostgreSQL 压缩后磁盘体积。

Python tracemalloc 首遍重放峰值（fixture 提前分配、非 RSS）在 500 回合为 `58,556→643,464 B`，约增加 0.56 MiB，主要为首次物化并持久保留的每回合回执。这里没有内存降低结论，换取的是可追溯的实际状态变化。

StoryMarkdown 使用固定长正文、24 人物、1200 帧（120 次正文变化）、7 次中位数；脚本是浅层 memo/useMemo 纯计算 harness，测量解析和匹配器开销，不包含真实 React DOM 提交或浏览器 FPS。

派生耗时 `560.16→63.17ms`；组件执行 `1200→120` 次，人物匹配器构造 `1200→1` 次。此结果不能换算成真实模型流速度或 FPS 提升。

上下文使用 6 条长正文，检查组装字节/字符、估算 token、硬约束与尾部标记。字符/字节公式只能用于两版相对对照，不能代替供应商 tokenizer 或真实 token 账单。

500 回合上下文 `15126→15394` 字符、`33558→33958` UTF-8 字节，粗估 token（字符数÷2 向上取整）`7563→7697`。近期正文 `5298→5292` 字符；最新两回合尾部标记从全丢变为全保，系统硬约束两版均保留。改进是同正文预算保留落点，没有 token 缩减结论。没有测量真实模型首字/全回合延迟、浏览器传输带宽或生产并发容量。

### 代码精简的实际边界

- `gameExperience.ts` 从 594 行降到 281 行，净减 313 行；回合/生成器 stream 加上新的公共生命周期，合计从 712 行降到 586 行，净减 126 行。
- 已改动的 45 个生产代码文件合计 `15286→16228` 行，**净增 942 行**：删除旧重复职责的同时，新增了时间线隔离、旧档兼容、回执与持续状态展示。不能把局部精简说成全仓代码净缩减。
- 回归测试、两个迁移和三个 benchmark 脚本单独统计，不混入生产代码性能或精简结论。没有删除仍用于非数值条件/关系的旧服务，没有做全仓格式化或依赖升级。

### 复现方式

先在仓库根目录安装既有 API/Web 依赖；提供 PostgreSQL + pgvector 的隔离测试实例。全量 pytest 会重建指定测试库的 schema，应只传一次性测试库 URL。

```sh
cd api
TEST_DATABASE_URL="$ISOLATED_TEST_DATABASE_URL" PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
python3 -m ruff check .
cd ../web
npm test
npm run lint
npx tsc --noEmit
npm run build
```

基准在仓库根目录运行，两个版本顺序执行。API 基准脚本主动禁止模型/HTTP；SQL 基准严格仅接受两个固定测试库名和 `/private/tmp/rpgforge-refactor-pg` Unix socket，运行前需要提供该一次性 PostgreSQL 实例。本轮用临时 `pgserver`（测试工具，未加入应用依赖）提供；建库及基准表属于该临时实例，脚本结束清理自己的表。

```sh
BASELINE_ROOT="$(mktemp -d)"
git archive 573d69a api | tar -x -C "$BASELINE_ROOT"
PYTHONPATH="$BASELINE_ROOT/api" python3 api/scripts/benchmark_state_rebuild.py --acts 8 --anchors 6 --repeats 7
PYTHONPATH=api python3 api/scripts/benchmark_state_rebuild.py --acts 8 --anchors 6 --repeats 7
PYTHONPATH="$BASELINE_ROOT/api" python3 api/scripts/benchmark_runtime.py --api-root "$BASELINE_ROOT/api" --database-url 'postgresql+psycopg://postgres@/rpgforge_perf_before_test?host=/private/tmp/rpgforge-refactor-pg' --label before --output /private/tmp/runtime-before.json
PYTHONPATH=api python3 api/scripts/benchmark_runtime.py --api-root api --database-url 'postgresql+psycopg://postgres@/rpgforge_perf_after_test?host=/private/tmp/rpgforge-refactor-pg' --label after --output /private/tmp/runtime-after.json
node web/scripts/benchmark-story-render.mjs --baseline-ref 573d69a
```

测量后停止自行创建的临时 PostgreSQL，清理该基准副本和输出文件；不要把命令指向任何业务数据库。保存的 JSON 已去除本机项目绝对路径。

### 发布与恢复

- 新 migration head 为 `20261107_0032`，只在本轮临时库演练；生产尚未应用。
- 发布前需备份数据库，统一发布 API/worker/web，执行迁移并完成旧档读取和真实回合烟测；本轮没有获得生产发布授权。
- 已停止本轮临时前后端服务与 PostgreSQL，清理 16 个本轮专用临时文件/目录（基线副本、数据库、工具包、缓存及临时结果）。代码、回归、可复现 benchmark、脱敏测量记录及验收截图保留；已安装的标准开发依赖和构建产物可继续使用。
- B4、新自然转场语义、真实模型长局质量/首字延迟、生产网络与真实移动设备验收仍为独立后续范围。
