<p align="center">
  <img src="web/public/rpg-deepseek-logo.png" alt="RPGForge" width="200" />
</p>

<h1 align="center">RPGForge</h1>

<p align="center"><a href="README.md">English</a> · <strong>简体中文</strong></p>

<p align="center"><em>属于你自己的 AI 游戏主持人。选定任意世界，开启一场会记住你的长篇文字 RPG。</em></p>

---

RPGForge 是一个可自部署的 AI 文字 RPG 引擎。你描述想玩的冒险类型——赛博朋克劫案、武侠复仇、生存恐怖、校园日常——AI 会先采访你，搭建出完整的世界与规则，然后作为你的游戏主持人（GM），一回合接一回合地把这个世界跑起来。

项目目前处于早期公开预览阶段，面向 Docker 自部署。

## 玩起来是什么体验

- **你出点子，AI 造世界。** 回答一段简短采访，RPGForge 就能生成一套完整可玩的游戏：背景设定、规则、势力、角色，以及开场场景。
- **每一回合都是真正的叙事。** AI 流式写出当前场景，再给你 A/B/C/D 选项——或者直接输入你想做的任何事。
- **剧情状态真的会延续。** 处境、关系、任务、待解线索、已知事实和幕进度都会作为文字化游戏状态被记录，而不只是花哨的描述文字。
- **NPC 会记住你。** 关系随你的实际行为变化，世界会替你记账。
- **剧情保持一致。** 幕后有故事导演、节奏压力、输出观测和异步审计，确保每一回合忠于最初设定的世界与规则，同时不把游玩变成可见数值游戏。
- **它记得住长线。** 回合记忆、章节记忆、长期记忆三层叠加，让单个冒险能跑很久而不丢线索。
- **随处可玩。** 移动端友好的游玩界面、桌面端仪表盘、带头像的角色档案，以及清爽的 Markdown 叙事渲染。

## 快速开始（自己跑起来玩）

RPGForge 以 Docker 栈运行——一条命令加一个浏览器就够了。

环境要求：Docker 29+ 与 Docker Compose v2。

1. 复制环境变量文件：

   ```bash
   cp .env.example .env
   ```

2. 配置 DeepSeek API Key——可以写进 `.env`（`DEEPSEEK_API_KEY=...`），也可以之后在应用内 `/settings` 页面填写。

3. 启动全部服务：

   ```bash
   docker compose up -d --build
   ```

4. 打开游戏：
   - 网页：http://localhost:3000
   - 手机（同一 Wi-Fi）：`http://<你电脑的局域网IP>:3000`

然后点 **New Game**，回答采访，开始游玩。

> 默认只暴露 web 端口。浏览器与 Next.js 通信，Next.js 在 Docker 内部把所有请求代理给 API。不确定起没起来？打开 http://localhost:3000/health 看看。

---

## 自部署与开发

以下内容面向运行、配置或二次开发 RPGForge 的人。

### 架构

```text
Browser
  |
  | http://localhost:3000
  v
Next.js web
  |
  | Docker internal network
  v
FastAPI api ---- Redis/RQ queue ---- worker
  |                                |
  v                                v
PostgreSQL + pgvector <------------
```

服务在 `docker-compose.yml` 中定义：

- `web`：Next.js 前端，映射到宿主机 `3000` 端口。
- `api`：FastAPI 后端，默认仅在 Docker 网络内可达。
- `worker`：消费 `rpgforge` 队列的 RQ worker，负责生成与回合任务。
- `postgres`：带 pgvector 的 PostgreSQL。
- `redis`：任务队列与进度缓存。

### 环境要求

- Docker 29+
- Docker Compose v2
- Node.js 22+（本地前端开发）
- Python 3.11+（本地后端开发）

### 配置

在 `.env` 或应用设置页填写密钥。不要提交 `.env`。

重要变量：

