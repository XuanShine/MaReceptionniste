from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse

from ma_receptionniste.auth import (
    MIN_PASSWORD_LENGTH,
    EmailDejaUtilise,
    authenticate,
    register_user,
    safe_redirect,
)
from ma_receptionniste.db import get_session
from ma_receptionniste.web.rendu import hx, page, rediriger

router = APIRouter()


def _identite(email: str, password: str) -> dict | None:
    with get_session() as session:
        user = authenticate(session, email, password)
        if user is None:
            return None
        return {"id": user.id, "nom": user.nom}


def _inscrire(email: str, nom: str, password: str) -> dict:
    with get_session() as session:
        user = register_user(session, email, nom, password)
        return {"id": user.id, "nom": user.nom}


def _ouvrir(request: Request, identite: dict) -> None:
    request.session["user_id"] = identite["id"]
    request.session["nom"] = identite["nom"]


@router.get("/login")
async def formulaire_login(request: Request, redirect_to: str = "/"):
    cible = safe_redirect(redirect_to)
    if request.session.get("user_id"):
        return RedirectResponse(cible, status_code=303)
    return page(request, "login.html", {"titre": "Connexion", "titre_carte": "Connexion", "redirect_to": cible})


@router.post("/login")
async def login(request: Request):
    form = await request.form()
    cible = safe_redirect(str(form.get("redirect_to") or "/"))
    email = str(form.get("email") or "")
    password = str(form.get("password") or "")
    identite = await run_in_threadpool(_identite, email, password)
    if identite is None:
        return page(
            request,
            "login.html",
            {
                "titre": "Connexion",
                "titre_carte": "Connexion",
                "redirect_to": cible,
                "erreur": "Email ou mot de passe incorrect",
                "email": email,
            },
        )
    _ouvrir(request, identite)
    return rediriger(request, cible)


@router.get("/register")
async def formulaire_inscription(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return page(request, "register.html", {"titre": "Inscription", "titre_carte": "Créer un compte"})


@router.post("/register")
async def inscription(request: Request):
    form = await request.form()
    nom = str(form.get("nom") or "")
    email = str(form.get("email") or "")
    password = str(form.get("password") or "")
    confirmation = str(form.get("confirmation") or "")
    erreur = _valider_inscription(nom, email, password, confirmation)
    if erreur:
        return page(
            request,
            "register.html",
            {"titre": "Inscription", "titre_carte": "Créer un compte", "erreur": erreur, "nom": nom, "email": email},
        )
    try:
        identite = await run_in_threadpool(_inscrire, email, nom, password)
    except EmailDejaUtilise:
        return page(
            request,
            "register.html",
            {
                "titre": "Inscription",
                "titre_carte": "Créer un compte",
                "erreur": "Un compte existe déjà avec cet email",
                "nom": nom,
                "email": email,
            },
        )
    _ouvrir(request, identite)
    return rediriger(request, "/")


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    if hx(request):
        return rediriger(request, "/login")
    return RedirectResponse("/login", status_code=303)


def _valider_inscription(nom: str, email: str, password: str, confirmation: str) -> str | None:
    if not (nom.strip() and email.strip() and password):
        return "Tous les champs sont obligatoires"
    if "@" not in email:
        return "Email invalide"
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Le mot de passe doit faire au moins {MIN_PASSWORD_LENGTH} caractères"
    if password != confirmation:
        return "Les mots de passe ne correspondent pas"
    return None
