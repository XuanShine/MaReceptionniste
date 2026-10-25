from nicegui import run, ui

from ma_gouvernante.journal import lister
from ma_gouvernante.models import TOUS_LES_ROLES
from ma_gouvernante.pages.layout import etat_vide, page, utilisateur_connecte
from ma_gouvernante.pages.registre import ajouter_carte
from ma_gouvernante.pages.theme import date_heure

ajouter_carte(TOUS_LES_ROLES, "Historique", "/historique")


@ui.page("/historique")
async def historique() -> None:
    utilisateur = await utilisateur_connecte()
    if utilisateur is None:
        ui.navigate.to("/login")
        return
    lignes = await run.io_bound(lister)
    with page("/historique", "Historique", utilisateur["role"], utilisateur["nom"]):
        with ui.card().props("flat bordered").classes("w-full rounded-lg p-0 gap-0"):
            if not lignes:
                etat_vide("history", "Aucune ligne.")
                return
            for ligne in lignes:
                with ui.row().classes("w-full items-baseline justify-between px-4 py-3 border-b border-slate-100"):
                    ui.label(ligne["description"]).classes("text-sm")
                    ui.label(date_heure(ligne["date"])).classes("text-xs text-ardoise shrink-0")
