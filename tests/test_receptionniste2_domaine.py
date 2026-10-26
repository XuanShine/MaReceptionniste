"""Règle d'hôtel : date_fin est le matin du départ, elle ne compte pas comme une nuit.

Un séjour du 10 au 12 occupe les nuits du 10 et du 11. Un autre peut commencer le 12.
Une réservation annulée garde ses séjours, sans bloquer la chambre.
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from ma_receptionniste2.affichage import instant_fr
from ma_receptionniste2.auth import EmailDejaUtilise, IdentifiantsRefuses, authentifier, inscrire, safe_redirect
from ma_receptionniste2.db import moteur
from ma_receptionniste2.lectures import BlocSejour, nuits_entre, segments, semaine_planning
from ma_receptionniste2.models import (
    Base,
    Chambre,
    Client,
    EtatChambre,
    Historique,
    Reservation,
    Sejour,
    StatutReservation,
    User,
)
from ma_receptionniste2.sejours import (
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
    engine = moteur("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as ouverte:
        yield ouverte


def colonnes_indexees(session: Session, table: str) -> set[str]:
    connection = session.connection()
    index_names = [row[1] for row in connection.exec_driver_sql(f"PRAGMA index_list('{table}')")]
    colonnes: set[str] = set()
    for name in index_names:
        for info in connection.exec_driver_sql(f"PRAGMA index_info('{name}')"):
            colonnes.add(info[2])
    return colonnes


def dossier(session: Session, *, nom_chambre: str = "101", position: int = 1):
    client = Client(nom="Dupont", prenom="Alice")
    chambre = Chambre(nom=nom_chambre, position=position)
    session.add(client)
    session.add(chambre)
    session.commit()
    reservation = Reservation(client_id=client.id)
    session.add(reservation)
    session.commit()
    return client, chambre, reservation


def test_le_schema_n_ecrase_pas_l_application_d_origine():
    from ma_receptionniste.models import Client as Ancien

    assert Ancien.__table__.metadata is not Client.__table__.metadata
    assert "client" in Ancien.__table__.metadata.tables
    assert "client" in Client.__table__.metadata.tables


@pytest.mark.parametrize(
    ("debut_a", "fin_a", "debut_b", "fin_b", "chevauche"),
    [
        (NUIT_10, DEPART_12, DEPART_12, DEPART_14, False),
        (NUIT_10, DEPART_12, NUIT_11, date(2026, 10, 13), True),
        (NUIT_10, DEPART_14, NUIT_11, DEPART_12, True),
        (DEPART_12, DEPART_14, NUIT_10, DEPART_12, False),
    ],
)
def test_periodes_se_chevauchent(debut_a, fin_a, debut_b, fin_b, chevauche) -> None:
    assert periodes_se_chevauchent(debut_a, fin_a, debut_b, fin_b) is chevauche


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
    assert chambre_libre(session, chambre.id, DEPART_12, DEPART_14)
    assert not chambre_libre(session, chambre.id, NUIT_11, date(2026, 10, 13))
    assert reservation.client.nom == "Dupont"
    assert client.reservations[0].id == reservation.id
    assert reservation.sejours[0].chambre.nom == "101"


def test_sejour_adjacent_accepte(session: Session) -> None:
    _, chambre, reservation = dossier(session)
    enregistrer_sejour(
        session, reservation_id=reservation.id, chambre_id=chambre.id, date_debut=NUIT_10, date_fin=DEPART_12
    )
    session.commit()
    suivant = enregistrer_sejour(
        session, reservation_id=reservation.id, chambre_id=chambre.id, date_debut=DEPART_12, date_fin=DEPART_14
    )
    session.commit()
    assert suivant.date_debut == DEPART_12


def test_chevauchement_refuse(session: Session) -> None:
    _, chambre, reservation = dossier(session)
    enregistrer_sejour(
        session, reservation_id=reservation.id, chambre_id=chambre.id, date_debut=NUIT_10, date_fin=DEPART_12
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
    _, chambre, reservation = dossier(session)
    autre = Chambre(nom="102", position=2)
    session.add(autre)
    session.commit()
    enregistrer_sejour(
        session, reservation_id=reservation.id, chambre_id=chambre.id, date_debut=NUIT_10, date_fin=DEPART_12
    )
    session.commit()
    second = enregistrer_sejour(
        session, reservation_id=reservation.id, chambre_id=autre.id, date_debut=NUIT_10, date_fin=DEPART_12
    )
    session.commit()
    assert second.chambre_id == autre.id


def test_reservation_annulee_libere_la_chambre(session: Session) -> None:
    _, chambre, reservation = dossier(session)
    enregistrer_sejour(
        session, reservation_id=reservation.id, chambre_id=chambre.id, date_debut=NUIT_10, date_fin=DEPART_12
    )
    session.commit()
    reservation.statut = StatutReservation.annulee
    session.commit()
    autre = Reservation(client_id=reservation.client_id)
    session.add(autre)
    session.commit()
    sejour = enregistrer_sejour(
        session, reservation_id=autre.id, chambre_id=chambre.id, date_debut=NUIT_10, date_fin=DEPART_12
    )
    session.commit()
    assert sejour.id is not None
    assert reservation.statut == StatutReservation.annulee


@pytest.mark.parametrize(("debut", "fin"), [(NUIT_10, NUIT_10), (DEPART_12, NUIT_10)])
def test_dates_de_sejour_invalides(session: Session, debut: date, fin: date) -> None:
    _, chambre, reservation = dossier(session)
    with pytest.raises(SejourInvalide):
        enregistrer_sejour(
            session, reservation_id=reservation.id, chambre_id=chambre.id, date_debut=debut, date_fin=fin
        )


def test_modifier_un_sejour_ne_se_chevauche_pas_lui_meme(session: Session) -> None:
    _, chambre, reservation = dossier(session)
    sejour = enregistrer_sejour(
        session, reservation_id=reservation.id, chambre_id=chambre.id, date_debut=NUIT_10, date_fin=DEPART_12
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


def test_valeurs_par_defaut(session: Session) -> None:
    chambre = Chambre(nom="101", position=1)
    assert chambre.etat == EtatChambre.non_pret
    client = Client(nom="Dupont")
    session.add(client)
    session.add(chambre)
    session.commit()
    reservation = Reservation(client_id=client.id)
    session.add(reservation)
    session.commit()
    assert reservation.statut == StatutReservation.confirmee
    assert reservation.date_creation.tzinfo is not None
    assert client.prenom is None
    assert client.adresse is None
    assert client.notes is None


def test_historique_avec_et_sans_utilisateur(session: Session) -> None:
    _, _, reservation = dossier(session)
    user = User(email="alice@example.com", nom="Alice", password_hash="hash")
    session.add(user)
    session.commit()
    liee = Historique(
        reservation_id=reservation.id,
        user_id=user.id,
        description="Appel du client",
        date=datetime(2026, 10, 10, 9, 0, tzinfo=UTC),
    )
    libre = Historique(description="Pense-bête accueil", date=datetime(2026, 10, 10, 9, 5, tzinfo=UTC))
    session.add(liee)
    session.add(libre)
    session.commit()
    assert liee.user.nom == "Alice"
    assert reservation.historiques[0].description == "Appel du client"
    assert libre.reservation_id is None
    assert libre.user_id is None


def test_nom_de_chambre_unique(session: Session) -> None:
    session.add(Chambre(nom="101", position=1))
    session.commit()
    session.add(Chambre(nom="101", position=2))
    with pytest.raises(IntegrityError):
        session.commit()


def test_reservation_sans_client_refusee(session: Session) -> None:
    session.add(Reservation(client_id=999))
    with pytest.raises(IntegrityError):
        session.commit()


def test_effacer_un_client_qui_a_une_reservation(session: Session) -> None:
    client, _, _ = dossier(session)
    session.delete(client)
    with pytest.raises(IntegrityError):
        session.commit()


def test_effacer_une_chambre_occupee(session: Session) -> None:
    _, chambre, reservation = dossier(session)
    enregistrer_sejour(
        session, reservation_id=reservation.id, chambre_id=chambre.id, date_debut=NUIT_10, date_fin=DEPART_12
    )
    session.commit()
    session.delete(chambre)
    with pytest.raises(IntegrityError):
        session.commit()


def test_effacer_une_reservation_qui_a_un_sejour(session: Session) -> None:
    _, chambre, reservation = dossier(session)
    enregistrer_sejour(
        session, reservation_id=reservation.id, chambre_id=chambre.id, date_debut=NUIT_10, date_fin=DEPART_12
    )
    session.commit()
    session.delete(reservation)
    with pytest.raises(IntegrityError):
        session.commit()


def test_effacer_l_utilisateur_conserve_la_note(session: Session) -> None:
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
    session.refresh(note)
    assert note.user_id is None
    assert note.description == "Appel du client"
    assert note.reservation_id == reservation.id


def test_effacer_une_reservation_conserve_la_note(session: Session) -> None:
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


def test_planning_compte_les_nuits_et_ignore_les_annulees(session: Session) -> None:
    client = Client(nom="Dupont", prenom="Alice")
    chambre = Chambre(nom="101", position=1)
    autre = Chambre(nom="102", position=2)
    session.add(client)
    session.add(chambre)
    session.add(autre)
    session.commit()
    confirmee = Reservation(client_id=client.id)
    annulee = Reservation(client_id=client.id, statut=StatutReservation.annulee)
    session.add(confirmee)
    session.add(annulee)
    session.commit()
    session.add(Sejour(reservation_id=confirmee.id, chambre_id=chambre.id, date_debut=NUIT_10, date_fin=DEPART_12))
    session.add(
        Sejour(
            reservation_id=annulee.id,
            chambre_id=autre.id,
            date_debut=NUIT_10,
            date_fin=DEPART_12,
            nom_client="Ne pas afficher",
        )
    )
    session.commit()

    assert nuits_entre(NUIT_10, DEPART_12, NUIT_10, date(2026, 10, 13)) == [NUIT_10, NUIT_11]
    semaine = semaine_planning(session, NUIT_10, NUIT_10)
    ligne = next(item for item in semaine.lignes if item.nom == "101")
    assert ligne.segments[0].longueur == 2
    assert ligne.segments[0].sejour.nom == "Alice Dupont"
    assert ligne.segments[0].sejour.reservation_id == confirmee.id
    assert ligne.segments[1].sejour is None
    libre = next(item for item in semaine.lignes if item.nom == "102")
    assert all(segment.sejour is None for segment in libre.segments)


def test_segments_decoupent_une_ligne() -> None:
    bloc = BlocSejour(reservation_id=1, nom="Alice", nuits=(NUIT_10, NUIT_11))
    blocs = segments([NUIT_10, NUIT_11, DEPART_12], [bloc])
    assert [item.longueur for item in blocs] == [2, 1]
    assert blocs[1].sejour is None


def test_mot_de_passe_et_email(session: Session) -> None:
    user = inscrire(session, "  Alice@Example.com ", "Alice", "secret")
    session.commit()
    assert "secret" not in user.password_hash
    assert authentifier(session, "ALICE@example.com", "secret").id == user.id
    with pytest.raises(IdentifiantsRefuses):
        authentifier(session, "alice@example.com", "mauvais")
    with pytest.raises(EmailDejaUtilise):
        inscrire(session, "Alice@example.com", "Alice 2", "secret")


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("/clients", "/clients"),
        (None, "/"),
        ("", "/"),
        ("https://evil.com", "/"),
        ("//evil.com", "/"),
        ("/ok\nSet-Cookie", "/"),
    ],
)
def test_safe_redirect(target: str | None, expected: str) -> None:
    assert safe_redirect(target) == expected


def test_heure_affichee_a_paris() -> None:
    assert instant_fr(datetime(2026, 10, 10, 9, 0, tzinfo=UTC)) == "10/10/2026 11:00"
    assert instant_fr(datetime(2026, 1, 10, 9, 0, tzinfo=UTC)) == "10/01/2026 10:00"
