from asyncio import Lock
from datetime import date, timedelta

from fastapi.responses import RedirectResponse
from nicegui import app, run, ui
from sqlalchemy.exc import IntegrityError

from ma_receptionniste.consultations import ecran_parametres
from ma_receptionniste.disponibilites import disponibilites_par_type, matrice_disponibilites
from ma_receptionniste.facturation import TAXE_SEJOUR_CENTIMES, format_euros
from ma_receptionniste.pages.composants.facture import carte_identite_hotel
from ma_receptionniste.pages.layout import CHEMIN_PARAMETRES, NOM_ETABLISSEMENT, badge, etat_vide, page
from ma_receptionniste.saisie import (
    CatalogueInvalide,
    attribuer_chambres_virtuelles,
    attribuer_occupation_chambre,
    attribuer_type_chambre,
    basculer_etat,
    creer_chambre,
    creer_chambre_virtuelle,
    creer_occupation_chambre,
    enregistrer_chambre_virtuelle,
    enregistrer_type_chambre,
    modifier_etage_chambre,
    modifier_occupation_chambre,
    supprimer_chambre_virtuelle,
    supprimer_occupation_chambre,
    supprimer_type_chambre,
)
from ma_receptionniste.wubook import ImportWubookImpossible, mettre_a_jour_types_wubook

_AVERTISSEMENTS = frozenset(
    {
        "Le libellé est obligatoire",
        "Le nom raccourci est obligatoire",
        "Le nom raccourci tient sur 4 caractères",
        "Le prix est obligatoire",
        "Le prix ne peut pas être négatif",
        "Le nombre de personnes doit être au moins 1",
        "Le type de lits est obligatoire",
        "L'étage doit être un nombre entier",
    }
)
_CHAMP = "borderless dense hide-bottom-space"
_CHAMP_CLASSES = "w-full rounded px-2 hover:bg-slate-100 focus-within:bg-slate-100"
_ENTETE = "px-4 py-2 text-xs font-semibold text-ardoise border-b border-slate-200"
_CELLULE = "px-4 h-11 flex items-center border-b border-slate-100"
_COLONNES_TYPES = "grid-template-columns: minmax(10rem, 1fr) minmax(12rem, 1fr) 7rem 7rem 9rem 8rem 8rem 11rem 12rem;"
_COLONNES_OCCUPATIONS = "grid-template-columns: 8rem 1fr 8rem;"
_COLONNES_CHAMBRES = "grid-template-columns: 5rem 8rem 6rem 1fr 1.5fr 1fr 9rem 11rem;"


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


