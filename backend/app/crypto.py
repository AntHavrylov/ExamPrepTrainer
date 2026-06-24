from cryptography.fernet import Fernet

from app.config import settings

_fernet = Fernet(settings.api_key_encryption_key.encode())


def encrypt(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet.decrypt(token.encode()).decode()
