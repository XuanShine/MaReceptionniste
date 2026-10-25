from datetime import date

from nicegui import run, ui

from ma_gouvernante.actions import etat_chambre, fiche, statut
from ma_gouvernante.garde import acteur_courant
from ma_gouvernante.menage import (
    COULEUR_STATUT,
    LIBELLE_ETAT,
    LIBELLE_STATUT,
    Action,
    ChambreInconnue,
    DroitRefuse,
    EtatChambre,
    EtatInvalide,
    FicheChambre,
    StatutMenage,
    autorise,
    libelle_statut,
    libelle_type,
)
from ma_gouvernante.pages.layout import badge, etat_vide, page, refuser
from ma_receptionniste.pages.theme import date_courte, date_heure, date_longue


@ui.page("/chambres/{chambre_id}")
async def page_fiche(chambre_id: int) -> None:
    acteur = acteur_courant()
    if refuser(acteur):
        return
    assert acteur is not None
    aujourd_hui = date.today()
    try:
        donnees = await run.io_bound(fiche, acteur, chambre_id, aujourd_hui)
    except ChambreInconnue:
        with page("/chambres", "Chambre", acteur):
            etat_vide("bed", "Cette chambre n'existe pas.", "Retour aux chambres", "/chambres")
        return

    peut_gerer = autorise(acteur, Action.gerer_chambres)
    peut_statut = autorise(acteur, Action.changer_statut)

    @ui.refreshable
    async def contenu() -> None:
        fiche_chambre = await run.io_bound(fiche, acteur, chambre_id, aujourd_hui)
        _entete(acteur, fiche_chambre, peut_gerer, contenu)
        _menage(acteur, fiche_chambre, aujourd_hui, peut_statut, contenu)
        _historique(fiche_chambre)

    with page("/chambres", f"Chambre {donnees.nom}", acteur):
        ui.link("Chambres", "/chambres").classes("text-sm text-primary no-underline hover:underline")
        await contenu()


def _entete(acteur, fiche_chambre: FicheChambre, peut_gerer: bool, contenu) -> None:
    prete = fiche_chambre.etat == EtatChambre.pret.value
    with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-4 gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            with ui.column().classes("gap-1"):
                ui.label(fiche_chambre.nom).classes("text-3xl font-semibold tabular-nums leading-none")
                detail = fiche_chambre.type_chambre or "Type non renseigné"
                ui.label(f"Position {fiche_chambre.position} · {detail}").classes("text-sm text-ardoise")
            with ui.row().classes("items-center gap-2"):
                badge(LIBELLE_ETAT[EtatChambre(fiche_chambre.etat)], "positive" if prete else "warning")
                if not peut_gerer:
                    return

                async def basculer() -> None:
                    cible = EtatChambre.non_pret.value if prete else EtatChambre.pret.value
                    try:
                        await run.io_bound(etat_chambre, acteur, fiche_chambre.id, cible)
                    except (DroitRefuse, EtatInvalide, ChambreInconnue):
                        ui.notify("Changement d'état refusé", type="negative")
                        return
                    await contenu.refresh()

                ui.button("Marquer non prête" if prete else "Marquer prête", on_click=basculer).props(
                    "flat dense color=primary"
                )


def _menage(acteur, fiche_chambre: FicheChambre, jour: date, peut_statut: bool, contenu) -> None:
    with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-4 gap-3"):
        ui.label(f"Ménage du {date_longue(jour)}").classes("text-sm font-semibold first-letter:uppercase")
        menage = fiche_chambre.menage
        if menage is None:
            ui.label("Aucun ménage pour cette chambre aujourd'hui.").classes("text-sm text-ardoise")
            return
        with ui.row().classes("items-center gap-2"):
            ui.label(libelle_type(menage.type)).classes("text-base")
            badge(libelle_statut(menage.statut), COULEUR_STATUT.get(menage.statut, "ardoise"))
        if menage.notes:
            ui.label(menage.notes).classes("text-sm")
        if menage.cree_par:
            ui.label(f"Liste de {menage.cree_par}").classes("text-xs text-ardoise")
        if not peut_statut:
            return
        with ui.row().classes("gap-2"):
            for valeur in StatutMenage:
                _bouton_statut(acteur, menage.id, menage.statut, valeur, contenu)


def _bouton_statut(acteur, menage_id: int, statut_actuel: str, valeur: StatutMenage, contenu) -> None:
    courant = statut_actuel == valeur.value

    async def appliquer() -> None:
        try:
            await run.io_bound(statut, acteur, menage_id, valeur.value)
        except DroitRefuse:
            ui.notify("Vous ne pouvez pas changer ce statut", type="negative")
            return
        await contenu.refresh()

    bouton = ui.button(LIBELLE_STATUT[valeur], on_click=appliquer).props("dense no-caps color=primary")
    if not courant:
        bouton.props("flat")


def _historique(fiche_chambre: FicheChambre) -> None:
    with ui.column().classes("w-full gap-2"):
        ui.label("Historique").classes("text-sm font-semibold")
        if not fiche_chambre.historique:
            ui.label("Aucun changement de statut pour cette chambre.").classes("text-sm text-ardoise")
            return
        for ligne in fiche_chambre.historique:
            with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3 gap-2"):
                with ui.row().classes("w-full items-center justify-between no-wrap"):
                    with ui.row().classes("items-center gap-2"):
                        badge(libelle_statut(ligne.ancien), COULEUR_STATUT.get(ligne.ancien, "ardoise"))
                        ui.icon("arrow_forward", size="1rem").classes("text-ardoise")
                        badge(libelle_statut(ligne.nouveau), COULEUR_STATUT.get(ligne.nouveau, "ardoise"))
                    ui.label(date_heure(ligne.quand)).classes("text-xs text-ardoise tabular-nums")
                ui.label(f"{ligne.auteur} · ménage du {date_courte(ligne.date)}").classes("text-xs text-ardoise")
