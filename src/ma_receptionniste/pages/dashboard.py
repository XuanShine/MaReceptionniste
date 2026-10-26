from nicegui import run, ui

from ma_receptionniste.consultations import ResumeJour, charger_resume
from ma_receptionniste.pages.layout import page


@ui.page("/dashboard")
async def dashboard() -> None:
    with page("/dashboard", "Dashboard"):
        resume = await run.io_bound(charger_resume)
        _indicateurs(resume)


def _indicateurs(resume: ResumeJour) -> None:
    cartes = (
        ("Arrivées", resume.arrivees, "login", "primary"),
        ("Départs", resume.departs, "logout", "accent"),
        ("En maison", resume.en_maison, "hotel", "secondary"),
        ("Chambres non prêtes", resume.chambres_non_pretes, "cleaning_services", "warning"),
    )
    with ui.grid(columns=4).classes("w-full gap-3"):
        for libelle, valeur, icone, couleur in cartes:
            with ui.card().props("flat bordered").classes("flex-row items-center gap-3 px-4 py-3 rounded-lg"):
                with ui.element("div").classes(f"rounded-lg p-2 bg-{couleur}-soft text-{couleur} flex"):
                    ui.icon(icone, size="1.25rem")
                with ui.column().classes("gap-0"):
                    ui.label(str(valeur)).classes("text-2xl font-semibold leading-none tabular-nums")
                    ui.label(libelle).classes("text-xs text-ardoise mt-1")
