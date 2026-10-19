from datetime import date

from nicegui import run, ui

from ma_receptionniste.consultations import STATUT_SEJOUR, lister_reservations, options_clients
from ma_receptionniste.facturation import format_euros
from ma_receptionniste.pages.layout import etat_vide, ouvrir_nouvelle_reservation, page
from ma_receptionniste.pages.theme import date_courte

COLONNES = [
    {"name": "client", "label": "Client", "field": "client", "align": "left", "sortable": True},
    {"name": "canal", "label": "Canal", "field": "canal", "align": "left", "sortable": True},
    {"name": "chambres", "label": "Chambres", "field": "chambres", "align": "left"},
    {"name": "arrivee", "label": "Arrivée", "field": "arrivee", "align": "left"},
    {"name": "depart", "label": "Départ", "field": "depart", "align": "left"},
    {"name": "nuits", "label": "Nuits", "field": "nuits", "align": "right"},
    {"name": "statut", "label": "Statut", "field": "statut", "align": "left", "sortable": True},
    {"name": "total", "label": "Total TTC", "field": "total", "align": "right"},
]
BADGE_STATUT = """
<q-td :props="props">
  <q-badge :color="props.row.couleur + '-soft'" :text-color="props.row.couleur" :label="props.value"
           class="px-2 py-1 font-medium" />
</q-td>
"""


def _ligne_tableau(reservation: dict) -> dict:
    statut = STATUT_SEJOUR[reservation["statut"]]
    return {
        "id": reservation["id"],
        "client": reservation["client"],
        "canal": reservation["partenaire"] or "—",
        "chambres": reservation["chambres"] or "—",
        "arrivee": date_courte(reservation["date_debut"]),
        "depart": date_courte(reservation["date_fin"]),
        "nuits": reservation["nuits"] or "",
        "statut": statut.libelle,
        "couleur": statut.couleur,
        "total": format_euros(reservation["total"]),
    }


@ui.page("/reservations")
async def reservations() -> None:
    clients = await run.io_bound(options_clients)
    lignes = await run.io_bound(lister_reservations)
    # Les réservations sans séjour (juste créées) d'abord, puis de l'arrivée la plus lointaine à la plus ancienne.
    lignes.sort(key=lambda reservation: reservation["date_debut"] or date.max, reverse=True)

    async def creer() -> None:
        if client_id.value is None:
            ui.notify("Choisissez un client", type="warning")
            return
        await ouvrir_nouvelle_reservation(client_id.value)

    with page("/reservations", "Réservations"):
        with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3"):
            if not clients:
                etat_vide(
                    "person_add", "Ajoutez un client avant de créer une réservation.", "Ajouter un client", "/clients"
                )
            else:
                with ui.row().classes("w-full items-center gap-3 no-wrap"):
                    ui.icon("add_circle", size="1.25rem").classes("text-primary")
                    ui.label("Nouvelle réservation pour").classes("text-sm text-ardoise whitespace-nowrap")
                    client_id = ui.select(clients, value=next(iter(clients)), with_input=True).classes("w-80")
                    ui.button("Créer", on_click=creer)
        with ui.card().props("flat bordered").classes("w-full rounded-lg p-0 gap-0"):
            with ui.row().classes("w-full items-center justify-between px-4 py-3 border-b border-slate-200"):
                ui.label(f"{len(lignes)} réservation{'s' if len(lignes) > 1 else ''}").classes("text-sm text-ardoise")
                recherche = (
                    ui.input(placeholder="Rechercher un client, une chambre, un canal…")
                    .props("clearable")
                    .classes("w-96")
                )
                with recherche.add_slot("prepend"):
                    ui.icon("search", size="1.1rem")
            if not lignes:
                etat_vide("book_online", "Aucune réservation pour l'instant.")
                return
            tableau = (
                ui.table(
                    columns=COLONNES, rows=[_ligne_tableau(ligne) for ligne in lignes], row_key="id", pagination=50
                )
                .props("dense flat no-results-label='Aucune réservation ne correspond'")
                .classes("w-full [&_tbody_tr]:cursor-pointer")
            )
            tableau.add_slot("body-cell-statut", BADGE_STATUT)
            tableau.on("rowClick", lambda e: ui.navigate.to(f"/reservations/{e.args[1]['id']}"))
            recherche.bind_value_to(tableau, "filter")
