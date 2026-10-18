from nicegui import run, ui
from sqlalchemy.exc import IntegrityError

from ma_receptionniste.consultations import lister_chambres
from ma_receptionniste.pages.layout import header
from ma_receptionniste.saisie import basculer_etat, creer_chambre


@ui.page("/chambres")
async def chambres() -> None:
    header("/chambres")

    @ui.refreshable
    async def liste() -> None:
        rows = await run.io_bound(lister_chambres)
        if not rows:
            ui.label("Aucune chambre")
            return
        for row in rows:
            with ui.row().classes("w-full items-center justify-between border-b py-2"):
                ui.label(f"{row['position']} — {row['nom']}").classes("text-lg")
                ui.badge(row["etat_label"], color="positive" if row["etat"] == "pret" else "warning")

                async def changer(chambre_id: int = row["id"]) -> None:
                    await run.io_bound(basculer_etat, chambre_id)
                    await liste.refresh()

                ui.button("Changer l'état", on_click=changer).props("outline")

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

    with ui.column().classes("w-full max-w-3xl mx-auto p-4 gap-4"):
        ui.label("Chambres").classes("text-2xl font-bold")
        with ui.row().classes("items-end"):
            nom = ui.input("Nom")
            position = ui.number("Position", value=1, min=0, precision=0)
            ui.button("Ajouter", on_click=ajouter)
        await liste()
