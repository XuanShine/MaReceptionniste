"""Moteur SQLite et création des tables."""

import os
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine

DB_PATH = Path(__file__).resolve().parent.parent / "hotel_pms.db"


def creer_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, echo=os.environ.get("SQL_ECHO") == "1")
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _cles_etrangeres(connexion, _):
            curseur = connexion.cursor()
            curseur.execute("PRAGMA foreign_keys=ON")
            curseur.close()

    return engine


def initialiser(engine: Engine, reset: bool = False) -> None:
    import hotel_pms.models  # noqa: F401
    from hotel_pms.seed import alimenter

    if reset:
        SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    alimenter(engine, forcer=reset)


def preparer_url(url: str) -> str:
    if url.startswith("sqlite:///"):
        chemin = Path(url.removeprefix("sqlite:///"))
        if chemin.parent and str(chemin.parent) not in ("", "."):
            chemin.parent.mkdir(parents=True, exist_ok=True)
    return url