| 变量 | 用途 |
| --- | --- |
| `DATABASE_URL` | API 使用的 SQLAlchemy 数据库 URL。 |
| `REDIS_URL` | RQ worker 队列使用的 Redis URL。 |
| `DEEPSEEK_API_KEY` | 可选的默认 DeepSeek API Key，也可在 `/settings` 保存。 |
| `DEEPSEEK_BASE_URL` | 可选的 DeepSeek 兼容 base URL。 |
| `DEEPSEEK_FLASH_MODEL` | 默认 Flash 模型槽位名。 |
| `DEEPSEEK_PRO_MODEL` | 默认 Pro 模型槽位名。 |
| `SETTINGS_ADMIN_TOKEN` | 公网暴露时，保存模型/API 设置前所需的令牌。 |
| `INTERNAL_API_URL` | web 容器访问 api 容器使用的 URL。 |

更多细节见 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

### 本地开发

本地运行后端：

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

本地运行前端：

```bash
cd web
npm install
INTERNAL_API_URL=http://localhost:8000 npm run dev
```

从 `api/` 应用数据库迁移：

```bash
alembic upgrade head
```

### 检查

后端：

```bash
cd api
ruff check .
pytest
```

前端：

```bash
cd web
npm run lint
npm run build
```

Docker：

```bash
docker compose up -d --build api worker web
docker compose ps
```

### 可观测性与 AI 质量

每次 LLM 调用（故事导演、GM、异步 drift 审计、状态抽取、上下文压缩、judge、生成器）都会连同完整的
prompt、输出、token 用量、延迟和状态记录到 `agent_traces` 表。每回合的遥测标志
（`director_used_fallback`、`drift_severity`、`rewrite_triggered`、`extractor_failed`）
记录在 `turn_jobs` 上。

管理后台（由 `SETTINGS_ADMIN_TOKEN` 令牌保护）：

- 浏览器打开 `/admin`，输入管理令牌。
- 聚合卡片：fallback / 重写 / 抽取失败率、drift severity 分布、各 agent 平均延迟、judge 平均分。
- 最近 LLM 调用表——点任意行查看完整 prompt / reasoning / 输出。
- 按 game id 查询 judge 评分。

管理 API（需 `X-Settings-Admin-Token`）：

- `GET /api/admin/stats/recent-turns`
- `GET /api/admin/traces`、`GET /api/admin/traces/{id}`
- `GET /api/admin/turn-jobs/{job_id}/traces`
- `GET /api/admin/golden`、`GET /api/admin/games/{game_id}/evaluations`
- `POST /api/admin/turns/{turn_id}/evaluate`

CLI 工具（在 api 容器内运行，如 `docker compose exec api ...`）：

```bash
python -m scripts.replay_trace --turn-job-id <UUID>   # 重放某回合的 LLM 调用
python -m scripts.diff_traces --agent gm_runtime --last 2  # 比对两条 trace（不消耗 API）
python -m scripts.label_trace <TRACE_ID> --label good      # 把某条 trace 标为 golden 样例
python -m scripts.judge_turn --game-id <UUID> --last 1     # 用 LLM-as-Judge 给某回合评分
```

完整设计与路线图见 [优化计划](docs/OPTIMIZATION_PLAN.md)。

### 文档

- [架构](docs/ARCHITECTURE.md)
- [配置](docs/CONFIGURATION.md)
- [部署](docs/DEPLOYMENT.md)
- [API 概览](docs/API.md)
- [AI 剧情运行时指南](docs/AI_STORY_RUNTIME_GUIDE.md)
- [优化计划](docs/OPTIMIZATION_PLAN.md)

### 安全

RPGForge 为自部署而生。公网暴露前请：

- 设置高强度的 `SETTINGS_ADMIN_TOKEN`。
- 把公网部署放在带认证的反向代理之后。
- 保持 `.env` 私密。
- 把数据库当作密钥存储：本版本运行时的 DeepSeek API Key 以明文存于其中。
- 不要公开本地 Docker 卷、数据库导出、生成的私有游戏或上传的角色头像。

见 [SECURITY.md](SECURITY.md)。

### 路线图

- 提升真实游玩稳定性与长会话记忆表现。
- 增加游戏模板与存档的导入/导出流程。
- 增加更丰富的角色档案工具。
- 扩展对 prompt 架构的评测与回归测试。
- 把 TTS 作为可选的未来扩展，而非核心需求。

## 许可证

MIT 许可证。见 [LICENSE](LICENSE)。
