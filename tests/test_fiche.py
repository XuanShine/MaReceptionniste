from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlmodel import Session, select

from ma_receptionniste.consultations import lire_reservation
from ma_receptionniste.db import preparer_base
from ma_receptionniste.dossier import (
    DossierInvalide,
    DossierSaisi,
    ajouter_consommation,
    appliquer_etat_dossier,
    compte_fiche,
    enregistrer_dossier,
    etat_affiche,
    euros,
    lire_montant,
    nombre_nuits,
    synthese,
)
from ma_receptionniste.models import (
    Chambre,
    Client,
    Consommation,
    EtatDossier,
    Reglement,
    Reservation,
    Sejour,
    StatutReservation,
)
from ma_receptionniste.sejours import ChambreOccupee, SejourInvalide, enregistrer_sejour

NUIT_18 = date(2026, 10, 18)
DEPART_20 = date(2026, 10, 20)
NUIT_10 = date(2026, 10, 10)
DEPART_12 = date(2026, 10, 12)

ANCIEN_SCHEMA = """
CREATE TABLE client (
    id INTEGER NOT NULL,
    nom VARCHAR NOT NULL,
    prenom VARCHAR,
    telephone VARCHAR,
    email VARCHAR,
    adresse VARCHAR,
    notes VARCHAR,
    cree_le DATETIME NOT NULL,
    PRIMARY KEY (id)
);
CREATE TABLE chambre (
    id INTEGER NOT NULL,
    nom VARCHAR NOT NULL,
    position INTEGER NOT NULL,
    etat VARCHAR NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (nom)
);
CREATE TABLE reservation (
    id INTEGER NOT NULL,
    client_id INTEGER NOT NULL,
    statut VARCHAR NOT NULL,
    date_creation DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(client_id) REFERENCES client (id)
);
CREATE TABLE sejour (
    id INTEGER NOT NULL,
    reservation_id INTEGER NOT NULL,
    chambre_id INTEGER NOT NULL,
    date_debut DATE NOT NULL,
    date_fin DATE NOT NULL,
    nom_client VARCHAR,
    PRIMARY KEY (id),
    FOREIGN KEY(reservation_id) REFERENCES reservation (id),
    FOREIGN KEY(chambre_id) REFERENCES chambre (id)
);
CREATE TABLE user (
    id INTEGER NOT NULL,
    email VARCHAR NOT NULL,
    nom VARCHAR NOT NULL,
    password_hash VARCHAR NOT NULL,
    cree_le DATETIME NOT NULL,
    PRIMARY KEY (id)
);
CREATE TABLE historique (
    id INTEGER NOT NULL,
    reservation_id INTEGER,
    user_id INTEGER,
    description VARCHAR NOT NULL,
    date DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(reservation_id) REFERENCES reservation (id) ON DELETE SET NULL,
    FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE SET NULL
);
"""


