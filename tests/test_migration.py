"""Une base créée avant l'ajout des colonnes doit continuer à s'ouvrir, sans perdre ses lignes."""

from datetime import date

import pytest
from sqlmodel import Session, create_engine, select

from ma_receptionniste.db import (
    CatalogueIllisible,
    ColonneNonAjoutable,
    ajouter_colonnes_manquantes,
    create_db_and_tables,
)
from ma_receptionniste.models import (
    Chambre,
    Client,
    Consommation,
    ModeReglement,
    OccupationChambre,
    Reglement,
    Reservation,
    Sejour,
    TypeChambre,
)

ANCIEN_SCHEMA = """
CREATE TABLE user (
    id INTEGER NOT NULL, email VARCHAR NOT NULL, nom VARCHAR NOT NULL,
    password_hash VARCHAR NOT NULL, cree_le DATETIME NOT NULL, PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_user_email ON user (email);
CREATE TABLE client (
    id INTEGER NOT NULL, nom VARCHAR NOT NULL, prenom VARCHAR, telephone VARCHAR, email VARCHAR,
    adresse VARCHAR, notes VARCHAR, cree_le DATETIME NOT NULL, PRIMARY KEY (id)
);
CREATE INDEX ix_client_nom ON client (nom);
CREATE TABLE chambre (
    id INTEGER NOT NULL, nom VARCHAR NOT NULL, position INTEGER NOT NULL, etat VARCHAR NOT NULL,
    PRIMARY KEY (id), UNIQUE (nom)
);
CREATE TABLE reservation (
    id INTEGER NOT NULL, client_id INTEGER NOT NULL, statut VARCHAR NOT NULL, date_creation DATETIME NOT NULL,
    PRIMARY KEY (id), FOREIGN KEY(client_id) REFERENCES client (id)
);
CREATE INDEX ix_reservation_client_id ON reservation (client_id);
CREATE TABLE sejour (
    id INTEGER NOT NULL, reservation_id INTEGER NOT NULL, chambre_id INTEGER NOT NULL,
    date_debut DATE NOT NULL, date_fin DATE NOT NULL, nom_client VARCHAR, PRIMARY KEY (id),
    FOREIGN KEY(reservation_id) REFERENCES reservation (id), FOREIGN KEY(chambre_id) REFERENCES chambre (id)
);
CREATE INDEX ix_sejour_reservation_id ON sejour (reservation_id);
CREATE INDEX ix_sejour_chambre_id ON sejour (chambre_id);
CREATE TABLE historique (
    id INTEGER NOT NULL, reservation_id INTEGER, user_id INTEGER, description VARCHAR NOT NULL,
    date DATETIME NOT NULL, PRIMARY KEY (id),
    FOREIGN KEY(reservation_id) REFERENCES reservation (id) ON DELETE SET NULL,
    FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE SET NULL
);
CREATE INDEX ix_historique_reservation_id ON historique (reservation_id);
INSERT INTO client (id, nom, prenom, cree_le) VALUES (1, 'Dupont', 'Alice', '2026-10-01 09:00:00.000000');
INSERT INTO chambre (id, nom, position, etat) VALUES (1, '101', 1, 'pret');
INSERT INTO reservation (id, client_id, statut, date_creation) VALUES (1, 1, 'confirmee', '2026-10-01 09:05:00.000000');
INSERT INTO sejour (id, reservation_id, chambre_id, date_debut, date_fin, nom_client)
    VALUES (1, 1, 1, '2026-10-10', '2026-10-12', 'Martin');
"""


def ancienne_base(script: str):
    engine = create_engine("sqlite://")
    with engine.begin() as connexion:
        connexion.connection.executescript(script)
    return engine


