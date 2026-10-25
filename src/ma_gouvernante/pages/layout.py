from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from nicegui import app, run, ui

from ma_gouvernante.auth import charger_utilisateur, logout_user
from ma_gouvernante.models import Role
from ma_gouvernante.pages.registre import cartes_pour
from ma_gouvernante.pages.theme import date_longue

ICONES = {
    "Accueil": "home",
    "Chambres": "bed",
    "Liste du jour": "cleaning_services",
    "Signalements ouverts": "report_problem",
    "Historique": "history",
}


def icone(titre: str) -> str:
    return ICONES.get(titre, "folder")


async def utilisateur_connecte() -> dict | None:
    user_id = app.storage.user.get("user_id")
    if user_id is None:
        return None
    return await run.io_bound(charger_utilisateur, user_id)


@contextmanager
def page(actif: str, titre: str, role: Role | str, nom: str) -> Iterator[None]:
    ui.page_title(f"{titre} · Ma Gouvernante")
    ui.query("body").classes("bg-fond")
    _menu(actif, role, nom)
    with ui.column().classes("w-full max-w-[1400px] mx-auto px-6 py-4 gap-4"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label(titre).classes("text-xl font-semibold")
            ui.label(date_longue(date.today())).classes("text-sm text-ardoise first-letter:uppercase")
        yield


def badge(libelle: str, couleur: str) -> None:
    ui.badge(libelle).props(f"color={couleur}-soft text-color={couleur}").classes("px-2 py-1 font-medium")


def etat_vide(icone_nom: str, phrase: str) -> None:
    with ui.column().classes("w-full items-center gap-2 py-10 text-ardoise"):
        ui.icon(icone_nom, size="2.5rem").classes("text-slate-300")
        ui.label(phrase).classes("text-sm")


def _menu(actif: str, role: Role | str, nom: str) -> None:
    entrees = [("Accueil", "/", icone("Accueil"))]
    entrees += [(carte["titre"], carte["href"], icone(carte["titre"])) for carte in cartes_pour(role)]

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
            ui.label("Ma Gouvernante").classes("text-xs text-ardoise tracking-wide")
        with ui.column().classes("w-full gap-1 px-3"):
            for libelle, cible, icone_nom in entrees:
                courant = _courant(cible, actif)
                with ui.link(target=cible).classes(
                    "w-full flex items-center gap-3 rounded-md px-3 py-2 text-sm no-underline transition-colors "
                    + (
                        "bg-primary-soft text-primary font-semibold"
                        if courant
                        else "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                    )
                ):
                    ui.element("div").classes("w-[3px] h-4 -ml-3 rounded-r " + ("bg-primary" if courant else ""))
                    ui.icon(icone_nom, size="1.25rem")
                    ui.label(libelle)
        ui.space()
        with ui.row().classes("w-full items-center gap-2 px-4 py-3 border-t border-slate-200 no-wrap"):
            ui.avatar(_initiales(nom), color="primary-soft", text_color="primary", size="2rem").classes("text-xs")
            ui.label(nom).classes("text-sm truncate flex-1")
            ui.button(icon="logout", on_click=deconnexion).props("flat round dense color=ardoise").tooltip(
                "Se déconnecter"
            )


def _courant(cible: str, actif: str) -> bool:
    if cible == "/":
        return actif == "/"
    return actif == cible or actif.startswith(f"{cible}/")


def _initiales(nom: str) -> str:
    return "".join(mot[0] for mot in nom.split()[:2]).upper() or "?"
