from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import (
    analytics,
    dashboard,
    equipment,
    exercises,
    history,
    plan_assistant,
    profiles,
    sessions,
    templates,
)

settings = get_settings()
settings.media_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Workout Pal API",
    description="Personal home-gym trainer and workout tracker.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (profiles, dashboard, exercises, equipment, templates, plan_assistant, sessions, history, analytics):
    app.include_router(module.router)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")
