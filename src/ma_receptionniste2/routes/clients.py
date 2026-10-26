from typing import Annotated

from fastapi import APIRouter, Form, Request

from ma_receptionniste2.commandes import SaisieRefusee, creer_client
from ma_receptionniste2.lectures import lister_clients
from ma_receptionniste2.web import SessionDB, Utilisateur, exiger_jeton, html, repondre, socle

router = APIRouter()
Texte = Annotated[str, Form()]


def _contexte(request, session, user, **formulaire):
    valeurs = {"nom": "", "prenom": "", "email": "", "telephone": "", "adresse": "", "notes": "", "erreur": None}
    valeurs.update(formulaire)
    return socle(request, user, clients=lister_clients(session), actif="/clients", **valeurs)


@router.get("/clients")
def page(request: Request, session: SessionDB, user: Utilisateur):
    return html(request, "clients.html", _contexte(request, session, user))


@router.post("/clients")
def ajouter(
    request: Request,
    session: SessionDB,
    user: Utilisateur,
    nom: Texte = "",
    prenom: Texte = "",
    email: Texte = "",
    telephone: Texte = "",
    adresse: Texte = "",
    notes: Texte = "",
    csrf: Texte = "",
):
    exiger_jeton(request, csrf)
    erreur = None
    try:
        creer_client(session, nom, prenom, email, telephone, adresse, notes)
    except SaisieRefusee as exc:
        erreur = str(exc)
    else:
        nom = prenom = email = telephone = adresse = notes = ""
    return repondre(
        request,
        page="clients.html",
        fragment="_clients.html",
        contexte=_contexte(
            request,
            session,
            user,
            erreur=erreur,
            nom=nom,
            prenom=prenom,
            email=email,
            telephone=telephone,
            adresse=adresse,
            notes=notes,
        ),
    )
