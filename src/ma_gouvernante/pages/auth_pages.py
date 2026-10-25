from collections.abc import Iterator
from contextlib import contextmanager

from nicegui import app, run, ui

from ma_gouvernante.auth import authenticate, safe_redirect


def _connecter(email: str, password: str) -> dict | None:
    return authenticate(email, password)


def _ouvrir(identite: dict, cible: str) -> None:
    app.storage.user.update(user_id=identite["id"], nom=identite["nom"])
    ui.navigate.to(cible)


@contextmanager
def _carte(titre: str, page: str) -> Iterator[None]:
    ui.page_title(f"{page} · Ma Gouvernante")
    ui.query("body").classes("bg-fond")
    with ui.column().classes("absolute-center items-center gap-6 w-[24rem]"):
        with ui.column().classes("items-center gap-0"):
            ui.label("Hôtel Panorama").classes("text-2xl font-semibold text-primary")
            ui.label("Ma Gouvernante").classes("text-sm text-ardoise tracking-wide")
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
