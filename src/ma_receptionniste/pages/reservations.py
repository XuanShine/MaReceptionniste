from nicegui import run, ui

from ma_receptionniste.consultations import lister_reservations, options_clients
from ma_receptionniste.dossier import jour_fr
from ma_receptionniste.pages.layout import cadre, titre
from ma_receptionniste.saisie import creer_reservation


def _resume(sejours: list[dict]) -> str:
    if not sejours:
        return "Aucun séjour"
    morceaux = []
    for sejour in sejours:
        morceaux.append(f"{sejour['chambre_nom']} · {jour_fr(sejour['date_debut'])} → {jour_fr(sejour['date_fin'])}")
    return "  ·  ".join(morceaux)


@ui.page("/reservations")
async def reservations() -> None:
    clients = await run.io_bound(options_clients)

    async def creer() -> None:
        if client_id.value is None:
            ui.notify("Choisissez un client", type="warning")
            return
        reservation_id = await run.io_bound(creer_reservation, client_id.value)
        ui.navigate.to(f"/reservations/{reservation_id}")

    @ui.refreshable
    async def liste() -> None:
        rows = await run.io_bound(lister_reservations)
        table_rows = [
            {
                "id": row["id"],
                "occupant": row["occupant"],
                "client": row["client"],
                "etat": row["etat_label"],
                "sejours": _resume(row["sejours"]),
                "lien": f"/reservations/{row['id']}",
            }
            for row in rows
        ]
        if not table_rows:
            ui.label("Aucune réservation").classes("texte-discret")
            return
        table = (
            ui.table(
                columns=[
                    {"name": "occupant", "label": "Nom", "field": "occupant", "align": "left"},
                    {"name": "client", "label": "Client", "field": "client", "align": "left"},
                    {"name": "etat", "label": "Statut", "field": "etat", "align": "left"},
                    {"name": "sejours", "label": "Séjours", "field": "sejours", "align": "left"},
                ],
                rows=table_rows,
                row_key="id",
                pagination={"rowsPerPage": 0},
            )
            .props("dense flat hide-bottom")
            .classes("w-full fiche-table feuille")
        )
        table.add_slot(
            "body-cell-occupant",
            """
            <q-td :props="props">
                <a :href="props.row.lien" style="color:#1f3d32;font-weight:600;text-decoration:none">
                    {{ props.value }}
                </a>
            </q-td>
            """,
        )

    with cadre("/reservations"):
        titre("Réservations", "Ouvrir une fiche séjour")
        if not clients:
            ui.label("Ajoutez un client avant de créer une réservation.").classes("texte-discret")
            ui.link("Aller aux clients", "/clients")
        else:
            with ui.row().classes("items-end gap-2"):
                client_id = ui.select(clients, label="Client", value=next(iter(clients))).props("dense outlined")
                ui.button("Créer", on_click=creer).props("unelevated no-caps")
        await liste()
