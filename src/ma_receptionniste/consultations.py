from datetime import date, timedelta

from sqlmodel import Session, select

from ma_receptionniste.db import get_session
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

ETAT_LABEL = {
    EtatChambre.pret: "Prête",
    EtatChambre.non_pret: "Non prête",
}
STATUT_LABEL = {
    StatutReservation.confirmee: "Confirmée",
    StatutReservation.annulee: "Annulée",
}


def nuits_entre(debut_sejour: date, fin_sejour: date, debut_fenetre: date, fin_fenetre: date) -> list[date]:
    """Nuits du séjour visibles dans [debut_fenetre, fin_fenetre). Le matin du départ est exclu."""
    jour = max(debut_sejour, debut_fenetre)
    borne = min(fin_sejour, fin_fenetre)
    nuits: list[date] = []
    while jour < borne:
        nuits.append(jour)
        jour += timedelta(days=1)
    return nuits


def segments(jours: list[date], sejours: list[dict]) -> list[dict]:
    """Découpe une ligne de planning : un bloc par séjour continu, une case par nuit libre."""
    par_nuit: dict[date, dict] = {}
    for sejour in sejours:
        for nuit in sejour["nuits"]:
            par_nuit[nuit] = sejour
    resultat: list[dict] = []
    index = 0
    while index < len(jours):
        sejour = par_nuit.get(jours[index])
        longueur = 1
        if sejour is not None:
            while index + longueur < len(jours) and par_nuit.get(jours[index + longueur]) is sejour:
                longueur += 1
        resultat.append({"sejour": sejour, "longueur": longueur})
        index += longueur
    return resultat


def _nom_client(prenom: str | None, nom: str) -> str:
    if prenom:
        return f"{prenom} {nom}"
    return nom


def _statut_label(valeur: StatutReservation | str) -> str:
    cle = str(valeur)
    return STATUT_LABEL.get(StatutReservation(cle), cle)


def _etat(valeur: EtatChambre | str) -> str:
    return valeur.value if isinstance(valeur, EtatChambre) else str(valeur)


def planning(session: Session, debut: date, fin: date) -> dict:
    chambres = session.exec(select(Chambre).order_by(Chambre.position, Chambre.nom)).all()
    lignes = session.exec(
        select(Sejour, Client)
        .join(Reservation, Reservation.id == Sejour.reservation_id)
        .join(Client, Client.id == Reservation.client_id)
        .where(Reservation.statut != StatutReservation.annulee)
        .where(Sejour.date_debut < fin)
        .where(Sejour.date_fin > debut)
        .order_by(Sejour.date_debut)
    ).all()
    sejours = []
    for sejour, client in lignes:
        sejours.append(
            {
                "id": sejour.id,
                "chambre_id": sejour.chambre_id,
                "reservation_id": sejour.reservation_id,
                "date_debut": sejour.date_debut,
                "date_fin": sejour.date_fin,
                "nom": sejour.nom_client or _nom_client(client.prenom, client.nom),
                "nuits": nuits_entre(sejour.date_debut, sejour.date_fin, debut, fin),
            }
        )
    return {
        "chambres": [
            {
                "id": chambre.id,
                "nom": chambre.nom,
                "position": chambre.position,
                "etat": _etat(chambre.etat),
                "etat_label": ETAT_LABEL.get(EtatChambre(_etat(chambre.etat)), _etat(chambre.etat)),
            }
            for chambre in chambres
        ],
        "sejours": sejours,
    }


def charger_planning(debut: date, fin: date) -> dict:
    with get_session() as session:
        return planning(session, debut, fin)


def lister_chambres() -> list[dict]:
    with get_session() as session:
        chambres = session.exec(select(Chambre).order_by(Chambre.position, Chambre.nom)).all()
        return [
            {
                "id": chambre.id,
                "nom": chambre.nom,
                "position": chambre.position,
                "etat": _etat(chambre.etat),
                "etat_label": ETAT_LABEL.get(EtatChambre(_etat(chambre.etat)), _etat(chambre.etat)),
            }
            for chambre in chambres
        ]


def lister_clients() -> list[dict]:
    with get_session() as session:
        clients = session.exec(select(Client).order_by(Client.cree_le.desc())).all()
        return [
            {
                "id": client.id,
                "nom": client.nom,
                "prenom": client.prenom,
                "email": client.email,
                "telephone": client.telephone,
                "adresse": client.adresse,
                "notes": client.notes,
            }
            for client in clients
        ]


def options_clients() -> dict[int, str]:
    # ui.select attend identifiant → libellé.
    return {
        client["id"]: f"{_nom_client(client['prenom'], client['nom'])} #{client['id']}" for client in lister_clients()
    }


def options_chambres() -> dict[int, str]:
    return {chambre["id"]: chambre["nom"] for chambre in lister_chambres()}


def _sejour_dict(sejour: Sejour, chambre_nom: str) -> dict:
    return {
        "id": sejour.id,
        "chambre_id": sejour.chambre_id,
        "chambre_nom": chambre_nom,
        "date_debut": sejour.date_debut,
        "date_fin": sejour.date_fin,
        "nom_client": sejour.nom_client,
    }


def _note_dict(note: Historique, auteur: str | None) -> dict:
    return {
        "id": note.id,
        "description": note.description,
        "date": note.date,
        "auteur": auteur,
    }


def lister_reservations() -> list[dict]:
    with get_session() as session:
        reservations = session.exec(select(Reservation).order_by(Reservation.date_creation.desc())).all()
        resultat = []
        for reservation in reservations:
            client = session.get(Client, reservation.client_id)
            sejours = session.exec(
                select(Sejour).where(Sejour.reservation_id == reservation.id).order_by(Sejour.date_debut)
            ).all()
            resultat.append(
                {
                    "id": reservation.id,
                    "client": _nom_client(client.prenom, client.nom) if client else "Client inconnu",
                    "statut": str(reservation.statut),
                    "statut_label": _statut_label(reservation.statut),
                    "sejours": [
                        _sejour_dict(sejour, session.get(Chambre, sejour.chambre_id).nom) for sejour in sejours
                    ],
                }
            )
        return resultat


def detail_reservation(reservation_id: int) -> dict | None:
    with get_session() as session:
        reservation = session.get(Reservation, reservation_id)
        if reservation is None:
            return None
        client = session.get(Client, reservation.client_id)
        sejours = session.exec(
            select(Sejour).where(Sejour.reservation_id == reservation.id).order_by(Sejour.date_debut)
        ).all()
        notes = session.exec(
            select(Historique).where(Historique.reservation_id == reservation.id).order_by(Historique.date.desc())
        ).all()
        return {
            "id": reservation.id,
            "client": _nom_client(client.prenom, client.nom) if client else "Client inconnu",
            "statut": str(reservation.statut),
            "statut_label": _statut_label(reservation.statut),
            "sejours": [_sejour_dict(sejour, session.get(Chambre, sejour.chambre_id).nom) for sejour in sejours],
            "notes": [_note_dict(note, _auteur(session, note.user_id)) for note in notes],
        }


def _auteur(session: Session, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    user = session.get(User, user_id)
    return user.nom if user else None
