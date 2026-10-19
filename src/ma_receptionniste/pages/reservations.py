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
from ma_receptionniste.pages.layout import header
from ma_receptionniste.saisie import ajouter_note, ajouter_sejour, annuler_reservation, creer_reservation
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


@ui.page("/reservations")
async def reservations() -> None:
    header("/reservations")

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
        if not rows:
            ui.label("Aucune réservation")
            return
        for row in rows:
            with ui.card().classes("w-full"):
                titre = f"{row['client']} — {STATUT_SEJOUR[row['statut']].libelle}"
                ui.link(titre, f"/reservations/{row['id']}").classes("text-lg")
                if not row["chambres"]:
                    ui.label("Aucun séjour").classes("text-grey")
                    continue
                ui.label(f"{row['chambres']} · {_afficher_date(row['date_debut'])} → {_afficher_date(row['date_fin'])}")

    with ui.column().classes("w-full max-w-3xl mx-auto p-4 gap-4"):
        ui.label("Réservations").classes("text-2xl font-bold")
        if not clients:
            ui.label("Ajoutez un client avant de créer une réservation.")
            ui.link("Aller aux clients", "/clients")
        else:
            with ui.row().classes("items-end"):
                client_id = ui.select(clients, label="Client", value=next(iter(clients)))
                ui.button("Créer", on_click=creer)
        await liste()


@ui.page("/reservations/{reservation_id}")
async def reservation(reservation_id: int) -> None:
    header("/reservations")
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

    with ui.column().classes("w-full max-w-3xl mx-auto p-4 gap-4"):
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
