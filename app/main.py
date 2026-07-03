import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import close_pool, fetch_one, init_pool
from app.routers import analytics, forum, kqxs, predictions, rbk, stats, ums
from app.scheduler import create_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    logger.info("PostgreSQL pool ready")
    scheduler = None
    if settings.enable_scheduler:
        scheduler = create_scheduler()
        scheduler.start()
        logger.info("Scheduler started")
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
    close_pool()
    logger.info("Shutdown complete")


app = FastAPI(title="Lottery Analytics", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(kqxs.router)
app.include_router(rbk.router)
app.include_router(ums.router)
app.include_router(analytics.router)
app.include_router(stats.router)
app.include_router(predictions.router)
app.include_router(forum.router)


@app.get("/health")
def health():
    try:
        row = fetch_one("SELECT 1 AS ok")
        db_ok = row is not None
    except Exception:
        logger.exception("Health check DB query failed")
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": "postgres" if db_ok else "down"}
