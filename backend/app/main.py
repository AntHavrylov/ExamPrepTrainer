from fastapi import FastAPI

from app.config import settings
from app.routers import auth

app = FastAPI(title=settings.app_name)

app.include_router(auth.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
