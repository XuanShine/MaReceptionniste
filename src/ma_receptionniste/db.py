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
        # Les ALTER des clés partent après les catalogues : SQLite refuse une REFERENCES vers une table absente.
        _creer_tables_catalogue(connexion)
        for colonne in manquantes:
            nom_table = engine.dialect.identifier_preparer.format_table(colonne.table)
            definition = _definition_colonne(colonne, engine.dialect)
            connexion.exec_driver_sql(f"ALTER TABLE {nom_table} ADD COLUMN {definition}")
        _reprendre_valeurs_anciennes(connexion, set(ajoutees))
        _retirer_colonnes_remplacees(connexion)
        _fusionner_le_nom_client(connexion)
        _repartir_les_types_de_chambre(connexion)
        _indexer_les_liens_chambre(connexion)
    return ajoutees


def _definition_colonne(colonne: Column, dialect) -> str:
    # CreateColumn sur SQLite omet REFERENCES. Sans elle, un ALTER perd le ON DELETE RESTRICT du modèle.
    definition = str(CreateColumn(colonne).compile(dialect=dialect))
    if not colonne.foreign_keys or "REFERENCES" in definition.upper():
        return definition
    cle = next(iter(colonne.foreign_keys))
    action = cle.ondelete or "RESTRICT"
    return f"{definition} REFERENCES {cle.column.table.name}({cle.column.name}) ON DELETE {action}"


def _creer_tables_catalogue(connexion) -> None:
    from ma_receptionniste.models import OccupationChambre, TypeChambre

    TypeChambre.__table__.create(connexion, checkfirst=True)
    OccupationChambre.__table__.create(connexion, checkfirst=True)


def _repartir_les_types_de_chambre(connexion) -> None:
    """L'ancien texte devient un catalogue. On relit le schéma, pas seulement les colonnes juste ajoutées."""
    if not (_a_colonne(connexion, "chambre", "type_chambre") and _a_colonne(connexion, "chambre", "type_chambre_id")):
        return
    connexion.exec_driver_sql(
        "INSERT INTO type_chambre (libelle) "
        "SELECT DISTINCT trim(type_chambre) FROM chambre "
        "WHERE type_chambre IS NOT NULL AND trim(type_chambre) != '' "
        "AND trim(type_chambre) NOT IN (SELECT libelle FROM type_chambre)"
    )
    connexion.exec_driver_sql(
        "UPDATE chambre SET type_chambre_id = ("
        "SELECT id FROM type_chambre WHERE libelle = trim(chambre.type_chambre)"
        ") WHERE type_chambre_id IS NULL AND type_chambre IS NOT NULL AND trim(type_chambre) != ''"
    )
    connexion.exec_driver_sql("ALTER TABLE chambre DROP COLUMN type_chambre")


def _indexer_les_liens_chambre(connexion) -> None:
    for nom in ("type_chambre_id", "occupation_chambre_id"):
        if _a_colonne(connexion, "chambre", nom):
            connexion.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS ix_chambre_{nom} ON chambre ({nom})")


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


def _fusionner_le_nom_client(connexion) -> None:
    """L'écran montrait le prénom puis le nom. On recolle cet ordre dans nom avant de retirer l'ancienne colonne."""
    if not _a_colonne(connexion, "client", "prenom"):
        return
    connexion.exec_driver_sql(
        "UPDATE client SET nom = trim(prenom || ' ' || nom) WHERE prenom IS NOT NULL AND trim(prenom) != ''"
    )
    connexion.exec_driver_sql("ALTER TABLE client DROP COLUMN prenom")


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
