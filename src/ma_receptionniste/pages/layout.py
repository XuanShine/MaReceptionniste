from nicegui import app, ui

from ma_receptionniste.auth import logout_user

LIENS = (
    ("/", "Planning"),
    ("/chambres", "Chambres"),
    ("/clients", "Clients"),
    ("/reservations", "Réservations"),
)


def fond() -> None:
    ui.query("body").classes("bg-white")


def header(actif: str) -> None:
    fond()

    def deconnexion() -> None:
        logout_user()
        ui.navigate.to("/login")

    with ui.header().classes("items-center justify-between"):
        with ui.row().classes("items-center gap-4"):
            for href, label in LIENS:
                style = "text-white"
                if href == actif:
                    style += " font-bold underline"
                ui.link(label, href).classes(style)
        with ui.row().classes("items-center"):
            ui.label(app.storage.user.get("nom", ""))
            ui.button("Déconnexion", icon="logout", on_click=deconnexion).props("flat color=white")
