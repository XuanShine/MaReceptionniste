from datetime import UTC, datetime

from ma_receptionniste.db import get_session
from ma_receptionniste.models import Chambre, Client, EtatChambre, Historique, Reservation, StatutReservation
from ma_receptionniste.sejours import enregistrer_sejour


def creer_chambre(nom: str, position: int) -> int:
    with get_session() as session:
        chambre = Chambre(nom=nom.strip(), position=position)
        session.add(chambre)
        session.commit()
        return chambre.id


def basculer_etat(chambre_id: int) -> None:
    with get_session() as session:
        chambre = session.get(Chambre, chambre_id)
        if chambre is None:
            return
        chambre.etat = EtatChambre.pret if str(chambre.etat) == EtatChambre.non_pret else EtatChambre.non_pret
        session.add(chambre)
        session.commit()


def creer_client(
    nom: str,
    prenom: str | None = None,
    email: str | None = None,
    telephone: str | None = None,
    adresse: str | None = None,
    notes: str | None = None,
) -> int:
    with get_session() as session:
        client = Client(
            nom=nom.strip(),
            prenom=_vide(prenom),
            email=_vide(email),
            telephone=_vide(telephone),
            adresse=_vide(adresse),
            notes=_vide(notes),
        )
        session.add(client)
        session.commit()
        return client.id


def creer_reservation(client_id: int) -> int:
    with get_session() as session:
        reservation = Reservation(client_id=client_id)
        session.add(reservation)
        session.commit()
        return reservation.id


def ajouter_sejour(
    reservation_id: int,
    chambre_id: int,
    date_debut,
    date_fin,
    nom_client: str | None = None,
) -> int:
    with get_session() as session:
        sejour = enregistrer_sejour(
            session,
            reservation_id=reservation_id,
            chambre_id=chambre_id,
            date_debut=date_debut,
            date_fin=date_fin,
            nom_client=_vide(nom_client),
        )
        session.commit()
        return sejour.id


def annuler_reservation(reservation_id: int) -> None:
    with get_session() as session:
        reservation = session.get(Reservation, reservation_id)
        if reservation is None:
            return
        reservation.statut = StatutReservation.annulee
        session.add(reservation)
        session.commit()


def ajouter_note(reservation_id: int, user_id: int | None, description: str) -> None:
    with get_session() as session:
        session.add(
            Historique(
                reservation_id=reservation_id,
                user_id=user_id,
                description=description.strip(),
                date=datetime.now(UTC),
            )
        )
        session.commit()


def _vide(valeur: str | None) -> str | None:
    if valeur is None:
        return None
    texte = valeur.strip()
    return texte or None
