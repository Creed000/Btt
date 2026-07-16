from fastapi import FastAPI

from app.database.init_db import init_db
from app.api import api_router

app = FastAPI(
    title="BTT Platform",
    version="0.1.0",
)

# Подключение API
app.include_router(api_router, prefix="/api/v1")

@app.on_event("startup")
async def startup():
    init_db()

@app.get("/")
async def root():
    return {
        "project": "BTT",
        "status": "running",
        "version": "0.1.0",
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy"
    }

@app.get("/ready")
async def ready():
    return {
        "status": "ready"
    }

@app.get("/version")
async def version():
    return {
        "version": "0.1.0"
    }
