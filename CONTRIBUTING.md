# Contributing

Thanks for your interest in RPGForge.

This project is in early public preview. Contributions are welcome, but large changes should start with an issue so the design can be discussed before implementation.

## Development Setup

Start the full stack:

```bash
cp .env.example .env
docker compose up -d --build
```

Run backend checks:

```bash
cd api
ruff check .
pytest
```

Run frontend checks:

```bash
cd web
npm run lint
npm run build
```

## Pull Request Guidelines

- Keep changes scoped to one feature or fix.
- Include tests for backend behavior changes.
- Run the relevant checks before opening a pull request.
- Update documentation when configuration, API behavior, deployment, or user workflow changes.
- Never commit `.env`, API keys, database dumps, generated private games, or uploaded portraits.

## Code Style

- Backend uses FastAPI, SQLAlchemy, Alembic, pytest, and Ruff.
- Frontend uses Next.js, React, TypeScript, and ESLint.
- Prefer existing project patterns over new abstractions.
