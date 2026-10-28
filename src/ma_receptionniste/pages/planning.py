from dataclasses import dataclass
from datetime import date, timedelta
from typing import ClassVar, Self

from nicegui import run, ui

from ma_receptionniste.consultations import charger_planning, segments
from ma_receptionniste.pages.layout import header

JOURS = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")
MOIS = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")


@dataclass(frozen=True)
class Semaine:
    lundi: date
    DUREE: ClassVar[int] = 7

    def __post_init__(self) -> None:
        object.__setattr__(self, "lundi", self.lundi - timedelta(days=self.lundi.weekday()))

    @property
    def fin(self) -> date:
        return self.lundi + timedelta(days=self.DUREE)

    @property
    def jours(self) -> tuple[date, ...]:
        return tuple(self.lundi + timedelta(days=offset) for offset in range(self.DUREE))

    def precedente(self) -> Self:
        return Semaine(self.lundi - timedelta(days=self.DUREE))

    def suivante(self) -> Self:
        return Semaine(self.lundi + timedelta(days=self.DUREE))


GRILLE = f"grid-template-columns: 10rem repeat({Semaine.DUREE}, 6rem);"


def _periode(semaine: Semaine) -> str:
    lundi = semaine.jours[0]
    dimanche = semaine.jours[-1]
    return f"{lundi.day} {MOIS[lundi.month - 1]} – {dimanche.day} {MOIS[dimanche.month - 1]} {dimanche.year}"


@ui.page("/")
async def planning() -> None:
    header("/")
    semaine = Semaine(date.today())

    @ui.refreshable
    async def grille() -> None:
        data = await run.io_bound(charger_planning, semaine.lundi, semaine.fin)
        ui.label(_periode(semaine)).classes("text-xl font-bold")
        if not data["chambres"]:
            ui.label("Aucune chambre")
            ui.link("Ajouter une chambre", "/chambres")
            return
        with ui.element("div").classes("w-full overflow-x-auto"):
            with ui.element("div").classes("grid gap-1 min-w-max").style(GRILLE):
                ui.label("")
                for jour in semaine.jours:
                    ui.label(f"{JOURS[jour.weekday()]} {jour.day}").classes("text-center")
                for chambre in data["chambres"]:
                    with ui.column().classes("sticky left-0 z-10 bg-white justify-center pr-2"):
                        ui.label(chambre["nom"]).classes("font-bold")
                        couleur = "positive" if chambre["etat"] == "pret" else "warning"
                        ui.badge(chambre["etat_label"], color=couleur)
                    sejours = [sejour for sejour in data["sejours"] if sejour["chambre_id"] == chambre["id"]]
                    for bloc in segments(semaine.jours, sejours):
                        if bloc["sejour"] is None:
                            ui.element("div").classes("min-h-12 rounded border border-grey-4")
                            continue
                        reservation_id = bloc["sejour"]["reservation_id"]

                        def ouvrir(reservation_id: int = reservation_id) -> None:
                            ui.navigate.to(f"/reservations/{reservation_id}")

                        ui.button(bloc["sejour"]["nom"], on_click=ouvrir).props("unelevated no-caps").classes(
                            "min-h-12 w-full"
                        ).style(f"grid-column: span {bloc['longueur']}")

    async def afficher(cible: Semaine) -> None:
        nonlocal semaine
        semaine = cible
        await grille.refresh()

    async def aujourdhui() -> None:
        await afficher(Semaine(date.today()))

    async def precedente() -> None:
        await afficher(semaine.precedente())

    async def suivante() -> None:
        await afficher(semaine.suivante())

    with ui.column().classes("w-full p-4 gap-4"):
        ui.label("Planning").classes("text-2xl font-bold")
        with ui.row().classes("items-center"):
            ui.button("Semaine précédente", on_click=precedente).props("outline")
            ui.button("Aujourd'hui", on_click=aujourdhui).props("outline")
            ui.button("Semaine suivante", on_click=suivante).props("outline")
        await grille()
