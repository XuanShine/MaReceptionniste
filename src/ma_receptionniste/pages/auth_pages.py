from collections.abc import Iterator
from contextlib import contextmanager

from nicegui import app, run, ui

from ma_receptionniste.auth import (
    MIN_PASSWORD_LENGTH,
    EmailDejaUtilise,
    authenticate,
    register_user,
    safe_redirect,
)
from ma_receptionniste.db import get_session


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


@contextmanager
def _carte(titre: str, page: str) -> Iterator[None]:
    ui.page_title(f"{page} · Ma Réceptionniste")
    ui.query("body").classes("bg-fond")
    with ui.column().classes("absolute-center items-center gap-6 w-[24rem]"):
        with ui.column().classes("items-center gap-0"):
            ui.label("Hôtel Panorama").classes("text-2xl font-semibold text-primary")
            ui.label("Ma Réceptionniste").classes("text-sm text-ardoise tracking-wide")
        with ui.card().props("flat bordered").classes("w-full p-6 gap-4 rounded-xl"):
            ui.label(titre).classes("text-base font-semibold")
            yield


@ui.page("/login")
async def login(redirect_to: str = "/") -> None:
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

    with _carte("Connexion", "Connexion"):
        email = ui.input("Email").props("type=email autofocus").classes("w-full").on("keydown.enter", connexion)
        password = (
            ui.input("Mot de passe", password=True, password_toggle_button=True)
            .classes("w-full")
            .on("keydown.enter", connexion)
        )
        ui.button("Se connecter", on_click=connexion).classes("w-full")
        ui.link("Créer un compte", "/register").classes("text-sm text-primary no-underline hover:underline self-center")


@ui.page("/register")
async def register() -> None:
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

    with _carte("Créer un compte", "Inscription"):
        nom = ui.input("Nom").props("autofocus").classes("w-full")
        email = ui.input("Email").props("type=email").classes("w-full")
        password = ui.input("Mot de passe", password=True, password_toggle_button=True).classes("w-full")
        confirmation = (
            ui.input("Confirmer le mot de passe", password=True).classes("w-full").on("keydown.enter", inscription)
        )
        ui.button("S'inscrire", on_click=inscription).classes("w-full")
        ui.link("Déjà un compte ? Se connecter", "/login").classes(
            "text-sm text-primary no-underline hover:underline self-center"
        )
