# RPGForge

RPGForge is a Docker-first AI text RPG engine for creating and playing structured, long-running narrative games.

It combines a rule/world generator, a focused play interface, persistent game state, worldbook retrieval, character archives, Markdown narrative rendering, and server-side streaming jobs for AI output. The project is currently in early public preview and is intended for self-hosted experimentation.

## Features

- AI-assisted game setup with interview, outline, and parallel section generation.
- DeepSeek model routing for rule generation, story output, director checks, drift validation, state extraction, and memory compression.
- Turn-based gameplay with streamed narrative output, A/B/C/D choices, and free-form player actions.
- Structured state v2 with player status, XP, abilities, skill proficiency, NPC relationships, quests, conditions, and open threads.
- Story director and drift validator layers to keep gameplay closer to the original rules and world assumptions.
- Worldbook retrieval with deterministic local vectors and pgvector.
- Context summaries for turn, chapter, and long-term memory.
- Character archives with user-uploaded portrait images.
- Mobile-friendly play UI, desktop dashboard pages, uploaded character portraits, and Markdown story rendering.
- Single public web port in Docker; the browser talks to Next.js, and Next.js proxies API traffic internally.

## Architecture

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

## Requirements

- Docker 29+
- Docker Compose v2
- Node.js 22+ for local frontend development
- Python 3.11+ for local backend development

## Quick Start

Copy the environment file:

```bash
cp .env.example .env
```

Start the stack:

```bash
docker compose up -d --build
```

Open the app:

- Web: http://localhost:3000
- Health check through the web proxy: http://localhost:3000/health
- Same-LAN mobile testing: `http://<computer-lan-ip>:3000`

Only the web service exposes a host port by default. API requests go through the Next.js proxy to the Docker-internal FastAPI service.

## Configuration

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

## Development

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

## Checks

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

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Configuration](docs/CONFIGURATION.md)
- [Deployment](docs/DEPLOYMENT.md)
- [API Overview](docs/API.md)
- [AI Story Runtime Guide](docs/AI_STORY_RUNTIME_GUIDE.md)
- [Optimization Plan](docs/OPTIMIZATION_PLAN.md)

## Security

RPGForge is built for self-hosting. Before exposing it publicly:

- Set a strong `SETTINGS_ADMIN_TOKEN`.
- Put public deployments behind an authenticated reverse proxy.
- Keep `.env` private.
- Treat the database as secret storage: runtime DeepSeek API keys are stored there in plaintext in this version.
- Do not publish local Docker volumes, database dumps, generated private games, or uploaded character portraits.

See [SECURITY.md](SECURITY.md).

## Roadmap

- Improve real-play stability and long-session memory behavior.
- Add import/export flows for game templates and game saves.
- Add richer character archive tools.
- Expand evaluation and regression tests for prompt architecture.
- Keep TTS as an optional future extension rather than a core requirement.

## License

MIT License. See [LICENSE](LICENSE).
