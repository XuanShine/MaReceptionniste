from nicegui import app, ui
from sqlmodel import select

from ma_receptionniste.auth import (
    MIN_PASSWORD_LENGTH,
    EmailDejaUtilise,
    authenticate,
    login_user,
    logout_user,
    register_user,
    safe_redirect,
)
from ma_receptionniste.db import get_session
from ma_receptionniste.models import Client


def header() -> None:
    def deconnexion() -> None:
        logout_user()
        ui.navigate.to("/login")

    with ui.header().classes("items-center justify-between"):
        ui.label("Ma Réceptionniste").classes("text-xl font-bold")
        with ui.row().classes("items-center"):
            ui.label(app.storage.user.get("nom", ""))
            ui.button("Déconnexion", icon="logout", on_click=deconnexion).props("flat color=white")


@ui.page("/login")
def login(redirect_to: str = "/") -> None:
    redirect_to = safe_redirect(redirect_to)
    if "user_id" in app.storage.user:
        ui.navigate.to(redirect_to)
        return

    def connexion() -> None:
        with get_session() as session:
            user = authenticate(session, email.value, password.value)
        if user is None:
            ui.notify("Email ou mot de passe incorrect", type="negative")
            return
        login_user(user)
        ui.navigate.to(redirect_to)

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
def register() -> None:
    if "user_id" in app.storage.user:
        ui.navigate.to("/")
        return

    def inscription() -> None:
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
            with get_session() as session:
                user = register_user(session, email.value, nom.value, password.value)
        except EmailDejaUtilise:
            ui.notify("Un compte existe déjà avec cet email", type="negative")
            return
        login_user(user)
        ui.navigate.to("/")

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


@ui.page("/")
def index() -> None:
    header()

    @ui.refreshable
    def liste_clients() -> None:
        with get_session() as session:
            clients = session.exec(select(Client).order_by(Client.cree_le.desc())).all()
        ui.table(
            columns=[
                {"name": "nom", "label": "Nom", "field": "nom", "align": "left"},
                {"name": "email", "label": "Email", "field": "email", "align": "left"},
                {"name": "telephone", "label": "Téléphone", "field": "telephone", "align": "left"},
            ],
            rows=[c.model_dump(mode="json") for c in clients],
            row_key="id",
        ).classes("w-full")

    def ajouter() -> None:
        if not nom.value:
            ui.notify("Le nom est obligatoire", type="warning")
            return
        with get_session() as session:
            session.add(Client(nom=nom.value, email=email.value or None, telephone=telephone.value or None))
            session.commit()
        nom.value = email.value = telephone.value = ""
        liste_clients.refresh()
        ui.notify("Client ajouté", type="positive")

    with ui.row().classes("items-end"):
        nom = ui.input("Nom")
        email = ui.input("Email")
        telephone = ui.input("Téléphone")
        ui.button("Ajouter", on_click=ajouter)

    liste_clients()
