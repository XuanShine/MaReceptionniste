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


class CatalogueIllisible(RuntimeError):
    """Deux types portent le même libellé. Aucune ligne n'est fusionnée ni supprimée."""


_TABLES_CATALOGUE = frozenset({"type_chambre", "occupation_chambre"})


def create_db_and_tables(engine: Engine = engine) -> None:
    from ma_receptionniste import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    for colonne in ajouter_colonnes_manquantes(engine):
        logger.info("Colonne ajoutée : %s", colonne)
    _preparer_facturation(engine)


def ajouter_colonnes_manquantes(engine: Engine) -> list[str]:
    """Ajoute les colonnes du modèle absentes des tables existantes, car create_all ne touche pas une table présente."""
    inspecteur = inspect(engine)
    tables_en_base = set(inspecteur.get_table_names())
    manquantes: list[Column] = []
    for table in SQLModel.metadata.sorted_tables:
        if table.name not in tables_en_base or table.name in _TABLES_CATALOGUE:
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

    def _appliquer(connexion) -> None:
        for colonne in manquantes:
            nom_table = engine.dialect.identifier_preparer.format_table(colonne.table)
            definition = _definition_colonne(colonne, engine.dialect)
            connexion.exec_driver_sql(f"ALTER TABLE {nom_table} ADD COLUMN {definition}")
        _reprendre_valeurs_anciennes(connexion, set(ajoutees))
        _retirer_colonnes_remplacees(connexion)
        _creer_tables_catalogue(connexion)
        if _table_existe(connexion, "type_chambre") and not _a_colonne(connexion, "type_chambre", "libelle"):
            connexion.exec_driver_sql("ALTER TABLE type_chambre ADD COLUMN libelle VARCHAR")
            ajoutees.append("type_chambre.libelle")
        _remplir_libelle_depuis_name(connexion)
        _repartir_les_types_de_chambre(connexion)
        _indexer_libelle(connexion)
        _ajouter_champs_type_chambre(connexion, ajoutees)
        _archiver_anciennes_cellules_virtuelles(connexion)
        _retirer_tarif_bb(connexion)
        _indexer_les_liens_chambre(connexion)

    _executer_en_transaction(engine, _appliquer)
    return ajoutees


def _executer_en_transaction(engine: Engine, travail) -> None:
    with engine.connect() as connexion:
        connexion.exec_driver_sql("BEGIN")
        try:
            travail(connexion)
            connexion.exec_driver_sql("COMMIT")
        except Exception:
            connexion.exec_driver_sql("ROLLBACK")
            raise


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


def _remplir_libelle_depuis_name(connexion) -> None:
    if not (_a_colonne(connexion, "type_chambre", "libelle") and _a_colonne(connexion, "type_chambre", "name")):
        return
    connexion.exec_driver_sql(
        "UPDATE type_chambre SET libelle = trim(name) "
        "WHERE (libelle IS NULL OR trim(libelle) = '') AND name IS NOT NULL AND trim(name) != ''"
    )


def _repartir_les_types_de_chambre(connexion) -> None:
    if not (_a_colonne(connexion, "chambre", "type_chambre") and _a_colonne(connexion, "chambre", "type_chambre_id")):
        return
    # NOT IN devient inconnu pour toutes les lignes dès qu'un libellé catalogue est NULL.
    connexion.exec_driver_sql(
        "INSERT INTO type_chambre (libelle) "
        "SELECT DISTINCT trim(type_chambre) FROM chambre "
        "WHERE type_chambre IS NOT NULL AND trim(type_chambre) != '' "
        "AND NOT EXISTS ("
        "SELECT 1 FROM type_chambre AS connu WHERE connu.libelle = trim(chambre.type_chambre)"
        ")"
    )
    connexion.exec_driver_sql(
        "UPDATE chambre SET type_chambre_id = ("
        "SELECT id FROM type_chambre WHERE libelle = trim(chambre.type_chambre)"
        ") WHERE type_chambre_id IS NULL AND type_chambre IS NOT NULL AND trim(type_chambre) != ''"
    )
    connexion.exec_driver_sql("ALTER TABLE chambre DROP COLUMN type_chambre")


