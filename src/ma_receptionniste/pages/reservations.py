from datetime import date, timedelta

from nicegui import app, run, ui
from sqlalchemy.exc import IntegrityError

from ma_receptionniste.consultations import (
    STATUT_SEJOUR,
    detail_reservation,
    lister_reservations,
    options_chambres,
    options_clients,
)
from ma_receptionniste.facturation import format_euros
from ma_receptionniste.pages.layout import etat_vide, ouvrir_nouvelle_reservation, page
from ma_receptionniste.pages.theme import date_courte
from ma_receptionniste.saisie import ajouter_note, ajouter_sejour, annuler_reservation
from ma_receptionniste.sejours import ChambreOccupee, SejourInvalide


def _lire_date(valeur: object) -> date | None:
    if not isinstance(valeur, str) or not valeur:
        return None
    try:
        return date.fromisoformat(valeur)
    except ValueError:
        return None


def _afficher_date(valeur: date) -> str:
    return valeur.strftime("%d/%m/%Y")


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


@ui.page("/reservations/{reservation_id}")
async def reservation(reservation_id: int) -> None:
    chambres = await run.io_bound(options_chambres)
    aujourd_hui = date.today()

    @ui.refreshable
    async def contenu() -> None:
        detail = await run.io_bound(detail_reservation, reservation_id)
        if detail is None:
            ui.label("Réservation introuvable")
            return
        with ui.row().classes("items-center gap-4"):
            ui.label(f"{detail['client']} — {detail['statut_label']}").classes("text-2xl font-bold")
            if detail["statut"] != "annulee":

                async def annuler() -> None:
                    await run.io_bound(annuler_reservation, reservation_id)
                    await contenu.refresh()
                    ui.notify("Réservation annulée", type="warning")

                ui.button("Annuler", on_click=annuler, color="negative").props("outline")
        if not detail["sejours"]:
            ui.label("Aucun séjour")
        for sejour in detail["sejours"]:
            nom = f" — {sejour['nom_client']}" if sejour["nom_client"] else ""
            ui.label(
                f"{sejour['chambre_nom']} · {_afficher_date(sejour['date_debut'])}"
                f" → {_afficher_date(sejour['date_fin'])}{nom}"
            )
        ui.label("Notes").classes("text-lg mt-4")
        if not detail["notes"]:
            ui.label("Aucune note").classes("text-grey")
        for note in detail["notes"]:
            auteur = note["auteur"] or "sans auteur"
            ui.label(f"{note['date'].strftime('%d/%m/%Y %H:%M')} · {auteur}").classes("text-grey text-sm")
            ui.label(note["description"])

    async def enregistrer() -> None:
        debut = _lire_date(arrivee.value)
        fin = _lire_date(depart.value)
        if chambre_id.value is None or debut is None or fin is None:
            ui.notify("Chambre et dates obligatoires", type="warning")
            return
        try:
            await run.io_bound(ajouter_sejour, reservation_id, chambre_id.value, debut, fin, nom_sejour.value)
        except ChambreOccupee:
            ui.notify("La chambre est déjà occupée sur cette période", type="negative")
            return
        except SejourInvalide:
            ui.notify("Le départ doit être après l'arrivée", type="warning")
            return
        nom_sejour.value = ""
        await contenu.refresh()
        ui.notify("Séjour ajouté", type="positive")

    async def noter() -> None:
        if not (description.value or "").strip():
            ui.notify("La note est vide", type="warning")
            return
        try:
            await run.io_bound(ajouter_note, reservation_id, app.storage.user.get("user_id"), description.value)
        except IntegrityError:
            ui.notify("Impossible d'enregistrer la note", type="negative")
            return
        description.value = ""
        await contenu.refresh()
        ui.notify("Note ajoutée", type="positive")

    with page("/reservations", "Réservation"), ui.column().classes("w-full max-w-3xl gap-4"):
        ui.link("Toutes les réservations", "/reservations")
        await contenu()
        ui.label("Ajouter un séjour").classes("text-lg")
        if not chambres:
            ui.label("Ajoutez une chambre avant un séjour.")
            ui.link("Aller aux chambres", "/chambres")
        else:
            chambre_id = ui.select(chambres, label="Chambre", value=next(iter(chambres)))
            nom_sejour = ui.input("Nom sur le séjour, si différent")
            with ui.row().classes("items-start"):
                with ui.column():
                    ui.label("Arrivée")
                    arrivee = ui.date(aujourd_hui.isoformat())
                with ui.column():
                    ui.label("Départ")
                    depart = ui.date((aujourd_hui + timedelta(days=1)).isoformat())
            ui.button("Enregistrer le séjour", on_click=enregistrer)
        with ui.row().classes("items-end"):
            description = ui.textarea("Note").classes("w-80")
            ui.button("Ajouter la note", on_click=noter)