def _moteur():
    from sqlmodel import create_engine

    moteur = create_engine("sqlite://")

    @event.listens_for(moteur, "connect")
    def _activer_cles_etrangeres(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return moteur


@pytest.fixture
def session():
    moteur = _moteur()
    preparer_base(moteur)
    with Session(moteur) as ouverte:
        yield ouverte


def _dossier(session: Session):
    client = Client(nom="PASSAGE", prenom=None)
    chambre = Chambre(nom="406", position=1)
    session.add(client)
    session.add(chambre)
    session.commit()
    reservation = Reservation(client_id=client.id)
    session.add(reservation)
    session.commit()
    return client, chambre, reservation


def _saisi(client_id: int, **remplace) -> DossierSaisi:
    valeurs = dict(
        client_id=client_id,
        nom_occupant="LE CLOEREC Benedicte",
        pays="FRANCE",
        telephone=None,
        email=None,
        adresse=None,
        partenaire="Booking.com",
        etat="en_cours",
        traite=False,
        type_voiture=None,
        date_facture=None,
        numero_facture=None,
        notes="arrivé : 19h20",
        notes_internes=None,
        notes_tempo=None,
        notes_facturation=None,
    )
    valeurs.update(remplace)
    return DossierSaisi(**valeurs)


def test_une_base_deja_remplie_garde_ses_lignes() -> None:
    moteur = _moteur()
    with moteur.begin() as connection:
        for statement in ANCIEN_SCHEMA.split(";"):
            if statement.strip():
                connection.exec_driver_sql(statement)
        connection.exec_driver_sql(
            "INSERT INTO client (nom, prenom, cree_le) VALUES ('Dupont', 'Alice', '2026-10-01 08:00:00')"
        )
        connection.exec_driver_sql("INSERT INTO chambre (nom, position, etat) VALUES ('101', 1, 'pret')")
        connection.exec_driver_sql(
            "INSERT INTO reservation (client_id, statut, date_creation) VALUES (1, 'confirmee', '2026-10-01 08:00:00')"
        )
        connection.exec_driver_sql(
            "INSERT INTO sejour (reservation_id, chambre_id, date_debut, date_fin) "
            "VALUES (1, 1, '2026-10-10', '2026-10-12')"
        )

    preparer_base(moteur)
    preparer_base(moteur)

    with Session(moteur) as session:
        client = session.exec(select(Client)).one()
        sejour = session.exec(select(Sejour)).one()
        reservation = session.exec(select(Reservation)).one()

    assert client.nom == "Dupont"
    assert client.prenom == "Alice"
    assert client.pays is None
    assert sejour.date_debut == NUIT_10
    assert sejour.date_fin == DEPART_12
    assert sejour.adultes == 1
    assert sejour.enfants == 0
    assert Decimal(sejour.remise_pct) == Decimal("0")
    assert sejour.prix_ttc is None
    assert str(reservation.etat_dossier) == EtatDossier.en_cours
    assert reservation.traite is False
    assert reservation.notes is None
    assert str(reservation.statut) == StatutReservation.confirmee


def test_la_ligne_de_la_capture_fait_deux_nuits_et_141_64() -> None:
    sejour = Sejour(
        reservation_id=1,
        chambre_id=1,
        date_debut=NUIT_18,
        date_fin=DEPART_20,
        type_produit="Single BB",
        prix_ttc=Decimal("137.64"),
        remise_pct=Decimal("0"),
        adultes=1,
        enfants=0,
        taxe_sejour=Decimal("4"),
    )

    compte = synthese([sejour], [], [])

    assert nombre_nuits(NUIT_18, DEPART_20) == 2
    assert compte.ttc == Decimal("137.64")
    assert compte.taxe == Decimal("4.00")
    assert compte.reste == Decimal("141.64")
    assert euros(compte.ttc) == "137,64"
    assert euros(compte.taxe) == "4,00"
    assert euros(Decimal("1234.5")) == "1 234,50"
    assert lire_montant("137,64") == Decimal("137.64")
    assert lire_montant("") is None


def test_une_remise_diminue_le_ttc_pas_la_taxe() -> None:
    sejour = Sejour(
        reservation_id=1,
        chambre_id=1,
        date_debut=NUIT_18,
        date_fin=DEPART_20,
        prix_ttc=Decimal("100"),
        remise_pct=Decimal("10"),
        taxe_sejour=Decimal("4"),
    )

    compte = synthese([sejour], [], [])

    assert compte.ttc == Decimal("90.00")
    assert compte.taxe == Decimal("4.00")
    assert compte.reste == Decimal("94.00")


def test_consommations_et_reglements_entrent_dans_le_reste() -> None:
    sejour = Sejour(
        reservation_id=1,
        chambre_id=1,
        date_debut=NUIT_18,
        date_fin=DEPART_20,
        prix_ttc=Decimal("100"),
        taxe_sejour=Decimal("4"),
    )
    conso = Consommation(reservation_id=1, libelle="Petit-déjeuner", montant=Decimal("12"), jour=NUIT_18)
    reglement = Reglement(reservation_id=1, mode="CB", montant=Decimal("50"), jour=NUIT_18)

    compte = synthese([sejour], [conso], [reglement])

    assert compte.consommations == Decimal("12.00")
    assert compte.regle == Decimal("50.00")
    assert compte.reste == Decimal("66.00")


def test_enregistrer_le_dossier_se_relit_comme_la_fiche(session: Session) -> None:
    client, chambre, reservation = _dossier(session)
    sejour = enregistrer_sejour(
        session,
        reservation_id=reservation.id,
        chambre_id=chambre.id,
        date_debut=NUIT_18,
        date_fin=DEPART_20,
        type_produit="Single BB",
        prix_ttc=Decimal("137.64"),
        remise_pct=Decimal("0"),
        adultes=1,
        enfants=0,
        taxe_sejour=Decimal("4"),
    )
    session.commit()
    enregistrer_dossier(session, reservation.id, _saisi(client.id, traite=True, type_voiture="Citadine"))
    session.commit()

    fiche = lire_reservation(session, reservation.id)

    assert fiche["occupant"] == "LE CLOEREC Benedicte"
    assert fiche["client"] == "PASSAGE"
    assert fiche["pays"] == "FRANCE"
    assert fiche["partenaire"] == "Booking.com"
    assert fiche["etat"] == "en_cours"
    assert fiche["etat_label"] == "En cours"
    assert fiche["traite"] is True
    assert fiche["type_voiture"] == "Citadine"
    assert fiche["notes"] == "arrivé : 19h20"
    assert fiche["modifications"] == []
    assert fiche["sejours"][0]["id"] == sejour.id
    assert fiche["sejours"][0]["nuits"] == 2
    assert fiche["sejours"][0]["chambre_nom"] == "406"
    assert Decimal(fiche["sejours"][0]["prix_ttc"]) == Decimal("137.64")
    assert Decimal(fiche["sejours"][0]["taxe_sejour"]) == Decimal("4.00")
    compte = compte_fiche(fiche["sejours"], fiche["consommations"], fiche["reglements"])
    assert compte.ttc == Decimal("137.64")
    assert compte.taxe == Decimal("4.00")
    assert compte.reste == Decimal("141.64")


def test_annuler_libere_la_chambre_et_reprendre_la_refuse_si_elle_est_reprise(session: Session) -> None:
    client, chambre, reservation = _dossier(session)
    enregistrer_sejour(
        session,
        reservation_id=reservation.id,
        chambre_id=chambre.id,
        date_debut=NUIT_10,
        date_fin=DEPART_12,
    )
    session.commit()
    enregistrer_dossier(session, reservation.id, _saisi(client.id, etat="annulee", nom_occupant=None))
    session.commit()

    assert etat_affiche(reservation.statut, reservation.etat_dossier) == "annulee"
    autre = Reservation(client_id=client.id)
    session.add(autre)
    session.commit()
    enregistrer_sejour(
        session,
        reservation_id=autre.id,
        chambre_id=chambre.id,
        date_debut=NUIT_10,
        date_fin=DEPART_12,
    )
    session.commit()

    with pytest.raises(ChambreOccupee):
        appliquer_etat_dossier(session, reservation, "en_cours")

    assert str(reservation.statut) == StatutReservation.annulee


def test_prix_negatif_et_montant_illisible_sont_refuses(session: Session) -> None:
    _, chambre, reservation = _dossier(session)

    with pytest.raises(SejourInvalide):
        enregistrer_sejour(
            session,
            reservation_id=reservation.id,
            chambre_id=chambre.id,
            date_debut=NUIT_10,
            date_fin=DEPART_12,
            prix_ttc=Decimal("-1"),
        )
    with pytest.raises(DossierInvalide):
        lire_montant("abc")
    with pytest.raises(DossierInvalide):
        ajouter_consommation(session, reservation.id, "  ", 1, Decimal("5"), NUIT_10)

    assert session.exec(select(Sejour)).all() == []
    assert session.exec(select(Consommation)).all() == []


def test_un_ticket_sans_objet_est_refuse(session: Session) -> None:
    from ma_receptionniste.dossier import ajouter_ticket

    _, _, reservation = _dossier(session)

    with pytest.raises(DossierInvalide):
        ajouter_ticket(session, reservation.id, "  ")


def test_la_note_historique_reste_une_modification(session: Session) -> None:
    from ma_receptionniste.models import Historique

    client, _, reservation = _dossier(session)
    session.add(
        Historique(
            reservation_id=reservation.id,
            description="Appel du client",
            date=datetime(2026, 10, 18, 19, 20, tzinfo=UTC),
        )
    )
    session.commit()
    enregistrer_dossier(session, reservation.id, _saisi(client.id))
    session.commit()

    fiche = lire_reservation(session, reservation.id)

    assert fiche["notes"] == "arrivé : 19h20"
    assert [note["description"] for note in fiche["modifications"]] == ["Appel du client"]
