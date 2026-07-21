# Optimization Log 2026-07

## 2026-07-21 — Round 60：驾驶舱归档与接手信息重整

### 背景

- 原 `docs/OPTIMIZATION_PLAN.md` 已增长到 1576 行，Round 1–59 全文、旧路线图、过时常量、查询样例和当前接手信息混在一起，AI 每次接手都需要加载大量历史。
- 旧文档仍写着 `stage_total=7`、TurnJob 14 分钟等历史值；当前代码真实值已经是 6 阶段、18 分钟，继续把旧文档当驾驶舱会误导后续修改。
- 现有 7 月日志只记录 Round 57 和 59，Round 55、56、58 仍主要留在旧驾驶舱内。

### 整理

- 将原驾驶舱完整移动为 `OPTIMIZATION_PLAN_ARCHIVE_THROUGH_ROUND_59.md`，标记为只读历史快照；保留 Round 1–59 全部内容，并修复归档移动后的相对链接。
- 重建主驾驶舱，只保留 AI 接手摘要、当前目标/边界、执行队列、实施模板、运行链路、业务决策、关键文件、验证清单、遗留疑点、最近 5 条完成摘要和历史索引。
- 以当前代码校准 TurnJob 6 阶段、18 分钟总超时、Maintenance 10 分钟、偏离审计每 3 回合和记忆摘要每 4 回合等接手信息。
- 补齐本月 Round 55、56、58 的日志索引和摘要，使 7 月记录连续。
- 本轮不修改业务代码、依赖、Docker、数据库或运行环境。

### 验证

- 完整归档 1578 行，59 个数字 Round（1–59）无缺失；主驾驶舱收敛到 247 行，只保留最近 5 条完成摘要。
- 主驾驶舱必需章节齐全，三份目标文档的 Markdown 相对链接无断链，旧本机绝对路径已移除。
- `git diff --check` 和公开内容脱敏检查通过。
- 三份文档同步到远端后 SHA-256 与本地一致；未重建容器，现有服务运行状态未受影响。

## 2026-07-21 — Round 59：移动端右侧溢出与帮助气泡修复

### 背景与根因

- 用户反馈移动端界面偶尔从右侧溢出。只读审查确认初始路由在 360px 以上稳定，但一个真实存档在 320px 下出现 `.game-screen clientWidth=320 / scrollWidth=342`。
- `.game-screen` 只定义三行，唯一隐式列仍为 `auto`；顶栏标题与“撤销/手账/菜单”的最小内容宽度会把整列撑宽。根节点隐藏横向滚动，因此表现为偶发推出或裁切，而非稳定滚动条。
- 记忆页 `HelpMark` 使用固定 288px 气泡并相对小图标居中，在 320–430px 下会越过左边界。
- 在场角色姓名条的 `overflow-x: auto` 是受控的局部滚动，不是页面级根因。

### 改动

- `web/app/globals.css`：为 `.game-screen` 增加 `grid-template-columns: minmax(0, 1fr)`。
- `web/app/games/[id]/memory/page.tsx`：帮助气泡在移动端固定到视口底部安全区，左右各留 0.75rem；`sm` 以上恢复绝对定位、图标下方居中和 288px 宽度。
- 未改动业务逻辑、API、数据库、Docker 配置或持久化数据；保留本轮开始前 `play/page.tsx` 与 `globals.css` 的已有未提交改动。

### 本地验证

- `git diff --check`：通过。
- `cd web && npm run lint`：通过。
- `cd web && npx tsc --noEmit`：通过。
- `cd web && npm test`：3 个测试文件、52 项全部通过。
- `cd web && npm run build`：Next.js 16.2.6 生产构建及全部路由生成通过。

### 远端部署与实页验证

