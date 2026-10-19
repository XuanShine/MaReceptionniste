from datetime import date, timedelta

from nicegui import run, ui

from ma_receptionniste.consultations import charger_planning, segments
from ma_receptionniste.pages.layout import cadre, titre

JOURS = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")
MOIS = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")
GRILLE = "grid-template-columns: 9.5rem repeat(7, minmax(4.75rem, 1fr));"


def _lundi(jour: date) -> date:
    return jour - timedelta(days=jour.weekday())


def _periode(lundi: date) -> str:
    dimanche = lundi + timedelta(days=6)
    if lundi.year == dimanche.year and lundi.month == dimanche.month:
        return f"{lundi.day} – {dimanche.day} {MOIS[dimanche.month - 1]} {dimanche.year}"
    return f"{lundi.day} {MOIS[lundi.month - 1]} – {dimanche.day} {MOIS[dimanche.month - 1]} {dimanche.year}"


@ui.page("/")
async def planning() -> None:
    lundi = _lundi(date.today())
    aujourd_hui = date.today()

    @ui.refreshable
    async def grille() -> None:
        jours = [lundi + timedelta(days=offset) for offset in range(7)]
        data = await run.io_bound(charger_planning, lundi, lundi + timedelta(days=7))
        if not data["chambres"]:
            ui.label("Aucune chambre").classes("texte-discret")
            ui.link("Ajouter une chambre", "/chambres")
            return
        with ui.element("div").classes("w-full overflow-x-auto"):
            with ui.element("div").classes("grid gap-1.5 min-w-[52rem]").style(GRILLE):
                ui.label("")
                for jour in jours:
                    with ui.column().classes("items-center gap-0 py-1"):
                        ui.label(JOURS[jour.weekday()]).classes("text-xs texte-discret")
                        style = "background:#1f3d32;color:#fbf8f3;" if jour == aujourd_hui else ""
                        ui.label(str(jour.day)).classes(
                            "w-7 h-7 flex items-center justify-center rounded-full text-sm font-semibold"
                        ).style(style)
                for chambre in data["chambres"]:
                    with ui.column().classes("justify-center pr-2 sticky left-0 z-10").style("background:#efeae2"):
                        ui.label(chambre["nom"]).classes("font-semibold text-sm leading-tight")
                        couleur = "#2c6b4a" if chambre["etat"] == "pret" else "#9a6230"
                        ui.label(chambre["etat_label"]).classes("text-xs").style(f"color:{couleur}")
                    sejours = [sejour for sejour in data["sejours"] if sejour["chambre_id"] == chambre["id"]]
                    for bloc in segments(jours, sejours):
                        if bloc["sejour"] is None:
                            ui.element("div").classes("min-h-14 rounded-md").style(
                                "background:#fbf8f3;border:1px solid #e6dfd2"
                            )
                            continue
                        reservation_id = bloc["sejour"]["reservation_id"]

                        def ouvrir(reservation_id: int = reservation_id) -> None:
                            ui.navigate.to(f"/reservations/{reservation_id}")

                        ui.button(bloc["sejour"]["nom"], on_click=ouvrir).props("unelevated no-caps dense").classes(
                            "sejour-barre min-h-14 w-full"
                        ).style(
                            f"grid-column: span {bloc['longueur']}; background:#1f3d32; "
                            "color:#f7f3ea; border-radius:8px;"
                        )

    async def deplacer(delta: int) -> None:
        nonlocal lundi
        lundi = _lundi(date.today()) if delta == 0 else lundi + timedelta(days=delta)
        periode.set_text(_periode(lundi))
        await grille.refresh()

    with cadre("/"):
        with ui.row().classes("w-full items-center justify-between"):
            titre("Planning", "Semaine des chambres")
            with ui.row().classes("items-center gap-1"):
                ui.button(icon="chevron_left", on_click=lambda: deplacer(-7)).props("flat round dense")
                periode = (
                    ui.label(_periode(lundi)).classes("text-sm font-semibold text-center").style("min-width: 14rem")
                )
                ui.button(icon="chevron_right", on_click=lambda: deplacer(7)).props("flat round dense")
                ui.button("Aujourd'hui", on_click=lambda: deplacer(0)).props("outline no-caps dense")
        await grille()
