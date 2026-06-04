from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import admin, characters, gameplay, games, generator, modules, progress, states
from app.routers import settings as settings_router

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="State-driven AI text RPG engine.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=(
        r"https?://("
        r"localhost|127\.0\.0\.1|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
        r")(:\d+)?"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "rpgforge-api",
        "version": "0.1.0",
        "environment": settings.app_env,
        "timestamp": datetime.now(UTC).isoformat(),
    }


app.include_router(games.router)
app.include_router(characters.router)
app.include_router(generator.router)
app.include_router(gameplay.router)
app.include_router(progress.router)
app.include_router(states.router)
app.include_router(settings_router.router)
app.include_router(admin.router)
app.include_router(modules.router)