def test_ancienne_base_recoit_les_nouvelles_colonnes() -> None:
    engine = ancienne_base(ANCIEN_SCHEMA)

    create_db_and_tables(engine)
    create_db_and_tables(engine)

    with Session(engine) as session:
        client = session.get(Client, 1)
        chambre = session.get(Chambre, 1)
        reservation = session.get(Reservation, 1)
        sejour = session.get(Sejour, 1)

        assert (client.nom, client.pays) == ("Dupont", None)
        assert (chambre.nom, chambre.type_chambre_id, chambre.occupation_chambre_id) == ("101", None, None)
        assert reservation.statut == "confirmee"
        assert reservation.nom_occupant is None
        assert reservation.partenaire is None
        assert reservation.numero_facture is None
        assert (sejour.date_debut, sejour.date_fin) == (date(2026, 10, 10), date(2026, 10, 12))
        assert sejour.nom_client == "Martin"
        assert (sejour.adultes, sejour.enfants, sejour.prix_nuit_centimes) == (1, 0, 0)

        session.add(Consommation(reservation_id=1, libelle="Petit-déjeuner", prix_unitaire_centimes=1400))
        session.add(Reglement(reservation_id=1, mode=ModeReglement.carte, montant_centimes=5000))
        session.commit()

        assert [c.libelle for c in session.exec(select(Consommation)).all()] == ["Petit-déjeuner"]
        assert session.exec(select(Reglement)).one().mode == ModeReglement.carte


def test_migration_idempotente() -> None:
    engine = ancienne_base(ANCIEN_SCHEMA)

    premiere = ajouter_colonnes_manquantes(engine)
    seconde = ajouter_colonnes_manquantes(engine)

    assert "sejour.adultes" in premiere
    assert seconde == []


ANCIEN_ARGENT = """
CREATE TABLE client (
    id INTEGER NOT NULL, nom VARCHAR NOT NULL, prenom VARCHAR, telephone VARCHAR, email VARCHAR,
    adresse VARCHAR, notes VARCHAR, cree_le DATETIME NOT NULL, PRIMARY KEY (id)
);
CREATE TABLE chambre (
    id INTEGER NOT NULL, nom VARCHAR NOT NULL, position INTEGER NOT NULL, etat VARCHAR NOT NULL,
    PRIMARY KEY (id), UNIQUE (nom)
);
CREATE TABLE reservation (
    id INTEGER NOT NULL, client_id INTEGER NOT NULL, statut VARCHAR NOT NULL, date_creation DATETIME NOT NULL,
    PRIMARY KEY (id)
);
CREATE TABLE sejour (
    id INTEGER NOT NULL, reservation_id INTEGER NOT NULL, chambre_id INTEGER NOT NULL,
    date_debut DATE NOT NULL, date_fin DATE NOT NULL, nom_client VARCHAR,
    prix_ttc NUMERIC, remise_pct NUMERIC NOT NULL DEFAULT 0,
    adultes INTEGER NOT NULL DEFAULT 1, enfants INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (id)
);
CREATE TABLE consommation (
    id INTEGER NOT NULL, reservation_id INTEGER NOT NULL, libelle VARCHAR NOT NULL,
    quantite INTEGER NOT NULL, montant NUMERIC(12, 2) NOT NULL DEFAULT '0', jour DATE NOT NULL,
    PRIMARY KEY (id)
);
CREATE TABLE reglement (
    id INTEGER NOT NULL, reservation_id INTEGER NOT NULL, mode VARCHAR NOT NULL,
    montant NUMERIC(12, 2) NOT NULL, jour DATE NOT NULL, reference VARCHAR, PRIMARY KEY (id)
);
INSERT INTO client (id, nom, cree_le) VALUES (1, 'Dupont', '2026-10-01 09:00:00');
INSERT INTO chambre (id, nom, position, etat) VALUES (1, '102', 1, 'non_pret');
INSERT INTO reservation (id, client_id, statut, date_creation) VALUES (1, 1, 'confirmee', '2026-10-18 06:23:43');
INSERT INTO sejour (id, reservation_id, chambre_id, date_debut, date_fin, prix_ttc)
    VALUES (1, 1, 1, '2026-10-20', '2026-10-23', 50);
INSERT INTO reglement (id, reservation_id, mode, montant, jour) VALUES (1, 1, 'CB', 50, '2026-10-19');
INSERT INTO reglement (id, reservation_id, mode, montant, jour) VALUES (2, 1, 'CB', 2, '2026-10-19');
"""


