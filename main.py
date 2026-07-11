from fastapi import FastAPI

app = FastAPI(
    title="BTT Platform",
    version="0.1.0",
)

@app.get("/")
async def root():
    return {
        "project": "BTT",
        "status": "running",
        "version": "0.1.0"
    }
