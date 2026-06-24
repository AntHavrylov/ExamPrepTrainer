from fastapi import FastAPI

from app.config import settings
from app.routers import ai, auth, question_bank, sections, sessions, settings as settings_router

app = FastAPI(title=settings.app_name)

app.include_router(auth.router)
app.include_router(sections.router)
app.include_router(ai.router)
app.include_router(sessions.router)
app.include_router(settings_router.router)
app.include_router(question_bank.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
