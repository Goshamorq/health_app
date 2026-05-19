from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import apply_migrations
from app.routes import dashboard as dashboard_routes
from app.routes import habits as habits_routes
from app.routes import hub as hub_routes
from app.routes import settings as settings_routes
from app.routes import trigger as trigger_routes
from app.routes import weekly as weekly_routes

ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    apply_migrations()
    yield


app = FastAPI(title="health_app", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
app.include_router(dashboard_routes.router)
app.include_router(hub_routes.router)
app.include_router(habits_routes.router)
app.include_router(trigger_routes.router)
app.include_router(weekly_routes.router)
app.include_router(settings_routes.router)
