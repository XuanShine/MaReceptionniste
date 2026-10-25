import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, event
from sqlmodel import Session, create_engine

GOUVERNANTE_DATABASE_URL = os.environ.get("GOUVERNANTE_DATABASE_URL", "sqlite:///ma_gouvernante.db")

engine = create_engine(
    GOUVERNANTE_DATABASE_URL,
    connect_args={"check_same_thread": False} if GOUVERNANTE_DATABASE_URL.startswith("sqlite") else {},
)


@event.listens_for(engine, "connect")
def _activer_cles_etrangeres(dbapi_connection, _) -> None:
    if GOUVERNANTE_DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_db_and_tables(moteur: Engine = engine) -> None:
    from ma_gouvernante.models import GouvernanteModel

    GouvernanteModel.metadata.create_all(moteur)


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
