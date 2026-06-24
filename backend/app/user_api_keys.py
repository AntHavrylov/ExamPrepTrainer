from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crypto import decrypt, encrypt
from app.models import UserApiKey

PROVIDER_OPENROUTER = "openrouter"


def get_user_api_key_row(db: Session, user_id: int) -> UserApiKey | None:
    return db.scalar(select(UserApiKey).where(UserApiKey.user_id == user_id))


def get_effective_credentials(db: Session, user_id: int) -> tuple[str, str] | None:
    """Returns (api_key, model) for the user's saved key, or None if unset."""
    row = get_user_api_key_row(db, user_id)
    if row is None:
        return None
    return decrypt(row.encrypted_api_key), row.model


def save_user_api_key(db: Session, user_id: int, api_key: str, model: str) -> UserApiKey:
    row = get_user_api_key_row(db, user_id)
    encrypted = encrypt(api_key)
    if row is None:
        row = UserApiKey(
            user_id=user_id, provider=PROVIDER_OPENROUTER, encrypted_api_key=encrypted, model=model
        )
        db.add(row)
    else:
        row.encrypted_api_key = encrypted
        row.model = model
    db.commit()
    db.refresh(row)
    return row


def delete_user_api_key(db: Session, user_id: int) -> None:
    row = get_user_api_key_row(db, user_id)
    if row is not None:
        db.delete(row)
        db.commit()
