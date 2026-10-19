"""Une base créée avant l'ajout des colonnes doit continuer à s'ouvrir, sans perdre ses lignes."""

from datetime import date

import pytest
from sqlmodel import Session, create_engine, select

from ma_receptionniste.db import ColonneNonAjoutable, ajouter_colonnes_manquantes, create_db_and_tables
from ma_receptionniste.models import Chambre, Client, Consommation, ModeReglement, Reglement, Reservation, Sejour

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

        assert (client.nom, client.prenom, client.pays) == ("Dupont", "Alice", None)
        assert (chambre.nom, chambre.type_chambre) == ("101", None)
        assert reservation.statut == "confirmee"
        assert reservation.traitee is False
        assert reservation.partenaire is None
        assert reservation.numero_facture is None
        assert (sejour.date_debut, sejour.date_fin) == (date(2026, 10, 10), date(2026, 10, 12))
        assert sejour.nom_client == "Martin"
        assert (sejour.adultes, sejour.enfants, sejour.prix_nuit_centimes, sejour.remise_pct) == (1, 0, 0, 0)

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
    assert "reservation.traitee" in premiere
    assert seconde == []


def test_colonne_obligatoire_sans_defaut_refusee_sans_rien_toucher() -> None:
    # position est NOT NULL sans server_default : aucune valeur sûre pour les lignes existantes.
    # type_chambre, elle, serait ajoutable, mais la base doit rester telle quelle.
    engine = ancienne_base("CREATE TABLE chambre (id INTEGER NOT NULL, nom VARCHAR NOT NULL, PRIMARY KEY (id));")

    with pytest.raises(ColonneNonAjoutable):
        ajouter_colonnes_manquantes(engine)

    with engine.connect() as connexion:
        colonnes = [ligne[1] for ligne in connexion.exec_driver_sql("PRAGMA table_info('chambre')")]
    assert colonnes == ["id", "nom"]
