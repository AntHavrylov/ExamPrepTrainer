from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory():
    """Exposes the session factory itself (not an opened session).

    FastAPI closes `yield`-dependencies like `get_db` as soon as the route
    function returns, before a StreamingResponse body actually streams. Code
    that needs to write to the DB after streaming has started must open its
    own session via this factory instead of reusing the request-scoped one.
    """
    return SessionLocal
