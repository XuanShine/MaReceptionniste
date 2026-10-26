from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from nicegui import app, run, ui

from ma_receptionniste.auth import logout_user
from ma_receptionniste.consultations import options_clients
from ma_receptionniste.pages.theme import date_longue
from ma_receptionniste.saisie import creer_reservation

RESERVATION_OUVERTE = "reservation_ouverte"
ACTIF_DETAIL = "detail"


def ouvrir_reservation(reservation_id: int) -> None:
    app.storage.user[RESERVATION_OUVERTE] = reservation_id


def fermer_reservation() -> None:
    app.storage.user.pop(RESERVATION_OUVERTE, None)


def _entrees() -> tuple[tuple[str | None, str, str, str], ...]:
    ouverte = app.storage.user.get(RESERVATION_OUVERTE)
    return (
        ("/dashboard", "Dashboard", "dashboard", "/dashboard"),
        ("/", "Planning", "calendar_month", "/"),
        ("/reservations", "Réservations", "book_online", "/reservations"),
        (
            f"/reservations/{ouverte}" if ouverte else None,
            "Détail Réservation",
            "description",
            ACTIF_DETAIL,
        ),
        ("/clients", "Clients", "people", "/clients"),
        ("/chambres", "Chambres", "bed", "/chambres"),
    )


@contextmanager
def page(actif: str, titre: str) -> Iterator[None]:
    """Cadre commun : menu latéral, barre de titre, puis le contenu de la page."""
    ui.page_title(f"{titre} · Ma Réceptionniste")
    ui.query("body").classes("bg-fond")
    _menu(actif)
    ouvrir_dialogue = _dialogue_nouvelle_reservation()
    with ui.column().classes("w-full max-w-[1400px] mx-auto px-6 py-4 gap-4"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label(titre).classes("text-xl font-semibold")
            with ui.row().classes("items-center gap-4 no-wrap"):
                ui.label(date_longue(date.today())).classes("text-sm text-ardoise first-letter:uppercase")
                ui.button("Nouvelle réservation", icon="add", on_click=ouvrir_dialogue)
        yield


def badge(libelle: str, couleur: str) -> None:
    ui.badge(libelle).props(f"color={couleur}-soft text-color={couleur}").classes("px-2 py-1 font-medium")


def etat_vide(icone: str, phrase: str, action: str | None = None, cible: str | None = None) -> None:
    with ui.column().classes("w-full items-center gap-2 py-10 text-ardoise"):
        ui.icon(icone, size="2.5rem").classes("text-slate-300")
        ui.label(phrase).classes("text-sm")
        if action and cible:
            ui.link(action, cible).classes("text-sm text-primary font-medium no-underline hover:underline")


def _menu(actif: str) -> None:
    nom = app.storage.user.get("nom", "")

    def deconnexion() -> None:
        logout_user()
        ui.navigate.to("/login")

    with (
        ui.left_drawer(value=True, fixed=True, bordered=True)
        .props("width=220 behavior=desktop")
        .classes("bg-white p-0 column no-wrap")
    ):
        with ui.column().classes("gap-0 px-5 pt-5 pb-6"):
            ui.label("Hôtel Panorama").classes("text-lg font-semibold text-primary leading-tight")
            ui.label("Ma Réceptionniste").classes("text-xs text-ardoise tracking-wide")
        with ui.column().classes("w-full gap-1 px-3"):
            for cible, libelle, icone, cle in _entrees():
                _entree_menu(cible, libelle, icone, courant=cle == actif)
        ui.space()
        with ui.row().classes("w-full items-center gap-2 px-4 py-3 border-t border-slate-200 no-wrap"):
            ui.avatar(_initiales(nom), color="primary-soft", text_color="primary", size="2rem").classes("text-xs")
            ui.label(nom).classes("text-sm truncate flex-1")
            ui.button(icon="logout", on_click=deconnexion).props("flat round dense color=ardoise").tooltip(
                "Se déconnecter"
            )


def _entree_menu(cible: str | None, libelle: str, icone: str, *, courant: bool) -> None:
    if cible is None:
        style = "text-slate-300 cursor-default"
    elif courant:
        style = "bg-primary-soft text-primary font-semibold"
    else:
        style = "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
    classes = f"w-full flex items-center gap-3 rounded-md px-3 py-2 text-sm no-underline transition-colors {style}"
    conteneur = ui.element("div").classes(classes) if cible is None else ui.link(target=cible).classes(classes)
    with conteneur:
        ui.element("div").classes("w-[3px] h-4 -ml-3 rounded-r " + ("bg-primary" if courant else ""))
        ui.icon(icone, size="1.25rem")
        ui.label(libelle)


def _dialogue_nouvelle_reservation():
    with ui.dialog() as dialogue, ui.card().classes("w-[26rem] gap-4"):
        ui.label("Nouvelle réservation").classes("text-base font-semibold")
        client = ui.select({}, label="Client", with_input=True).classes("w-full")
        with ui.row().classes("w-full items-center justify-between"):
            ui.link("Nouveau client", "/clients").classes("text-sm text-primary no-underline hover:underline")
            with ui.row().classes("gap-2"):
                ui.button("Annuler", on_click=dialogue.close).props("flat color=ardoise")
                bouton_creer = ui.button("Créer et ouvrir la fiche")

    async def creer() -> None:
        if client.value is None:
            ui.notify("Choisissez un client", type="warning")
            return
        await ouvrir_nouvelle_reservation(client.value)

    bouton_creer.on_click(creer)

    async def ouvrir() -> None:
        options = await run.io_bound(options_clients)
        if not options:
            ui.notify("Ajoutez d'abord un client", type="warning")
            ui.navigate.to("/clients")
            return
        client.set_options(options, value=next(iter(options)))
        dialogue.open()

    return ouvrir


async def ouvrir_nouvelle_reservation(client_id: int) -> None:
    reservation_id = await run.io_bound(creer_reservation, client_id)
    ui.navigate.to(f"/reservations/{reservation_id}")


def _initiales(nom: str) -> str:
    return "".join(mot[0] for mot in nom.split()[:2]).upper() or "?"
