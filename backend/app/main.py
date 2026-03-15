import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import api_router
from .database import engine, Base

logger = logging.getLogger(__name__)

# Create tables on startup (no-op if they already exist; non-fatal so the
# server starts even if the DB is temporarily unreachable).
try:
    Base.metadata.create_all(bind=engine)
except Exception as exc:
    logger.warning("create_all skipped — DB not reachable at startup: %s", exc)

app = FastAPI(
    title="SolaraDashboard API",
    description="Sales & inventory aggregation API for multi-portal e-commerce",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3131",
        "https://solara-frontend-891651347357.asia-south1.run.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