def _options_virtuelles(virtuelles: list[dict]) -> dict[int, str]:
    return {ligne["id"]: ligne["nom_raccourci"] for ligne in virtuelles}


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
    disponibilites: dict[int, ui.label] = {}
    verrou_disponibilites = Lock()

    async def actualiser_disponibilites() -> None:
        async with verrou_disponibilites:
            jour = date.today()
            matrice = await run.io_bound(matrice_disponibilites, jour, jour + timedelta(days=1))
            if matrice is None:
                return
            totaux = disponibilites_par_type(matrice)
            par_type = {
                type_["id"]: valeurs[0] for type_, valeurs in zip(totaux["types"], totaux["valeurs"], strict=True)
            }
            for type_id, label in disponibilites.items():
                label.set_text(str(par_type[type_id]) if type_id in par_type else "—")

    @ui.refreshable
    async def corps() -> None:
        ecran = await run.io_bound(ecran_parametres)
        options_types = _options_types(ecran["types"])
        options_occupations = _options_occupations(ecran["occupations"])
        options_virtuelles = _options_virtuelles(ecran["virtuelles"])
        type_nouvelle.set_options(options_types, value=_conserver(type_nouvelle.value, options_types))
        occupation_nouvelle.set_options(
            options_occupations, value=_conserver(occupation_nouvelle.value, options_occupations)
        )
        virtuelles_nouvelle.set_options(
            options_virtuelles, value=[valeur for valeur in virtuelles_nouvelle.value if valeur in options_virtuelles]
        )
        position.value = ecran["position"]
        for slot in (slot_types, slot_occupations, slot_chambres):
            slot.clear()
        disponibilites.clear()
        with slot_types:
            _types(ecran["types"])
        with slot_occupations:
            _occupations(ecran["occupations"])
        with slot_chambres:
            _chambres(ecran)
        await actualiser_disponibilites()

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
        with ui.card().props("flat bordered").classes("w-full rounded-lg p-0 gap-0 overflow-x-auto"):
            if not types:
                etat_vide("category", "Aucun type. Importez les types de chambres de Wubook avec le bouton ci-dessus.")
                return
            with ui.element("div").classes("grid w-full min-w-[94rem] text-sm").style(_COLONNES_TYPES):
                for titre, classes in (
                    ("Libellé", ""),
                    ("Description", ""),
                    ("wubook_id", ""),
                    ("Raccourci", ""),
                    ("Disponibles aujourd’hui", ""),
                    ("Prix", ""),
                    ("Prix mini", ""),
                    ("Channel Manager", " text-center"),
                    ("", ""),
                ):
                    ui.label(titre).classes(_ENTETE + classes)
                for ligne in types:
                    _ligne_type(ligne)

    def _ligne_type(ligne: dict) -> None:
        with ui.element("div").classes(_CELLULE):
            libelle = ui.input(value=ligne["libelle"]).props(_CHAMP, remove="outlined").classes(_CHAMP_CLASSES)
        with ui.element("div").classes(_CELLULE):
            description = (
                ui.input(value=ligne["description"], placeholder="Description")
                .props(_CHAMP, remove="outlined")
                .classes(_CHAMP_CLASSES)
                .mark(f"description-type-{ligne['id']}")
            )
        ui.label(str(ligne["wubook_id"]) if ligne["wubook_id"] is not None else "—").classes(
            f"{_CELLULE} tabular-nums text-ardoise"
        )
        with ui.element("div").classes(_CELLULE):
            raccourci = (
                ui.input(value=ligne["nom_raccourci"] or "")
                .props(f"{_CHAMP} maxlength=4", remove="outlined")
                .classes(_CHAMP_CLASSES)
            )
        disponibilites[ligne["id"]] = (
            ui.label("—").classes(f"{_CELLULE} tabular-nums").mark(f"disponibilite-type-{ligne['id']}")
        )
        with ui.element("div").classes(_CELLULE):
            prix = _prix(ligne["prix_defaut"])
        with ui.element("div").classes(_CELLULE):
            mini = _prix(ligne["prix_mini"])
        with ui.element("div").classes(f"{_CELLULE} justify-center"):
            channel = ui.checkbox(value=ligne["channel_manager_uniquement"]).props("dense")

        async def enregistrer() -> None:
            if _type_inchange(
                ligne, libelle.value, raccourci.value, prix.value, mini.value, channel.value, description.value
            ):
                return
            await _sauver(
                lambda: run.io_bound(
                    enregistrer_type_chambre,
                    ligne["id"],
                    libelle.value or "",
                    raccourci.value or "",
                    float(prix.value or 0),
                    float(mini.value or 0),
                    bool(channel.value),
                    description=description.value or "",
                ),
                "Type enregistré",
            )

        for champ in (libelle, description, raccourci, prix, mini):
            champ.on("blur", enregistrer).on("keydown.enter", enregistrer)
        channel.on_value_change(enregistrer)

        async def supprimer() -> None:
            await _sauver(lambda: run.io_bound(supprimer_type_chambre, ligne["id"]), None)

        with ui.element("div").classes(f"{_CELLULE} justify-end gap-1 no-wrap"):
            _menu_virtuelles(ligne)
            ui.button("Supprimer", on_click=supprimer).props("flat dense color=negative")

    def _menu_virtuelles(ligne: dict) -> None:
        fleche = ui.button(icon="chevron_right").props("flat round dense").classes("text-ardoise")
        with fleche:
            menu = ui.menu().mark(f"virtuelles-{ligne['id']}")
            menu.props["auto-close"] = False
            with menu:
                with ui.column().classes("p-3 gap-2"):
                    with ui.row().classes("items-end gap-2 px-1 text-xs font-semibold text-ardoise no-wrap"):
                        ui.label("wubook_id").classes("w-24")
                        ui.label("Raccourci").classes("w-24")
                        ui.label("Description").classes("w-64")
                        ui.label("Prix").classes("w-32")
                        ui.label("Prix mini").classes("w-32")
                    for virtuelle in ligne["virtuelles"]:
                        _ligne_virtuelle(virtuelle)
                    _ajout_virtuelle(ligne["id"])

        def ouvrir() -> None:
            fleche.props("icon=expand_more")

        def fermer() -> None:
            fleche.props("icon=chevron_right")

        menu.on("show", ouvrir)
        menu.on("hide", fermer)

    def _ligne_virtuelle(virtuelle: dict) -> None:
        with ui.row().classes("items-center gap-2 no-wrap"):
            ui.label(str(virtuelle["wubook_id"]) if virtuelle["wubook_id"] is not None else "—").classes(
                "w-24 tabular-nums text-ardoise"
            )
            raccourci = _champ_raccourci(virtuelle["nom_raccourci"])
            description = (
                ui.input(value=virtuelle["description"], placeholder="Description")
                .props("dense")
                .classes("w-64")
                .mark(f"description-virtuelle-{virtuelle['id']}")
            )
            prix = _champ_prix(virtuelle["prix_defaut"])
            mini = _champ_prix(virtuelle["prix_mini"])

            async def enregistrer() -> None:
                if _virtuelle_inchangee(virtuelle, raccourci.value, prix.value, mini.value, description.value):
                    return
                await _sauver(
                    lambda: run.io_bound(
                        enregistrer_chambre_virtuelle,
                        virtuelle["id"],
                        raccourci.value or "",
                        _prix_saisi(prix.value),
                        _prix_saisi(mini.value),
                        description=description.value or "",
                    ),
                    "Chambre virtuelle enregistrée",
                )

            for champ in (raccourci, description, prix, mini):
                champ.on("blur", enregistrer).on("keydown.enter", enregistrer)

            async def supprimer() -> None:
                await _sauver(lambda: run.io_bound(supprimer_chambre_virtuelle, virtuelle["id"]), None)

            ui.button("Supprimer", on_click=supprimer).props("flat dense color=negative")

    def _ajout_virtuelle(type_chambre_id: int) -> None:
        with ui.row().classes("items-center gap-2 no-wrap").mark(f"ajout-virtuelle-{type_chambre_id}"):
            ui.element("div").classes("w-24")
            raccourci = _champ_raccourci("").mark("raccourci")
            description = (
                ui.input(placeholder="Description")
                .props("dense")
                .classes("w-64")
                .mark(f"description-nouvelle-virtuelle-{type_chambre_id}")
            )
            prix = _champ_prix(None).mark("prix")
            mini = _champ_prix(None).mark("prix-mini")

            async def ajouter() -> None:
                try:
                    virtuelle_id = await run.io_bound(
                        creer_chambre_virtuelle,
                        type_chambre_id,
                        raccourci.value or "",
                        _prix_saisi(prix.value),
                        _prix_saisi(mini.value),
                        description=description.value or "",
                    )
                except CatalogueInvalide as erreur:
                    ui.notify(str(erreur), type=_ton(str(erreur)))
                    return
                if virtuelle_id is None:
                    return
                ui.notify("Chambre virtuelle ajoutée", type="positive")
                await corps.refresh()

            for champ in (raccourci, description, prix, mini):
                champ.on("keydown.enter", ajouter)
            ui.button("Ajouter une chambre virtuelle", icon="add", on_click=ajouter).props("flat dense")

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
            lits = ui.input(value=ligne["type_lits"]).props(_CHAMP, remove="outlined").classes(_CHAMP_CLASSES)

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
        with ui.card().props("flat bordered").classes("w-full rounded-lg p-0 gap-0 overflow-x-auto"):
            if not chambres:
                etat_vide("bed", "Aucune chambre. Ajoutez la première avec le formulaire ci-dessus.")
                return
            options_types = _options_types(ecran["types"])
            options_occupations = _options_occupations(ecran["occupations"])
            options_virtuelles = _options_virtuelles(ecran["virtuelles"])
            with ui.element("div").classes("grid w-full min-w-[75rem] text-sm").style(_COLONNES_CHAMBRES):
                for titre in ("Position", "Chambre", "Étage", "Type", "Chambres virtuelles", "Occupation", "État", ""):
                    ui.label(titre).classes(_ENTETE)
                for chambre in chambres:
                    _ligne_chambre(chambre, options_types, options_occupations, options_virtuelles)

    def _ligne_chambre(chambre: dict, options_types: dict, options_occupations: dict, options_virtuelles: dict) -> None:
        prete = chambre["etat"] == "pret"
        ui.label(str(chambre["position"])).classes(f"{_CELLULE} tabular-nums text-ardoise")
        ui.label(chambre["nom"]).classes(f"{_CELLULE} font-semibold tabular-nums")
        with ui.element("div").classes(_CELLULE):
            etage = (
                ui.number(value=chambre["etage"], precision=0, step=1)
                .props(_CHAMP, remove="outlined")
                .classes(_CHAMP_CLASSES)
                .mark(f"etage-chambre-{chambre['id']}")
            )

        async def changer_etage() -> None:
            if etage.value == chambre["etage"]:
                return
            await _sauver(
                lambda: run.io_bound(modifier_etage_chambre, chambre["id"], etage.value),
                "Étage enregistré",
            )

        etage.on("blur", changer_etage).on("keydown.enter", changer_etage)
        with ui.element("div").classes(_CELLULE):
            select_type = (
                ui.select(
                    _avec_choix(options_types, chambre["type_chambre_id"], chambre["type_chambre"]),
                    value=chambre["type_chambre_id"],
                )
                .props("dense options-dense borderless", remove="outlined")
                .classes("w-full")
                .mark(f"type-chambre-{chambre['id']}")
            )

        async def changer_type() -> None:
            await _sauver(
                lambda: run.io_bound(attribuer_type_chambre, chambre["id"], _lien(select_type.value)),
                "Type enregistré",
            )

        select_type.on_value_change(changer_type)
        with ui.element("div").classes(_CELLULE.replace("h-11", "min-h-11")):
            select_virtuelles = (
                ui.select(options_virtuelles, value=chambre["chambres_virtuelles_ids"], multiple=True)
                .props("dense options-dense borderless use-chips", remove="outlined")
                .classes("w-full")
                .mark(f"virtuelles-chambre-{chambre['id']}")
            )

        async def changer_virtuelles() -> None:
            await _sauver(
                lambda: run.io_bound(
                    attribuer_chambres_virtuelles, chambre["id"], [int(valeur) for valeur in select_virtuelles.value]
                ),
                "Chambres virtuelles enregistrées",
            )

        select_virtuelles.on_value_change(changer_virtuelles)
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

    async def importer_types() -> None:
        if not bouton_import.enabled:
            return
        bouton_import.disable()
        bouton_confirmer.disable()
        bouton_confirmer.props("loading")
        try:
            resultat = await run.io_bound(mettre_a_jour_types_wubook)
            if resultat is None:
                return
            nombre_types, nombre_virtuelles = resultat
            confirmation_import.close()
            type_nouvelle.set_value(None)
            await corps.refresh()
            ui.notify(
                f"{nombre_types} types de chambres et {nombre_virtuelles} chambres virtuelles importés",
                type="positive",
            )
        except ImportWubookImpossible as erreur:
            ui.notify(str(erreur), type="negative")
        finally:
            bouton_confirmer.props(remove="loading")
            bouton_confirmer.enable()
            bouton_import.enable()

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
                etage=etage_nouveau.value,
                chambres_virtuelles_ids=[int(valeur) for valeur in virtuelles_nouvelle.value],
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
        etage_nouveau.value = 0
        type_nouvelle.value = None
        occupation_nouvelle.value = None
        virtuelles_nouvelle.value = []
        await corps.refresh()
        ui.notify("Chambre ajoutée", type="positive")

    with page(CHEMIN_PARAMETRES, "Paramètres"):
        _bandeau()
        await carte_identite_hotel()
        with ui.column().classes("w-full gap-3"):
            with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3 gap-3"):
                ui.label("Types de chambre").classes("text-sm font-semibold")
                ui.label(
                    "La mise à jour remplace tous les types et toutes les chambres virtuelles par les données Wubook."
                ).classes("text-sm text-ardoise")
                with ui.dialog().props("persistent") as confirmation_import, ui.card().classes("max-w-xl"):
                    ui.label("Remplacer le catalogue local ?").classes("text-lg font-semibold")
                    ui.label(
                        "Les types de chambres et les chambres virtuelles existants seront supprimés puis "
                        "remplacés par ceux de Wubook. Les modifications locales seront écrasées."
                    )
                    ui.label(
                        "Les chambres physiques sont conservées. Leurs affectations sont rétablies par wubook_id ; "
                        "un type absent de Wubook ou sans wubook_id sera désaffecté."
                    )
                    ui.label(
                        "Les affectations des chambres virtuelles sont rétablies par wubook_id ; "
                        "celles absentes de Wubook ou sans wubook_id seront désaffectées."
                    )
                    with ui.row().classes("w-full justify-end"):
                        ui.button("Annuler", on_click=confirmation_import.close).props("flat")
                        bouton_confirmer = ui.button("Remplacer et importer", on_click=importer_types)
                bouton_import = ui.button(
                    "Mettre à jour les types de chambres de Wubook", icon="sync", on_click=confirmation_import.open
                )
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
                with ui.row().classes("w-full items-start gap-3").mark("ajout-chambre"):
                    nom = ui.input("Nom ou numéro *").classes("w-48").on("keydown.enter", ajouter_chambre)
                    type_nouvelle = ui.select({None: "Aucune"}, label="Type", value=None).classes("w-56")
                    virtuelles_nouvelle = (
                        ui.select({}, label="Chambres virtuelles", value=[], multiple=True)
                        .props("use-chips")
                        .classes("w-56")
                        .mark("virtuelles-nouvelle-chambre")
                    )
                    occupation_nouvelle = ui.select({None: "Aucune"}, label="Occupation", value=None).classes("w-56")
                    position = ui.number("Position", value=1, min=0, precision=0).classes("w-32")
                    etage_nouveau = (
                        ui.number("Étage", value=0, precision=0, step=1).classes("w-24").mark("etage-nouvelle-chambre")
                    )
                    ui.button("Ajouter", icon="add", on_click=ajouter_chambre).classes("mt-0.5")
            slot_chambres = ui.column().classes("w-full")
        await corps()
        ui.timer(30, actualiser_disponibilites, immediate=False).mark("actualisation-disponibilites")


