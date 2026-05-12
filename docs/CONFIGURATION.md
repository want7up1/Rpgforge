# Configuration

RPGForge can be configured through `.env` and the in-app `/settings` page.

## Environment File

Create a local environment file:

```bash
cp .env.example .env
```

Never commit `.env`.

## Core Variables

| Variable | Required | Description |
| --- | --- | --- |
| `COMPOSE_PROJECT_NAME` | No | Docker Compose project name. |
| `APP_ENV` | No | Application environment label. |
| `DATABASE_URL` | Yes | SQLAlchemy PostgreSQL connection string. |
| `REDIS_URL` | Yes | Redis connection string. |
| `INTERNAL_API_URL` | Yes for web | URL used by Next.js to proxy API requests. |
| `SETTINGS_ADMIN_TOKEN` | Required for public deployments | Token required to save DeepSeek settings. In `APP_ENV=production`, saving is blocked when this token is missing. |

## DeepSeek Settings

DeepSeek can be configured in `.env` or saved from `/settings`.

| Variable | Description |
| --- | --- |
| `DEEPSEEK_API_KEY` | Default API key. |
| `DEEPSEEK_BASE_URL` | Optional OpenAI-compatible DeepSeek endpoint. |
| `DEEPSEEK_FLASH_MODEL` | Default Flash model slot. |
| `DEEPSEEK_PRO_MODEL` | Default Pro model slot. |

Saved settings in the database take precedence over `.env` values. Runtime API keys are stored
in the database in plaintext in this version, so protect database backups and Docker volumes as
secret material.

The settings page also supports task-level model routing. Each AI workflow step can choose the Pro or Flash slot:

- Rule interview.
- Complete configuration generation.
- Story output.
- Story director.
- Drift validation.
- State extraction.
- Memory compression.

Thinking is enabled where the app expects reasoning-heavy behavior. The current DeepSeek thinking effort is configured by the application code for supported calls.

## Public Exposure

Before exposing the app outside a trusted network:

1. Set a strong `SETTINGS_ADMIN_TOKEN`.
2. Use HTTPS through a reverse proxy.
3. Put the app behind an authenticated reverse proxy.
4. Avoid exposing the API container directly.
5. Back up the database and portrait volumes privately.
6. Rotate any API key that may have been used during public testing.

## Optional Audio Variables

The current core app does not require TTS. Audio-related variables remain reserved for future optional extensions:

| Variable | Description |
| --- | --- |
| `MIMO_API_KEY` | Reserved for optional TTS integration. |
| `AUDIO_STORAGE_PATH` | Reserved audio storage path. |
