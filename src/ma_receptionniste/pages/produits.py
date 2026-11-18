from nicegui import run, ui

from ma_receptionniste.consultations import lister_produits
from ma_receptionniste.facturation import centimes, format_euros
from ma_receptionniste.models import Produit
from ma_receptionniste.pages.layout import badge, etat_vide, page
from ma_receptionniste.saisie import (
    TAUX_TVA_DEFAUT,
    TAUX_TVA_POUR_MILLE,
    ProduitInvalide,
    creer_produit,
    definir_produit_actif,
    modifier_produit,
)

_COLONNES = "grid-template-columns: minmax(12rem, 1fr) 8rem 6rem 6rem 7rem 14rem;"
_ENTETE = "px-4 py-2 text-xs font-semibold text-ardoise"
_CELLULE = "px-4 h-11 flex items-center"
_ESPACE_FINE = "\u202f"


def _euros(montant: int) -> float:
    return montant / 100


def _champ_prix(libelle: str) -> ui.number:
    champ = ui.number(libelle, min=0, step=0.01, precision=2, format="%.2f")
    champ.props["suffix"] = "€"
    return champ


def _prix_saisi(valeur: float | None) -> int | None:
    if valeur is None:
        return None
    try:
        return centimes(valeur)
    except (ArithmeticError, ValueError):
        return None


def _libelle_taux(pour_mille: int) -> str:
    entier, dixieme = divmod(pour_mille, 10)
    texte = f"{entier},{dixieme}" if dixieme else str(entier)
    return f"{texte}{_ESPACE_FINE}%"


def _champ_tva(valeur: int = TAUX_TVA_DEFAUT) -> ui.select:
    return ui.select(
        {taux: _libelle_taux(taux) for taux in TAUX_TVA_POUR_MILLE},
        label="TVA",
        value=valeur,
    ).classes("w-28")


def _taux_saisi(valeur: int | None) -> int | None:
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        return None
    return valeur


