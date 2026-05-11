# RPGForge Web

Next.js frontend for RPGForge.

The web app provides the dashboard, game creation workflow, focused play UI, game detail pages, history, status, memory tools, character archives, theme switching, and settings.

## Requirements

- Node.js 22+
- npm 11+

## Run Locally

```bash
npm install
INTERNAL_API_URL=http://localhost:8000 npm run dev
```

Open http://localhost:3000.

## Docker

In Docker, the browser only talks to the web port. Next.js proxies `/api/*` and `/health` to the API service through Docker's internal network.

```bash
docker compose up -d --build web
```

## Scripts

- `npm run dev`: start the development server.
- `npm run build`: build the production app.
- `npm run start`: start the production server.
- `npm run lint`: run ESLint.

## UI Areas

- `/`: dashboard.
- `/games`: game list and delete actions.
- `/games/new`: AI-assisted game setup.
- `/games/[id]`: game detail.
- `/games/[id]/play`: focused story and player action interface.
- `/games/[id]/history`: previous turns.
- `/games/[id]/status`: player-facing structured state.
- `/games/[id]/memory`: worldbook and context diagnostics.
- `/games/[id]/characters`: character archive and portraits.
- `/settings`: DeepSeek settings and task-level model routing.
