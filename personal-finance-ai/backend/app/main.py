import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.full_routes import router as full_router
from app.api.routes import router
from app.core.config import settings
from app.db import base  # noqa: F401
from app.db.init_db import seed_defaults
from app.db.migrations import run_additive_migrations
from app.db.session import Base, SessionLocal, engine
from app.services.duplicate_detection import reconcile_duplicate_flags
from app.services.market_data_service import refresh_market_data_if_due


async def _market_refresh_loop() -> None:
    while True:
        await asyncio.sleep(60)
        with SessionLocal() as db:
            await asyncio.to_thread(refresh_market_data_if_due, db)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    run_additive_migrations(engine)
    for directory in (
        settings.uploads_dir,
        settings.processed_dir,
        settings.reports_dir,
        settings.chroma_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        seed_defaults(db)
        reconcile_duplicate_flags(db)
    market_task = asyncio.create_task(_market_refresh_loop())
    try:
        yield
    finally:
        market_task.cancel()
        try:
            await market_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_origin_regex=(
        r"^https?://("
        r"localhost|127\.0\.0\.1|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
        r")(:\d+)?$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix=settings.api_prefix)
app.include_router(full_router, prefix=settings.api_prefix)

if settings.frontend_dist_dir.exists():
    app.mount(
        "/",
        StaticFiles(directory=settings.frontend_dist_dir, html=True),
        name="frontend",
    )
