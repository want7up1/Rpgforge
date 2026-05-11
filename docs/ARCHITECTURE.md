# Architecture

RPGForge is a self-hosted AI text RPG system built around a Docker Compose stack.

## Runtime Services

```text
Browser
  |
  v
web: Next.js
  |
  v
api: FastAPI
  |
  +-- worker: background jobs
  +-- redis: job queue and progress snapshots
  +-- postgres: relational data and pgvector lore retrieval
```

The browser talks to the `web` service on port `3000`. The web service proxies `/api/*` and `/health` to the API service through the internal Docker network. This keeps deployment simple because only one public port is needed.

## Backend

The backend lives in `api/`.

Main responsibilities:

- Game CRUD and generated game persistence.
- Rule interview and complete configuration generation.
- Streaming progress snapshots for long-running AI work.
- Turn generation and turn history.
- Story director and drift validation prompt layers.
- State extraction and state v2 application.
- Character archives and portrait file storage.
- Worldbook retrieval and context summaries.
- Runtime DeepSeek settings and task-level model routing.

Key directories:

- `api/app/routers/`: HTTP API routes.
- `api/app/services/`: generation, gameplay, state, memory, and integration logic.
- `api/app/models/`: SQLAlchemy models.
- `api/app/schemas/`: Pydantic schemas.
- `api/app/prompts/`: prompt templates.
- `api/migrations/`: Alembic migrations.
- `api/tests/`: backend tests.

## Frontend

The frontend lives in `web/`.

Main responsibilities:

- Dashboard and game list.
- Game creation workflow.
- Focused play page with streamed narrative updates.
- Game detail, history, status, memory, and character archive pages.
- Settings page for API key, model slots, and task routing.
- Theme switching and mobile layout.

Key directories:

- `web/app/`: Next.js App Router pages.
- `web/components/`: shared UI components.
- `web/lib/`: API client, types, and state helpers.

## AI Generation Flow

Game setup uses a staged flow:

1. Interview gathers the player's concept and confirms the direction.
2. Director-style outline generation produces the overall structure.
3. Section generation runs in smaller pieces to reduce response length and improve fault tolerance.
4. The backend merges and validates the resulting game configuration.
5. A game is persisted with config, lore entries, modes, state, and characters.

Gameplay uses a runtime flow:

1. The player chooses A/B/C/D or submits a free-form action.
2. The turn job builds context from recent turns, worldbook entries, state, summaries, and character data.
3. The GM model streams story content.
4. State extraction runs after the turn.
5. Approved state changes update canonical game state.
6. Memory summaries and context diagnostics are refreshed.

## Persistence

PostgreSQL stores games, turns, state, summaries, lore, characters, runtime settings, and job records. pgvector is used for local vector search over lore entries.

Redis stores job coordination and progress snapshots used by polling and server-sent events.

Uploaded portraits are stored in the `portrait_data` Docker volume by default.
