# Deployment

RPGForge is designed to run behind one public web port.

## Docker Compose

Start the stack:

```bash
cp .env.example .env
docker compose up -d --build
```

Check service state:

```bash
docker compose ps
```

View logs:

```bash
docker compose logs -f web api worker
```

## Port Layout

By default:

- Public browser traffic uses `web:3000`.
- The API listens on `api:8000` inside the Docker network.
- PostgreSQL and Redis are internal services.

External reverse proxies should point to the web container or host port `3000`. Do not route browser traffic directly to `8000` unless you intentionally expose the API.

## Reverse Proxy Notes

For Nginx, Caddy, Cloudflare Tunnel, or similar tools:

- Proxy the public domain to `http://127.0.0.1:3000`.
- Keep long-lived HTTP connections enabled for server-sent events.
- Increase request and response timeouts for long AI generation jobs.
- Use HTTPS.
- Consider access control if the instance contains private game data.

## Data Volumes

Docker volumes:

- `postgres_data`: database.
- `audio_data`: reserved for optional audio output.
- `portrait_data`: uploaded character portraits.

These volumes may contain private user data. Do not publish or commit them.

## Updating

After code changes:

```bash
docker compose up -d --build
```

The API container runs Alembic migrations on startup.

## Backup

Back up the database and portrait volume before upgrading a public instance.

Example database dump:

```bash
docker compose exec postgres pg_dump -U rpg rpgforge > rpgforge.sql
```

Store backups privately.
