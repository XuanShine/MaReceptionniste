import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///ma_receptionniste.db")

engine = create_engine(
    DATABASE_URL,
    echo=os.environ.get("SQL_ECHO") == "1",
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)


@event.listens_for(engine, "connect")
def _activer_cles_etrangeres(dbapi_connection, _) -> None:
    # SQLite ignore les clés étrangères tant que ce pragma n'est pas posé.
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


COLONNES_AJOUTEES = {
    "client": {
        "pays": "VARCHAR",
    },
    "reservation": {
        "etat_dossier": "VARCHAR NOT NULL DEFAULT 'en_cours'",
        "traite": "INTEGER NOT NULL DEFAULT 0",
        "nom_occupant": "VARCHAR",
        "partenaire": "VARCHAR",
        "type_voiture": "VARCHAR",
        "date_facture": "DATE",
        "numero_facture": "VARCHAR",
        "notes": "TEXT",
        "notes_internes": "TEXT",
        "notes_tempo": "TEXT",
        "notes_facturation": "TEXT",
    },
    "sejour": {
        "type_produit": "VARCHAR",
        "prix_ttc": "NUMERIC",
        "remise_pct": "NUMERIC NOT NULL DEFAULT 0",
        "adultes": "INTEGER NOT NULL DEFAULT 1",
        "enfants": "INTEGER NOT NULL DEFAULT 0",
        "taxe_sejour": "NUMERIC",
    },
}


def preparer_base(cible=None) -> None:
    from ma_receptionniste import models  # noqa: F401

    base = engine if cible is None else cible
    SQLModel.metadata.create_all(base)
    with base.begin() as connection:
        for table, colonnes in COLONNES_AJOUTEES.items():
            presentes = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info('{table}')")}
            for nom, ddl in colonnes.items():
                if nom not in presentes:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {nom} {ddl}")


def create_db_and_tables() -> None:
    preparer_base()


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
