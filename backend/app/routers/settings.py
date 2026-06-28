import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.client import AIClientError, get_ai_provider_factory, get_default_ai_provider
from app.ai.provider import AIProvider, ModelInfo
from app.auth.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas import (
    ApiKeySaveRequest,
    ApiKeyStatusRead,
    LanguageUpdate,
    ModelOption,
    ModelUpdateRequest,
    SessionLengthUpdate,
    UserRead,
)
from app.user_api_keys import delete_user_api_key, get_user_api_key_row, save_user_api_key

router = APIRouter(prefix="/settings", tags=["settings"])

_MODELS_CACHE_TTL_SECONDS = 3600
_models_cache: tuple[float, list[ModelInfo]] | None = None


async def _list_models_cached(ai_client: AIProvider) -> list[ModelInfo]:
    global _models_cache
    now = time.monotonic()
    if _models_cache is not None and now - _models_cache[0] < _MODELS_CACHE_TTL_SECONDS:
        return _models_cache[1]

    models = await ai_client.list_models()
    _models_cache = (now, models)
    return models


@router.get("/models", response_model=list[ModelOption])
async def list_models(
    current_user: User = Depends(get_current_user),
    ai_client: AIProvider = Depends(get_default_ai_provider),
) -> list[ModelInfo]:
    try:
        return await _list_models_cached(ai_client)
    except AIClientError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.get("/api-key", response_model=ApiKeyStatusRead)
def get_api_key_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiKeyStatusRead:
    row = get_user_api_key_row(db, current_user.id)
    if row is None:
        return ApiKeyStatusRead(has_key=False)
    return ApiKeyStatusRead(has_key=True, model=row.model)


@router.put("/api-key", response_model=ApiKeyStatusRead)
async def save_api_key(
    payload: ApiKeySaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider_factory=Depends(get_ai_provider_factory),
) -> ApiKeyStatusRead:
    candidate = provider_factory(api_key=payload.api_key, model=payload.model)
    if not await candidate.validate_key():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That API key could not be verified with OpenRouter. Double-check it and try again.",
        )

    row = save_user_api_key(db, current_user.id, payload.api_key, payload.model)
    return ApiKeyStatusRead(has_key=True, model=row.model)


@router.patch("/api-key", response_model=ApiKeyStatusRead)
def update_model(
    payload: ModelUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiKeyStatusRead:
    row = get_user_api_key_row(db, current_user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No API key saved")
    row.model = payload.model
    db.commit()
    db.refresh(row)
    return ApiKeyStatusRead(has_key=True, model=row.model)


@router.delete("/api-key", status_code=status.HTTP_204_NO_CONTENT)
def remove_api_key(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    delete_user_api_key(db, current_user.id)


@router.put("/language", response_model=UserRead)
def update_language(
    payload: LanguageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    current_user.language = payload.language
    db.commit()
    db.refresh(current_user)
    return current_user


@router.put("/session-length", response_model=UserRead)
def update_session_length(
    payload: SessionLengthUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    current_user.session_length = payload.session_length
    db.commit()
    db.refresh(current_user)
    return current_user