@ui.page("/produits")
async def produits() -> None:
    catalogue = await run.io_bound(lister_produits)
    texte = ""
    ecriture = False
    produit_edite: int | None = None

    def correspondants() -> list[Produit]:
        requete = " ".join(texte.casefold().split())
        if not requete:
            return list(catalogue)
        return [produit for produit in catalogue if requete in produit.nom.casefold()]

    def phrase(nombre: int) -> str:
        if nombre == 0:
            return "Aucun produit"
        if nombre == 1:
            return "1 produit"
        return f"{nombre} produits"

    @ui.refreshable
    def tableau() -> None:
        lignes = correspondants()
        compteur.set_text(phrase(len(lignes)))
        if not lignes:
            message = (
                "Aucun produit. Ajoutez-en un avec le formulaire ci-dessus."
                if not catalogue
                else "Aucun produit ne correspond."
            )
            etat_vide("inventory_2" if not catalogue else "search_off", message)
            return
        with ui.element("div").classes("grid w-full border-b border-slate-200").style(_COLONNES):
            for titre, classes in (
                ("Nom", ""),
                ("Prix TTC", " justify-end"),
                ("TVA", " justify-end"),
                ("Ponctuel", ""),
                ("État", ""),
                ("", ""),
            ):
                ui.label(titre).classes(_ENTETE + classes)
        for produit in lignes:
            _ligne(produit)

    def _ligne(produit: Produit) -> None:
        def modifier_celui_ci(produit: Produit = produit) -> None:
            ouvrir_edition(produit)

        async def basculer_celui_ci(produit: Produit = produit) -> None:
            await basculer(produit.id, not produit.actif)

        with ui.element("div").classes("grid w-full items-center border-b border-slate-100 text-sm").style(
            _COLONNES
        ).mark(f"ligne-produit-{produit.id}"):
            ui.label(produit.nom).classes(_CELLULE).mark(f"nom-produit-{produit.id}")
            ui.label(format_euros(produit.prix_unitaire_centimes)).classes(f"{_CELLULE} justify-end tabular-nums")
            ui.label(_libelle_taux(produit.taux_tva_pour_mille)).classes(f"{_CELLULE} justify-end tabular-nums").mark(
                f"tva-produit-{produit.id}"
            )
            ui.label("Oui" if produit.ponctuel else "—").classes(_CELLULE).mark(f"ponctuel-etat-{produit.id}")
            with ui.element("div").classes(_CELLULE):
                if produit.actif:
                    badge("Actif", "positive")
                else:
                    badge("Inactif", "ardoise")
            with ui.element("div").classes(f"{_CELLULE} justify-end gap-1"):
                ui.button("Modifier", on_click=modifier_celui_ci).props("flat dense color=primary").mark(
                    f"modifier-produit-{produit.id}"
                )
                ui.button(
                    "Réactiver" if not produit.actif else "Désactiver",
                    on_click=basculer_celui_ci,
                ).props("flat dense color=ardoise").mark(f"actif-produit-{produit.id}")

    async def recharger_catalogue() -> None:
        nonlocal catalogue
        produits_lus = await run.io_bound(lister_produits)
        if produits_lus is None:
            return
        catalogue = produits_lus
        await tableau.refresh()

    async def filtrer(evenement) -> None:
        nonlocal texte
        texte = evenement.value or ""
        await tableau.refresh()

    def ouvrir_edition(produit: Produit) -> None:
        nonlocal produit_edite
        produit_edite = produit.id
        nom_edition.set_value(produit.nom)
        prix_edition.set_value(_euros(produit.prix_unitaire_centimes))
        tva_edition.set_value(produit.taux_tva_pour_mille)
        ponctuel_edition.set_value(bool(produit.ponctuel))
        dialogue.open()

    async def ajouter() -> None:
        nonlocal ecriture
        if ecriture:
            return
        if not (nom.value or "").strip():
            ui.notify("Le nom est obligatoire", type="warning")
            return
        montant = _prix_saisi(prix.value)
        if montant is None:
            ui.notify("Le prix est obligatoire", type="warning")
            return
        taux = _taux_saisi(tva.value)
        if taux is None:
            ui.notify("Le taux de TVA est obligatoire", type="warning")
            return
        ecriture = True
        bouton_creer.disable()
        try:
            await run.io_bound(
                creer_produit, nom.value, montant, taux_tva_pour_mille=taux, ponctuel=bool(ponctuel.value)
            )
        except ProduitInvalide as erreur:
            ui.notify(str(erreur), type="warning")
        else:
            nom.set_value("")
            prix.set_value(None)
            tva.set_value(TAUX_TVA_DEFAUT)
            ponctuel.set_value(False)
            await recharger_catalogue()
            ui.notify("Produit ajouté", type="positive")
        finally:
            ecriture = False
            bouton_creer.enable()

    async def enregistrer() -> None:
        nonlocal ecriture
        if ecriture or produit_edite is None:
            return
        if not (nom_edition.value or "").strip():
            ui.notify("Le nom est obligatoire", type="warning")
            return
        montant = _prix_saisi(prix_edition.value)
        if montant is None:
            ui.notify("Le prix est obligatoire", type="warning")
            return
        taux = _taux_saisi(tva_edition.value)
        if taux is None:
            ui.notify("Le taux de TVA est obligatoire", type="warning")
            return
        ecriture = True
        bouton_enregistrer.disable()
        try:
            modifie = await run.io_bound(
                modifier_produit,
                produit_edite,
                nom_edition.value,
                montant,
                taux_tva_pour_mille=taux,
                ponctuel=bool(ponctuel_edition.value),
            )
        except ProduitInvalide as erreur:
            ui.notify(str(erreur), type="warning")
        else:
            dialogue.close()
            await recharger_catalogue()
            if modifie:
                ui.notify("Produit modifié", type="positive")
        finally:
            ecriture = False
            bouton_enregistrer.enable()

    async def basculer(produit_id: int, actif: bool) -> None:
        nonlocal ecriture
        if ecriture:
            return
        ecriture = True
        try:
            modifie = await run.io_bound(definir_produit_actif, produit_id, actif)
        except ProduitInvalide as erreur:
            await recharger_catalogue()
            ui.notify(str(erreur), type="warning")
        else:
            await recharger_catalogue()
            if modifie:
                ui.notify("Produit réactivé" if actif else "Produit désactivé", type="positive")
        finally:
            ecriture = False

    with page("/produits", "Produits"):
        with ui.dialog() as dialogue, ui.card().classes("w-[28rem] gap-3 p-5"):
            ui.label("Modifier le produit").classes("text-base font-semibold")
            nom_edition = ui.input("Nom").mark("nom-edition")
            prix_edition = _champ_prix("Prix TTC").mark("prix-edition")
            tva_edition = _champ_tva().mark("tva-edition")
            ponctuel_edition = ui.checkbox("Ponctuel").mark("ponctuel-edition")
            with ui.row().classes("w-full justify-end gap-2 pt-2"):
                ui.button("Annuler", on_click=dialogue.close).props("flat color=ardoise")
                bouton_enregistrer = ui.button("Enregistrer", on_click=enregistrer).mark("enregistrer-produit")
        with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3 gap-3"):
            ui.label("Nouveau produit").classes("text-sm font-semibold")
            with ui.row().classes("w-full items-end gap-3"):
                nom = ui.input("Nom").classes("w-80").mark("nom-produit")
                prix = _champ_prix("Prix TTC").classes("w-36").mark("prix-produit")
                tva = _champ_tva().mark("tva-produit")
                ponctuel = ui.checkbox("Ponctuel").mark("ponctuel-produit")
                bouton_creer = ui.button("Ajouter le produit", icon="add", on_click=ajouter).mark("creer-produit")
        with ui.card().props("flat bordered").classes("w-full rounded-lg p-0 gap-0 overflow-x-auto"):
            with ui.row().classes("w-full items-center justify-between px-4 py-3 border-b border-slate-200"):
                compteur = ui.label().classes("text-sm text-ardoise")
                recherche = (
                    ui.input(placeholder="Rechercher un produit…")
                    .props("clearable")
                    .classes("w-96")
                    .on_value_change(filtrer)
                    .mark("recherche-produit")
                )
                with recherche.add_slot("prepend"):
                    ui.icon("search", size="1.1rem")
            tableau()
