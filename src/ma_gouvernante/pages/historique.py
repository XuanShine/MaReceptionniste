from datetime import date, timedelta

from nicegui import run, ui

from ma_gouvernante.actions import historique
from ma_gouvernante.garde import acteur_courant
from ma_gouvernante.menage import COULEUR_STATUT, libelle_statut
from ma_gouvernante.pages.layout import badge, etat_vide, page, refuser
from ma_receptionniste.pages.theme import date_courte, date_heure, date_longue


@ui.page("/historique")
async def page_historique(jour: str = "") -> None:
    acteur = acteur_courant()
    if refuser(acteur):
        return
    assert acteur is not None
    filtre: date | None = None
    if jour:
        try:
            filtre = date.fromisoformat(jour.strip()[:10])
        except ValueError:
            filtre = None

    def aller(cible: str) -> None:
        ui.navigate.to(cible)

    lignes = await run.io_bound(historique, acteur, filtre)
    with page("/historique", "Historique", acteur):
        with ui.row().classes("w-full items-center justify-between"):
            if filtre is None:
                ui.label("Tous les changements de statut").classes("text-sm text-ardoise")
            else:
                ui.label(date_longue(filtre)).classes("text-sm text-ardoise first-letter:uppercase")
            with ui.row().classes("gap-2"):
                ui.button("Tout", on_click=lambda: aller("/historique")).props("flat dense color=primary")
                ui.button(
                    "Aujourd'hui",
                    on_click=lambda: aller(f"/historique?jour={date.today().isoformat()}"),
                ).props("flat dense color=ardoise")
                if filtre is not None:
                    ui.button(
                        "Veille",
                        on_click=lambda: aller(f"/historique?jour={(filtre - timedelta(days=1)).isoformat()}"),
                    ).props("flat dense color=ardoise")
        if not lignes:
            etat_vide("history", "Aucun changement de statut.")
            return
        for ligne in lignes:
            with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3 gap-2"):
                with ui.row().classes("w-full items-center justify-between no-wrap"):
                    ui.label(ligne.chambre).classes("font-semibold tabular-nums")
                    ui.label(date_heure(ligne.quand)).classes("text-xs text-ardoise tabular-nums")
                with ui.row().classes("items-center gap-2"):
                    badge(libelle_statut(ligne.ancien), COULEUR_STATUT.get(ligne.ancien, "ardoise"))
                    ui.icon("arrow_forward", size="1rem").classes("text-ardoise")
                    badge(libelle_statut(ligne.nouveau), COULEUR_STATUT.get(ligne.nouveau, "ardoise"))
                ui.label(f"{ligne.auteur} · ménage du {date_courte(ligne.date)}").classes("text-xs text-ardoise")
