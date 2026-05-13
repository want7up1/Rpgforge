from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _connect_args_for_url(database_url: str) -> dict[str, object]:
    url = make_url(database_url)
    if url.drivername == "postgresql+psycopg":
        return {"prepare_threshold": None}
    return {}


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args=_connect_args_for_url(settings.database_url),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


def dispose_db_connections() -> None:
    engine.dispose(close=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
