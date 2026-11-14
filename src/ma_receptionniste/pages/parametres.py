from fastapi.responses import RedirectResponse
from nicegui import app, run, ui
from sqlalchemy.exc import IntegrityError

from ma_receptionniste.consultations import ecran_parametres
from ma_receptionniste.facturation import TAXE_SEJOUR_CENTIMES, format_euros
from ma_receptionniste.pages.layout import CHEMIN_PARAMETRES, NOM_ETABLISSEMENT, badge, etat_vide, page
from ma_receptionniste.saisie import (
    CatalogueInvalide,
    attribuer_occupation_chambre,
    attribuer_type_chambre,
    basculer_etat,
    creer_chambre,
    creer_occupation_chambre,
    creer_type_chambre,
    modifier_occupation_chambre,
    renommer_type_chambre,
    supprimer_occupation_chambre,
    supprimer_type_chambre,
)

_AVERTISSEMENTS = frozenset(
    {
        "Le libellé est obligatoire",
        "Le nombre de personnes doit être au moins 1",
        "Le type de lits est obligatoire",
    }
)
_CHAMP = "borderless dense hide-bottom-space"
_CHAMP_CLASSES = "w-full rounded px-2 hover:bg-slate-100 focus-within:bg-slate-100"
_ENTETE = "px-4 py-2 text-xs font-semibold text-ardoise border-b border-slate-200"
_CELLULE = "px-4 h-11 flex items-center border-b border-slate-100"
_COLONNES_TYPES = "grid-template-columns: 1fr 8rem;"
_COLONNES_OCCUPATIONS = "grid-template-columns: 8rem 1fr 8rem;"
_COLONNES_CHAMBRES = "grid-template-columns: 5rem 8rem 1fr 1fr 9rem 11rem;"


def _lien(valeur: int | str | None) -> int | None:
    if valeur is None or valeur == "":
        return None
    return int(valeur)


def _ton(message: str) -> str:
    return "warning" if message in _AVERTISSEMENTS else "negative"


def _options_types(types: list[dict]) -> dict[int | None, str]:
    return {None: "Aucune", **{ligne["id"]: ligne["libelle"] for ligne in types}}


def _options_occupations(occupations: list[dict]) -> dict[int | None, str]:
    return {
        None: "Aucune",
        **{ligne["id"]: f"{ligne['nombre_personnes']} · {ligne['type_lits']}" for ligne in occupations},
    }


def _conserver(valeur: int | None, options: dict[int | None, str]) -> int | None:
    return valeur if valeur in options else None


def _avec_choix(options: dict[int | None, str], identifiant: int | None, libelle: str | None) -> dict[int | None, str]:
    if identifiant is None or identifiant in options:
        return options
    return {**options, identifiant: libelle or "—"}


@app.get("/chambres")
def anciennes_chambres() -> RedirectResponse:
    return RedirectResponse(CHEMIN_PARAMETRES)


