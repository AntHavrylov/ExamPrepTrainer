import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, status

from app.auth.deps import get_current_user
from app.config import settings
from app.models import User

_hits: dict[int, deque[float]] = defaultdict(deque)


def check_ai_rate_limit(user_id: int) -> None:
    now = time.monotonic()
    window = settings.ai_rate_limit_window_seconds
    bucket = _hits[user_id]

    while bucket and now - bucket[0] > window:
        bucket.popleft()

    if len(bucket) >= settings.ai_rate_limit_max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded, please try again shortly",
        )

    bucket.append(now)


def enforce_ai_rate_limit(current_user: User = Depends(get_current_user)) -> User:
    check_ai_rate_limit(current_user.id)
    return current_user
