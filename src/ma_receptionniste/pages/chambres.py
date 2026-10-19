from nicegui import run, ui
from sqlalchemy.exc import IntegrityError

from ma_receptionniste.consultations import lister_chambres
from ma_receptionniste.pages.layout import etat_vide, page
from ma_receptionniste.saisie import basculer_etat, creer_chambre, modifier_type_chambre

TYPES_COURANTS = ["Single BB", "Double", "Twin", "Triple", "Familiale", "Suite"]
COLONNES = "grid-template-columns: 5rem 8rem 1fr 9rem 11rem;"


@ui.page("/chambres")
async def chambres() -> None:
    @ui.refreshable
    async def liste() -> None:
        lignes = await run.io_bound(lister_chambres)
        position.value = max((chambre["position"] for chambre in lignes), default=0) + 1
        if not lignes:
            etat_vide("bed", "Aucune chambre. Ajoutez la première avec le formulaire ci-dessus.")
            return
        with ui.element("div").classes("grid w-full text-sm").style(COLONNES):
            for entete in ("Position", "Chambre", "Type", "État", ""):
                ui.label(entete).classes("px-4 py-2 text-xs font-semibold text-ardoise border-b border-slate-200")
            for chambre in lignes:
                _ligne(chambre)

    def _ligne(chambre: dict) -> None:
        cellule = "px-4 h-11 flex items-center border-b border-slate-100"
        prete = chambre["etat"] == "pret"
        ui.label(str(chambre["position"])).classes(f"{cellule} tabular-nums text-ardoise")
        ui.label(chambre["nom"]).classes(f"{cellule} font-semibold tabular-nums")
        with ui.element("div").classes(cellule):
            type_chambre = (
                ui.input(value=chambre["type_chambre"] or "", placeholder="Type", autocomplete=TYPES_COURANTS)
                .props("borderless dense hide-bottom-space", remove="outlined")
                .classes("w-64 rounded px-2 hover:bg-slate-100 focus-within:bg-slate-100")
            )

        enregistre = chambre["type_chambre"] or ""

        async def enregistrer_type() -> None:
            nonlocal enregistre
            valeur = (type_chambre.value or "").strip()
            if valeur == enregistre:
                return
            await run.io_bound(modifier_type_chambre, chambre["id"], valeur)
            enregistre = valeur
            ui.notify(f"Type de la chambre {chambre['nom']} enregistré", type="positive")

        type_chambre.on("blur", enregistrer_type).on("keydown.enter", enregistrer_type)
        couleur = "positive" if prete else "warning"
        with ui.element("div").classes(cellule):
            ui.badge(chambre["etat_label"]).props(f"color={couleur}-soft text-color={couleur}").classes(
                "px-2 py-1 font-medium"
            )

        async def basculer() -> None:
            await run.io_bound(basculer_etat, chambre["id"])
            await liste.refresh()

        with ui.element("div").classes(f"{cellule} justify-end"):
            ui.button("Marquer non prête" if prete else "Marquer prête", on_click=basculer).props(
                "flat dense color=primary"
            )

    async def ajouter() -> None:
        if not (nom.value or "").strip():
            ui.notify("Le nom est obligatoire", type="warning")
            return
        try:
            await run.io_bound(creer_chambre, nom.value, int(position.value or 0), type_nouvelle.value)
        except IntegrityError:
            ui.notify("Ce nom de chambre existe déjà", type="negative")
            return
        nom.value = type_nouvelle.value = ""
        await liste.refresh()
        ui.notify("Chambre ajoutée", type="positive")

    with page("/chambres", "Chambres"):
        with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3 gap-3"):
            ui.label("Nouvelle chambre").classes("text-sm font-semibold")
            with ui.row().classes("w-full items-start gap-3 no-wrap"):
                nom = ui.input("Nom ou numéro *").classes("w-48").on("keydown.enter", ajouter)
                type_nouvelle = ui.input("Type", autocomplete=TYPES_COURANTS).classes("w-56")
                position = ui.number("Position", value=1, min=0, precision=0).classes("w-32")
                ui.button("Ajouter", icon="add", on_click=ajouter).classes("mt-0.5")
        with ui.card().props("flat bordered").classes("w-full rounded-lg p-0 gap-0"):
            await liste()
