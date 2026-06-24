from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.config import settings
from app.db import get_db
from app.models import RefreshToken, User
from app.schemas import RefreshRequest, Token, UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def _as_aware_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _issue_tokens(db: Session, user_id: int) -> Token:
    access_token = create_access_token(subject=str(user_id))
    raw_refresh_token = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(raw_refresh_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    db.commit()
    return Token(access_token=access_token, refresh_token=raw_refresh_token)


def _get_active_refresh_token(db: Session, raw_token: str) -> RefreshToken:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token"
    )
    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
    )
    if stored is None or stored.revoked_at is not None:
        raise invalid
    if _as_aware_utc(stored.expires_at) < datetime.now(timezone.utc):
        raise invalid
    return stored


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        language=payload.language,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    return _issue_tokens(db, user.id)


@router.post("/refresh", response_model=Token)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> Token:
    stored = _get_active_refresh_token(db, payload.refresh_token)
    stored.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return _issue_tokens(db, stored.user_id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshRequest, db: Session = Depends(get_db)) -> None:
    stored = _get_active_refresh_token(db, payload.refresh_token)
    stored.revoked_at = datetime.now(timezone.utc)
    db.commit()


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
