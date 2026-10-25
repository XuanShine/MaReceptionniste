from nicegui import ui

from ma_gouvernante.models import libelle_role
from ma_gouvernante.pages.layout import icone, page, utilisateur_connecte
from ma_gouvernante.pages.registre import cartes_pour


@ui.page("/")
async def accueil() -> None:
    utilisateur = await utilisateur_connecte()
    if utilisateur is None:
        ui.navigate.to("/login")
        return
    titre = libelle_role(utilisateur["role"])
    cartes = cartes_pour(utilisateur["role"])
    with page("/", titre, utilisateur["role"], utilisateur["nom"]):
        with ui.row().classes("w-full gap-4 flex-wrap"):
            for carte in cartes:
                with ui.link(target=carte["href"]).classes("no-underline text-inherit w-64"):
                    with ui.card().props("flat bordered").classes("w-full rounded-lg p-4 gap-2"):
                        ui.icon(icone(carte["titre"]), size="1.5rem").classes("text-primary")
                        ui.label(carte["titre"]).classes("text-base font-semibold text-slate-900")
