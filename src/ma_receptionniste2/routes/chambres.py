from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from starlette.exceptions import HTTPException

from ma_receptionniste2.commandes import NomChambrePris, SaisieRefusee, basculer_etat, creer_chambre
from ma_receptionniste2.lectures import chambre_vue, lister_chambres
from ma_receptionniste2.web import SessionDB, Utilisateur, exiger_jeton, html, repondre, socle

router = APIRouter()
Texte = Annotated[str, Form()]


def _contexte(request: Request, session, user, *, erreur=None, nom="", position="1"):
    return socle(
        request,
        user,
        chambres=lister_chambres(session),
        erreur=erreur,
        nom=nom,
        position=position,
        actif="/chambres",
    )


@router.get("/chambres")
def page(request: Request, session: SessionDB, user: Utilisateur):
    return html(request, "chambres.html", _contexte(request, session, user))


@router.post("/chambres")
def ajouter(
    request: Request,
    session: SessionDB,
    user: Utilisateur,
    nom: Texte = "",
    position: Texte = "1",
    csrf: Texte = "",
):
    exiger_jeton(request, csrf)
    erreur = None
    try:
        pos = int(position)
    except ValueError:
        erreur = "La position doit être un nombre entier"
    else:
        try:
            creer_chambre(session, nom, pos)
        except NomChambrePris:
            erreur = "Ce nom de chambre existe déjà"
        except SaisieRefusee as exc:
            erreur = str(exc)
        else:
            nom, position = "", "1"
    return repondre(
        request,
        page="chambres.html",
        fragment="_chambres.html",
        contexte=_contexte(request, session, user, erreur=erreur, nom=nom, position=position),
    )


@router.post("/chambres/{chambre_id}/etat")
def changer_etat(request: Request, chambre_id: int, session: SessionDB, user: Utilisateur, csrf: Texte = ""):
    exiger_jeton(request, csrf)
    if basculer_etat(session, chambre_id) is None:
        raise HTTPException(404)
    if not request.headers.get("hx-request"):
        return RedirectResponse("/chambres", status_code=303)
    chambre = chambre_vue(session, chambre_id)
    return html(request, "_chambre_ligne.html", socle(request, user, chambre=chambre, actif="/chambres"))
