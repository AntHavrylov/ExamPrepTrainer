from fastapi import APIRouter, Depends, HTTPException, status

from app.ai.client import AIClientError, OpenRouterClient, get_ai_client
from app.auth.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/ping")
async def ping(
    current_user: User = Depends(get_current_user),
    ai_client: OpenRouterClient = Depends(get_ai_client),
) -> dict[str, str]:
    try:
        text = await ai_client.complete([{"role": "user", "content": "Say hello in one word"}])
    except AIClientError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return {"response": text}
