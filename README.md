<p align="center">
  <img src="web/public/rpg-deepseek-logo.png" alt="RPGForge" width="200" />
</p>

<h1 align="center">RPGForge</h1>

<p align="center"><strong>English</strong> · <a href="README.zh-CN.md">简体中文</a></p>

<p align="center"><em>Your own AI Game Master. Pick any world, and play a long-running text RPG where the story remembers you.</em></p>

---

RPGForge is a self-hosted AI text RPG engine. You describe the kind of adventure you want — a cyberpunk heist, a wuxia revenge tale, survival horror, a slice-of-life academy — and the AI interviews you, builds the whole world and ruleset, then runs it as your Game Master, turn after turn.

It's currently in early public preview and built to be self-hosted with Docker.

## What it feels like to play

- **You bring the idea, the AI builds the world.** Answer a short interview and RPGForge generates a complete, playable game: setting, rules, factions, characters, and an opening scene.
- **Every turn is real storytelling.** The AI writes the scene as it streams in, then offers you A/B/C/D choices — or just type whatever you want to do instead.
- **Your story state actually persists.** Conditions, relationships, quests, open threads, discovered facts, and act progress are tracked as narrative state, not just flavor text.
- **NPCs remember you.** Relationships shift based on what you actually do, and the world keeps the receipts.
- **The story stays coherent.** Behind the scenes, a story director, pacing signals, output observation, and async audits keep turns faithful to the world and rules you started with — without turning play into a visible numbers game.
- **It remembers the long game.** Turn, chapter, and long-term memory layers let a single adventure run for a very long time without losing the thread.
- **Play anywhere.** A mobile-friendly play screen, a desktop dashboard, character archives with portraits, and clean Markdown storytelling.

## Quick Start (play it yourself)

RPGForge runs as a Docker stack — one command and a browser is all you need.

Requirements: Docker 29+ and Docker Compose v2.

1. Copy the environment file:

   ```bash
   cp .env.example .env
   ```

2. Add a DeepSeek API key — either in `.env` (`DEEPSEEK_API_KEY=...`) or later on the in-app `/settings` page.

3. Start everything:

   ```bash
   docker compose up -d --build
   ```

4. Open the game:
   - Web: http://localhost:3000
   - On your phone (same Wi-Fi): `http://<your-computer-lan-ip>:3000`

Then hit **New Game**, answer the interview, and start playing.

> Only the web port is exposed by default. The browser talks to Next.js, which proxies everything to the API inside Docker. Not sure it's up? Check http://localhost:3000/health.

---

## Self-hosting & development

The rest of this document is for people running, configuring, or hacking on RPGForge.

### Architecture

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

Services are defined in `docker-compose.yml`:

- `web`: Next.js frontend, exposed on host port `3000`.
- `api`: FastAPI backend, only reachable inside the Docker network by default.
- `worker`: RQ worker that consumes `rpgforge` queue jobs for generation and turns.
- `postgres`: PostgreSQL with pgvector.
- `redis`: job queue and progress cache.

### Requirements

- Docker 29+
- Docker Compose v2
- Node.js 22+ for local frontend development
- Python 3.11+ for local backend development

### Configuration

Set secrets in `.env` or in the app settings page. Do not commit `.env`.

Important variables:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy database URL used by the API. |
| `REDIS_URL` | Redis URL used by the RQ worker queue. |
| `DEEPSEEK_API_KEY` | Optional default DeepSeek API key. Can also be saved in `/settings`. |
| `DEEPSEEK_BASE_URL` | Optional DeepSeek-compatible base URL. |
| `DEEPSEEK_FLASH_MODEL` | Default Flash model slot name. |
| `DEEPSEEK_PRO_MODEL` | Default Pro model slot name. |
| `SETTINGS_ADMIN_TOKEN` | Token required before saving model/API settings when exposed publicly. |
| `INTERNAL_API_URL` | URL the web container uses to reach the API container. |

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for more details.

### Development

Run the backend locally:

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Run the frontend locally:

```bash
cd web
npm install
INTERNAL_API_URL=http://localhost:8000 npm run dev
```

Apply database migrations from `api/`:

```bash
alembic upgrade head
```

### Checks

Backend:

```bash
cd api
ruff check .
pytest
```

Frontend:

```bash
cd web
npm run lint
npm run build
```

Docker:

```bash
docker compose up -d --build api worker web
docker compose ps
```

### Observability & AI quality

Every LLM call (story director, GM, async drift audit, state extractor, context
compressor, judge, generator) is recorded in the `agent_traces` table with its
full prompt, output, token usage, latency, and status. Per-turn telemetry flags
(`director_used_fallback`, `drift_severity`, `rewrite_triggered`,
`extractor_failed`) live on `turn_jobs`.

Admin dashboard (token-gated by `SETTINGS_ADMIN_TOKEN`):

- Open `/admin` in the browser, enter the admin token.
- Aggregate cards: fallback / rewrite / extractor-failure rates, drift severity
  distribution, per-agent average latency, average judge score.
- Recent LLM calls table — click any row for the full prompt / reasoning / output.
- Judge score query by game id.

Admin API (require `X-Settings-Admin-Token`):

- `GET /api/admin/stats/recent-turns`
- `GET /api/admin/traces`, `GET /api/admin/traces/{id}`
- `GET /api/admin/turn-jobs/{job_id}/traces`
- `GET /api/admin/golden`, `GET /api/admin/games/{game_id}/evaluations`
- `POST /api/admin/turns/{turn_id}/evaluate`

CLI tools (run inside the api container, e.g. `docker compose exec api ...`):

```bash
python -m scripts.replay_trace --turn-job-id <UUID>   # replay a turn's LLM calls
python -m scripts.diff_traces --agent gm_runtime --last 2  # compare two traces (no API cost)
python -m scripts.label_trace <TRACE_ID> --label good      # mark a trace as a golden case
python -m scripts.judge_turn --game-id <UUID> --last 1     # LLM-as-Judge score a turn
```

See [Optimization Plan](docs/OPTIMIZATION_PLAN.md) for the full design and roadmap.

### Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Configuration](docs/CONFIGURATION.md)
- [Deployment](docs/DEPLOYMENT.md)
- [API Overview](docs/API.md)
- [AI Story Runtime Guide](docs/AI_STORY_RUNTIME_GUIDE.md)
- [Optimization Plan](docs/OPTIMIZATION_PLAN.md)

### Security

RPGForge is built for self-hosting. Before exposing it publicly:

- Set a strong `SETTINGS_ADMIN_TOKEN`.
- Put public deployments behind an authenticated reverse proxy.
- Keep `.env` private.
- Treat the database as secret storage: runtime DeepSeek API keys are stored there in plaintext in this version.
- Do not publish local Docker volumes, database dumps, generated private games, or uploaded character portraits.

See [SECURITY.md](SECURITY.md).

### Roadmap

- Improve real-play stability and long-session memory behavior.
- Add import/export flows for game templates and game saves.
- Add richer character archive tools.
- Expand evaluation and regression tests for prompt architecture.
- Keep TTS as an optional future extension rather than a core requirement.

## License

MIT License. See [LICENSE](LICENSE).
