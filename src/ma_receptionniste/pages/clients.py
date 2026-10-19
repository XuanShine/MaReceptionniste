from nicegui import run, ui

from ma_receptionniste.consultations import lister_clients
from ma_receptionniste.pages.layout import cadre, titre
from ma_receptionniste.saisie import creer_client


@ui.page("/clients")
async def clients() -> None:
    @ui.refreshable
    async def liste() -> None:
        rows = await run.io_bound(lister_clients)
        ui.table(
            columns=[
                {"name": "nom", "label": "Nom", "field": "nom", "align": "left"},
                {"name": "prenom", "label": "Prénom", "field": "prenom", "align": "left"},
                {"name": "pays", "label": "Pays", "field": "pays", "align": "left"},
                {"name": "email", "label": "Email", "field": "email", "align": "left"},
                {"name": "telephone", "label": "Téléphone", "field": "telephone", "align": "left"},
                {"name": "adresse", "label": "Adresse", "field": "adresse", "align": "left"},
                {"name": "notes", "label": "Notes", "field": "notes", "align": "left"},
            ],
            rows=rows,
            row_key="id",
            pagination={"rowsPerPage": 0},
        ).props("dense flat hide-bottom").classes("w-full fiche-table feuille")

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
            pays.value,
        )
        nom.value = prenom.value = email.value = telephone.value = adresse.value = notes.value = pays.value = ""
        await liste.refresh()
        ui.notify("Client ajouté", type="positive")

    with cadre("/clients"):
        titre("Clients", "Comptes de facturation et occupants")
        with ui.column().classes("feuille w-full p-3 gap-2"):
            with ui.row().classes("items-end gap-2"):
                nom = ui.input("Nom").props("dense outlined").classes("w-40")
                prenom = ui.input("Prénom").props("dense outlined").classes("w-40")
                pays = ui.input("Pays").props("dense outlined").classes("w-36")
                email = ui.input("Email").props("dense outlined").classes("w-48")
                telephone = ui.input("Téléphone").props("dense outlined").classes("w-36")
            with ui.row().classes("items-end gap-2"):
                adresse = ui.input("Adresse").props("dense outlined").classes("w-64")
                notes = ui.input("Notes").props("dense outlined").classes("w-64")
                ui.button("Ajouter", on_click=ajouter).props("unelevated no-caps")
        await liste()