- 部署前校验远端两个目标文件与审查基线 SHA-256 一致；只同步 `globals.css` 与记忆页文件。
- `docker compose up -d --build --no-deps web`：镜像构建成功，仅重新创建 `rpgforge-web-1`；API、worker、PostgreSQL、Redis 运行时长保持不变。
- `docker compose ps`：服务全部运行，API/PostgreSQL/Redis healthy；Web 日志显示 Next.js Ready，无异常。
- Web `/`：HTTP 200；API `/health`：`status=ok`、environment=production。
- Playwright（Chrome + iPhone 13 设备模拟）：
  - 13 个路由 × 320/360/375/390/430px，共 65 组初始状态，无横向溢出。
  - 4 个真实存档 × 280/300/320/330/360/390/430px，共 28 组，无文档级或 `.game-screen` 溢出。
  - 320px 下菜单、手账、展开命令行、角色弹窗 4 个动态状态均通过。
  - 5 个帮助入口 × 320/360/390/430px，共 20 次聚焦检查均位于视口内。
  - 320px 游玩页与帮助气泡视觉截图通过；浏览器控制台 0 error。

### 验证边界

- 本机未安装 Playwright WebKit 浏览器组件，为保持依赖边界未临时安装；自动化验收使用现有 Chrome 的 iPhone 13 设备模拟。修复仅使用标准 CSS Grid、响应式定位和安全区变量。

## 2026-07-18 — Round 58：前端 UI 全面重做

### 目标与信息架构

- 在业务功能冻结前提下，将前端改为“文字游戏 × 像素风 × 磷光绿终端”，并重新组织页面层级。
- 壳外流程：标题画面 → 存档槽位 → 三幕创建向导，并保留工坊、全局设置和管理入口。
- 壳内以游玩页为中心；原游戏概览页改为跳转游玩页，指标、设定概览、状态快照、导出和危险操作迁入 `/games/[id]/camp`。

### 主要改动

- 游玩页从三栏改为单栏剧情卷轴、紧凑顶栏和底部命令行；状态、队伍、历史、记忆、剧本、营地进入局内菜单或手账抽屉。
- 建立 `.px-*` 设计系统：像素切角、磷光绿 token、CRT 扫描线/暗角、按钮、输入框、徽章、折叠、表格、focus-visible 和 reduced-motion。
- 新增 `PixelDialog` 和 `GameMenu`，合并并删除旧 `GamePageHeader` / `ChatHistorySheet`；看板、工坊和设置逻辑保持不变，仅统一外观。
- 移动端补充修复 viewport 高度回退、iOS 输入字号、角色卡密度、头像容器适配和默认折叠的自定义行动输入区。

### 验证与部署

- ESLint、TypeScript、52 项 vitest、Next.js 生产构建及全路由通过。
- 远端同步前端文件并重建 Web；服务健康、日志正常，壳外和真实存档局内页面均可访问。
- Playwright 覆盖 360/375/390px 页面、弹窗、抽屉和命令行，补充复查时未发现横向溢出。
- 后续 Round 59 又覆盖了更窄的 320px 与特定真实存档组合，并修复两个遗漏边界。

## 2026-07-06 — Round 57：非数值代价闭环 + 替代锚点组

### 背景

游玩方向审查指出两项优先问题：

- 纯叙事化后，失败、受伤、暴露、失信、追捕等代价可能只停留在 GM 正文里，未稳定进入后续状态。
- 幕推进要求所有 `required=true` 锚点全部完成，无法表达“潜入/说服/绕路任选一条也能推进”的多路径主线。

本轮只修这两项，不恢复骰子、属性、技能或数值资源。

### 改动

