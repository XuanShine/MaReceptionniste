from nicegui import run, ui
from sqlalchemy.exc import IntegrityError

from ma_gouvernante.actions import ajouter_chambre, chambres, etat_chambre
from ma_gouvernante.garde import acteur_courant
from ma_gouvernante.menage import (
    LIBELLE_ETAT,
    Action,
    DroitRefuse,
    EtatChambre,
    EtatInvalide,
    NomChambreVide,
    autorise,
)
from ma_gouvernante.pages.layout import badge, etat_vide, page, refuser

TYPES_COURANTS = ["Single BB", "Double", "Twin", "Triple", "Familiale", "Suite"]


@ui.page("/chambres")
async def page_chambres() -> None:
    acteur = acteur_courant()
    if refuser(acteur):
        return
    assert acteur is not None
    peut_gerer = autorise(acteur, Action.gerer_chambres)
    with page("/chambres", "Chambres", acteur):

        @ui.refreshable
        async def tableau() -> None:
            lignes = await run.io_bound(chambres, acteur)
            if peut_gerer:
                position.value = max((ligne.position for ligne in lignes), default=0) + 1
            if not lignes:
                phrase = (
                    "Aucune chambre. Ajoutez la première avec le formulaire ci-dessus."
                    if peut_gerer
                    else "Aucune chambre."
                )
                etat_vide("bed", phrase)
                return
            for ligne in lignes:
                with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3"):
                    with ui.row().classes("w-full items-center justify-between no-wrap"):
                        with ui.link(target=f"/chambres/{ligne.id}").classes(
                            "flex-1 no-underline text-inherit min-w-0"
                        ):
                            ui.label(ligne.nom).classes("text-lg font-semibold tabular-nums text-primary")
                            detail = ligne.type_chambre or "Type non renseigné"
                            ui.label(f"Position {ligne.position} · {detail}").classes("text-xs text-ardoise")
                        with ui.row().classes("items-center gap-2"):
                            prete = ligne.etat == EtatChambre.pret.value
                            badge(LIBELLE_ETAT[EtatChambre(ligne.etat)], "positive" if prete else "warning")
                            if not peut_gerer:
                                continue

                            async def basculer(chambre_id=ligne.id, etat=ligne.etat) -> None:
                                cible = (
                                    EtatChambre.non_pret.value
                                    if etat == EtatChambre.pret.value
                                    else EtatChambre.pret.value
                                )
                                try:
                                    await run.io_bound(etat_chambre, acteur, chambre_id, cible)
                                except (DroitRefuse, EtatInvalide):
                                    ui.notify("Changement d'état refusé", type="negative")
                                    return
                                await tableau.refresh()

                            ui.button("Marquer non prête" if prete else "Marquer prête", on_click=basculer).props(
                                "flat dense color=primary"
                            )

        async def ajouter() -> None:
            if not (nom.value or "").strip():
                ui.notify("Le nom est obligatoire", type="warning")
                return
            try:
                await run.io_bound(
                    ajouter_chambre,
                    acteur,
                    nom.value,
                    int(position.value or 0),
                    type_nouvelle.value,
                )
            except NomChambreVide:
                ui.notify("Le nom est obligatoire", type="warning")
                return
            except DroitRefuse:
                ui.notify("Seule l'admin crée des chambres", type="negative")
                return
            except IntegrityError:
                ui.notify("Ce nom de chambre existe déjà", type="negative")
                return
            nom.value = ""
            type_nouvelle.value = ""
            ui.notify("Chambre ajoutée", type="positive")
            await tableau.refresh()

        if peut_gerer:
            with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3 gap-3"):
                ui.label("Nouvelle chambre").classes("text-sm font-semibold")
                with ui.row().classes("w-full items-end gap-3"):
                    nom = ui.input("Nom ou numéro").classes("w-48").on("keydown.enter", ajouter)
                    type_nouvelle = ui.input("Type", autocomplete=TYPES_COURANTS).classes("w-56")
                    position = ui.number("Position", value=1, min=0, precision=0).classes("w-32")
                    ui.button("Ajouter", icon="add", on_click=ajouter)
        await tableau()
