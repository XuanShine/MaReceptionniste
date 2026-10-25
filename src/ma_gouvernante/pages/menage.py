from nicegui import run, ui

from ma_gouvernante.droits import Refus, peut
from ma_gouvernante.menage import RetraitRefuse, changer_statut, lire_liste, remplir_liste, retirer_ligne
from ma_gouvernante.models import Role, StatutMenage, libelle_menage
from ma_gouvernante.pages.layout import badge, etat_vide, page, utilisateur_connecte
from ma_gouvernante.pages.registre import ajouter_carte, lien_chambre

ajouter_carte((Role.admin, Role.receptionniste, Role.femme_de_chambre), "Liste du jour", "/menage")

OPTIONS_STATUT = {
    StatutMenage.a_faire.value: "À faire",
    StatutMenage.en_cours.value: "En cours",
    StatutMenage.faite.value: "Faite",
}
COULEUR_STATUT = {
    StatutMenage.a_faire.value: "ardoise",
    StatutMenage.en_cours.value: "accent",
    StatutMenage.faite.value: "positive",
}


@ui.page("/menage")
async def menage() -> None:
    utilisateur = await utilisateur_connecte()
    if utilisateur is None:
        ui.navigate.to("/login")
        return
    peut_remplir = peut(utilisateur["role"], "creer_liste")
    peut_changer = peut(utilisateur["role"], "changer_menage")

    @ui.refreshable
    async def liste() -> None:
        du_jour = await run.io_bound(lire_liste)
        if du_jour is None:
            etat_vide("cleaning_services", "La liste du jour n'existe pas encore.")
            return
        if not du_jour["lignes"]:
            etat_vide("cleaning_services", "Aucune chambre sur la liste.")
            return
        for ligne in du_jour["lignes"]:
            _ligne(ligne)

    def _ligne(ligne: dict) -> None:
        with ui.row().classes("w-full items-center gap-3 px-4 py-3 border-b border-slate-100 no-wrap"):
            href = lien_chambre(ligne["chambre_id"])
            if href:
                ui.link(ligne["nom"], href).classes("font-semibold tabular-nums text-primary no-underline w-24")
            else:
                ui.label(ligne["nom"]).classes("font-semibold tabular-nums w-24")
            if peut_changer:
                choix = ui.select(OPTIONS_STATUT, value=ligne["statut"]).classes("w-40")
                choix.on_value_change(_appliquer(ligne["id"], ligne["statut"]))
            else:
                badge(libelle_menage(ligne["statut"]), COULEUR_STATUT.get(ligne["statut"], "ardoise"))
            if peut_remplir and ligne["statut"] == StatutMenage.a_faire.value:

                async def retirer_cette(ligne_id: int = ligne["id"]) -> None:
                    await retirer(ligne_id)

                ui.button("Retirer", on_click=retirer_cette).props("flat dense color=ardoise")

    def _appliquer(ligne_id: int, actuel: str):
        async def appliquer(evenement) -> None:
            if evenement.value == actuel:
                return
            try:
                await run.io_bound(changer_statut, utilisateur["id"], ligne_id, evenement.value)
            except Refus:
                ui.notify("Action non autorisée", type="negative")
            await liste.refresh()

        return appliquer

    async def retirer(ligne_id: int) -> None:
        try:
            await run.io_bound(retirer_ligne, utilisateur["id"], ligne_id)
        except RetraitRefuse:
            ui.notify("Seule une ligne à faire peut être retirée", type="warning")
            return
        except Refus:
            ui.notify("Action non autorisée", type="negative")
            return
        await liste.refresh()

    async def remplir() -> None:
        try:
            await run.io_bound(remplir_liste, utilisateur["id"])
        except Refus:
            ui.notify("Action non autorisée", type="negative")
            return
        await liste.refresh()

    with page("/menage", "Liste du jour", utilisateur["role"], utilisateur["nom"]):
        if peut_remplir:
            with ui.row().classes("w-full"):
                ui.button("Remplir avec les chambres en service", icon="cleaning_services", on_click=remplir)
        with ui.card().props("flat bordered").classes("w-full rounded-lg p-0 gap-0"):
            await liste()