def test_ancienne_base_reprend_les_montants_en_euros() -> None:
    engine = ancienne_base(ANCIEN_ARGENT)

    create_db_and_tables(engine)

    with Session(engine) as session:
        assert session.get(Chambre, 1).type_chambre_id is None
        assert session.get(Sejour, 1).prix_nuit_centimes == 5000
        reglements = session.exec(select(Reglement).order_by(Reglement.id)).all()
        assert [(r.mode, r.montant_centimes, r.date.date()) for r in reglements] == [
            (ModeReglement.carte, 5000, date(2026, 10, 19)),
            (ModeReglement.carte, 200, date(2026, 10, 19)),
        ]
        session.add(Reglement(reservation_id=1, mode=ModeReglement.carte, montant_centimes=10400))
        session.add(Consommation(reservation_id=1, libelle="Bar", quantite=1, prix_unitaire_centimes=300))
        session.commit()
        montants = [r.montant_centimes for r in session.exec(select(Reglement).order_by(Reglement.id))]
        assert montants == [5000, 200, 10400]
        assert session.exec(select(Consommation)).one().prix_unitaire_centimes == 300
        session.get(Sejour, 1).prix_nuit_centimes = 100
        session.commit()

    create_db_and_tables(engine)

    with Session(engine) as session:
        assert session.get(Sejour, 1).prix_nuit_centimes == 100


def test_colonne_obligatoire_sans_defaut_refusee_sans_rien_toucher() -> None:
    # position est NOT NULL sans server_default : aucune valeur sûre pour les lignes existantes.
    engine = ancienne_base("CREATE TABLE chambre (id INTEGER NOT NULL, nom VARCHAR NOT NULL, PRIMARY KEY (id));")

    with pytest.raises(ColonneNonAjoutable):
        ajouter_colonnes_manquantes(engine)

    with engine.connect() as connexion:
        colonnes = [ligne[1] for ligne in connexion.exec_driver_sql("PRAGMA table_info('chambre')")]
    assert colonnes == ["id", "nom"]


def _colonnes(engine, table: str) -> list[str]:
    with engine.connect() as connexion:
        return [ligne[1] for ligne in connexion.exec_driver_sql(f"PRAGMA table_info('{table}')")]


def _index(engine, table: str) -> set[str]:
    with engine.connect() as connexion:
        return {ligne[1] for ligne in connexion.exec_driver_sql(f"PRAGMA index_list('{table}')")}


def _sql(engine, table: str) -> str:
    with engine.connect() as connexion:
        return connexion.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).scalar_one()


def test_base_vierge_cree_les_catalogues_vides() -> None:
    engine = create_engine("sqlite://")

    create_db_and_tables(engine)
    assert ajouter_colonnes_manquantes(engine) == []

    with Session(engine) as session:
        assert session.exec(select(TypeChambre)).all() == []
        assert session.exec(select(OccupationChambre)).all() == []
        type_chambre = TypeChambre(libelle="Double")
        session.add(type_chambre)
        session.commit()
        session.add(Chambre(nom="101", position=1, type_chambre_id=type_chambre.id))
        session.commit()
        type_id, chambre_id = type_chambre.id, session.exec(select(Chambre)).one().id

    assert ajouter_colonnes_manquantes(engine) == []

    with Session(engine) as session:
        assert session.get(TypeChambre, type_id).libelle == "Double"
        assert session.get(Chambre, chambre_id).type_chambre_id == type_id
    assert "type_chambre" not in _colonnes(engine, "chambre")
    assert {"type_chambre_id", "occupation_chambre_id"} <= set(_colonnes(engine, "chambre"))
    assert "uq_type_chambre_libelle" in _index(engine, "type_chambre")


SCHEMA_NICEGUI = """
CREATE TABLE chambre (
    id INTEGER NOT NULL, nom VARCHAR NOT NULL, type_chambre VARCHAR, position INTEGER NOT NULL,
    etat VARCHAR NOT NULL, PRIMARY KEY (id), UNIQUE (nom)
);
INSERT INTO chambre (id, nom, type_chambre, position, etat) VALUES
    (1, '101', 'Double', 1, 'pret'),
    (2, '102', 'double', 2, 'pret'),
    (3, '103', '  Double  ', 3, 'non_pret'),
    (4, '104', '   ', 4, 'pret'),
    (5, '105', NULL, 5, 'pret');
"""


