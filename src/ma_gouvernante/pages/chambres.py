from nicegui import run, ui

from ma_gouvernante.chambres import NomDejaPris, NomVide, changer_etat, creer_chambre, tableau
from ma_gouvernante.droits import Refus, peut
from ma_gouvernante.models import EtatChambre, Role, libelle_etat, libelle_menage
from ma_gouvernante.pages.layout import badge, etat_vide, page, utilisateur_connecte
from ma_gouvernante.pages.registre import ajouter_carte, lien_chambre

ajouter_carte((Role.admin,), "Chambres", "/chambres")


@ui.page("/chambres")
async def chambres() -> None:
    utilisateur = await utilisateur_connecte()
    if utilisateur is None:
        ui.navigate.to("/login")
        return
    peut_gerer = peut(utilisateur["role"], "gerer_chambres")

    @ui.refreshable
    async def liste() -> None:
        lignes = await run.io_bound(tableau)
        if peut_gerer:
            position.value = max((chambre["position"] for chambre in lignes), default=0) + 1
        if not lignes:
            etat_vide("bed", "Aucune chambre.")
            return
        colonnes = "5rem 8rem 9rem 10rem 8rem"
        entetes = ["Position", "Chambre", "État", "Ménage", "Signalements"]
        if peut_gerer:
            colonnes += " 11rem"
            entetes.append("")
        with ui.element("div").classes("grid w-full text-sm").style(f"grid-template-columns: {colonnes};"):
            for entete in entetes:
                ui.label(entete).classes("px-4 py-2 text-xs font-semibold text-ardoise border-b border-slate-200")
            for chambre in lignes:
                _ligne(chambre)

    def _ligne(chambre: dict) -> None:
        cellule = "px-4 h-11 flex items-center border-b border-slate-100"
        ui.label(str(chambre["position"])).classes(f"{cellule} tabular-nums text-ardoise")
        href = lien_chambre(chambre["id"])
        if href:
            ui.link(chambre["nom"], href).classes(f"{cellule} font-semibold tabular-nums text-primary no-underline")
        else:
            ui.label(chambre["nom"]).classes(f"{cellule} font-semibold tabular-nums")
        with ui.element("div").classes(cellule):
            en_service = chambre["etat"] == EtatChambre.en_service.value
            badge(libelle_etat(chambre["etat"]), "positive" if en_service else "warning")
        with ui.element("div").classes(cellule):
            if chambre["menage"] is None:
                couleur = "ardoise"
            elif chambre["menage"] == "faite":
                couleur = "positive"
            else:
                couleur = "accent"
            badge(libelle_menage(chambre["menage"]), couleur)
        with ui.element("div").classes(cellule):
            nombre = chambre["signalements_ouverts"]
            badge(str(nombre), "negative" if nombre else "ardoise")
        if not peut_gerer:
            return

        async def basculer(chambre_id: int = chambre["id"], etat: str = chambre["etat"]) -> None:
            cible = EtatChambre.hors_service if etat == EtatChambre.en_service.value else EtatChambre.en_service
            try:
                await run.io_bound(changer_etat, utilisateur["id"], chambre_id, cible)
            except Refus:
                ui.notify("Action non autorisée", type="negative")
                return
            await liste.refresh()

        with ui.element("div").classes(f"{cellule} justify-end"):
            if chambre["etat"] == EtatChambre.en_service.value:
                libelle = "Mettre hors service"
            else:
                libelle = "Remettre en service"
            ui.button(libelle, on_click=basculer).props("flat dense color=primary")

    async def ajouter() -> None:
        if not (nom.value or "").strip():
            ui.notify("Le nom est obligatoire", type="warning")
            return
        try:
            await run.io_bound(creer_chambre, utilisateur["id"], nom.value, int(position.value or 0))
        except NomVide:
            ui.notify("Le nom est obligatoire", type="warning")
            return
        except NomDejaPris:
            ui.notify("Ce nom de chambre existe déjà", type="negative")
            return
        except Refus:
            ui.notify("Action non autorisée", type="negative")
            return
        nom.value = ""
        await liste.refresh()
        ui.notify("Chambre ajoutée", type="positive")

    with page("/chambres", "Chambres", utilisateur["role"], utilisateur["nom"]):
        if peut_gerer:
            with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3 gap-3"):
                ui.label("Nouvelle chambre").classes("text-sm font-semibold")
                with ui.row().classes("w-full items-end gap-3"):
                    nom = ui.input("Nom ou numéro").classes("w-48").on("keydown.enter", ajouter)
                    position = ui.number("Position", value=1, min=0, precision=0).classes("w-32")
                    ui.button("Ajouter", icon="add", on_click=ajouter)
        with ui.card().props("flat bordered").classes("w-full rounded-lg p-0 gap-0"):
            await liste()