def _indexer_libelle(connexion) -> None:
    if not _a_colonne(connexion, "type_chambre", "libelle"):
        return
    doublon = connexion.exec_driver_sql(
        "SELECT libelle FROM type_chambre WHERE libelle IS NOT NULL GROUP BY libelle HAVING COUNT(*) > 1"
    ).first()
    if doublon is not None:
        raise CatalogueIllisible("Plusieurs types portent le même libellé")
    connexion.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uq_type_chambre_libelle ON type_chambre(libelle)")


def _ajouter_champs_type_chambre(connexion, ajoutees: list[str]) -> None:
    if not _table_existe(connexion, "type_chambre"):
        return
    if not _a_colonne(connexion, "type_chambre", "wubook_id"):
        connexion.exec_driver_sql("ALTER TABLE type_chambre ADD COLUMN wubook_id INTEGER")
        ajoutees.append("type_chambre.wubook_id")
    if not _a_colonne(connexion, "type_chambre", "description"):
        connexion.exec_driver_sql("ALTER TABLE type_chambre ADD COLUMN description VARCHAR NOT NULL DEFAULT ''")
        ajoutees.append("type_chambre.description")
    if not _a_colonne(connexion, "type_chambre", "disponibilite"):
        connexion.exec_driver_sql("ALTER TABLE type_chambre ADD COLUMN disponibilite INTEGER NOT NULL DEFAULT 0")
        ajoutees.append("type_chambre.disponibilite")
        if _a_colonne(connexion, "type_chambre", "availability"):
            connexion.exec_driver_sql(
                "UPDATE type_chambre SET disponibilite = availability WHERE availability IS NOT NULL"
            )
    if not _a_colonne(connexion, "type_chambre", "nom_raccourci"):
        connexion.exec_driver_sql("ALTER TABLE type_chambre ADD COLUMN nom_raccourci VARCHAR(4)")
        ajoutees.append("type_chambre.nom_raccourci")
        if _a_colonne(connexion, "type_chambre", "shortname"):
            connexion.exec_driver_sql(
                "UPDATE type_chambre SET nom_raccourci = trim(shortname) "
                "WHERE shortname IS NOT NULL AND trim(shortname) != ''"
            )
    if not _a_colonne(connexion, "type_chambre", "prix_defaut"):
        connexion.exec_driver_sql("ALTER TABLE type_chambre ADD COLUMN prix_defaut FLOAT NOT NULL DEFAULT 0")
        ajoutees.append("type_chambre.prix_defaut")
        if _a_colonne(connexion, "type_chambre", "price"):
            connexion.exec_driver_sql("UPDATE type_chambre SET prix_defaut = price WHERE price IS NOT NULL")
    if not _a_colonne(connexion, "type_chambre", "prix_mini"):
        connexion.exec_driver_sql("ALTER TABLE type_chambre ADD COLUMN prix_mini FLOAT NOT NULL DEFAULT 0")
        ajoutees.append("type_chambre.prix_mini")
        if _a_colonne(connexion, "type_chambre", "min_price"):
            connexion.exec_driver_sql("UPDATE type_chambre SET prix_mini = min_price WHERE min_price IS NOT NULL")
    if not _a_colonne(connexion, "type_chambre", "channel_manager_uniquement"):
        connexion.exec_driver_sql(
            "ALTER TABLE type_chambre ADD COLUMN channel_manager_uniquement BOOLEAN NOT NULL DEFAULT 0"
        )
        ajoutees.append("type_chambre.channel_manager_uniquement")
        if _a_colonne(connexion, "type_chambre", "woodoo"):
            connexion.exec_driver_sql(
                "UPDATE type_chambre SET channel_manager_uniquement = woodoo WHERE woodoo IS NOT NULL"
            )
    _indexer_nom_raccourci(connexion)


