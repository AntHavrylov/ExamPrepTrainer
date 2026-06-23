from fastapi import FastAPI

from app.config import settings
from app.routers import ai, auth, sections, sessions

app = FastAPI(title=settings.app_name)

app.include_router(auth.router)
app.include_router(sections.router)
app.include_router(ai.router)
app.include_router(sessions.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