def test_la_colonne_texte_devient_un_catalogue_partage() -> None:
    engine = ancienne_base(SCHEMA_NICEGUI)

    create_db_and_tables(engine)

    with Session(engine) as session:
        types = {ligne.libelle: ligne.id for ligne in session.exec(select(TypeChambre))}
        chambres = {chambre.nom: chambre.type_chambre_id for chambre in session.exec(select(Chambre))}
        occupations = session.exec(select(OccupationChambre)).all()
    assert set(types) == {"Double", "double"}
    assert chambres["101"] == chambres["103"] == types["Double"]
    assert chambres["102"] == types["double"]
    assert chambres["104"] is None
    assert chambres["105"] is None
    assert occupations == []
    assert "type_chambre" not in _colonnes(engine, "chambre")
    sql = _sql(engine, "chambre")
    assert "REFERENCES type_chambre(id) ON DELETE RESTRICT" in sql
    assert "REFERENCES occupation_chambre(id) ON DELETE RESTRICT" in sql

    assert ajouter_colonnes_manquantes(engine) == []
    with Session(engine) as session:
        assert {ligne.libelle: ligne.id for ligne in session.exec(select(TypeChambre))} == types
        assert {chambre.nom: chambre.type_chambre_id for chambre in session.exec(select(Chambre))} == chambres


SCHEMA_HTMX = """
CREATE TABLE type_chambre (
    id INTEGER NOT NULL, libelle VARCHAR NOT NULL, PRIMARY KEY (id), UNIQUE (libelle)
);
INSERT INTO type_chambre (id, libelle) VALUES (9, 'Double');
CREATE TABLE occupation_chambre (
    id INTEGER NOT NULL, nombre_personnes INTEGER NOT NULL, type_lits VARCHAR NOT NULL, PRIMARY KEY (id),
    UNIQUE (nombre_personnes, type_lits)
);
INSERT INTO occupation_chambre (id, nombre_personnes, type_lits) VALUES (4, 2, 'Twin');
CREATE TABLE chambre (
    id INTEGER NOT NULL, nom VARCHAR NOT NULL, position INTEGER NOT NULL, etat VARCHAR NOT NULL,
    type_chambre_id INTEGER, occupation_chambre_id INTEGER, PRIMARY KEY (id), UNIQUE (nom),
    FOREIGN KEY(type_chambre_id) REFERENCES type_chambre (id) ON DELETE RESTRICT,
    FOREIGN KEY(occupation_chambre_id) REFERENCES occupation_chambre (id) ON DELETE RESTRICT
);
INSERT INTO chambre (id, nom, position, etat, type_chambre_id, occupation_chambre_id)
    VALUES (1, '101', 1, 'pret', 9, 4);
"""


def test_une_base_htmx_deja_migree_garde_ses_identifiants() -> None:
    engine = ancienne_base(SCHEMA_HTMX)

    assert ajouter_colonnes_manquantes(engine) == []
    assert ajouter_colonnes_manquantes(engine) == []

    with Session(engine) as session:
        assert session.get(TypeChambre, 9).libelle == "Double"
        chambre = session.get(Chambre, 1)
        assert (chambre.type_chambre_id, chambre.occupation_chambre_id) == (9, 4)
        assert session.get(OccupationChambre, 4).type_lits == "Twin"
    assert "uq_type_chambre_libelle" in _index(engine, "type_chambre")
    assert "type_chambre" not in _colonnes(engine, "chambre")


