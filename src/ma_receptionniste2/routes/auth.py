from typing import Annotated

from fastapi import APIRouter, Form, Request

from ma_receptionniste2.auth import (
    EmailDejaUtilise,
    IdentifiantsRefuses,
    authentifier,
    inscrire,
    message_inscription,
    safe_redirect,
)
from ma_receptionniste2.web import SessionDB, exiger_jeton, html, repondre, socle

router = APIRouter()

Texte = Annotated[str, Form()]


def _auth(request: Request, **extra) -> dict:
    return socle(request, actif="", **extra)


@router.get("/login")
def formulaire_login(request: Request, redirect_to: str = "/"):
    if request.session.get("user_id"):
        return repondre(
            request,
            page="login.html",
            fragment="_login.html",
            contexte={},
            redirection=safe_redirect(redirect_to),
        )
    return html(
        request,
        "login.html",
        _auth(request, erreur=None, email="", redirect_to=safe_redirect(redirect_to)),
    )


@router.post("/login")
def connecter(
    request: Request,
    session: SessionDB,
    email: Texte = "",
    password: Texte = "",
    redirect_to: Texte = "/",
    csrf: Texte = "",
):
    exiger_jeton(request, csrf)
    cible = safe_redirect(redirect_to)
    try:
        user = authentifier(session, email, password)
    except IdentifiantsRefuses:
        return repondre(
            request,
            page="login.html",
            fragment="_login.html",
            contexte=_auth(request, erreur="Email ou mot de passe incorrect", email=email, redirect_to=cible),
        )
    request.session["user_id"] = user.id
    return repondre(request, page="login.html", fragment="_login.html", contexte={}, redirection=cible)


@router.get("/register")
def formulaire_inscription(request: Request):
    if request.session.get("user_id"):
        return repondre(request, page="register.html", fragment="_register.html", contexte={}, redirection="/")
    return html(request, "register.html", _auth(request, erreur=None, nom="", email=""))


@router.post("/register")
def inscrire_compte(
    request: Request,
    session: SessionDB,
    nom: Texte = "",
    email: Texte = "",
    password: Texte = "",
    confirmation: Texte = "",
    csrf: Texte = "",
):
    exiger_jeton(request, csrf)
    erreur = message_inscription(nom, email, password, confirmation)
    if erreur is None:
        try:
            user = inscrire(session, email, nom, password)
        except EmailDejaUtilise:
            erreur = "Un compte existe déjà avec cet email"
        else:
            request.session["user_id"] = user.id
            return repondre(request, page="register.html", fragment="_register.html", contexte={}, redirection="/")
    return repondre(
        request,
        page="register.html",
        fragment="_register.html",
        contexte=_auth(request, erreur=erreur, nom=nom, email=email),
    )


@router.post("/logout")
def deconnecter(request: Request, csrf: Texte = ""):
    exiger_jeton(request, csrf)
    request.session.clear()
    return repondre(request, page="login.html", fragment="_login.html", contexte={}, redirection="/login")