@ui.page(CHEMIN_PARAMETRES)
async def parametres() -> None:
    @ui.refreshable
    async def corps() -> None:
        ecran = await run.io_bound(ecran_parametres)
        options_types = _options_types(ecran["types"])
        options_occupations = _options_occupations(ecran["occupations"])
        type_nouvelle.set_options(options_types, value=_conserver(type_nouvelle.value, options_types))
        occupation_nouvelle.set_options(
            options_occupations, value=_conserver(occupation_nouvelle.value, options_occupations)
        )
        position.value = ecran["position"]
        for slot in (slot_types, slot_occupations, slot_chambres):
            slot.clear()
        with slot_types:
            _types(ecran["types"])
        with slot_occupations:
            _occupations(ecran["occupations"])
        with slot_chambres:
            _chambres(ecran)

    async def _sauver(action, message: str | None) -> None:
        try:
            resultat = await action()
        except CatalogueInvalide as erreur:
            ui.notify(str(erreur), type=_ton(str(erreur)))
            await corps.refresh()
            return
        if message is None:
            if resultat is False:
                return
            await corps.refresh()
            return
        if resultat is not True:
            return
        ui.notify(message, type="positive")
        await corps.refresh()

    def _types(types: list[dict]) -> None:
        with ui.card().props("flat bordered").classes("w-full rounded-lg p-0 gap-0"):
            if not types:
                etat_vide("category", "Aucun type. Ajoutez le premier avec le formulaire ci-dessus.")
                return
            with ui.element("div").classes("grid w-full text-sm").style(_COLONNES_TYPES):
                for titre in ("Libellé", ""):
                    ui.label(titre).classes(_ENTETE)
                for ligne in types:
                    _ligne_type(ligne)

    def _ligne_type(ligne: dict) -> None:
        with ui.element("div").classes(_CELLULE):
            champ = (
                ui.input(value=ligne["libelle"])
                .props(_CHAMP, remove="outlined")
                .classes(_CHAMP_CLASSES)
            )

        async def enregistrer() -> None:
            if (champ.value or "").strip() == ligne["libelle"]:
                return
            await _sauver(
                lambda: run.io_bound(renommer_type_chambre, ligne["id"], champ.value or ""),
                "Type enregistré",
            )

        champ.on("blur", enregistrer).on("keydown.enter", enregistrer)

        async def supprimer() -> None:
            await _sauver(lambda: run.io_bound(supprimer_type_chambre, ligne["id"]), None)

        with ui.element("div").classes(f"{_CELLULE} justify-end"):
            ui.button("Supprimer", on_click=supprimer).props("flat dense color=negative")

    def _occupations(occupations: list[dict]) -> None:
        with ui.card().props("flat bordered").classes("w-full rounded-lg p-0 gap-0"):
            if not occupations:
                etat_vide("bed", "Aucune occupation. Ajoutez la première avec le formulaire ci-dessus.")
                return
            with ui.element("div").classes("grid w-full text-sm").style(_COLONNES_OCCUPATIONS):
                for titre in ("Personnes", "Lits", ""):
                    ui.label(titre).classes(_ENTETE)
                for ligne in occupations:
                    _ligne_occupation(ligne)

    def _ligne_occupation(ligne: dict) -> None:
        with ui.element("div").classes(_CELLULE):
            personnes = (
                ui.number(value=ligne["nombre_personnes"], min=0, precision=0)
                .props(_CHAMP, remove="outlined")
                .classes(_CHAMP_CLASSES)
            )
        with ui.element("div").classes(_CELLULE):
            lits = (
                ui.input(value=ligne["type_lits"])
                .props(_CHAMP, remove="outlined")
                .classes(_CHAMP_CLASSES)
            )

        async def enregistrer() -> None:
            personnes_saisies = int(personnes.value or 0)
            lits_saisis = (lits.value or "").strip()
            if personnes_saisies == ligne["nombre_personnes"] and lits_saisis == ligne["type_lits"]:
                return
            await _sauver(
                lambda: run.io_bound(
                    modifier_occupation_chambre,
                    ligne["id"],
                    personnes_saisies,
                    lits_saisis,
                ),
                "Occupation enregistrée",
            )

        personnes.on("blur", enregistrer).on("keydown.enter", enregistrer)
        lits.on("blur", enregistrer).on("keydown.enter", enregistrer)

        async def supprimer() -> None:
            await _sauver(lambda: run.io_bound(supprimer_occupation_chambre, ligne["id"]), None)

        with ui.element("div").classes(f"{_CELLULE} justify-end"):
            ui.button("Supprimer", on_click=supprimer).props("flat dense color=negative")

    def _chambres(ecran: dict) -> None:
        chambres = ecran["chambres"]
        with ui.card().props("flat bordered").classes("w-full rounded-lg p-0 gap-0"):
            if not chambres:
                etat_vide("bed", "Aucune chambre. Ajoutez la première avec le formulaire ci-dessus.")
                return
            options_types = _options_types(ecran["types"])
            options_occupations = _options_occupations(ecran["occupations"])
            with ui.element("div").classes("grid w-full text-sm").style(_COLONNES_CHAMBRES):
                for titre in ("Position", "Chambre", "Type", "Occupation", "État", ""):
                    ui.label(titre).classes(_ENTETE)
                for chambre in chambres:
                    _ligne_chambre(chambre, options_types, options_occupations)

    def _ligne_chambre(chambre: dict, options_types: dict, options_occupations: dict) -> None:
        prete = chambre["etat"] == "pret"
        ui.label(str(chambre["position"])).classes(f"{_CELLULE} tabular-nums text-ardoise")
        ui.label(chambre["nom"]).classes(f"{_CELLULE} font-semibold tabular-nums")
        with ui.element("div").classes(_CELLULE):
            select_type = (
                ui.select(
                    _avec_choix(options_types, chambre["type_chambre_id"], chambre["type_chambre"]),
                    value=chambre["type_chambre_id"],
                )
                .props("dense options-dense borderless", remove="outlined")
                .classes("w-full")
            )

        async def changer_type() -> None:
            await _sauver(
                lambda: run.io_bound(attribuer_type_chambre, chambre["id"], _lien(select_type.value)),
                "Type enregistré",
            )

        select_type.on_value_change(changer_type)
        with ui.element("div").classes(_CELLULE):
            select_occupation = (
                ui.select(
                    _avec_choix(options_occupations, chambre["occupation_chambre_id"], None),
                    value=chambre["occupation_chambre_id"],
                )
                .props("dense options-dense borderless", remove="outlined")
                .classes("w-full")
            )

        async def changer_occupation() -> None:
            await _sauver(
                lambda: run.io_bound(attribuer_occupation_chambre, chambre["id"], _lien(select_occupation.value)),
                "Occupation enregistrée",
            )

        select_occupation.on_value_change(changer_occupation)
        with ui.element("div").classes(_CELLULE):
            badge(chambre["etat_label"], "positive" if prete else "warning")

        async def basculer() -> None:
            await run.io_bound(basculer_etat, chambre["id"])
            await corps.refresh()

        with ui.element("div").classes(f"{_CELLULE} justify-end"):
            ui.button("Marquer non prête" if prete else "Marquer prête", on_click=basculer).props(
                "flat dense color=primary"
            )

    async def ajouter_type() -> None:
        try:
            type_id = await run.io_bound(creer_type_chambre, libelle_nouveau.value or "")
        except CatalogueInvalide as erreur:
            ui.notify(str(erreur), type=_ton(str(erreur)))
            return
        if type_id is None:
            return
        libelle_nouveau.value = ""
        await corps.refresh()
        ui.notify("Type ajouté", type="positive")

    async def ajouter_occupation() -> None:
        try:
            occupation_id = await run.io_bound(
                creer_occupation_chambre,
                int(personnes_nouvelles.value or 0),
                lits_nouveaux.value or "",
            )
        except CatalogueInvalide as erreur:
            ui.notify(str(erreur), type=_ton(str(erreur)))
            return
        if occupation_id is None:
            return
        personnes_nouvelles.value = 1
        lits_nouveaux.value = ""
        await corps.refresh()
        ui.notify("Occupation ajoutée", type="positive")

    async def ajouter_chambre() -> None:
        if not (nom.value or "").strip():
            ui.notify("Le nom est obligatoire", type="warning")
            return
        try:
            chambre_id = await run.io_bound(
                creer_chambre,
                nom.value,
                int(position.value or 0),
                type_chambre_id=_lien(type_nouvelle.value),
                occupation_chambre_id=_lien(occupation_nouvelle.value),
            )
        except CatalogueInvalide as erreur:
            ui.notify(str(erreur), type=_ton(str(erreur)))
            return
        except IntegrityError:
            ui.notify("Ce nom de chambre existe déjà", type="negative")
            return
        if chambre_id is None:
            return
        nom.value = ""
        type_nouvelle.value = None
        occupation_nouvelle.value = None
        await corps.refresh()
        ui.notify("Chambre ajoutée", type="positive")

    with page(CHEMIN_PARAMETRES, "Paramètres"):
        _bandeau()
        with ui.column().classes("w-full gap-3"):
            with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3 gap-3"):
                ui.label("Types de chambre").classes("text-sm font-semibold")
                ui.label(
                    "Un type est partagé. Le renommer change le libellé de chaque chambre qui le cite."
                ).classes("text-sm text-ardoise")
                with ui.row().classes("w-full items-start gap-3 no-wrap"):
                    libelle_nouveau = ui.input("Libellé").classes("w-64").on("keydown.enter", ajouter_type)
                    ui.button("Ajouter", icon="add", on_click=ajouter_type).classes("mt-0.5")
            slot_types = ui.column().classes("w-full")
        with ui.column().classes("w-full gap-3"):
            with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3 gap-3"):
                ui.label("Occupations").classes("text-sm font-semibold")
                ui.label(
                    "Une occupation est partagée. La modifier change le nombre de personnes "
                    "et le type de lits de chaque chambre qui la cite."
                ).classes("text-sm text-ardoise")
                with ui.row().classes("w-full items-start gap-3 no-wrap"):
                    personnes_nouvelles = ui.number("Personnes", value=1, min=0, precision=0).classes("w-32")
                    lits_nouveaux = ui.input("Type de lits").classes("w-56").on("keydown.enter", ajouter_occupation)
                    ui.button("Ajouter", icon="add", on_click=ajouter_occupation).classes("mt-0.5")
            slot_occupations = ui.column().classes("w-full")
        with ui.column().classes("w-full gap-3"):
            with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3 gap-3"):
                ui.label("Chambres").classes("text-sm font-semibold")
                with ui.row().classes("w-full items-start gap-3 no-wrap"):
                    nom = ui.input("Nom ou numéro *").classes("w-48").on("keydown.enter", ajouter_chambre)
                    type_nouvelle = ui.select({None: "Aucune"}, label="Type", value=None).classes("w-56")
                    occupation_nouvelle = ui.select({None: "Aucune"}, label="Occupation", value=None).classes("w-56")
                    position = ui.number("Position", value=1, min=0, precision=0).classes("w-32")
                    ui.button("Ajouter", icon="add", on_click=ajouter_chambre).classes("mt-0.5")
            slot_chambres = ui.column().classes("w-full")
        await corps()


def _bandeau() -> None:
    with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3"):
        with ui.row().classes("w-full items-start gap-10"):
            _fait("Établissement", NOM_ETABLISSEMENT)
            with ui.column().classes("gap-0"):
                ui.label("Taxe de séjour").classes("text-xs text-ardoise")
                ui.label(format_euros(TAXE_SEJOUR_CENTIMES)).classes("text-sm font-semibold")
                ui.label("par adulte et par nuit").classes("text-xs text-ardoise")
            _fait("Devise", "EUR")


def _fait(titre: str, valeur: str) -> None:
    with ui.column().classes("gap-0"):
        ui.label(titre).classes("text-xs text-ardoise")
        ui.label(valeur).classes("text-sm font-semibold")
