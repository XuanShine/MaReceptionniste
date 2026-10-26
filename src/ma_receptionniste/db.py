import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Column, Engine, event, inspect
from sqlalchemy.schema import CreateColumn
from sqlmodel import Session, SQLModel, create_engine

logger = logging.getLogger(__name__)

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


class ColonneNonAjoutable(RuntimeError):
    """Une colonne du modèle manque en base et ne peut pas être ajoutée sans valeur."""


def create_db_and_tables(engine: Engine = engine) -> None:
    from ma_receptionniste import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    for colonne in ajouter_colonnes_manquantes(engine):
        logger.info("Colonne ajoutée : %s", colonne)


def ajouter_colonnes_manquantes(engine: Engine) -> list[str]:
    """Ajoute les colonnes du modèle absentes des tables existantes, car create_all ne touche pas une table présente."""
    inspecteur = inspect(engine)
    tables_en_base = set(inspecteur.get_table_names())
    manquantes: list[Column] = []
    for table in SQLModel.metadata.sorted_tables:
        if table.name not in tables_en_base:
            continue
        presentes = {colonne["name"] for colonne in inspecteur.get_columns(table.name)}
        manquantes += [colonne for colonne in table.columns if colonne.name not in presentes]
    for colonne in manquantes:
        if not colonne.nullable and colonne.server_default is None:
            raise ColonneNonAjoutable(
                f"{colonne.table.name}.{colonne.name} manque en base : "
                "rendez-la nullable ou donnez-lui un server_default"
            )
    ajoutees = [f"{colonne.table.name}.{colonne.name}" for colonne in manquantes]
    with engine.begin() as connexion:
        for colonne in manquantes:
            nom_table = engine.dialect.identifier_preparer.format_table(colonne.table)
            definition = CreateColumn(colonne).compile(dialect=engine.dialect)
            connexion.exec_driver_sql(f"ALTER TABLE {nom_table} ADD COLUMN {definition}")
        _reprendre_valeurs_anciennes(connexion, set(ajoutees))
        _retirer_colonnes_remplacees(connexion)
    return ajoutees


def _a_colonne(connexion, table: str, colonne: str) -> bool:
    noms = {ligne[1] for ligne in connexion.exec_driver_sql(f"PRAGMA table_info('{table}')")}
    return colonne in noms


def _reprendre_valeurs_anciennes(connexion, ajoutees: set[str]) -> None:
    """Recopie les euros d'un schéma antérieur, seulement pour les colonnes qui viennent d'être ajoutées."""
    if "sejour.prix_nuit_centimes" in ajoutees and _a_colonne(connexion, "sejour", "prix_ttc"):
        connexion.exec_driver_sql(
            "UPDATE sejour SET prix_nuit_centimes = CAST(ROUND(prix_ttc * 100) AS INTEGER) WHERE prix_ttc IS NOT NULL"
        )
    if "reglement.montant_centimes" in ajoutees and _a_colonne(connexion, "reglement", "montant"):
        connexion.exec_driver_sql(
            "UPDATE reglement SET montant_centimes = CAST(ROUND(montant * 100) AS INTEGER) WHERE montant IS NOT NULL"
        )
        connexion.exec_driver_sql("UPDATE reglement SET mode = 'carte' WHERE mode = 'CB'")
    if "reglement.date" in ajoutees and _a_colonne(connexion, "reglement", "jour"):
        connexion.exec_driver_sql("UPDATE reglement SET date = date(jour) || ' 00:00:00' WHERE jour IS NOT NULL")


def _retirer_colonnes_remplacees(connexion) -> None:
    """Ces colonnes ne sont plus dans le modèle. NOT NULL les fait rejeter tout INSERT qui ne les nomme pas."""
    if _a_colonne(connexion, "reglement", "jour") and _a_colonne(connexion, "reglement", "date"):
        connexion.exec_driver_sql(
            "UPDATE reglement SET date = date(jour) || ' 00:00:00' "
            "WHERE jour IS NOT NULL AND date = '1970-01-01 00:00:00'"
        )
    if _a_colonne(connexion, "consommation", "jour") and _a_colonne(connexion, "consommation", "date"):
        connexion.exec_driver_sql(
            "UPDATE consommation SET date = date(jour) || ' 00:00:00' "
            "WHERE jour IS NOT NULL AND date = '1970-01-01 00:00:00'"
        )
    remplacees = (
        ("reglement", "montant", "montant_centimes"),
        ("reglement", "jour", "date"),
        ("consommation", "jour", "date"),
    )
    for table, ancienne, nouvelle in remplacees:
        if _a_colonne(connexion, table, ancienne) and _a_colonne(connexion, table, nouvelle):
            connexion.exec_driver_sql(f"ALTER TABLE {table} DROP COLUMN {ancienne}")


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