SCHEMA_WUBOOK = """
CREATE TABLE type_chambre (
    id INTEGER NOT NULL, wubook_id INTEGER, name VARCHAR, shortname VARCHAR,
    beds INTEGER NOT NULL DEFAULT 1, price NUMERIC NOT NULL DEFAULT 0, libelle VARCHAR,
    PRIMARY KEY (id)
);
INSERT INTO type_chambre (id, wubook_id, name, shortname, beds, price, libelle) VALUES
    (9, 90, 'Double', 'DBL', 1, 80, 'Double'),
    (10, 91, 'Queen', 'QN', 1, 90, 'King'),
    (11, 92, '  Twin  ', 'TWN', 2, 70, NULL);
CREATE TABLE occupation_chambre (
    id INTEGER NOT NULL, nombre_personnes INTEGER NOT NULL, type_lits VARCHAR NOT NULL, PRIMARY KEY (id),
    UNIQUE (nombre_personnes, type_lits)
);
CREATE TABLE chambre (
    id INTEGER NOT NULL, nom VARCHAR NOT NULL, position INTEGER NOT NULL, etat VARCHAR NOT NULL,
    type_chambre_id INTEGER, occupation_chambre_id INTEGER, PRIMARY KEY (id), UNIQUE (nom),
    FOREIGN KEY(type_chambre_id) REFERENCES type_chambre (id) ON DELETE RESTRICT,
    FOREIGN KEY(occupation_chambre_id) REFERENCES occupation_chambre (id) ON DELETE RESTRICT
);
INSERT INTO chambre (id, nom, position, etat, type_chambre_id) VALUES
    (1, '101', 1, 'pret', 9),
    (2, '102', 2, 'pret', 9);
"""


def test_la_base_wubook_garde_ses_lignes_et_accepte_un_nouveau_libelle() -> None:
    engine = ancienne_base(SCHEMA_WUBOOK)

    create_db_and_tables(engine)
    assert ajouter_colonnes_manquantes(engine) == []

    with engine.connect() as connexion:
        lignes = connexion.exec_driver_sql(
            "SELECT id, name, libelle, wubook_id, beds FROM type_chambre ORDER BY id"
        ).all()
    assert lignes == [
        (9, "Double", "Double", 90, 1),
        (10, "Queen", "King", 91, 1),
        (11, "  Twin  ", "Twin", 92, 2),
    ]
    assert {"wubook_id", "name", "shortname", "beds", "price", "libelle"} <= set(_colonnes(engine, "type_chambre"))
    assert "uq_type_chambre_libelle" in _index(engine, "type_chambre")
    with Session(engine) as session:
        assert session.exec(select(OccupationChambre)).all() == []
        assert [chambre.type_chambre_id for chambre in session.exec(select(Chambre).order_by(Chambre.nom))] == [9, 9]
        session.add(TypeChambre(libelle="Suite"))
        session.commit()
        suite = session.exec(select(TypeChambre).where(TypeChambre.libelle == "Suite")).one()
        assert suite.id not in {9, 10, 11}
    with engine.connect() as connexion:
        suite = connexion.exec_driver_sql(
            "SELECT wubook_id, name, shortname, beds, price, libelle FROM type_chambre WHERE libelle = 'Suite'"
        ).one()
    assert suite == (None, None, None, 1, 0, "Suite")


SCHEMA_LIBELLES_DOUBLES = """
CREATE TABLE type_chambre (
    id INTEGER NOT NULL, name VARCHAR NOT NULL, PRIMARY KEY (id)
);
INSERT INTO type_chambre (id, name) VALUES (1, 'Double'), (2, 'Double');
CREATE TABLE chambre (
    id INTEGER NOT NULL, nom VARCHAR NOT NULL, position INTEGER NOT NULL, etat VARCHAR NOT NULL,
    type_chambre_id INTEGER, PRIMARY KEY (id), UNIQUE (nom)
);
INSERT INTO chambre (id, nom, position, etat, type_chambre_id) VALUES (1, '101', 1, 'pret', 1);
"""


def test_des_libelles_en_double_annulent_la_migration() -> None:
    engine = ancienne_base(SCHEMA_LIBELLES_DOUBLES)

    with pytest.raises(CatalogueIllisible):
        create_db_and_tables(engine)

    assert "libelle" not in _colonnes(engine, "type_chambre")
    assert "occupation_chambre_id" not in _colonnes(engine, "chambre")
    assert "uq_type_chambre_libelle" not in _index(engine, "type_chambre")
    with engine.connect() as connexion:
        assert connexion.exec_driver_sql("SELECT id, name FROM type_chambre ORDER BY id").all() == [
            (1, "Double"),
            (2, "Double"),
        ]
        assert connexion.exec_driver_sql("SELECT type_chambre_id FROM chambre").scalar_one() == 1
