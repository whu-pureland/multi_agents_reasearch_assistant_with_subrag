from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_events import router as events_router
from app.api.routes_interactions import router as interactions_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_tools import router as tools_router
from app.api.routes_uploads import router as uploads_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(jobs_router, prefix=settings.api_prefix, tags=["jobs"])
    app.include_router(uploads_router, prefix=settings.api_prefix, tags=["uploads"])
    app.include_router(events_router, prefix=settings.api_prefix, tags=["events"])
    app.include_router(interactions_router, prefix=settings.api_prefix, tags=["interactions"])
    app.include_router(tools_router, prefix=settings.api_prefix, tags=["tools"])

    return app


app = create_app()