def _indexer_nom_raccourci(connexion) -> None:
    if not _a_colonne(connexion, "type_chambre", "nom_raccourci"):
        return
    doublon = connexion.exec_driver_sql(
        "SELECT nom_raccourci FROM type_chambre WHERE nom_raccourci IS NOT NULL "
        "GROUP BY nom_raccourci HAVING COUNT(*) > 1"
    ).first()
    if doublon is not None:
        raise CatalogueIllisible("Plusieurs types portent le même nom raccourci")
    trop_long = connexion.exec_driver_sql(
        "SELECT nom_raccourci FROM type_chambre WHERE nom_raccourci IS NOT NULL AND length(nom_raccourci) > 4"
    ).first()
    if trop_long is not None:
        raise CatalogueIllisible("Un nom raccourci dépasse 4 caractères")
    connexion.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_type_chambre_nom_raccourci ON type_chambre(nom_raccourci)"
    )


def _archiver_anciennes_cellules_virtuelles(connexion) -> None:
    # Ces cellules portent des formules, pas les prix du modèle ChambreVirtuelle.
    # Les archives gardent leurs données sans retenir les types par une clé étrangère.
    if _table_existe(connexion, "cellule_virtuelle"):
        connexion.exec_driver_sql(
            "CREATE TABLE archive_cellule_virtuelle AS "
            "SELECT cellule.*, type_chambre.wubook_id AS type_chambre_wubook_id, "
            "type_chambre.libelle AS type_chambre_libelle "
            "FROM cellule_virtuelle AS cellule "
            "LEFT JOIN type_chambre ON type_chambre.id = cellule.type_chambre_id"
        )
        connexion.exec_driver_sql("DROP TABLE cellule_virtuelle")
    if _table_existe(connexion, "option_virtuelle"):
        connexion.exec_driver_sql("CREATE TABLE archive_option_virtuelle AS SELECT * FROM option_virtuelle")
        connexion.exec_driver_sql("DROP TABLE option_virtuelle")


def _retirer_tarif_bb(connexion) -> None:
    if _table_existe(connexion, "type_chambre") and _a_colonne(connexion, "type_chambre", "tarif_bb"):
        connexion.exec_driver_sql("ALTER TABLE type_chambre DROP COLUMN tarif_bb")


def _indexer_les_liens_chambre(connexion) -> None:
    for nom in ("type_chambre_id", "occupation_chambre_id"):
        if _a_colonne(connexion, "chambre", nom):
            connexion.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS ix_chambre_{nom} ON chambre ({nom})")


def _table_existe(connexion, table: str) -> bool:
    return (
        connexion.exec_driver_sql("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).first()
        is not None
    )


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


def _preparer_facturation(engine: Engine) -> None:
    """Pose les index de facture et initialise le compteur après les numéros déjà attribués, sans les renuméroter."""

    def _appliquer(connexion) -> None:
        if not _table_existe(connexion, "facture") or not _table_existe(connexion, "compteur_facture"):
            return
        connexion.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_facture_courante ON facture (reservation_id) WHERE courante = 1"
        )
        connexion.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_facture_remplace "
            "ON facture (remplace_id) WHERE remplace_id IS NOT NULL"
        )
        plancher = (
            "COALESCE((SELECT MAX(numero_facture) FROM reservation), 0)"
            if _a_colonne(connexion, "reservation", "numero_facture")
            else "0"
        )
        connexion.exec_driver_sql(
            "INSERT INTO compteur_facture (id, dernier_numero) "
            f"SELECT 1, MAX(COALESCE((SELECT MAX(numero) FROM facture), 0), {plancher}) "
            "WHERE NOT EXISTS (SELECT 1 FROM compteur_facture WHERE id = 1)"
        )

    _executer_en_transaction(engine, _appliquer)


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