def _champ_raccourci(valeur: str) -> ui.input:
    return ui.input(value=valeur).props("dense maxlength=4").classes("w-24")


def _champ_prix(valeur: float | None) -> ui.number:
    return (
        ui.number(value=valeur, min=0, precision=2, step=0.01, format="%.2f", suffix="€").props("dense").classes("w-32")
    )


def _prix_saisi(valeur: float | None) -> float | None:
    if valeur is None or valeur == "":
        return None
    return float(valeur)


def _virtuelle_inchangee(
    ligne: dict, raccourci: str | None, prix: float | None, mini: float | None, description: str | None
) -> bool:
    saisi, saisi_mini = _prix_saisi(prix), _prix_saisi(mini)
    return (
        (raccourci or "").strip() == ligne["nom_raccourci"]
        and (description or "").strip() == ligne["description"]
        and saisi is not None
        and saisi_mini is not None
        and round(saisi, 2) == round(float(ligne["prix_defaut"]), 2)
        and round(saisi_mini, 2) == round(float(ligne["prix_mini"]), 2)
    )


def _prix(valeur: float) -> ui.number:
    return (
        ui.number(value=valeur, min=0, precision=2, step=0.01, format="%.2f", suffix="€")
        .props(_CHAMP, remove="outlined")
        .classes(_CHAMP_CLASSES)
    )


def _type_inchange(
    ligne: dict,
    libelle: str | None,
    raccourci: str | None,
    prix: float | None,
    mini: float | None,
    channel: bool | None,
    description: str | None,
) -> bool:
    return (
        (libelle or "").strip() == ligne["libelle"]
        and (description or "").strip() == ligne["description"]
        and ((raccourci or "").strip() or None) == ligne["nom_raccourci"]
        and round(float(prix or 0), 2) == round(float(ligne["prix_defaut"]), 2)
        and round(float(mini or 0), 2) == round(float(ligne["prix_mini"]), 2)
        and bool(channel) == ligne["channel_manager_uniquement"]
    )


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
