from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import ai, auth, question_bank, sections, sessions, settings as settings_router

app = FastAPI(title=settings.app_name)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # Strip the `input` field from Pydantic v2 errors — it echoes the full
    # request value back in the response body, which can be megabytes for a
    # large document submission and is never useful to the client.
    errors = [
        {k: v for k, v in err.items() if k != "input"}
        for err in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})

app.include_router(auth.router)
app.include_router(sections.router)
app.include_router(ai.router)
app.include_router(sessions.router)
app.include_router(settings_router.router)
app.include_router(question_bank.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
