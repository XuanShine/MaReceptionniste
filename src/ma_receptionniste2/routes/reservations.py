from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Form, Request
from starlette.exceptions import HTTPException

from ma_receptionniste2.calendrier import lire_date
from ma_receptionniste2.commandes import (
    SaisieRefusee,
    ajouter_note,
    ajouter_sejour,
    annuler_reservation,
    creer_reservation,
)
from ma_receptionniste2.lectures import choix_chambres, choix_clients, detail_reservation, lister_reservations
from ma_receptionniste2.sejours import ChambreOccupee, SejourInvalide
from ma_receptionniste2.web import SessionDB, Utilisateur, exiger_jeton, html, repondre, socle

router = APIRouter()
Texte = Annotated[str, Form()]


def _entier(valeur: str) -> int | None:
    try:
        return int(valeur)
    except ValueError:
        return None


def _liste(request, session, user, *, erreur=None, client_id=""):
    return socle(
        request,
        user,
        reservations=lister_reservations(session),
        clients=choix_clients(session),
        erreur=erreur,
        client_id=client_id,
        actif="/reservations",
    )


def _fiche(
    request,
    session,
    user,
    reservation_id: int,
    *,
    erreur=None,
    erreur_note=None,
    chambre_id="",
    nom_client="",
    date_debut="",
    date_fin="",
    description="",
):
    fiche = detail_reservation(session, reservation_id)
    if fiche is None:
        return None
    aujourd_hui = request.app.state.aujourd_hui()
    if not date_debut:
        date_debut = aujourd_hui.isoformat()
    if not date_fin:
        date_fin = (aujourd_hui + timedelta(days=1)).isoformat()
    return socle(
        request,
        user,
        fiche=fiche,
        chambres=choix_chambres(session),
        erreur=erreur,
        erreur_note=erreur_note,
        chambre_id=chambre_id,
        nom_client=nom_client,
        date_debut=date_debut,
        date_fin=date_fin,
        description=description,
        actif="/reservations",
    )


@router.get("/reservations")
def page(request: Request, session: SessionDB, user: Utilisateur):
    return html(request, "reservations.html", _liste(request, session, user))


@router.post("/reservations")
def creer(
    request: Request,
    session: SessionDB,
    user: Utilisateur,
    client_id: Texte = "",
    csrf: Texte = "",
):
    exiger_jeton(request, csrf)
    identifiant = _entier(client_id)
    if identifiant is None:
        erreur = "Choisissez un client"
    else:
        try:
            reservation = creer_reservation(session, identifiant)
        except SaisieRefusee:
            erreur = "Choisissez un client"
        else:
            return repondre(
                request,
                page="reservations.html",
                fragment="_reservations.html",
                contexte={},
                redirection=f"/reservations/{reservation.id}",
            )
    return repondre(
        request,
        page="reservations.html",
        fragment="_reservations.html",
        contexte=_liste(request, session, user, erreur=erreur, client_id=client_id),
    )


@router.get("/reservations/{reservation_id}")
def fiche(request: Request, reservation_id: int, session: SessionDB, user: Utilisateur):
    contexte = _fiche(request, session, user, reservation_id)
    if contexte is None:
        raise HTTPException(404)
    return html(request, "reservation.html", contexte)


@router.post("/reservations/{reservation_id}/annuler")
def annuler(request: Request, reservation_id: int, session: SessionDB, user: Utilisateur, csrf: Texte = ""):
    exiger_jeton(request, csrf)
    if not annuler_reservation(session, reservation_id):
        raise HTTPException(404)
    contexte = _fiche(request, session, user, reservation_id)
    return repondre(request, page="reservation.html", fragment="_fiche.html", contexte=contexte)


@router.post("/reservations/{reservation_id}/sejours")
def sejour(
    request: Request,
    reservation_id: int,
    session: SessionDB,
    user: Utilisateur,
    chambre_id: Texte = "",
    nom_client: Texte = "",
    date_debut: Texte = "",
    date_fin: Texte = "",
    csrf: Texte = "",
):
    exiger_jeton(request, csrf)
    fiche = detail_reservation(session, reservation_id)
    if fiche is None:
        raise HTTPException(404)
    identifiant = _entier(chambre_id)
    debut = lire_date(date_debut)
    fin = lire_date(date_fin)
    erreur = None
    if fiche.annulee:
        erreur = "La réservation est annulée"
    elif identifiant is None or debut is None or fin is None:
        erreur = "Chambre et dates obligatoires"
    else:
        try:
            ajouter_sejour(session, reservation_id, identifiant, debut, fin, nom_client)
        except ChambreOccupee:
            erreur = "La chambre est déjà occupée sur cette période"
        except SejourInvalide as exc:
            erreur = str(exc)
        else:
            nom_client = ""
    contexte = _fiche(
        request,
        session,
        user,
        reservation_id,
        erreur=erreur,
        chambre_id=chambre_id,
        nom_client=nom_client,
        date_debut=date_debut,
        date_fin=date_fin,
    )
    return repondre(request, page="reservation.html", fragment="_fiche_sejours.html", contexte=contexte)


@router.post("/reservations/{reservation_id}/notes")
def note(
    request: Request,
    reservation_id: int,
    session: SessionDB,
    user: Utilisateur,
    description: Texte = "",
    csrf: Texte = "",
):
    exiger_jeton(request, csrf)
    erreur_note = None
    try:
        ajouter_note(session, reservation_id, user.id, description)
    except SaisieRefusee as exc:
        erreur_note = str(exc)
    else:
        description = ""
    contexte = _fiche(request, session, user, reservation_id, erreur_note=erreur_note, description=description)
    if contexte is None:
        raise HTTPException(404)
    return repondre(request, page="reservation.html", fragment="_fiche_notes.html", contexte=contexte)
