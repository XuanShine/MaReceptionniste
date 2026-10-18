from nicegui import run, ui

from ma_receptionniste.consultations import lister_clients
from ma_receptionniste.pages.layout import header
from ma_receptionniste.saisie import creer_client


@ui.page("/clients")
async def clients() -> None:
    header("/clients")

    @ui.refreshable
    async def liste() -> None:
        rows = await run.io_bound(lister_clients)
        ui.table(
            columns=[
                {"name": "nom", "label": "Nom", "field": "nom", "align": "left"},
                {"name": "prenom", "label": "Prénom", "field": "prenom", "align": "left"},
                {"name": "email", "label": "Email", "field": "email", "align": "left"},
                {"name": "telephone", "label": "Téléphone", "field": "telephone", "align": "left"},
                {"name": "adresse", "label": "Adresse", "field": "adresse", "align": "left"},
                {"name": "notes", "label": "Notes", "field": "notes", "align": "left"},
            ],
            rows=rows,
            row_key="id",
        ).classes("w-full")

    async def ajouter() -> None:
        if not (nom.value or "").strip():
            ui.notify("Le nom est obligatoire", type="warning")
            return
        await run.io_bound(
            creer_client,
            nom.value,
            prenom.value,
            email.value,
            telephone.value,
            adresse.value,
            notes.value,
        )
        nom.value = prenom.value = email.value = telephone.value = adresse.value = notes.value = ""
        await liste.refresh()
        ui.notify("Client ajouté", type="positive")

    with ui.column().classes("w-full max-w-5xl mx-auto p-4 gap-4"):
        ui.label("Clients").classes("text-2xl font-bold")
        with ui.row().classes("items-end"):
            nom = ui.input("Nom")
            prenom = ui.input("Prénom")
            email = ui.input("Email")
            telephone = ui.input("Téléphone")
        with ui.row().classes("items-end w-full"):
            adresse = ui.input("Adresse").classes("w-64")
            notes = ui.textarea("Notes").classes("w-64")
            ui.button("Ajouter", on_click=ajouter)
        await liste()
