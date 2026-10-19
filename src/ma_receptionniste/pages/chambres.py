from nicegui import run, ui
from sqlalchemy.exc import IntegrityError

from ma_receptionniste.consultations import lister_chambres
from ma_receptionniste.pages.layout import cadre, titre
from ma_receptionniste.saisie import basculer_etat, creer_chambre


@ui.page("/chambres")
async def chambres() -> None:
    @ui.refreshable
    async def liste() -> None:
        rows = await run.io_bound(lister_chambres)
        with ui.column().classes("feuille w-full gap-0 px-3"):
            with ui.row().classes("w-full items-center py-2 text-xs texte-discret"):
                ui.label("Position").classes("w-16")
                ui.label("Chambre").classes("flex-1")
                ui.label("État").classes("w-28")
                ui.label("").classes("w-36")
            if not rows:
                ui.label("Aucune chambre").classes("py-3 texte-discret")
                return
            for row in rows:
                with ui.row().classes("w-full items-center py-2").style("border-top: 1px solid #e6dfd2"):
                    ui.label(str(row["position"])).classes("w-16 texte-discret")
                    ui.label(row["nom"]).classes("flex-1 font-medium")
                    couleur = "#2c6b4a" if row["etat"] == "pret" else "#9a6230"
                    ui.label(row["etat_label"]).classes("w-28 text-sm").style(f"color:{couleur}")

                    async def changer(chambre_id: int = row["id"]) -> None:
                        await run.io_bound(basculer_etat, chambre_id)
                        await liste.refresh()

                    libelle = "Marquer à faire" if row["etat"] == "pret" else "Marquer prête"
                    ui.button(libelle, on_click=changer).props("outline no-caps dense").classes("w-36")

    async def ajouter() -> None:
        if not (nom.value or "").strip():
            ui.notify("Le nom est obligatoire", type="warning")
            return
        try:
            await run.io_bound(creer_chambre, nom.value, int(position.value or 0))
        except IntegrityError:
            ui.notify("Ce nom de chambre existe déjà", type="negative")
            return
        nom.value = ""
        await liste.refresh()
        ui.notify("Chambre ajoutée", type="positive")

    with cadre("/chambres"):
        titre("Chambres", "Nom, ordre sur le planning, état de la chambre")
        with ui.row().classes("items-end gap-2"):
            nom = ui.input("Nom").props("dense outlined").classes("w-48")
            position = ui.number("Position", value=1, min=0, precision=0).props("dense outlined")
            ui.button("Ajouter", on_click=ajouter).props("unelevated no-caps")
        await liste()
