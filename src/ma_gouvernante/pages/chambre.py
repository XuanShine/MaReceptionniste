from pathlib import Path

from nicegui import run, ui

from ma_gouvernante.chambres import detail
from ma_gouvernante.droits import Refus, peut
from ma_gouvernante.models import TOUS_LES_ROLES, libelle_etat, libelle_menage
from ma_gouvernante.pages.layout import badge, etat_vide, page, utilisateur_connecte
from ma_gouvernante.pages.registre import ajouter_carte, lien_chambre, lier_chambre
from ma_gouvernante.pages.theme import date_heure
from ma_gouvernante.signalements import (
    TAILLE_MAX_OCTETS,
    NoteVide,
    PhotoRefusee,
    lister_ouverts,
    ouvrir,
    resoudre,
)

ajouter_carte(TOUS_LES_ROLES, "Signalements ouverts", "/signalements")
lier_chambre(lambda chambre_id: f"/chambres/{chambre_id}")


def _url_photo(photo_path: str | None) -> str | None:
    if not photo_path:
        return None
    return f"/gouvernante-media/{Path(photo_path).name}"


@ui.page("/signalements")
async def file_ouverte() -> None:
    utilisateur = await utilisateur_connecte()
    if utilisateur is None:
        ui.navigate.to("/login")
        return
    rapports = await run.io_bound(lister_ouverts)
    with page("/signalements", "Signalements ouverts", utilisateur["role"], utilisateur["nom"]):
        with ui.card().props("flat bordered").classes("w-full rounded-lg p-0 gap-0"):
            if not rapports:
                etat_vide("report_problem", "Aucun signalement ouvert.")
                return
            for rapport in rapports:
                _carte_rapport(rapport, resoudre_ici=False, utilisateur=utilisateur)


@ui.page("/chambres/{chambre_id}")
async def chambre(chambre_id: int) -> None:
    utilisateur = await utilisateur_connecte()
    if utilisateur is None:
        ui.navigate.to("/login")
        return
    fiche = await run.io_bound(detail, chambre_id)
    if fiche is None:
        with page(f"/chambres/{chambre_id}", "Chambre", utilisateur["role"], utilisateur["nom"]):
            etat_vide("bed", "Cette chambre n'existe pas.")
        return

    photo: dict[str, bytes | str | None] = {"contenu": None, "nom": None}
    peut_signaler = peut(utilisateur["role"], "signaler")
    peut_resoudre = peut(utilisateur["role"], "resoudre")

    @ui.refreshable
    async def rapports() -> None:
        lignes = await run.io_bound(lister_ouverts, chambre_id)
        if not lignes:
            etat_vide("report_problem", "Aucun signalement ouvert.")
            return
        for rapport in lignes:
            _carte_rapport(rapport, resoudre_ici=peut_resoudre, utilisateur=utilisateur, apres=rapports.refresh)

    async def recevoir(evenement) -> None:
        photo["contenu"] = await evenement.file.read()
        photo["nom"] = evenement.file.name

    async def envoyer() -> None:
        try:
            await run.io_bound(ouvrir, utilisateur["id"], chambre_id, note.value or "", photo["contenu"], photo["nom"])
        except NoteVide:
            ui.notify("La note est obligatoire", type="warning")
            return
        except PhotoRefusee:
            ui.notify("Photo refusée. Formats acceptés : jpeg, png, webp, 8 Mo maximum.", type="negative")
            return
        except Refus:
            ui.notify("Action non autorisée", type="negative")
            return
        note.value = ""
        photo["contenu"] = None
        photo["nom"] = None
        ui.notify("Signalement ouvert", type="positive")
        await rapports.refresh()

    with page(f"/chambres/{chambre_id}", fiche["nom"], utilisateur["role"], utilisateur["nom"]):
        with ui.row().classes("items-center gap-2"):
            en_service = fiche["etat"] == "en_service"
            badge(libelle_etat(fiche["etat"]), "positive" if en_service else "warning")
            badge(libelle_menage(fiche["menage"]), "positive" if fiche["menage"] == "faite" else "ardoise")
        if peut_signaler:
            with ui.card().props("flat bordered").classes("w-full rounded-lg p-4 gap-3"):
                ui.label("Signaler un problème").classes("text-sm font-semibold")
                note = ui.textarea("Note").classes("w-full")
                ui.upload(
                    label="Photo facultative",
                    auto_upload=True,
                    max_file_size=TAILLE_MAX_OCTETS,
                    on_upload=recevoir,
                    on_rejected=lambda _: ui.notify("Fichier refusé", type="negative"),
                )
                ui.button("Signaler", icon="report_problem", on_click=envoyer)
        with ui.card().props("flat bordered").classes("w-full rounded-lg p-0 gap-0"):
            ui.label("Signalements ouverts").classes("text-sm font-semibold px-4 pt-3")
            await rapports()


def _carte_rapport(rapport: dict, *, resoudre_ici: bool, utilisateur: dict, apres=None) -> None:
    with ui.column().classes("w-full gap-2 px-4 py-3 border-b border-slate-100"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            href = lien_chambre(rapport["chambre_id"])
            if href:
                ui.link(rapport["chambre_nom"], href).classes("font-semibold text-primary no-underline")
            else:
                ui.label(rapport["chambre_nom"]).classes("font-semibold")
            badge("Ouvert", "warning")
        ui.label(rapport["note"]).classes("text-sm")
        ui.label(f"{rapport['auteur_nom']} · {date_heure(rapport['cree_le'])}").classes("text-xs text-ardoise")
        url = _url_photo(rapport["photo_path"])
        if url:
            ui.image(url).classes("w-48 rounded-md")
        if resoudre_ici:

            async def marquer(signalement_id: int = rapport["id"]) -> None:
                try:
                    await run.io_bound(resoudre, utilisateur["id"], signalement_id)
                except Refus:
                    ui.notify("Action non autorisée", type="negative")
                    return
                ui.notify("Signalement résolu", type="positive")
                if apres is not None:
                    await apres()

            ui.button("Résoudre", on_click=marquer).props("flat dense color=primary")
