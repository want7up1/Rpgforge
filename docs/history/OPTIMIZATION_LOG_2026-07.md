# Optimization Log 2026-07

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