- `gm_runtime.md`：要求 GM 把风险/代价写成后续能被状态提取器承接的具体剧情后果。
- `extract_state_delta.md`：新增非数值代价闭环规则。GM 输出明确发生代价时，提取器必须落到 `condition_updates`、`relationship_events`、`open_thread_updates` 或 `quest_updates`；不得只因 risk/cost hint 存在就虚构代价。
- `story_settings.py`：新增 `completion_anchors[].alternative_group` 规范化字段；runtime_story 会过滤已满足替代组的兄弟锚点。
- `state_applier.py`：ready/advance/current_act_anchor_progress/fallback anchor quest 改按“required requirement group”计算。同组 required 锚点任一完成即满足该组；未分组锚点仍单独必达。
- `act_pacing.py`：open_required_count 和 next_required_anchor 支持替代组，避免同一替代路线组被算成多个必达项。
- `settings_guide_exporter.py`、`authoring_kit_exporter.py`、`generate_config_section.md`：同步作者可见字段说明。
- 测试新增覆盖 prompt 合同、替代组 runtime 投影、替代组转幕、act_pacing 计数和填写说明字段。

### 验证

- `cd api && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_markdown_contracts.py tests/test_act_pacing.py tests/test_games.py::test_settings_guide_documents_every_normalized_field tests/test_gameplay.py::test_runtime_story_filters_satisfied_alternative_anchor_group tests/test_gameplay.py::test_state_delta_advances_after_alternative_anchor_group_and_required_anchor`
  - 结果：15 passed。
- `cd api && python3 -m ruff check app tests`
  - 结果：All checks passed。
- 远端运行环境：
  - 最小同步后重建 `api` / `worker`。
  - `docker compose ps`：`api` healthy，`worker` running，依赖服务 healthy。
  - `GET /health`：`status=ok`。
  - 容器内目标 pytest：15 passed。
  - `api` / `worker` 启动日志无异常。

### 未完成

- 本机带 `db_session` 的旧目标测试仍因本地 Postgres `postgres:5432` 连接被关闭而无法跑通；需在容器或远端运行环境复验。
- 代价闭环是 prompt + 状态提取合同，仍需真实模型回合验证是否稳定按合同落库并被后续回合承接。

## 2026-07-03 — Round 56：纯叙事契约部署与 migration 验证

### 部署范围

- 部署 Round 55 的纯叙事状态契约、TurnJob 默认阶段数和公开文档修正。
- 部署前创建 PostgreSQL dump 压缩备份；不删除或重建 Postgres/Redis 数据卷，不覆盖私有配置或运行态数据。
- 按文件清单同步代码，仅重建 API / worker；Web 无运行时代码变化，PostgreSQL / Redis 保持原数据卷。
- API 启动时执行 Alembic migration 到 `20260703_0030`。

### 远端验证

- API、PostgreSQL、Redis healthy，worker 与 Web 正常运行。
- Alembic current 为 `20260703_0030 (head)`，`turn_jobs.stage_total` 数据库默认值为 6。
- API health、Web 首页、游戏列表和脱敏设置读取接口正常。
- 容器内纯叙事状态、阶段数、act pacing 和 prompt 合同目标测试通过；ruff 通过。
- 抽查目标文件 SHA-256，本地与远端一致。

### 边界

- 本轮未消耗模型额度做真实生成或回合 E2E；真实模型行为仍需后续单独验证。

## 2026-07-03 — Round 55：纯叙事契约收口

### 背景与改动

- Round 53 已转向纯叙事，但状态提取 schema 仍暴露旧 XP、技能和能力 delta；新建 TurnJob 的默认阶段数与真实运行阶段数不一致，公开文档也残留旧机制描述。
- `StateDeltaExtraction` 删除 `xp_events`、`skill_events`、`ability_updates`，并增加回归测试锁住纯叙事 delta 契约。
- TurnJob ORM 默认、server default 与 `TurnJobRead` 默认统一为 6，新增 migration `20260703_0030_turn_job_stage_total_default.py`。
- README 和 AI runtime guide 改为当前文字化 conditions、relationships、导演层、节奏信号、输出观察和异步审计说明。

### 验证与交付边界

- 纯叙事状态、阶段默认值、act pacing 和 Markdown 合同目标测试通过；ruff 通过；公开内容脱敏检查通过。
- Round 55 本身未部署；数据库 migration 与运行态验证在 Round 56 完成。
