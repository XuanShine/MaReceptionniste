from nicegui import app, run, ui

from ma_receptionniste.auth import (
    MIN_PASSWORD_LENGTH,
    EmailDejaUtilise,
    authenticate,
    register_user,
    safe_redirect,
)
from ma_receptionniste.db import get_session
from ma_receptionniste.pages.layout import fond


def _connecter(email: str, password: str) -> dict | None:
    with get_session() as session:
        user = authenticate(session, email, password)
        if user is None:
            return None
        return {"id": user.id, "nom": user.nom}


def _inscrire(email: str, nom: str, password: str) -> dict:
    with get_session() as session:
        user = register_user(session, email, nom, password)
        return {"id": user.id, "nom": user.nom}


def _ouvrir(identite: dict, cible: str) -> None:
    app.storage.user.update(user_id=identite["id"], nom=identite["nom"])
    ui.navigate.to(cible)


@ui.page("/login")
async def login(redirect_to: str = "/") -> None:
    fond()
    redirect_to = safe_redirect(redirect_to)
    if "user_id" in app.storage.user:
        ui.navigate.to(redirect_to)
        return

    async def connexion() -> None:
        identite = await run.io_bound(_connecter, email.value, password.value)
        if identite is None:
            ui.notify("Email ou mot de passe incorrect", type="negative")
            return
        _ouvrir(identite, redirect_to)

    with ui.card().classes("absolute-center w-80"):
        ui.label("Connexion").classes("text-xl font-bold")
        email = ui.input("Email").props("type=email autofocus").classes("w-full").on("keydown.enter", connexion)
        password = (
            ui.input("Mot de passe", password=True, password_toggle_button=True)
            .classes("w-full")
            .on("keydown.enter", connexion)
        )
        ui.button("Se connecter", on_click=connexion).classes("w-full")
        ui.link("Créer un compte", "/register")


@ui.page("/register")
async def register() -> None:
    fond()
    if "user_id" in app.storage.user:
        ui.navigate.to("/")
        return

    async def inscription() -> None:
        if not (nom.value.strip() and email.value.strip() and password.value):
            ui.notify("Tous les champs sont obligatoires", type="warning")
            return
        if "@" not in email.value:
            ui.notify("Email invalide", type="warning")
            return
        if len(password.value) < MIN_PASSWORD_LENGTH:
            ui.notify(f"Le mot de passe doit faire au moins {MIN_PASSWORD_LENGTH} caractères", type="warning")
            return
        if password.value != confirmation.value:
            ui.notify("Les mots de passe ne correspondent pas", type="warning")
            return
        try:
            identite = await run.io_bound(_inscrire, email.value, nom.value, password.value)
        except EmailDejaUtilise:
            ui.notify("Un compte existe déjà avec cet email", type="negative")
            return
        _ouvrir(identite, "/")

    with ui.card().classes("absolute-center w-80"):
        ui.label("Créer un compte").classes("text-xl font-bold")
        nom = ui.input("Nom").props("autofocus").classes("w-full")
        email = ui.input("Email").props("type=email").classes("w-full")
        password = ui.input("Mot de passe", password=True, password_toggle_button=True).classes("w-full")
        confirmation = (
            ui.input("Confirmer le mot de passe", password=True).classes("w-full").on("keydown.enter", inscription)
        )
        ui.button("S'inscrire", on_click=inscription).classes("w-full")
        ui.link("Déjà un compte ? Se connecter", "/login")
