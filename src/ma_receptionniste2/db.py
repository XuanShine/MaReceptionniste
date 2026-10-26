import os

from sqlalchemy import Engine, event
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from ma_receptionniste2.models import Base

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///ma_receptionniste2.db")


def moteur(url: str, *, echo: bool = False) -> Engine:
    arguments: dict = {"echo": echo}
    if url.startswith("sqlite"):
        arguments["connect_args"] = {"check_same_thread": False}
    if url == "sqlite://":
        # Une base :memory: est privée à chaque connexion sans un pool statique.
        arguments["poolclass"] = StaticPool
    engine = create_engine(url, **arguments)
    preparer(engine)
    return engine


def preparer(engine: Engine) -> None:
    # L'identité mémoire d'un moteur est recyclée. On marque l'objet lui-même.
    if getattr(engine, "_cles_etrangeres", False):
        return
    engine._cles_etrangeres = True  # type: ignore[attr-defined]

    @event.listens_for(engine, "connect")
    def _activer_cles_etrangeres(dbapi_connection, _) -> None:
        # SQLite ignore les clés étrangères tant que ce pragma n'est pas posé.
        if engine.url.get_backend_name() == "sqlite":
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()


def creer_tables(engine: Engine) -> None:
    preparer(engine)
    Base.metadata.create_all(engine)


def moteur_par_defaut() -> Engine:
    return moteur(DATABASE_URL, echo=os.environ.get("SQL_ECHO") == "1")
