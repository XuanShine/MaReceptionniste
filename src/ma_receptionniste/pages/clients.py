from nicegui import run, ui

from ma_receptionniste.consultations import lister_clients
from ma_receptionniste.pages.layout import etat_vide, page
from ma_receptionniste.saisie import creer_client

COLONNES = [
    {"name": "nom", "label": "Nom", "field": "nom", "align": "left", "sortable": True},
    {"name": "prenom", "label": "Prénom", "field": "prenom", "align": "left", "sortable": True},
    {"name": "pays", "label": "Pays", "field": "pays", "align": "left", "sortable": True},
    {"name": "telephone", "label": "Téléphone", "field": "telephone", "align": "left"},
    {"name": "email", "label": "Email", "field": "email", "align": "left"},
    {"name": "adresse", "label": "Adresse", "field": "adresse", "align": "left"},
    {"name": "notes", "label": "Notes", "field": "notes", "align": "left"},
]


@ui.page("/clients")
async def clients() -> None:
    lignes = await run.io_bound(lister_clients)

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
        for champ in (nom, prenom, pays, email, telephone, adresse, notes):
            champ.value = ""
        a_jour = await run.io_bound(lister_clients)
        tableau.update_rows(a_jour)
        _afficher(a_jour)
        ui.notify("Client ajouté", type="positive")

    def _afficher(lignes: list[dict]) -> None:
        compteur.set_text(f"{len(lignes)} client{'s' if len(lignes) > 1 else ''}")
        tableau.set_visibility(bool(lignes))
        vide.set_visibility(not lignes)

    with page("/clients", "Clients"):
        with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3 gap-3"):
            ui.label("Nouveau client").classes("text-sm font-semibold")
            with ui.grid(columns=4).classes("w-full gap-3"):
                nom = ui.input("Nom *")
                prenom = ui.input("Prénom")
                pays = ui.input("Pays de nationalité", autocomplete=["France", "Italie", "Allemagne", "Royaume-Uni"])
                telephone = ui.input("Téléphone")
                email = ui.input("Email")
                adresse = ui.input("Adresse").classes("col-span-2")
                notes = ui.input("Notes")
            with ui.row().classes("w-full justify-end"):
                ui.button("Ajouter le client", icon="person_add", on_click=ajouter)
        with ui.card().props("flat bordered").classes("w-full rounded-lg p-0 gap-0"):
            with ui.row().classes("w-full items-center justify-between px-4 py-3 border-b border-slate-200"):
                compteur = ui.label().classes("text-sm text-ardoise")
                recherche = ui.input(placeholder="Rechercher un client…").props("clearable").classes("w-96")
                with recherche.add_slot("prepend"):
                    ui.icon("search", size="1.1rem")
            tableau = (
                ui.table(columns=COLONNES, rows=lignes, row_key="id", pagination=50)
                .props("dense flat no-results-label='Aucun client ne correspond'")
                .classes("w-full")
            )
            recherche.bind_value_to(tableau, "filter")
            with ui.element("div").classes("w-full") as vide:
                etat_vide("people", "Aucun client pour l'instant. Commencez par le formulaire ci-dessus.")
        _afficher(lignes)
