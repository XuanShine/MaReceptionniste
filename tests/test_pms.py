"""Contrat des modèles PMS et de l'écriture d'un séjour.

Règle d'hôtel utilisée partout : date_fin est le matin du départ, elle ne compte
pas comme une nuit. Un séjour du 10 au 12 occupe les nuits du 10 et du 11.
Un autre séjour peut donc commencer le 12.
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

from ma_receptionniste.models import (
    Chambre,
    Client,
    EtatChambre,
    Historique,
    Reservation,
    Sejour,
    StatutReservation,
    User,
)
from ma_receptionniste.sejours import (
    ChambreOccupee,
    SejourInvalide,
    chambre_libre,
    enregistrer_sejour,
    periodes_se_chevauchent,
)

NUIT_10 = date(2026, 10, 10)
DEPART_12 = date(2026, 10, 12)
NUIT_11 = date(2026, 10, 11)
DEPART_14 = date(2026, 10, 14)


@pytest.fixture
def session():
    # SQLite n'applique les clés étrangères que si ce pragma est posé
    # sur chaque connexion. Sans lui, un client_id inventé serait accepté.
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _activer_cles_etrangeres(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def colonnes_indexees(session: Session, table: str) -> set[str]:
    # Une FK SQLite n'a pas d'index automatique. On vérifie que les colonnes
    # utilisées pour chercher les séjours d'une chambre, etc., sont bien indexées.
    connection = session.connection()
    index_names = [row[1] for row in connection.exec_driver_sql(f"PRAGMA index_list('{table}')")]
    colonnes: set[str] = set()
    for name in index_names:
        for info in connection.exec_driver_sql(f"PRAGMA index_info('{name}')"):
            colonnes.add(info[2])
    return colonnes


def dossier(session: Session, *, nom_chambre: str = "101", position: int = 1):
    """Un client, une chambre et une réservation confirmée, prêts pour un séjour."""
    client = Client(nom="Dupont")
    chambre = Chambre(nom=nom_chambre, position=position)
    session.add(client)
    session.add(chambre)
    session.commit()

    reservation = Reservation(client_id=client.id)
    session.add(reservation)
    session.commit()
    return client, chambre, reservation


# --- La règle de dates, sans base ---


@pytest.mark.parametrize(
    ("debut_a", "fin_a", "debut_b", "fin_b", "chevauche"),
    [
        # Se touchent le matin du départ : la chambre est libre pour le suivant.
        (NUIT_10, DEPART_12, DEPART_12, DEPART_14, False),
        # Partagent la nuit du 11.
        (NUIT_10, DEPART_12, NUIT_11, date(2026, 10, 13), True),
        # Le second est entièrement dans le premier.
        (NUIT_10, DEPART_14, NUIT_11, DEPART_12, True),
        # Même période, dans l'autre sens : le chevauchement n'a pas d'ordre.
        (DEPART_12, DEPART_14, NUIT_10, DEPART_12, False),
    ],
)
def test_periodes_se_chevauchent(debut_a, fin_a, debut_b, fin_b, chevauche) -> None:
    assert periodes_se_chevauchent(debut_a, fin_a, debut_b, fin_b) is chevauche


# --- enregistrer_sejour est le seul chemin qui écrit un séjour ---


def test_enregistrer_sejour(session: Session) -> None:
    client, chambre, reservation = dossier(session)

    sejour = enregistrer_sejour(
        session,
        reservation_id=reservation.id,
        chambre_id=chambre.id,
        date_debut=NUIT_10,
        date_fin=DEPART_12,
        nom_client="Martin",
    )
    session.commit()

    assert isinstance(sejour, Sejour)
    assert sejour.id is not None
    assert sejour.nom_client == "Martin"
    # Le nom sur le séjour est optionnel : il ne sert que s'il diffère du client.
    assert chambre_libre(session, chambre.id, DEPART_12, DEPART_14)
    assert not chambre_libre(session, chambre.id, NUIT_11, date(2026, 10, 13))
    assert reservation.client.nom == "Dupont"
    assert client.reservations[0].id == reservation.id
    assert reservation.sejours[0].chambre.nom == "101"


def test_sejour_adjacent_accepte(session: Session) -> None:
    # Le premier part le 12, le second arrive le 12 : pas de nuit en commun.
    _, chambre, reservation = dossier(session)
    enregistrer_sejour(
        session,
        reservation_id=reservation.id,
        chambre_id=chambre.id,
        date_debut=NUIT_10,
        date_fin=DEPART_12,
    )
    session.commit()

    suivant = enregistrer_sejour(
        session,
        reservation_id=reservation.id,
        chambre_id=chambre.id,
        date_debut=DEPART_12,
        date_fin=DEPART_14,
    )
    session.commit()

    assert suivant.date_debut == DEPART_12


def test_chevauchement_refuse(session: Session) -> None:
    _, chambre, reservation = dossier(session)
    enregistrer_sejour(
        session,
        reservation_id=reservation.id,
        chambre_id=chambre.id,
        date_debut=NUIT_10,
        date_fin=DEPART_12,
    )
    session.commit()

    with pytest.raises(ChambreOccupee):
        enregistrer_sejour(
            session,
            reservation_id=reservation.id,
            chambre_id=chambre.id,
            date_debut=NUIT_11,
            date_fin=date(2026, 10, 13),
        )


def test_autre_chambre_peut_chevaucher(session: Session) -> None:
    # Deux chambres différentes peuvent être occupées les mêmes nuits,
    # y compris par la même réservation (une famille, deux chambres).
    _, chambre, reservation = dossier(session)
    autre = Chambre(nom="102", position=2)
    session.add(autre)
    session.commit()
    enregistrer_sejour(
        session,
        reservation_id=reservation.id,
        chambre_id=chambre.id,
        date_debut=NUIT_10,
        date_fin=DEPART_12,
    )
    session.commit()

    second = enregistrer_sejour(
        session,
        reservation_id=reservation.id,
        chambre_id=autre.id,
        date_debut=NUIT_10,
        date_fin=DEPART_12,
    )
    session.commit()

    assert second.chambre_id == autre.id


def test_reservation_annulee_libere_la_chambre(session: Session) -> None:
    # Annuler ne supprime pas la réservation : on change son statut.
    # Ses séjours ne bloquent plus la chambre.
    _, chambre, reservation = dossier(session)
    enregistrer_sejour(
        session,
        reservation_id=reservation.id,
        chambre_id=chambre.id,
        date_debut=NUIT_10,
        date_fin=DEPART_12,
    )
    session.commit()
    reservation.statut = StatutReservation.annulee
    session.commit()

    autre = Reservation(client_id=reservation.client_id)
    session.add(autre)
    session.commit()
    sejour = enregistrer_sejour(
        session,
        reservation_id=autre.id,
        chambre_id=chambre.id,
        date_debut=NUIT_10,
        date_fin=DEPART_12,
    )
    session.commit()

    assert sejour.id is not None
    assert reservation.statut == StatutReservation.annulee


@pytest.mark.parametrize(
    ("debut", "fin"),
    [
        (NUIT_10, NUIT_10),  # zéro nuit
        (DEPART_12, NUIT_10),  # départ avant l'arrivée
    ],
)
def test_dates_de_sejour_invalides(session: Session, debut: date, fin: date) -> None:
    _, chambre, reservation = dossier(session)

    with pytest.raises(SejourInvalide):
        enregistrer_sejour(
            session,
            reservation_id=reservation.id,
            chambre_id=chambre.id,
            date_debut=debut,
            date_fin=fin,
        )


def test_modifier_un_sejour_ne_se_chevauche_pas_lui_meme(session: Session) -> None:
    # ignorer_sejour_id retire ce séjour du calcul, sinon le rallonger
    # serait refusé à cause de ses propres nuits.
    _, chambre, reservation = dossier(session)
    sejour = enregistrer_sejour(
        session,
        reservation_id=reservation.id,
        chambre_id=chambre.id,
        date_debut=NUIT_10,
        date_fin=DEPART_12,
    )
    session.commit()

    modifie = enregistrer_sejour(
        session,
        reservation_id=reservation.id,
        chambre_id=chambre.id,
        date_debut=NUIT_10,
        date_fin=DEPART_14,
        ignorer_sejour_id=sejour.id,
    )
    session.commit()

    assert modifie.id == sejour.id
    assert modifie.date_fin == DEPART_14


# --- Modèles : valeurs par défaut et liens ---


def test_valeurs_par_defaut(session: Session) -> None:
    chambre = Chambre(nom="101", position=1)
    # Une chambre neuve n'est pas prête à recevoir quelqu'un.
    assert chambre.etat == EtatChambre.non_pret

    client = Client(nom="Dupont")
    session.add(client)
    session.add(chambre)
    session.commit()
    reservation = Reservation(client_id=client.id)
    session.add(reservation)
    session.commit()

    # Le cas courant est une réservation déjà confirmée.
    assert reservation.statut == StatutReservation.confirmee
    # SQLModel refuse un datetime sans fuseau : la valeur stockée est en UTC.
    assert reservation.date_creation.tzinfo is not None
    # Les champs ajoutés au client restent facultatifs.
    assert client.adresse is None
    assert client.notes is None


def test_historique_avec_et_sans_utilisateur(session: Session) -> None:
    client, _, reservation = dossier(session)
    user = User(email="alice@example.com", nom="Alice", password_hash="hash")
    session.add(user)
    session.commit()

    liee = Historique(
        reservation_id=reservation.id,
        user_id=user.id,
        description="Appel du client",
        date=datetime(2026, 10, 10, 9, 0, tzinfo=UTC),
    )
    # Une note peut exister sans réservation et sans compte (les deux FK sont vides).
    libre = Historique(
        description="Pense-bête accueil",
        date=datetime(2026, 10, 10, 9, 5, tzinfo=UTC),
    )
    session.add(liee)
    session.add(libre)
    session.commit()

    assert liee.user.nom == "Alice"
    assert reservation.historiques[0].description == "Appel du client"
    assert libre.reservation_id is None
    assert libre.user_id is None
    assert client.id == reservation.client_id


def test_nom_de_chambre_unique(session: Session) -> None:
    session.add(Chambre(nom="101", position=1))
    session.commit()
    session.add(Chambre(nom="101", position=2))

    with pytest.raises(IntegrityError):
        session.commit()


# --- Ce que les clés étrangères empêchent, et ce qu'elles laissent vivre ---


def test_reservation_sans_client_refusee(session: Session) -> None:
    reservation = Reservation(client_id=999)
    session.add(reservation)

    with pytest.raises(IntegrityError):
        session.commit()


def test_effacer_un_client_qui_a_une_reservation(session: Session) -> None:
    # RESTRICT : on ne fait pas disparaître un client encore cité.
    # L'annulation d'une réservation ne passe pas par une suppression.
    client, _, _ = dossier(session)
    session.delete(client)

    with pytest.raises(IntegrityError):
        session.commit()


def test_effacer_une_chambre_occupee(session: Session) -> None:
    _, chambre, reservation = dossier(session)
    enregistrer_sejour(
        session,
        reservation_id=reservation.id,
        chambre_id=chambre.id,
        date_debut=NUIT_10,
        date_fin=DEPART_12,
    )
    session.commit()
    session.delete(chambre)

    with pytest.raises(IntegrityError):
        session.commit()


def test_effacer_une_reservation_qui_a_un_sejour(session: Session) -> None:
    _, chambre, reservation = dossier(session)
    enregistrer_sejour(
        session,
        reservation_id=reservation.id,
        chambre_id=chambre.id,
        date_debut=NUIT_10,
        date_fin=DEPART_12,
    )
    session.commit()
    session.delete(reservation)

    with pytest.raises(IntegrityError):
        session.commit()


def test_effacer_l_utilisateur_conserve_la_note(session: Session) -> None:
    # ON DELETE SET NULL : le compte part, la trace de l'appel reste,
    # simplement sans auteur.
    _, _, reservation = dossier(session)
    user = User(email="alice@example.com", nom="Alice", password_hash="hash")
    session.add(user)
    session.commit()
    note = Historique(
        reservation_id=reservation.id,
        user_id=user.id,
        description="Appel du client",
        date=datetime(2026, 10, 10, 9, 0, tzinfo=UTC),
    )
    session.add(note)
    session.commit()

    session.delete(user)
    session.commit()
    # La mémoire de la session a encore l'ancien user_id : on relit la ligne.
    session.refresh(note)

    assert note.id is not None
    assert note.user_id is None
    assert note.description == "Appel du client"
    assert note.reservation_id == reservation.id


def test_effacer_une_reservation_conserve_la_note(session: Session) -> None:
    # Même règle pour la réservation, à condition qu'aucun séjour ne la retienne.
    # Ici la note n'a pas de séjour associé, la suppression est donc possible,
    # et reservation_id devient vide.
    _, _, reservation = dossier(session)
    note = Historique(
        reservation_id=reservation.id,
        description="Appel du client",
        date=datetime(2026, 10, 10, 9, 0, tzinfo=UTC),
    )
    session.add(note)
    session.commit()
    reservation_id = reservation.id

    session.delete(reservation)
    session.commit()
    session.refresh(note)

    assert note.reservation_id is None
    assert note.description == "Appel du client"
    assert session.get(Reservation, reservation_id) is None


def test_index_des_liens(session: Session) -> None:
    assert "client_id" in colonnes_indexees(session, "reservation")
    assert "reservation_id" in colonnes_indexees(session, "sejour")
    assert "chambre_id" in colonnes_indexees(session, "sejour")
    assert "reservation_id" in colonnes_indexees(session, "historique")
