from fastapi import FastAPI

from app.database.init_db import init_db

app = FastAPI(
    title="BTT Platform",
    version="0.1.0",
)


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
