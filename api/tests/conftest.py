import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://rpg:rpg@postgres:5432/rpgforge_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import app.models  # noqa: E402,F401
from app.db.session import Base, SessionLocal, engine  # noqa: E402


def ensure_test_database() -> None:
    test_url = make_url(TEST_DATABASE_URL)
    database_name = test_url.database
    if not database_name:
        raise RuntimeError("TEST_DATABASE_URL must include a database name.")

    admin_engine = create_engine(test_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    quoted_name = database_name.replace('"', '""')
    with admin_engine.connect() as connection:
        exists = connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
            {"database_name": database_name},
        )
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{quoted_name}"'))
    admin_engine.dispose()


def recreate_schema() -> None:
    ensure_test_database()
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture()
def reset_database():
    recreate_schema()
    try:
        yield
    finally:
        recreate_schema()


@pytest.fixture()
def db_session(reset_database) -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
