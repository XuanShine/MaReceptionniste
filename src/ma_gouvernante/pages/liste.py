from datetime import date, timedelta

from nicegui import run, ui

from ma_gouvernante.actions import chambres, liste, poser, retirer, statut
from ma_gouvernante.garde import acteur_courant
from ma_gouvernante.menage import (
    COULEUR_STATUT,
    LIBELLE_STATUT,
    LIBELLE_TYPE,
    Acteur,
    Action,
    ChambreInconnue,
    DroitRefuse,
    LigneMenage,
    StatutMenage,
    TypeMenage,
    TypeMenageInvalide,
    autorise,
    jour_depuis,
    libelle_statut,
    libelle_type,
)
from ma_gouvernante.pages.layout import badge, etat_vide, page, refuser
from ma_receptionniste.pages.theme import date_longue


def _iso(jour: date) -> str:
    return jour.isoformat()


@ui.page("/")
async def menage_du_jour(jour: str = "") -> None:
    acteur = acteur_courant()
    if refuser(acteur):
        return
    assert acteur is not None
    jour_courant = jour_depuis(jour)
    peut_editer = autorise(acteur, Action.editer_liste)
    peut_statut = autorise(acteur, Action.changer_statut)
    peut_retirer_avance = autorise(acteur, Action.retirer_en_cours)
    chambres_hotel = await run.io_bound(chambres, acteur)

    def aller(cible: date) -> None:
        ui.navigate.to(f"/?jour={_iso(cible)}")

    @ui.refreshable
    async def tableau() -> None:
        lignes = await run.io_bound(liste, acteur, jour_courant)
        compte = {valeur.value: sum(ligne.statut == valeur.value for ligne in lignes) for valeur in StatutMenage}
        with ui.row().classes("w-full gap-2"):
            for valeur in StatutMenage:
                badge(f"{LIBELLE_STATUT[valeur]} {compte[valeur.value]}", COULEUR_STATUT[valeur.value])
        if not lignes:
            etat_vide("mop", "Aucun ménage pour cette journée.")
            return
        for ligne in lignes:
            _carte_menage(acteur, ligne, jour_courant, peut_editer, peut_statut, peut_retirer_avance, tableau)

    with page("/", "Ménage", acteur):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label(date_longue(jour_courant)).classes("text-base text-ardoise first-letter:uppercase")
            with ui.row().classes("items-center gap-2"):
                ui.button("Veille", on_click=lambda: aller(jour_courant - timedelta(days=1))).props(
                    "flat dense color=ardoise"
                )
                ui.button("Aujourd'hui", on_click=lambda: aller(date.today())).props("flat dense color=primary")
                ui.button("Lendemain", on_click=lambda: aller(jour_courant + timedelta(days=1))).props(
                    "flat dense color=ardoise"
                )
        if peut_editer:
            _formulaire(acteur, jour_courant, chambres_hotel, tableau)
        await tableau()


def _formulaire(acteur: Acteur, jour: date, chambres_hotel, tableau) -> None:
    with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3 gap-3"):
        ui.label("Ajouter à la liste").classes("text-sm font-semibold")
        if not chambres_hotel:
            ui.label("Aucune chambre. Un admin doit d'abord en créer.").classes("text-sm text-ardoise")
            return
        options = {chambre.id: chambre.nom for chambre in chambres_hotel}
        with ui.row().classes("w-full items-end gap-3"):
            chambre = ui.select(options, label="Chambre", value=next(iter(options))).classes("w-36")
            type_menage = ui.select(
                {valeur.value: LIBELLE_TYPE[valeur] for valeur in TypeMenage},
                label="Type",
                value=TypeMenage.DEPART.value,
            ).classes("w-40")
            notes = ui.input("Notes").classes("flex-1")

            async def ajouter() -> None:
                if chambre.value is None:
                    ui.notify("Choisissez une chambre", type="warning")
                    return
                try:
                    await run.io_bound(poser, acteur, jour, int(chambre.value), type_menage.value, notes.value)
                except DroitRefuse:
                    ui.notify("Vous ne pouvez pas modifier la liste", type="negative")
                    return
                except ChambreInconnue:
                    ui.notify("Chambre introuvable", type="negative")
                    return
                except TypeMenageInvalide:
                    ui.notify("Type de ménage inconnu", type="warning")
                    return
                notes.value = ""
                ui.notify("Ménage enregistré", type="positive")
                await tableau.refresh()

            notes.on("keydown.enter", ajouter)
            ui.button("Ajouter", icon="add", on_click=ajouter)


def _carte_menage(
    acteur: Acteur,
    ligne: LigneMenage,
    jour: date,
    peut_editer: bool,
    peut_statut: bool,
    peut_retirer_avance: bool,
    tableau,
) -> None:
    with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3 gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            with ui.row().classes("items-center gap-3"):
                ui.label(ligne.chambre).classes("text-lg font-semibold tabular-nums")
                badge(libelle_statut(ligne.statut), COULEUR_STATUT.get(ligne.statut, "ardoise"))
            if ligne.cree_par:
                ui.label(f"Liste de {ligne.cree_par}").classes("text-xs text-ardoise")
        if peut_editer:
            _edition(acteur, ligne, jour, peut_retirer_avance, tableau)
        else:
            ui.label(libelle_type(ligne.type)).classes("text-sm")
            if ligne.notes:
                ui.label(ligne.notes).classes("text-sm text-ardoise")
        if peut_statut:
            with ui.row().classes("gap-2"):
                for valeur in StatutMenage:
                    _bouton_statut(acteur, ligne, valeur, tableau)


def _edition(acteur: Acteur, ligne: LigneMenage, jour: date, peut_retirer_avance: bool, tableau) -> None:
    with ui.row().classes("w-full items-end gap-3"):
        type_menage = ui.select(
            {valeur.value: LIBELLE_TYPE[valeur] for valeur in TypeMenage},
            label="Type",
            value=ligne.type,
        ).classes("w-40")
        notes = ui.input("Notes", value=ligne.notes or "").classes("flex-1")

        async def enregistrer() -> None:
            try:
                await run.io_bound(poser, acteur, jour, ligne.chambre_id, type_menage.value, notes.value)
            except DroitRefuse:
                ui.notify("Vous ne pouvez pas modifier la liste", type="negative")
                return
            ui.notify(f"Chambre {ligne.chambre} mise à jour", type="positive")
            await tableau.refresh()

        ui.button("Enregistrer", on_click=enregistrer).props("flat dense color=primary")
        if ligne.statut == StatutMenage.a_faire.value or peut_retirer_avance:

            async def enlever() -> None:
                try:
                    await run.io_bound(retirer, acteur, ligne.id)
                except DroitRefuse:
                    ui.notify("Vous ne pouvez pas retirer ce ménage", type="negative")
                    return
                ui.notify(f"Chambre {ligne.chambre} retirée de la liste", type="positive")
                await tableau.refresh()

            ui.button("Retirer", on_click=enlever).props("flat dense color=negative")


def _bouton_statut(acteur: Acteur, ligne: LigneMenage, valeur: StatutMenage, tableau) -> None:
    courant = ligne.statut == valeur.value

    async def appliquer() -> None:
        try:
            await run.io_bound(statut, acteur, ligne.id, valeur.value)
        except DroitRefuse:
            ui.notify("Vous ne pouvez pas changer ce statut", type="negative")
            return
        await tableau.refresh()

    bouton = ui.button(LIBELLE_STATUT[valeur], on_click=appliquer).props("dense no-caps color=primary")
    if not courant:
        bouton.props("flat")
