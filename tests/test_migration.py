"""Une base créée avant l'ajout des colonnes doit continuer à s'ouvrir, sans perdre ses lignes."""

from datetime import date

import pytest
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, create_engine, select

from ma_receptionniste.db import (
    CatalogueIllisible,
    ColonneNonAjoutable,
    ajouter_colonnes_manquantes,
    create_db_and_tables,
)
from ma_receptionniste.models import (
    Chambre,
    ChambreVirtuelle,
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


def test_la_colonne_tarif_bb_est_retiree() -> None:
    engine = ancienne_base(
        "CREATE TABLE type_chambre ("
        "id INTEGER NOT NULL, libelle VARCHAR NOT NULL, tarif_bb BOOLEAN NOT NULL DEFAULT 0, PRIMARY KEY (id)"
        ");"
        "INSERT INTO type_chambre (id, libelle, tarif_bb) VALUES (9, 'Double', 1);"
    )

    ajouter_colonnes_manquantes(engine)

    assert "tarif_bb" not in _colonnes(engine, "type_chambre")
    with Session(engine) as session:
        assert session.get(TypeChambre, 9).libelle == "Double"
    assert ajouter_colonnes_manquantes(engine) == []


def test_une_base_htmx_deja_migree_garde_ses_identifiants() -> None:
    engine = ancienne_base(SCHEMA_HTMX)

    assert ajouter_colonnes_manquantes(engine) == [
        "chambre.etage",
        "type_chambre.wubook_id",
        "type_chambre.description",
        "type_chambre.disponibilite",
        "type_chambre.nom_raccourci",
        "type_chambre.prix_defaut",
        "type_chambre.prix_mini",
        "type_chambre.channel_manager_uniquement",
    ]
    assert ajouter_colonnes_manquantes(engine) == []

    with Session(engine) as session:
        type_chambre = session.get(TypeChambre, 9)
        assert type_chambre.libelle == "Double"
        assert (type_chambre.description, type_chambre.disponibilite) == ("", 0)
        assert type_chambre.nom_raccourci is None
        assert (type_chambre.prix_defaut, type_chambre.prix_mini) == (0, 0)
        assert type_chambre.channel_manager_uniquement is False
        chambre = session.get(Chambre, 1)
        assert chambre.etage == 0
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
        double = session.get(TypeChambre, 9)
        assert double.wubook_id == 90
        assert (double.nom_raccourci, double.prix_defaut, double.prix_mini, double.channel_manager_uniquement) == (
            "DBL",
            80,
            0,
            False,
        )
        queen = session.get(TypeChambre, 10)
        assert (queen.nom_raccourci, queen.prix_defaut, queen.libelle) == ("QN", 90, "King")
        session.add(TypeChambre(libelle="Suite"))
        session.commit()
        suite = session.exec(select(TypeChambre).where(TypeChambre.libelle == "Suite")).one()
        assert suite.id not in {9, 10, 11}
        assert suite.nom_raccourci is None
    with engine.connect() as connexion:
        suite = connexion.exec_driver_sql(
            "SELECT wubook_id, name, shortname, beds, price, libelle FROM type_chambre WHERE libelle = 'Suite'"
        ).one()
    assert suite == (None, None, None, 1, 0, "Suite")


def test_une_base_sans_wubook_id_recoit_la_colonne_nullable() -> None:
    engine = ancienne_base(
        "CREATE TABLE type_chambre (id INTEGER PRIMARY KEY, libelle VARCHAR NOT NULL);"
        "INSERT INTO type_chambre (id, libelle) VALUES (1, 'Double');"
    )

    assert "type_chambre.wubook_id" in ajouter_colonnes_manquantes(engine)
    assert ajouter_colonnes_manquantes(engine) == []
    with Session(engine) as session:
        type_chambre = session.get(TypeChambre, 1)
        assert type_chambre.wubook_id is None
        type_chambre.wubook_id = 12345
        session.commit()
    with Session(engine) as session:
        assert session.get(TypeChambre, 1).wubook_id == 12345


@pytest.mark.parametrize("colonne_presente", [False, True])
def test_wubook_id_des_chambres_virtuelles_est_ajoute_ou_preserve(colonne_presente: bool) -> None:
    colonne = ", wubook_id INTEGER" if colonne_presente else ""
    engine = ancienne_base(
        "CREATE TABLE type_chambre (id INTEGER PRIMARY KEY, libelle VARCHAR NOT NULL);"
        "INSERT INTO type_chambre (id, libelle) VALUES (1, 'Double');"
        "CREATE TABLE chambre_virtuelle ("
        "id INTEGER PRIMARY KEY, type_chambre_id INTEGER NOT NULL, nom_raccourci VARCHAR(4) NOT NULL UNIQUE, "
        f"prix_defaut FLOAT NOT NULL, prix_mini FLOAT NOT NULL{colonne});"
        "INSERT INTO chambre_virtuelle (id, type_chambre_id, nom_raccourci, prix_defaut, prix_mini) "
        "VALUES (1, 1, 'DBL', 80, 50);"
        + ("UPDATE chambre_virtuelle SET wubook_id = 12345;" if colonne_presente else "")
    )

    ajoutees = ajouter_colonnes_manquantes(engine)
    assert ("chambre_virtuelle.wubook_id" in ajoutees) is not colonne_presente
    assert ajouter_colonnes_manquantes(engine) == []
    with Session(engine) as session:
        virtuelle = session.get(ChambreVirtuelle, 1)
        assert virtuelle.wubook_id == (12345 if colonne_presente else None)
        assert (virtuelle.nom_raccourci, virtuelle.prix_defaut, virtuelle.prix_mini) == ("DBL", 80, 50)
        virtuelle.wubook_id = 67890
        session.commit()
    with Session(engine) as session:
        assert session.get(ChambreVirtuelle, 1).wubook_id == 67890


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


def test_les_prix_wubook_sont_repris_une_seule_fois() -> None:
    engine = ancienne_base(
        "CREATE TABLE type_chambre ("
        "id INTEGER NOT NULL, libelle VARCHAR NOT NULL, shortname VARCHAR, "
        "price FLOAT, min_price FLOAT, woodoo INTEGER, PRIMARY KEY (id)"
        ");"
        "INSERT INTO type_chambre (id, libelle, shortname, price, min_price, woodoo) "
        "VALUES (9, 'Triple Balcon', '3B', 110, 50, 1);"
    )

    ajouter_colonnes_manquantes(engine)

    with Session(engine) as session:
        type_chambre = session.get(TypeChambre, 9)
        assert type_chambre.nom_raccourci == "3B"
        assert (type_chambre.prix_defaut, type_chambre.prix_mini) == (110, 50)
        assert type_chambre.channel_manager_uniquement is True
        type_chambre.prix_defaut = 120
        session.add(type_chambre)
        session.commit()

    assert ajouter_colonnes_manquantes(engine) == []
    with Session(engine) as session:
        assert session.get(TypeChambre, 9).prix_defaut == 120


def test_des_noms_raccourcis_en_double_annulent_la_migration() -> None:
    engine = ancienne_base(
        "CREATE TABLE type_chambre ("
        "id INTEGER NOT NULL, libelle VARCHAR NOT NULL, shortname VARCHAR, PRIMARY KEY (id)"
        ");"
        "INSERT INTO type_chambre (id, libelle, shortname) VALUES (1, 'Double', 'DBL'), (2, 'Twin', 'DBL');"
    )

    with pytest.raises(CatalogueIllisible):
        ajouter_colonnes_manquantes(engine)

    assert "nom_raccourci" not in _colonnes(engine, "type_chambre")


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


SCHEMA_CELLULES_VIRTUELLES = """
CREATE TABLE option_virtuelle (
    id INTEGER PRIMARY KEY, nom VARCHAR NOT NULL UNIQUE, formule_prix VARCHAR NOT NULL, description VARCHAR
);
CREATE TABLE cellule_virtuelle (
    id INTEGER PRIMARY KEY,
    type_chambre_id INTEGER NOT NULL REFERENCES type_chambre(id),
    option_id INTEGER NOT NULL REFERENCES option_virtuelle(id),
    shortname VARCHAR NOT NULL UNIQUE,
    UNIQUE (type_chambre_id, option_id)
);
INSERT INTO option_virtuelle (id, nom, formule_prix, description)
    VALUES (1, 'Petit Déjeuner', 'x+10*p', 'Supplément par personne');
INSERT INTO cellule_virtuelle (id, type_chambre_id, option_id, shortname) VALUES (1, 9, 1, '2BBB');
"""


def test_les_cellules_historiques_sont_archivees_sans_bloquer_les_types() -> None:
    engine = ancienne_base("PRAGMA foreign_keys=ON;" + SCHEMA_WUBOOK + SCHEMA_CELLULES_VIRTUELLES)

    create_db_and_tables(engine)
    assert ajouter_colonnes_manquantes(engine) == []

    with engine.connect() as connexion:
        tables = {ligne[0] for ligne in connexion.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"archive_cellule_virtuelle", "archive_option_virtuelle"} <= tables
        assert not {"cellule_virtuelle", "option_virtuelle"} & tables
        assert connexion.exec_driver_sql("SELECT * FROM archive_cellule_virtuelle").one() == (
            1,
            9,
            1,
            "2BBB",
            90,
            "Double",
        )
        assert connexion.exec_driver_sql("SELECT * FROM archive_option_virtuelle").one() == (
            1,
            "Petit Déjeuner",
            "x+10*p",
            "Supplément par personne",
        )
        assert connexion.exec_driver_sql("PRAGMA foreign_key_list('archive_cellule_virtuelle')").all() == []
        assert connexion.exec_driver_sql("PRAGMA foreign_key_list('archive_option_virtuelle')").all() == []
        assert connexion.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    with Session(engine) as session:
        assert session.get(TypeChambre, 9).wubook_id == 90
        assert session.get(Chambre, 1).type_chambre_id == 9
        assert session.get(Chambre, 2).type_chambre_id == 9
        assert session.exec(select(ChambreVirtuelle)).all() == []

    # L'archive ne doit plus empêcher le remplacement du catalogue.
    with engine.begin() as connexion:
        connexion.exec_driver_sql("UPDATE chambre SET type_chambre_id = NULL")
        connexion.exec_driver_sql("DELETE FROM type_chambre")
        assert connexion.exec_driver_sql("SELECT COUNT(*) FROM archive_cellule_virtuelle").scalar_one() == 1
        assert connexion.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_un_conflit_d_archive_ne_supprime_pas_les_donnees_historiques() -> None:
    engine = ancienne_base(
        "PRAGMA foreign_keys=ON;"
        + SCHEMA_WUBOOK
        + SCHEMA_CELLULES_VIRTUELLES
        + "CREATE TABLE archive_option_virtuelle (id INTEGER PRIMARY KEY);"
        + "INSERT INTO archive_option_virtuelle (id) VALUES (99);"
    )

    with pytest.raises(OperationalError, match="already exists"):
        ajouter_colonnes_manquantes(engine)

    with engine.connect() as connexion:
        assert connexion.exec_driver_sql("SELECT shortname FROM cellule_virtuelle").scalar_one() == "2BBB"
        assert connexion.exec_driver_sql("SELECT formule_prix FROM option_virtuelle").scalar_one() == "x+10*p"
        assert connexion.exec_driver_sql("SELECT id FROM archive_option_virtuelle").scalar_one() == 99
        assert (
            connexion.exec_driver_sql("SELECT name FROM sqlite_master WHERE name='archive_cellule_virtuelle'").all()
            == []
        )
        assert connexion.exec_driver_sql("PRAGMA foreign_key_check").all() == []


@pytest.mark.parametrize("champs_presents", [False, True])
def test_descriptions_disponibilite_et_etage_sont_ajoutes_ou_preserves(champs_presents: bool) -> None:
    type_champs = ", description VARCHAR NOT NULL DEFAULT '', disponibilite INTEGER NOT NULL DEFAULT 0"
    description = ", description VARCHAR NOT NULL DEFAULT ''"
    etage = ", etage INTEGER NOT NULL DEFAULT 0"
    engine = ancienne_base(
        "CREATE TABLE type_chambre (id INTEGER PRIMARY KEY, libelle VARCHAR NOT NULL, availability INTEGER"
        + (type_champs if champs_presents else "")
        + ");"
        "INSERT INTO type_chambre (id, libelle, availability) VALUES (1, 'Double', 6);"
        "CREATE TABLE chambre (id INTEGER PRIMARY KEY, nom VARCHAR NOT NULL, position INTEGER NOT NULL, "
        "etat VARCHAR NOT NULL" + (etage if champs_presents else "") + ");"
        "INSERT INTO chambre (id, nom, position, etat) VALUES (1, '101', 1, 'pret');"
        "CREATE TABLE chambre_virtuelle (id INTEGER PRIMARY KEY, type_chambre_id INTEGER NOT NULL, "
        "nom_raccourci VARCHAR(4) NOT NULL UNIQUE, prix_defaut FLOAT NOT NULL, prix_mini FLOAT NOT NULL"
        + (description if champs_presents else "")
        + ");"
        "INSERT INTO chambre_virtuelle (id, type_chambre_id, nom_raccourci, prix_defaut, prix_mini) "
        "VALUES (1, 1, 'DBL', 80, 50);"
        + (
            "UPDATE type_chambre SET description='Avec balcon', disponibilite=3;"
            "UPDATE chambre_virtuelle SET description='Petit déjeuner inclus';"
            "UPDATE chambre SET etage=2;"
            if champs_presents
            else ""
        )
    )

    ajoutees = ajouter_colonnes_manquantes(engine)
    for colonne in (
        "type_chambre.description",
        "type_chambre.disponibilite",
        "chambre_virtuelle.description",
        "chambre.etage",
    ):
        assert (colonne in ajoutees) is not champs_presents
    with Session(engine) as session:
        type_chambre = session.get(TypeChambre, 1)
        virtuelle = session.get(ChambreVirtuelle, 1)
        chambre = session.get(Chambre, 1)
        assert type_chambre.description == ("Avec balcon" if champs_presents else "")
        assert type_chambre.disponibilite == (3 if champs_presents else 6)
        assert virtuelle.description == ("Petit déjeuner inclus" if champs_presents else "")
        assert chambre.etage == (2 if champs_presents else 0)
        type_chambre.description = "Vue sur mer"
        type_chambre.disponibilite = 8
        virtuelle.description = "Occupation simple"
        chambre.etage = -1
        session.add_all([type_chambre, virtuelle, chambre])
        session.commit()

    assert ajouter_colonnes_manquantes(engine) == []
    with Session(engine) as session:
        assert session.get(TypeChambre, 1).description == "Vue sur mer"
        assert session.get(TypeChambre, 1).disponibilite == 8
        assert session.get(ChambreVirtuelle, 1).description == "Occupation simple"
        assert session.get(Chambre, 1).etage == -1


def test_migration_cree_et_preserve_la_table_de_liaison() -> None:
    engine = ancienne_base(
        "PRAGMA foreign_keys=ON;" + SCHEMA_HTMX + "CREATE TABLE chambre_virtuelle ("
        "id INTEGER PRIMARY KEY, type_chambre_id INTEGER NOT NULL REFERENCES type_chambre(id), "
        "nom_raccourci VARCHAR(4) NOT NULL UNIQUE, prix_defaut FLOAT NOT NULL, prix_mini FLOAT NOT NULL);"
        "INSERT INTO chambre_virtuelle (id, type_chambre_id, nom_raccourci, prix_defaut, prix_mini) "
        "VALUES (7, 9, 'DBL', 80, 50);"
    )
    with engine.connect() as connexion:
        assert connexion.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert (
            connexion.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='chambre_chambre_virtuelle'"
            ).all()
            == []
        )

    create_db_and_tables(engine)

    with Session(engine) as session:
        chambre = session.get(Chambre, 1)
        virtuelle = session.get(ChambreVirtuelle, 7)
        assert (chambre.nom, chambre.type_chambre_id, chambre.occupation_chambre_id) == ("101", 9, 4)
        assert (virtuelle.nom_raccourci, virtuelle.type_chambre_id, virtuelle.prix_defaut) == ("DBL", 9, 80)
        assert chambre.chambres_virtuelles == []
        assert virtuelle.chambres == []
        chambre.chambres_virtuelles.append(virtuelle)
        session.commit()

    create_db_and_tables(engine)

    with Session(engine) as session:
        assert [v.id for v in session.get(Chambre, 1).chambres_virtuelles] == [7]
        assert [c.id for c in session.get(ChambreVirtuelle, 7).chambres] == [1]
        assert session.get(TypeChambre, 9).libelle == "Double"
        assert session.get(OccupationChambre, 4).type_lits == "Twin"
    with engine.connect() as connexion:
        assert connexion.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        cles = connexion.exec_driver_sql("PRAGMA foreign_key_list('chambre_chambre_virtuelle')").all()
        assert {(cle[2], cle[3], cle[4], cle[6]) for cle in cles} == {
            ("chambre", "chambre_id", "id", "CASCADE"),
            ("chambre_virtuelle", "chambre_virtuelle_id", "id", "CASCADE"),
        }
        assert connexion.exec_driver_sql("PRAGMA foreign_key_check").all() == []
