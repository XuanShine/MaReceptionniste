from collections.abc import Iterator
from contextlib import contextmanager

from nicegui import app, ui

from ma_gouvernante.menage import LIBELLE_ROLE, Acteur
from ma_receptionniste.auth import logout_user
from ma_receptionniste.pages.layout import badge, etat_vide

__all__ = ["badge", "etat_vide", "page"]


def _initiales(nom: str) -> str:
    return "".join(mot[0] for mot in nom.split()[:2]).upper() or "?"


def _navigation() -> tuple[tuple[str, str, str], ...]:
    return (
        ("/", "Ménage", "mop"),
        ("/chambres", "Chambres", "bed"),
        ("/historique", "Historique", "history"),
    )


@contextmanager
def page(actif: str, titre: str, acteur: Acteur) -> Iterator[None]:
    ui.page_title(f"{titre} · Ma Gouvernante")
    ui.query("body").classes("bg-fond")
    _menu(actif, acteur)
    with ui.column().classes("w-full max-w-[1100px] mx-auto px-6 py-4 gap-4"):
        ui.label(titre).classes("text-xl font-semibold")
        yield


def _menu(actif: str, acteur: Acteur) -> None:
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
            for cible, libelle, icone in _navigation():
                courant = cible == actif
                with ui.link(target=cible).classes(
                    "w-full flex items-center gap-3 rounded-md px-3 py-2 text-sm no-underline transition-colors "
                    + (
                        "bg-primary-soft text-primary font-semibold"
                        if courant
                        else "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                    )
                ):
                    ui.element("div").classes("w-[3px] h-4 -ml-3 rounded-r " + ("bg-primary" if courant else ""))
                    ui.icon(icone, size="1.25rem")
                    ui.label(libelle)
        ui.space()
        with ui.column().classes("w-full gap-2 px-4 py-3 border-t border-slate-200"):
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                ui.avatar(_initiales(acteur.nom), color="primary-soft", text_color="primary", size="2rem").classes(
                    "text-xs"
                )
                with ui.column().classes("gap-0 flex-1 min-w-0"):
                    ui.label(acteur.nom).classes("text-sm truncate")
                    ui.label(LIBELLE_ROLE[acteur.role]).classes("text-xs text-ardoise")
            ui.button("Se déconnecter", icon="logout", on_click=deconnexion).props("flat dense color=ardoise").classes(
                "w-full"
            )


def refuser(acteur: Acteur | None) -> bool:
    if acteur is not None:
        return False
    if "user_id" in app.storage.user:
        logout_user()
    ui.navigate.to("/login")
    return True
