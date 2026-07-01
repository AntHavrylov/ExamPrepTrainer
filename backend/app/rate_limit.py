import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status

from app.auth.deps import get_current_user
from app.config import settings
from app.models import User

_hits: dict[int, deque[float]] = defaultdict(deque)
_auth_hits: dict[str, deque[float]] = defaultdict(deque)


def _check_bucket(hits: dict, key, max_requests: int, window_seconds: int) -> None:
    now = time.monotonic()
    bucket = hits[key]

    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()

    if len(bucket) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded, please try again shortly",
        )

    bucket.append(now)


def check_ai_rate_limit(user_id: int) -> None:
    _check_bucket(_hits, user_id, settings.ai_rate_limit_max_requests, settings.ai_rate_limit_window_seconds)


def enforce_ai_rate_limit(current_user: User = Depends(get_current_user)) -> User:
    check_ai_rate_limit(current_user.id)
    return current_user


def check_auth_rate_limit(key: str) -> None:
    _check_bucket(
        _auth_hits, key, settings.auth_rate_limit_max_requests, settings.auth_rate_limit_window_seconds
    )


def enforce_auth_rate_limit(request: Request) -> None:
    # Keyed by client IP (not email) so this can't be used to lock a victim
    # out of their own account by spamming their email from elsewhere.
    client_host = request.client.host if request.client else "unknown"
    check_auth_rate_limit(client_host)
