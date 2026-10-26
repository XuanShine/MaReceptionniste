from datetime import UTC, date, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from ma_receptionniste2.models import Chambre, Client, EtatChambre, Historique, Reservation, StatutReservation
from ma_receptionniste2.sejours import enregistrer_sejour

NOM_MAX = 200
NOTE_MAX = 4000


class SaisieRefusee(ValueError):
    """Le message est affiché tel quel au bureau."""


class NomChambrePris(ValueError):
    pass


def _vide(valeur: str | None) -> str | None:
    if valeur is None:
        return None
    texte = valeur.strip()
    return texte or None


def _nom(valeur: str, message_vide: str = "Le nom est obligatoire") -> str:
    texte = valeur.strip()
    if not texte:
        raise SaisieRefusee(message_vide)
    if len(texte) > NOM_MAX:
        raise SaisieRefusee("Le nom est trop long")
    return texte


def creer_chambre(session: Session, nom: str, position: int) -> Chambre:
    if position < 0:
        raise SaisieRefusee("La position doit être positive ou nulle")
    chambre = Chambre(nom=_nom(nom), position=position)
    session.add(chambre)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise NomChambrePris from None
    return chambre


def basculer_etat(session: Session, chambre_id: int) -> Chambre | None:
    chambre = session.get(Chambre, chambre_id)
    if chambre is None:
        return None
    chambre.etat = EtatChambre.pret if str(chambre.etat) == EtatChambre.non_pret else EtatChambre.non_pret
    session.add(chambre)
    session.flush()
    return chambre


def _borne(valeur: str | None, plafond: int, message: str) -> str | None:
    texte = _vide(valeur)
    if texte and len(texte) > plafond:
        raise SaisieRefusee(message)
    return texte


def creer_client(
    session: Session,
    nom: str,
    prenom: str | None = None,
    email: str | None = None,
    telephone: str | None = None,
    adresse: str | None = None,
    notes: str | None = None,
) -> Client:
    client = Client(
        nom=_nom(nom),
        prenom=_borne(prenom, NOM_MAX, "Le prénom est trop long"),
        email=_borne(email, NOM_MAX, "L'email est trop long"),
        telephone=_borne(telephone, NOM_MAX, "Le téléphone est trop long"),
        adresse=_borne(adresse, NOTE_MAX, "L'adresse est trop longue"),
        notes=_borne(notes, NOTE_MAX, "La note est trop longue"),
    )
    session.add(client)
    session.flush()
    return client


def creer_reservation(session: Session, client_id: int) -> Reservation:
    if session.get(Client, client_id) is None:
        raise SaisieRefusee("Choisissez un client")
    reservation = Reservation(client_id=client_id)
    session.add(reservation)
    session.flush()
    return reservation


def ajouter_sejour(
    session: Session,
    reservation_id: int,
    chambre_id: int,
    date_debut: date,
    date_fin: date,
    nom_client: str | None = None,
):
    sejour = enregistrer_sejour(
        session,
        reservation_id=reservation_id,
        chambre_id=chambre_id,
        date_debut=date_debut,
        date_fin=date_fin,
        nom_client=_vide(nom_client),
    )
    session.flush()
    return sejour


def annuler_reservation(session: Session, reservation_id: int) -> bool:
    reservation = session.get(Reservation, reservation_id)
    if reservation is None:
        return False
    reservation.statut = StatutReservation.annulee
    session.add(reservation)
    session.flush()
    return True


def ajouter_note(session: Session, reservation_id: int, user_id: int | None, description: str) -> Historique:
    if session.get(Reservation, reservation_id) is None:
        raise SaisieRefusee("Réservation introuvable")
    texte = description.strip()
    if not texte:
        raise SaisieRefusee("La note est vide")
    if len(texte) > NOTE_MAX:
        raise SaisieRefusee("La note est trop longue")
    note = Historique(
        reservation_id=reservation_id,
        user_id=user_id,
        description=texte,
        date=datetime.now(UTC),
    )
    session.add(note)
    session.flush()
    return note
