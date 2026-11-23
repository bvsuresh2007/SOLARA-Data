import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import api_router
from .auth import require_api_key
from .config import settings
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
    allow_origins=settings.allowed_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# /api requires an API key for programmatic callers (the autonomous runner);
# the browser dashboard is allowed through by trusted Origin. Auth is a no-op
# until DASHBOARD_API_KEYS is set. See app/auth.py.
app.include_router(api_router, prefix="/api", dependencies=[Depends(require_api_key)])

if settings.api_key_set():
    logger.info("External API auth ENABLED (%d key(s) configured)", len(settings.api_key_set()))
else:
    logger.warning("External API auth DISABLED — DASHBOARD_API_KEYS is empty; /api is open")


@app.get("/health")
def health():
    return {"status": "ok"}
