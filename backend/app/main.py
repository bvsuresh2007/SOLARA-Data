from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import api_router
from .database import engine, Base

# Create tables (Alembic handles migrations in production; this is for dev)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SolaraDashboard API",
    description="Sales & inventory aggregation API for multi-portal e-commerce",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
