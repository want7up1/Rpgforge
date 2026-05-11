# RPGForge API

FastAPI backend for RPGForge.

The API owns game persistence, AI generation jobs, gameplay turns, state updates, character archives, memory retrieval, runtime settings, and background worker coordination.

## Requirements

- Python 3.11+
- PostgreSQL 16 with pgvector
- Redis 7

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run Locally

```bash
uvicorn app.main:app --reload
```

Health check:

```bash
curl http://localhost:8000/health
```

Apply migrations:

```bash
alembic upgrade head
```

Run checks:

```bash
ruff check .
pytest
```

## Docker

The API is built by the root `docker-compose.yml` file:

```bash
docker compose up -d --build api
```

The API container runs `alembic upgrade head` before Uvicorn starts.

## Main Modules

- `app/routers/`: HTTP route definitions.
- `app/services/`: generation, gameplay, memory, state, character, and settings logic.
- `app/models/`: SQLAlchemy models.
- `app/schemas/`: Pydantic schemas.
- `app/prompts/`: prompt templates.
- `migrations/`: Alembic migrations.
- `tests/`: pytest suite.

## API Areas

- Games: create, list, view, delete, memory diagnostics, lore reindex, summary rebuild.
- Generator: interview, finalize, create-game, job status, server-sent events.
- Turns: list, create, async jobs, streamed progress, turn details.
- State: current state, deltas, edit, approve, reject.
- Characters: list, sync, edit, portrait upload/delete/read.
- Settings: DeepSeek key, base URL, model slots, task routing.

See [../docs/API.md](../docs/API.md) for endpoint details.
