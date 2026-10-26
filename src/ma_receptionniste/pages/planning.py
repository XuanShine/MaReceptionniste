from datetime import date, timedelta

from nicegui import run, ui

from ma_receptionniste.consultations import STATUT_SEJOUR, charger_planning, segments
from ma_receptionniste.pages.layout import etat_vide, page
from ma_receptionniste.pages.theme import JOURS, MOIS, date_courte
from ma_receptionniste.saisie import basculer_etat

GRILLE = "grid-template-columns: 13rem repeat(7, minmax(7.5rem, 1fr)); min-width: 65.5rem;"


def _lundi(jour: date) -> date:
    return jour - timedelta(days=jour.weekday())


def _periode(lundi: date) -> str:
    dimanche = lundi + timedelta(days=6)
    debut = f"{lundi.day} {MOIS[lundi.month - 1]}" if lundi.month != dimanche.month else str(lundi.day)
    return f"Du {debut} au {dimanche.day} {MOIS[dimanche.month - 1]} {dimanche.year}"


@ui.page("/")
async def planning() -> None:
    aujourd_hui = date.today()
    lundi = _lundi(aujourd_hui)

    async def aller_a(nouveau_lundi: date) -> None:
        nonlocal lundi
        lundi = nouveau_lundi
        await contenu.refresh()

    async def basculer(chambre_id: int) -> None:
        await run.io_bound(basculer_etat, chambre_id)
        await contenu.refresh()

    @ui.refreshable
    async def contenu() -> None:
        jours = [lundi + timedelta(days=offset) for offset in range(7)]
        data = await run.io_bound(charger_planning, lundi, lundi + timedelta(days=7))
        with ui.row().classes("w-full items-center gap-2"):
            ui.button(icon="chevron_left", on_click=lambda: aller_a(lundi - timedelta(days=7))).props(
                "outline dense color=ardoise"
            ).tooltip("Semaine précédente")
            ui.button("Aujourd'hui", on_click=lambda: aller_a(_lundi(aujourd_hui))).props("outline color=ardoise")
            ui.button(icon="chevron_right", on_click=lambda: aller_a(lundi + timedelta(days=7))).props(
                "outline dense color=ardoise"
            ).tooltip("Semaine suivante")
            ui.label(_periode(lundi)).classes("text-base font-medium ml-2")
            ui.space()
            for statut in STATUT_SEJOUR.values():
                if statut.couleur == "negative":
                    continue
                with ui.row().classes("items-center gap-1.5 text-xs text-ardoise"):
                    ui.element("div").classes(f"w-2.5 h-2.5 rounded-sm bg-{statut.couleur}")
                    ui.label(statut.libelle)
        with ui.card().props("flat bordered").classes("w-full p-0 overflow-hidden rounded-lg"):
            if not data["chambres"]:
                etat_vide("bed", "Aucune chambre n'est encore configurée.", "Ajouter une chambre", "/chambres")
                return
            _grille(jours, aujourd_hui, data, basculer)

    with page("/", "Planning"):
        await contenu()


def _grille(jours: list[date], aujourd_hui: date, data: dict, basculer) -> None:
    with ui.element("div").classes("w-full overflow-x-auto"):
        with ui.element("div").classes("grid text-sm").style(GRILLE):
            with ui.element("div").classes(
                "sticky left-0 z-20 bg-white border-b border-r border-slate-200 px-3 flex items-end pb-1.5"
            ):
                ui.label("Chambre").classes("text-xs font-semibold text-ardoise")
            for jour in jours:
                _entete_jour(jour, aujourd_hui)
            for chambre in data["chambres"]:
                _ligne(chambre, jours, aujourd_hui, data["sejours"], basculer)


def _fond(jour: date, aujourd_hui: date) -> str:
    if jour == aujourd_hui:
        return "bg-primary-pale"
    return "bg-slate-50" if jour.weekday() >= 5 else ""


def _entete_jour(jour: date, aujourd_hui: date) -> None:
    couleur = "text-primary" if jour == aujourd_hui else "text-ardoise"
    with ui.column().classes(
        f"{_fond(jour, aujourd_hui)} border-b border-r border-slate-200 items-center gap-0 py-1.5"
    ):
        ui.label(JOURS[jour.weekday()][:3] + ".").classes(f"text-[11px] uppercase tracking-wide {couleur}")
        ui.label(str(jour.day)).classes(f"text-base font-semibold tabular-nums leading-tight {couleur}")


def _ligne(chambre: dict, jours: list[date], aujourd_hui: date, sejours: list[dict], basculer) -> None:
    prete = chambre["etat"] == "pret"
    with ui.row().classes(
        "sticky left-0 z-10 bg-white border-b border-r border-slate-200 px-3 h-10 items-center gap-2 no-wrap"
    ):
        with (
            ui.element("button")
            .classes("w-5 h-5 flex items-center justify-center rounded-full hover:bg-slate-100 cursor-pointer")
            .on("click", lambda chambre_id=chambre["id"]: basculer(chambre_id))
        ):
            ui.element("div").classes("w-2.5 h-2.5 rounded-full " + ("bg-positive" if prete else "bg-warning"))
            ui.tooltip(f"{chambre['etat_label']} · cliquer pour basculer")
        ui.label(chambre["nom"]).classes("font-semibold tabular-nums")
        if chambre["type_chambre"]:
            ui.label(chambre["type_chambre"]).classes("text-xs text-ardoise truncate")
    lignes = [sejour for sejour in sejours if sejour["chambre_id"] == chambre["id"]]
    position = 0
    for bloc in segments(jours, lignes):
        jour = jours[position]
        position += bloc["longueur"]
        sejour = bloc["sejour"]
        if sejour is None:
            ui.element("div").classes(f"h-10 border-b border-r border-slate-200 {_fond(jour, aujourd_hui)}")
            continue
        _bloc(sejour, bloc["longueur"], jours)


def _bloc(sejour: dict, longueur: int, jours: list[date]) -> None:
    couleur = STATUT_SEJOUR[sejour["statut"]].couleur
    arrondi = ("rounded-l-none" if sejour["date_debut"] < jours[0] else "") + (
        " rounded-r-none" if sejour["date_fin"] > jours[-1] + timedelta(days=1) else ""
    )
    with ui.element("div").classes(f"col-span-{longueur} h-10 border-b border-r border-slate-200 p-1"):
        with (
            ui.element("div")
            .classes(
                f"h-full rounded-md bg-{couleur}-soft text-{couleur} flex items-stretch overflow-hidden "
                f"cursor-pointer transition-shadow hover:shadow-md {arrondi}"
            )
            .on(
                "click",
                lambda reservation_id=sejour["reservation_id"]: ui.navigate.to(f"/reservations/{reservation_id}"),
            )
        ):
            ui.element("div").classes(f"w-1 shrink-0 bg-{couleur}")
            with ui.column().classes("gap-0 px-2 justify-center min-w-0"):
                ui.label(sejour["nom"]).classes("text-[13px] font-semibold leading-tight truncate")
                if sejour["partenaire"]:
                    ui.label(sejour["partenaire"]).classes("text-[11px] leading-tight opacity-75 truncate")
            periode = f"{date_courte(sejour['date_debut'])} → {date_courte(sejour['date_fin'])}"
            ui.tooltip(" · ".join(filter(None, (sejour["nom"], sejour["partenaire"], periode))))
