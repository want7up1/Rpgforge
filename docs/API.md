# API Overview

The API is served by FastAPI. In Docker, browser requests should go through the Next.js proxy on port `3000`.

## Health

- `GET /health`

## Games

- `GET /api/games`
- `POST /api/games`
- `GET /api/games/{game_id}`
- `DELETE /api/games/{game_id}`
- `GET /api/games/{game_id}/memory`
- `GET /api/games/{game_id}/context-diagnostic`
- `POST /api/games/{game_id}/memory/lore/reindex`
- `POST /api/games/{game_id}/memory/summaries/rebuild`

## Generator

- `POST /api/generator/chat`
- `POST /api/generator/chat-jobs`
- `GET /api/generator/chat-jobs/active`
- `GET /api/generator/chat-jobs/{job_id}`
- `GET /api/generator/chat-jobs/{job_id}/events`
- `POST /api/generator/finalize`
- `POST /api/generator/finalize-jobs`
- `GET /api/generator/finalize-jobs/active`
- `GET /api/generator/finalize-jobs/{job_id}`
- `GET /api/generator/finalize-jobs/{job_id}/events`
- `POST /api/generator/create-game`

The job endpoints are preferred for browser clients. Event endpoints use server-sent events and can fall back to polling from the frontend client.

## Turns

- `GET /api/games/{game_id}/turns`
- `POST /api/games/{game_id}/turns`
- `POST /api/games/{game_id}/turns/jobs`
- `GET /api/games/{game_id}/turns/jobs/active`
- `GET /api/games/{game_id}/turns/jobs/{job_id}`
- `GET /api/games/{game_id}/turns/jobs/{job_id}/events`
- `GET /api/games/{game_id}/turns/{turn_id}`

Turn jobs expose incremental narrative progress so the play page can update while the GM model is still working.

## State

- `GET /api/games/{game_id}/state`
- `GET /api/games/{game_id}/state-deltas`
- `PATCH /api/games/{game_id}/state-deltas/{delta_id}`
- `POST /api/games/{game_id}/state-deltas/{delta_id}/approve`
- `POST /api/games/{game_id}/state-deltas/{delta_id}/reject`

## Characters

- `GET /api/games/{game_id}/characters`
- `POST /api/games/{game_id}/characters/sync`
- `GET /api/games/{game_id}/characters/{character_id}`
- `PATCH /api/games/{game_id}/characters/{character_id}`
- `POST /api/games/{game_id}/characters/{character_id}/portrait`
- `DELETE /api/games/{game_id}/characters/{character_id}/portrait`
- `GET /api/games/{game_id}/characters/{character_id}/portrait`

## Settings

- `GET /api/settings/deepseek`
- `PATCH /api/settings/deepseek`

When `SETTINGS_ADMIN_TOKEN` is set, saving settings requires the token. In production mode,
saving settings is rejected if the token is missing.
