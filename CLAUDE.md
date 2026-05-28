# RPGForge 项目说明（给 Claude）

## 必读

接手任何工作前，先读 [`docs/OPTIMIZATION_PLAN.md`](docs/OPTIMIZATION_PLAN.md)。该文件维护：

- 已完成的优化轮次和改动清单
- 当前 AI Agent 链路的速查表
- 待办路线图（阶段 0–4，带勾选框）
- 已明确"不做"的事项及理由
- 关键文件、常量、Telemetry 字段索引
- 已知遗留疑点

**完成新一轮工作后，在 OPTIMIZATION_PLAN.md §1 追加 `### Round N (日期)` 条目**，不要修改历史 Round。路线图条目落地打 `[x]`，不要删除。

## 项目结构

- `api/`：FastAPI 后端，AI Agent 链路与持久化
- `web/`：Next.js 前端
- `docs/`：项目文档
  - `ARCHITECTURE.md`：宏观架构
  - `AI_STORY_RUNTIME_GUIDE.md`：AI 剧情生成依据
  - `OPTIMIZATION_PLAN.md`：**本项目的工作驾驶舱**
  - `API.md` / `CONFIGURATION.md` / `DEPLOYMENT.md` / `PROJECT_GUIDE.md`：参考资料

## 部署

参见 `docker-compose.yml`，常用命令：

```bash
docker compose exec api alembic upgrade head     # 数据库迁移
docker compose restart api worker                 # 重启业务进程
docker compose exec api pytest tests/             # 后端测试（需要 Postgres）
```

本地无法直接 `pytest`，测试必须在 api 容器内跑。

## 工作约束

继承全局 `~/CLAUDE.md` 的所有偏好（中文回复、修改代码前先说方案等）。本项目额外约定：

- 修改 `app/services/gameplay.py` / 各 Agent 文件前，先确认 OPTIMIZATION_PLAN.md 中是否已有相关决策
- 新增 LLM 调用 → 必须设独立 timeout、必须有 fallback
- 新增 TurnJob 字段 → 同步 model / schema / router / `_publish_turn_snapshot` / 前端类型
- prompt 文件修改 → 在 OPTIMIZATION_PLAN.md 里记录改了哪个规则编号
