import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from nicegui import app, background_tasks, run, ui

from ma_receptionniste.consommation_ponctuelle import (
    NoteIllisible,
    cle_chambre,
    incoherences,
    jours_du_sejour,
    lire,
    nom_chambre,
)
from ma_receptionniste.consommation_ponctuelle import (
    totaux as totaux_note,
)
from ma_receptionniste.consultations import (
    MODE_REGLEMENT_LABEL,
    STATUT_SEJOUR,
    fiche_sejour,
    libelle_client,
    lire_client,
    lister_chambres,
    lister_produits,
    options_chambres,
    rechercher_clients,
)
from ma_receptionniste.facturation import Totaux, centimes, format_euros, montant_ligne, nuits, taxe_sejour
from ma_receptionniste.models import Client, ModeReglement, Reservation, StatutReservation
from ma_receptionniste.pages.clients import PAYS_COURANTS
from ma_receptionniste.pages.composants.facture import enregistrer_route_pdf, ouvrir_facturation
from ma_receptionniste.pages.layout import ACTIF_DETAIL, badge, etat_vide, fermer_reservation, ouvrir_reservation, page
from ma_receptionniste.pages.theme import JOURS, date_courte, date_heure, heure_locale
from ma_receptionniste.saisie import (
    CHAMPS_CLIENT,
    CHAMPS_FICHE,
    NOM_CLIENT_PASSAGE,
    FicheInvalide,
    OperationPonctuelle,
    ProduitInvalide,
    ajouter_consommation_produit,
    ajouter_note,
    ajouter_reglement,
    ajouter_sejour,
    annuler_reservation,
    champs_modifies,
    creer_client,
    enregistrer_fiche,
    modifier_consommation,
    modifier_consommation_ponctuelle,
    modifier_sejour,
    reprendre_reservation,
    supprimer_sejour,
)
from ma_receptionniste.sejours import ChambreOccupee, SejourInvalide

enregistrer_route_pdf()

logger = logging.getLogger(__name__)

PARTENAIRES = ["Booking.com", "Expedia", "Airbnb", "Direct", "Téléphone", "Site web", "Agence de voyage"]
ONGLETS_TEXTE = ("notes", "notes_client", "facturation")
ONGLETS_COMPTES = {
    "reservations": "Réservations",
    "consommations": "Consommations",
    "reglements": "Règlements",
    "modifications": "Modifications",
}
OPTIONS_STATUT = {
    statut.value: STATUT_SEJOUR[statut].libelle
    for statut in (
        StatutReservation.option_devis,
        StatutReservation.confirmee,
        StatutReservation.en_cours,
        StatutReservation.parti,
    )
}
DEFAUTS_LIGNE = {"adultes": 1, "enfants": 0, "prix_nuit_centimes": 0, "nom_client": None}

A_DROITE = "text-right"
A_GAUCHE = "text-left"
COLONNES_LIGNES: tuple[tuple[str, Callable[[dict], str], str], ...] = (
    ("Type", lambda ligne: ligne["type_chambre"] or "—", A_GAUCHE),
    (
        "Chambre",
        lambda ligne: " · ".join(filter(None, (ligne["chambre_nom"], ligne["nom_client"]))),
        A_GAUCHE,
    ),
    ("Nb nuits", lambda ligne: str(ligne["nuits"]), A_DROITE),
    ("Début", lambda ligne: date_courte(ligne["date_debut"]), A_GAUCHE),
    ("Fin", lambda ligne: date_courte(ligne["date_fin"]), A_GAUCHE),
    ("Prix TTC/nuit", lambda ligne: format_euros(ligne["prix_nuit_centimes"]), A_DROITE),
    ("Adultes", lambda ligne: str(ligne["adultes"]), A_DROITE),
    ("Enfants", lambda ligne: str(ligne["enfants"]), A_DROITE),
    ("Taxe de séjour", lambda ligne: format_euros(ligne["taxe"]), A_DROITE),
    ("Montant", lambda ligne: format_euros(ligne["montant"]), f"{A_DROITE} font-semibold"),
)
GROUPES_LIGNES = ((None, 2), ("Période / Prix", 4), ("Occupation / Taxe", 3), (None, 1))
COLONNES_CONSOMMATIONS = (
    ("Date", A_GAUCHE),
    ("Libellé", f"{A_GAUCHE} w-full"),
    ("Qté", A_DROITE),
    ("PU TTC", A_DROITE),
    ("Montant", f"{A_DROITE} font-semibold"),
)
COLONNES_REGLEMENTS = (("Date", A_GAUCHE), ("Mode", f"{A_GAUCHE} w-full"), ("Montant", f"{A_DROITE} font-semibold"))
COLONNES_HISTORIQUE = (
    ("Date", A_GAUCHE),
    ("Auteur", A_GAUCHE),
    ("Description", f"{A_GAUCHE} w-full whitespace-pre-line!"),
)
OPTIONS_MODES = {mode.value: libelle for mode, libelle in MODE_REGLEMENT_LABEL.items()}

TH = "px-3 py-1.5 text-xs font-semibold text-ardoise bg-slate-50 border-b border-slate-200 whitespace-nowrap"
TD = "px-3 h-9 border-b border-slate-100 whitespace-nowrap tabular-nums"
PROPS_SAISIE = "dense borderless hide-bottom-space"

# ui.keyboard ne sait pas empêcher le navigateur d'ouvrir « Enregistrer la page » sur Ctrl+S.
# Échap abandonne la fiche, sauf si un dialogue, un menu ou la ligne en cours est ouvert.
RACCOURCIS = """
<script>
window.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault();
    emitEvent('fiche-confirmer');
  } else if (event.key === 'Escape' && !document.querySelector('.q-dialog, .q-menu, .ligne-ouverte')) {
    emitEvent('fiche-abandon');
  }
}, true);
</script>
"""


@dataclass
class BrouillonLigne:
    chambre: ui.select
    nom: ui.input
    arrivee: ui.date_input
    depart: ui.date_input
    adultes: ui.number
    enfants: ui.number
    prix: ui.number
    options: dict[int, str]
    types_chambres: dict[int, str | None]
    libelle_type: ui.label
    libelle_nuits: ui.label
    libelle_taxe: ui.label
    libelle_montant: ui.label


@ui.page("/reservations/{reservation_id}")
async def fiche(reservation_id: int) -> None:
    donnees = await run.io_bound(fiche_sejour, reservation_id)
    if donnees is None:
        fermer_reservation()
        with page("/reservations", "Fiche séjour"):
            etat_vide(
                "search_off",
                f"La réservation n° {reservation_id} n'existe pas.",
                "Voir les réservations",
                "/reservations",
            )
        return
    ouvrir_reservation(reservation_id)
    user_id = app.storage.user.get("user_id")
    enregistre = _champs(donnees)
    valeurs = {cle: _valeur_affichee(valeur) for cle, valeur in enregistre.items()}
    client_id = donnees["client"]["id"]
    client_nom = donnees["client"]["nom"]
    enregistre_client_id = client_id
    champs: dict[str, ui.element] = {}
    ouvrir_clients: list[Callable[[str], None]] = []
    brouillon: BrouillonLigne | None = None
    ajout_en_cours = False
    enregistrement_en_cours = False
    vente_en_cours = False
    ecriture_ponctuelle = False
    produits_vente = await run.io_bound(lister_produits, actifs_seulement=True) or []
    catalogue_complet = await run.io_bound(lister_produits) or []
    couples_ajoutes: set[tuple[str, str]] = set()
    nombres_choisis: dict[tuple[str, str], int] = {}
    onglet_ponctuel: list[ui.tab] = []
    champs_ponctuels: dict[str, ui.element] = {}

    def passage_selectionne() -> bool:
        return client_nom == NOM_CLIENT_PASSAGE

    def verrouiller_client() -> None:
        passage = passage_selectionne()
        for cle in CHAMPS_CLIENT:
            champ = champs.get(cle)
            if champ is not None:
                champ.set_enabled(not passage)

    def appliquer_client(client: dict) -> None:
        nonlocal client_id, client_nom
        client_id = client["id"]
        client_nom = client["nom"]
        for cle, source in (
            ("nom", "nom"),
            ("pays", "pays"),
            ("telephone", "telephone"),
            ("email", "email"),
            ("adresse", "adresse"),
            ("notes_client", "notes"),
        ):
            champs[cle].set_value(_valeur_affichee(client.get(source)))
        champs["identite"].set_text(_texte_client(client_nom, client_id))
        verrouiller_client()

    def fiche_modifiee() -> bool:
        return bool(champs_modifies(enregistre, valeurs)) or client_id != enregistre_client_id

    async def recharger() -> None:
        nonlocal donnees
        donnees = await run.io_bound(fiche_sejour, reservation_id)
        for section in (entete, infos, consommations, ponctuelle, reglements, historique, totaux, actions):
            await section.refresh()
        verrouiller_client()
        dessiner_persiste()
        compter()
        signaler_incoherences()
        montant_reglement.value = _euros(max(donnees["totaux"].solde, 0))

    async def enregistrer_haut() -> list[str] | None:
        nonlocal enregistre, client_id, client_nom, enregistre_client_id
        try:
            libelles = await run.io_bound(enregistrer_fiche, reservation_id, user_id, dict(valeurs), client_id)
        except FicheInvalide as erreur:
            ui.notify(str(erreur), type="warning")
            return None
        if libelles:
            await recharger()
            enregistre = _champs(donnees)
            client_id = donnees["client"]["id"]
            client_nom = donnees["client"]["nom"]
            enregistre_client_id = client_id
            champs["identite"].set_text(_texte_client(client_nom, client_id))
            verrouiller_client()
        return libelles

    async def confirmer() -> None:
        libelles = await enregistrer_haut()
        if libelles:
            ui.notify("Fiche enregistrée", type="positive")
        elif libelles is not None:
            ui.notify("Aucune modification à enregistrer")

    async def valider() -> None:
        if await enregistrer_haut() is not None:
            fermer_reservation()
            ui.navigate.to("/")

    async def partir() -> None:
        fermer_reservation()
        ui.navigate.to("/")

    async def abandonner() -> None:
        if fiche_modifiee():
            confirmation_abandon.open()
        else:
            await partir()

    async def consulter_facture() -> None:
        await ouvrir_facturation(reservation_id, user_id=user_id, apres=recharger)

    async def annuler() -> None:
        await run.io_bound(annuler_reservation, reservation_id, user_id)
        await recharger()
        ui.notify("Réservation annulée", type="warning")

    async def reprendre() -> None:
        try:
            await run.io_bound(reprendre_reservation, reservation_id, user_id)
        except ChambreOccupee as erreur:
            ui.notify(str(erreur), type="warning")
            return
        await recharger()
        ui.notify("Réservation reprise", type="positive")

    async def modifier_ligne(ligne: dict) -> None:
        await ouvrir_ligne(ligne)

    def proposer_prix(evenement) -> None:
        try:
            identifiant = int(evenement.value)
        except (TypeError, ValueError):
            prix_unitaire.set_value(None)
            return
        produit = next((item for item in produits_vente if item.id == identifiant), None)
        prix_unitaire.set_value(None if produit is None else _euros(produit.prix_unitaire_centimes))

    async def actualiser_produits() -> None:
        nonlocal produits_vente
        produits = await run.io_bound(lister_produits, actifs_seulement=True)
        if produits is None:
            return
        produits_vente = produits
        produit_choisi.set_options({produit.id: produit.nom for produit in produits_vente})

    async def actualiser_catalogue() -> None:
        nonlocal catalogue_complet
        produits = await run.io_bound(lister_produits)
        if produits is None:
            return
        catalogue_complet = produits
        select = champs_ponctuels.get("produit")
        if select is None or select.is_deleted:
            return
        options = _options_produits_ponctuels()
        if select.options == options:
            return
        select.set_options(options, value=select.value if select.value in options else None)

    async def rafraichir_catalogue_consommations(evenement) -> None:
        if vente_en_cours or ecriture_ponctuelle:
            return
        if evenement.value == "consommations":
            await actualiser_produits()
        elif evenement.value == "ponctuelle":
            await actualiser_catalogue()

    async def ajouter_une_consommation() -> None:
        nonlocal vente_en_cours
        if vente_en_cours:
            return
        if produit_choisi.value is None:
            ui.notify("Choisissez un produit", type="warning")
            return
        quantite_saisie = _entier_positif(quantite.value)
        if quantite_saisie is None:
            ui.notify("La quantité doit être un entier supérieur à 0", type="warning")
            return
        prix_accepte = _prix_saisi(prix_unitaire.value)
        if prix_accepte is None:
            ui.notify("Indiquez le prix unitaire", type="warning")
            return
        vente_en_cours = True
        bouton_consommation.disable()
        try:
            await run.io_bound(
                ajouter_consommation_produit,
                reservation_id,
                int(produit_choisi.value),
                quantite_saisie,
                prix_accepte,
                user_id,
            )
        except ProduitInvalide as erreur:
            await actualiser_produits()
            ui.notify(str(erreur), type="warning")
        else:
            produit_choisi.set_value(None)
            quantite.set_value(1)
            await actualiser_produits()
            await recharger()
            ui.notify("Consommation ajoutée", type="positive")
        finally:
            vente_en_cours = False
            bouton_consommation.enable()

    async def ajouter_un_reglement() -> None:
        if not montant_reglement.value or montant_reglement.value <= 0:
            ui.notify("Indiquez un montant", type="warning")
            return
        await run.io_bound(
            ajouter_reglement, reservation_id, ModeReglement(mode.value), centimes(montant_reglement.value), user_id
        )
        await recharger()
        ui.notify("Règlement enregistré", type="positive")

    async def noter() -> None:
        if not (note.value or "").strip():
            ui.notify("La note est vide", type="warning")
            return
        await run.io_bound(ajouter_note, reservation_id, user_id, note.value)
        note.value = ""
        await recharger()
        ui.notify("Note ajoutée au journal", type="positive")

    @ui.refreshable
    def entete() -> None:
        _entete(donnees, abandonner)

    @ui.refreshable
    def infos() -> None:
        champs.update(_infos(donnees, valeurs, ouvrir_clients[0], client_nom, client_id, consulter_facture))

    async def enregistrer_consommation(ligne: dict, quantite_saisie: int, prix_accepte: int, jour: date) -> bool:
        nonlocal vente_en_cours
        if vente_en_cours:
            return False
        vente_en_cours = True
        bouton_consommation.disable()
        rechargee = False
        try:
            modifie = await run.io_bound(
                modifier_consommation, ligne["id"], quantite_saisie, prix_accepte, jour, user_id
            )
        except ProduitInvalide as erreur:
            ui.notify(str(erreur), type="warning")
            await recharger()
            rechargee = True
        else:
            if modifie:
                await recharger()
                ui.notify("Consommation modifiée", type="positive")
                rechargee = True
        finally:
            vente_en_cours = False
            bouton_consommation.enable()
        return rechargee

    @ui.refreshable
    def consommations() -> None:
        _tableau_consommations(donnees["consommations"], enregistrer_consommation, lambda: vente_en_cours)

    @ui.refreshable
    def reglements() -> None:
        _tableau(
            COLONNES_REGLEMENTS,
            [
                [
                    date_courte(heure_locale(reglement["date"])),
                    MODE_REGLEMENT_LABEL[reglement["mode"]],
                    format_euros(reglement["montant_centimes"]),
                ]
                for reglement in donnees["reglements"]
            ],
            "Aucun règlement.",
        )

    @ui.refreshable
    def historique() -> None:
        _tableau(
            COLONNES_HISTORIQUE,
            [
                [date_heure(entree["date"]), entree["auteur"] or "—", entree["description"]]
                for entree in donnees["historique"]
            ],
            "Aucune modification enregistrée.",
        )

    @ui.refreshable
    def totaux() -> None:
        _totaux(donnees["totaux"])

    @ui.refreshable
    def actions() -> None:
        annulee = donnees["reservation"]["statut"] == StatutReservation.annulee
        ui.button("Facturer", icon="receipt_long", on_click=consulter_facture).props("outline").set_enabled(not annulee)
        ui.button("Annuler la réservation", icon="event_busy", on_click=confirmation_annulation.open).props(
            "outline color=negative"
        ).set_enabled(not annulee)
        ui.button("Reprendre", icon="event_available", on_click=reprendre).props("outline").set_enabled(annulee)

    def _options_produits_ponctuels() -> dict[int, str]:
        return {
            produit.id: produit.nom
            for produit in catalogue_complet
            if produit.id is not None and produit.actif and produit.ponctuel
        }

    def _options_chambres_sejour() -> dict[str, str]:
        options: dict[str, str] = {}
        for ligne in donnees["lignes"]:
            options.setdefault(ligne["chambre_nom"], f"Chambre {ligne['chambre_nom']}")
        return options

    def _contenu_ponctuel() -> dict:
        return lire(donnees["reservation"].get("notes_internes"))

    def _notes_paire(contenu: dict, nom: str, produit: str) -> dict[date, int]:
        produits = (contenu.get("Consommation") or {}).get(cle_chambre(nom)) or {}
        return dict(produits.get(produit) or {})

    def signaler_incoherences() -> None:
        if not onglet_ponctuel:
            return
        onglet = onglet_ponctuel[0]
        try:
            contenu = _contenu_ponctuel()
        except NoteIllisible:
            onglet.props.set_optional("alert", None)
            return
        alerte = "negative" if incoherences(contenu, donnees["lignes"]) else None
        onglet.props.set_optional("alert", alerte)

    async def executer_ponctuelle(operation: OperationPonctuelle) -> None:
        nonlocal ecriture_ponctuelle
        if ecriture_ponctuelle:
            return
        ecriture_ponctuelle = True
        try:
            await run.io_bound(modifier_consommation_ponctuelle, reservation_id, operation, user_id)
        except NoteIllisible:
            ui.notify("La note interne est illisible. Elle n'a pas été modifiée.", type="negative")
        try:
            await recharger()
        finally:
            ecriture_ponctuelle = False

    @ui.refreshable
    def ponctuelle() -> None:
        champs_ponctuels.clear()
        note = donnees["reservation"].get("notes_internes")
        try:
            contenu = lire(note)
        except NoteIllisible:
            _note_illisible(note)
            return
        messages = incoherences(contenu, donnees["lignes"])
        if messages:
            _alerte_ponctuelle(messages)
        _formulaire_ponctuel()
        _paires_ponctuelles(contenu)

    def _formulaire_ponctuel() -> None:
        options_produits = _options_produits_ponctuels()
        options_chambres = _options_chambres_sejour()

        async def ajouter() -> None:
            if ecriture_ponctuelle:
                return
            if produit_ponctuel.value not in options_produits:
                ui.notify("Choisissez un produit", type="warning")
                return
            if chambre_ponctuelle.value not in options_chambres:
                ui.notify("Choisissez une chambre", type="warning")
                return
            nombre = _entier_positif(nombre_ponctuel.value)
            if nombre is None:
                ui.notify("Indiquez un nombre entier supérieur à 0", type="warning")
                return
            paire = (chambre_ponctuelle.value, options_produits[produit_ponctuel.value])
            couples_ajoutes.add(paire)
            nombres_choisis[paire] = nombre
            await ponctuelle.refresh()

        with _barre_saisie():
            produit_ponctuel = (
                ui.select(options_produits, label="Produit", with_input=True)
                .classes("w-64")
                .mark("produit-ponctuel")
            )
            chambre_ponctuelle = (
                ui.select(options_chambres, label="Chambre", with_input=True)
                .classes("w-48")
                .mark("chambre-ponctuelle")
            )
            nombre_ponctuel = (
                ui.number("Nombre", value=1, min=1, precision=0, format="%d").classes("w-28").mark("nombre-ponctuel")
            )
            ui.button("Ajouter", icon="add", on_click=ajouter).mark("ajouter-ponctuelle")
        champs_ponctuels["produit"] = produit_ponctuel

    def _colonnes_ponctuelles(contenu: dict, paires: set[tuple[str, str]]) -> list[date]:
        jours: set[date] = set()
        for nom, produit in paires:
            jours.update(_notes_paire(contenu, nom, produit))
            for ligne in donnees["lignes"]:
                if ligne["chambre_nom"] == nom:
                    jours.update(jours_du_sejour(ligne))
        return sorted(jours)

    def _paires_ponctuelles(contenu: dict) -> None:
        paires = set(couples_ajoutes)
        for cle, produits in (contenu.get("Consommation") or {}).items():
            nom = nom_chambre(str(cle))
            paires.update((nom, str(nom_produit)) for nom_produit in produits)
        if not paires:
            ui.label("Aucune consommation ponctuelle pour ce séjour.").classes("px-4 py-6 text-sm text-ardoise")
            return
        noms_catalogue = {produit.nom for produit in catalogue_complet}
        colonnes = _colonnes_ponctuelles(contenu, paires)
        aujourd_hui = date.today()
        with ui.element("div").classes("w-full overflow-x-auto"):
            with ui.element("table").classes("w-full text-sm border-collapse").mark("tableau-ponctuel"):
                with ui.element("thead"), ui.element("tr"):
                    _entete_ponctuel("produit", "Produit · Chambre", A_GAUCHE)
                    _entete_ponctuel("nombre", "Nombre", A_GAUCHE)
                    for jour in colonnes:
                        _entete_date_ponctuelle(jour, aujourd_hui)
                    _entete_ponctuel("total", "Total", A_DROITE)
                    _entete_ponctuel("actions", "", A_GAUCHE)
                with ui.element("tbody"):
                    for nom, produit in sorted(paires, key=lambda paire: (paire[1].casefold(), paire[0].casefold())):
                        _paire_ponctuelle(
                            contenu,
                            nom,
                            produit,
                            produit not in noms_catalogue,
                            colonnes,
                            aujourd_hui,
                        )

    def _paire_ponctuelle(
        contenu: dict,
        nom: str,
        produit: str,
        gris: bool,
        colonnes: list[date],
        aujourd_hui: date,
    ) -> None:
        notes = _notes_paire(contenu, nom, produit)
        cle = (nom, produit)
        if cle not in nombres_choisis:
            valeurs = {
                valeur
                for valeur in notes.values()
                if isinstance(valeur, int) and not isinstance(valeur, bool) and valeur > 0
            }
            nombres_choisis[cle] = valeurs.pop() if len(valeurs) == 1 else 1
        jours_sejour = {
            jour
            for ligne in donnees["lignes"]
            if ligne["chambre_nom"] == nom
            for jour in jours_du_sejour(ligne)
        }
        applicables = set(notes) | jours_sejour
        total = totaux_note(contenu).get((cle_chambre(nom), produit), 0)

        def memoriser_nombre(evenement, cle: tuple[str, str] = cle) -> None:
            nombre = _entier_positif(evenement.value)
            if nombre is not None:
                nombres_choisis[cle] = nombre

        async def changer_case(evenement, jour: date, nom: str = nom, produit: str = produit) -> None:
            if ecriture_ponctuelle:
                return
            try:
                actuelles = _notes_paire(_contenu_ponctuel(), nom, produit)
            except NoteIllisible:
                ui.notify("La note interne est illisible. Elle n'a pas été modifiée.", type="negative")
                await recharger()
                return
            coche = bool(evenement.value)
            nombre_voulu = nombres_choisis.get((nom, produit))
            if coche == (jour in actuelles) and (not coche or actuelles.get(jour) == nombre_voulu):
                return
            nombre = None
            if coche:
                nombre = _entier_positif(nombre_voulu)
                if nombre is None:
                    ui.notify("Indiquez un nombre entier supérieur à 0", type="warning")
                    await ponctuelle.refresh()
                    return
            await executer_ponctuelle(OperationPonctuelle("basculer", nom, produit, jour=jour, nombre=nombre))

        async def selectionner(nom: str = nom, produit: str = produit) -> None:
            nombre = _entier_positif(nombres_choisis.get((nom, produit)))
            if nombre is None:
                ui.notify("Indiquez un nombre entier supérieur à 0", type="warning")
                return
            jours_sejour = tuple(
                sorted(
                    {
                        jour
                        for ligne in donnees["lignes"]
                        if ligne["chambre_nom"] == nom
                        for jour in jours_du_sejour(ligne)
                    }
                )
            )
            if not jours_sejour:
                ui.notify("Cette chambre n'a pas de dates de séjour", type="warning")
                return
            await executer_ponctuelle(
                OperationPonctuelle("tout_cocher", nom, produit, jours=jours_sejour, nombre=nombre)
            )

        async def retirer(nom: str = nom, produit: str = produit) -> None:
            couples_ajoutes.discard((nom, produit))
            await executer_ponctuelle(OperationPonctuelle("tout_retirer", nom, produit))

        with ui.element("tr"):
            with ui.element("td").classes(f"{TD} align-middle whitespace-nowrap w-px"):
                with ui.row().classes("items-baseline gap-1.5 no-wrap"):
                    titre = ui.label(produit).classes(
                        "font-medium text-slate-400" if gris else "font-medium"
                    )
                    ui.label("·").classes("text-ardoise")
                    ui.label(nom).classes("text-ardoise")
                    if gris:
                        titre.mark(f"gris-ponctuel|{produit}")
                        ui.label("Hors catalogue").classes("text-xs text-slate-400")
            with _cellule_saisie().classes("w-px"):
                (
                    ui.number(value=nombres_choisis[cle], min=1, precision=0, format="%d")
                    .props(f"{PROPS_SAISIE} input-class=text-right")
                    .classes("w-16")
                    .on_value_change(memoriser_nombre)
                    .mark(f"nombre-ligne|{nom}|{produit}")
                )
            for jour in colonnes:
                hors = jour in notes and jour not in jours_sejour
                fond = "bg-primary-pale" if jour == aujourd_hui else "bg-warning-soft" if hors else ""
                with ui.element("td").classes(f"px-1 h-9 border-b border-slate-100 text-center align-middle {fond}"):
                    if jour not in applicables:
                        continue
                    case = ui.checkbox(value=jour in notes).props("dense")
                    case.on_value_change(lambda evenement, jour=jour: changer_case(evenement, jour))
                    case.mark(f"case-ponctuelle|{nom}|{produit}|{jour.isoformat()}")
            with ui.element("td").classes(f"{TD} text-right align-middle font-semibold"):
                ui.label(str(total)).mark(f"total-ponctuel|{nom}|{produit}")
            with ui.element("td").classes("px-2 border-b border-slate-100 align-middle"):
                with ui.row().classes("no-wrap items-center gap-1"):
                    ui.button(icon="select_all", on_click=selectionner).props("flat dense round").tooltip(
                        "Tout sélectionner"
                    ).mark(f"tout-ponctuel|{nom}|{produit}")
                    ui.button(icon="deselect", on_click=retirer).props("flat dense round color=ardoise").tooltip(
                        "Tout retirer"
                    ).mark(f"retirer-ponctuel|{nom}|{produit}")

    def compter() -> None:
        for cle, onglet in onglets_comptes.items():
            onglet.props["label"] = f"{ONGLETS_COMPTES[cle]} ({donnees['compteurs'][cle]})"

    ui.add_body_html(RACCOURCIS)
    ui.on("fiche-confirmer", confirmer)
    ui.on("fiche-abandon", abandonner)

    with page(ACTIF_DETAIL, "Fiche séjour"):
        ouvrir_ligne = _dialogue_ligne(user_id, recharger)
        confirmation_annulation = _confirmation(
            "Annuler la réservation ?",
            "Elle passe au statut « Annulée » et ses chambres sont libérées sur le planning.",
            "Annuler la réservation",
            annuler,
        )
        confirmation_abandon = _confirmation(
            "Abandonner les modifications ?",
            "Les changements de la fiche qui n'ont pas été confirmés seront perdus.",
            "Abandonner",
            partir,
        )
        ouvrir_clients.append(_dialogue_clients(appliquer_client))
        with ui.card().props("flat bordered").classes("w-full rounded-lg p-0 gap-0"):
            entete()
            with ui.element("div").classes("w-full grid grid-cols-12 gap-6 px-6 py-5"):
                with ui.column().classes("col-span-5 gap-0"):
                    infos()
                with ui.column().classes("col-span-7 gap-0"):
                    champs.update(_onglets_contacts(valeurs))
            verrouiller_client()

            with ui.column().classes("w-full gap-0 border-t border-slate-200"):
                with (
                    ui.tabs(value="reservations")
                    .props("dense align=left no-caps inline-label active-color=primary indicator-color=primary")
                    .classes("w-full px-3 text-ardoise border-b border-slate-200")
                    .mark("onglets-fiche") as onglets
                ):
                    onglets_comptes = {}
                    for cle in ONGLETS_COMPTES:
                        onglets_comptes[cle] = ui.tab(cle)
                        if cle == "consommations":
                            onglet_ponctuel.append(
                                ui.tab("ponctuelle", "Consommation ponctuelle").mark("onglet-ponctuelle")
                            )
                compter()
                signaler_incoherences()
                with ui.tab_panels(onglets, value="reservations", animated=False).classes("w-full"):
                    with ui.tab_panel("reservations").classes("p-0"):
                        corps_persiste, corps_brouillon, pied_lignes = _tableau_lignes()

                        def dessiner_persiste() -> None:
                            _remplir_persiste(corps_persiste, donnees["lignes"], modifier_ligne, brouillon is None)

                        def dessiner_pied() -> None:
                            pied_lignes.clear()
                            with pied_lignes:
                                if brouillon is None:
                                    _lien_ajout(ajouter_ligne)
                                else:
                                    _boutons_brouillon(enregistrer_brouillon, annuler_brouillon)

                        def fermer_brouillon() -> None:
                            nonlocal brouillon
                            brouillon = None
                            corps_brouillon.clear()
                            dessiner_pied()

                        def annuler_brouillon() -> None:
                            fermer_brouillon()
                            dessiner_persiste()

                        async def ajouter_ligne() -> None:
                            nonlocal brouillon, ajout_en_cours
                            if brouillon is not None or ajout_en_cours:
                                return
                            ajout_en_cours = True
                            try:
                                options, types_chambres = await run.io_bound(_catalogue_chambres)
                                if brouillon is not None:
                                    return
                                if not options:
                                    ui.notify("Ajoutez d'abord une chambre", type="warning")
                                    return
                                debut = donnees["debut"] or date.today()
                                brouillon = _monter_brouillon(
                                    corps_brouillon,
                                    options,
                                    types_chambres,
                                    debut,
                                    donnees["fin"] or debut + timedelta(days=1),
                                )
                                dessiner_persiste()
                                dessiner_pied()
                            finally:
                                ajout_en_cours = False

                        async def enregistrer_brouillon() -> None:
                            nonlocal enregistrement_en_cours
                            if brouillon is None or enregistrement_en_cours:
                                return
                            chambre_id = brouillon.chambre.value
                            debut = _lire_date(brouillon.arrivee.value)
                            fin = _lire_date(brouillon.depart.value)
                            if chambre_id is None or debut is None or fin is None:
                                ui.notify(
                                    "Choisissez la chambre et les dates d'arrivée et de départ",
                                    type="warning",
                                )
                                return
                            nom_client = brouillon.nom.value
                            adultes = int(brouillon.adultes.value or 0)
                            enfants = int(brouillon.enfants.value or 0)
                            prix_nuit = centimes(brouillon.prix.value or 0)
                            enregistrement_en_cours = True
                            try:
                                await run.io_bound(
                                    ajouter_sejour,
                                    reservation_id,
                                    chambre_id,
                                    debut,
                                    fin,
                                    nom_client,
                                    adultes,
                                    enfants,
                                    prix_nuit,
                                    user_id,
                                )
                            except ChambreOccupee as erreur:
                                ui.notify(str(erreur), type="negative")
                            except SejourInvalide as erreur:
                                ui.notify(str(erreur), type="warning")
                            else:
                                ui.notify("Ligne ajoutée", type="positive")
                                fermer_brouillon()
                                await recharger()
                            finally:
                                enregistrement_en_cours = False

                        dessiner_persiste()
                        dessiner_pied()
                    with ui.tab_panel("consommations").classes("p-0"):
                        consommations()
                        with _barre_saisie():
                            produit_choisi = (
                                ui.select(
                                    {produit.id: produit.nom for produit in produits_vente},
                                    label="Produit",
                                    with_input=True,
                                )
                                .classes("w-64")
                                .mark("produit-consommation")
                            )
                            quantite = (
                                ui.number("Qté", value=1, min=1, precision=0, format="%d")
                                .classes("w-24")
                                .mark("quantite-consommation")
                            )
                            prix_unitaire = _champ_euros("PU TTC").classes("w-36").mark("prix-consommation")
                            produit_choisi.on_value_change(proposer_prix)
                            bouton_consommation = ui.button(
                                "Ajouter", icon="add", on_click=ajouter_une_consommation
                            ).mark("ajouter-consommation")
                        onglets.on_value_change(rafraichir_catalogue_consommations)
                    with ui.tab_panel("ponctuelle").classes("p-0"):
                        ponctuelle()
                    with ui.tab_panel("reglements").classes("p-0"):
                        totaux()
                        reglements()
                        with _barre_saisie():
                            mode = ui.select(OPTIONS_MODES, label="Mode", value=ModeReglement.carte.value).classes(
                                "w-56"
                            )
                            montant_reglement = _champ_euros(
                                "Montant", _euros(max(donnees["totaux"].solde, 0))
                            ).classes("w-36")
                            ui.button("Enregistrer le règlement", icon="add", on_click=ajouter_un_reglement)
                    with ui.tab_panel("modifications").classes("p-0"):
                        with _barre_saisie(haut=True):
                            note = ui.input("Ajouter une note au journal").classes("flex-1").on("keydown.enter", noter)
                            ui.button("Ajouter la note", icon="edit_note", on_click=noter)
                        historique()
            with ui.row().classes(
                "w-full items-center gap-2 px-6 py-3 bg-white border-t border-slate-200 rounded-b-lg "
                "sticky bottom-0 z-10 no-wrap"
            ):
                actions()
                ui.space()
                ui.label("Ctrl+S confirme · Échap abandonne").classes("text-xs text-slate-400 mr-2")
                ui.button("Confirmer", icon="check", on_click=confirmer)
                ui.button("Ok", on_click=valider).props("outline")
                ui.button("Abandon", on_click=abandonner).props("flat color=ardoise")


def _valeur_affichee(valeur: object) -> object:
    if valeur is None:
        return ""
    if isinstance(valeur, StatutReservation):
        return valeur.value
    return valeur


def _champs(fiche: dict) -> dict:
    sources = {Client: fiche["client"], Reservation: fiche["reservation"]}
    return {cle: sources[modele][cle] for cle, (modele, _) in CHAMPS_FICHE.items()}


def _entete(fiche: dict, retour: Callable[[], Awaitable[None]]) -> None:
    statut = STATUT_SEJOUR[fiche["reservation"]["statut"]]
    details = [f"Réservation n° {fiche['id']}"]
    if fiche["debut"]:
        nombre = nuits(fiche["debut"], fiche["fin"])
        details.append(f"du {date_courte(fiche['debut'])} au {date_courte(fiche['fin'])}")
        details.append(f"{nombre} nuit{'s' if nombre > 1 else ''}")
    if fiche["reservation"]["partenaire"]:
        details.append(fiche["reservation"]["partenaire"])
    with ui.row().classes("w-full items-center gap-4 px-6 py-4 border-b border-slate-200 no-wrap"):
        with ui.column().classes("gap-1"):
            with ui.row().classes("items-center gap-3"):
                ui.label(fiche["reservation"]["nom_occupant"] or fiche["client"]["nom_complet"]).classes(
                    "text-2xl font-semibold leading-tight"
                )
                badge(statut.libelle, statut.couleur)
            ui.label(" · ".join(details)).classes("text-sm text-ardoise")
        ui.space()
        ui.button("Planning", icon="arrow_back", on_click=retour).props("flat color=ardoise")


def _texte_client(nom: str, identifiant: int) -> str:
    return f"{nom} · n° {identifiant}"


def _infos(
    fiche: dict,
    valeurs: dict,
    ouvrir_client: Callable[[str], None],
    nom_client: str,
    identifiant: int,
    consulter_facture: Callable[[], None],
) -> dict[str, ui.element]:
    reservation = fiche["reservation"]
    with ui.grid().classes("w-full gap-x-4 gap-y-2 items-center").style("grid-template-columns: 7rem 1fr"):
        _libelle("Nom")
        nom = ui.input(placeholder="Nom").bind_value(valeurs, "nom").mark("nom-client")
        _libelle(CHAMPS_FICHE["nom_occupant"][1])
        with ui.row().classes("w-full no-wrap items-center gap-1"):
            ui.input(placeholder="Nom sur le planning").bind_value(valeurs, "nom_occupant").classes("flex-1").mark(
                "occupant-reservation"
            )
            loupe = (
                ui.button(
                    icon="search",
                    on_click=lambda: ouvrir_client((valeurs.get("nom_occupant") or "").strip()),
                )
                .props("flat round dense")
                .mark("loupe-occupant")
            )
            loupe.tooltip("Rechercher ce nom")
        _libelle("Client")
        with (
            ui.row()
            .classes(
                "h-10 w-full items-center gap-2 px-3 rounded bg-slate-50 cursor-pointer hover:bg-primary-pale no-wrap"
            )
            .on("click", lambda: ouvrir_client(""))
            .mark("client-sejour")
        ):
            identite = ui.label(_texte_client(nom_client, identifiant)).classes("text-sm text-slate-700 truncate")
            ui.icon("expand_more", size="1.1rem").classes("text-ardoise")
        _libelle(CHAMPS_FICHE["pays"][1])
        pays = ui.input(autocomplete=PAYS_COURANTS).bind_value(valeurs, "pays").mark("pays-client")
        _libelle(CHAMPS_FICHE["partenaire"][1])
        ui.input(autocomplete=PARTENAIRES).bind_value(valeurs, "partenaire").mark("partenaire-reservation")
        _libelle("Statut")
        if reservation["statut"] == StatutReservation.annulee:
            badge(STATUT_SEJOUR[StatutReservation.annulee].libelle, "negative")
        else:
            ui.select(OPTIONS_STATUT).bind_value(valeurs, "statut").classes("w-48")
        _libelle(CHAMPS_FICHE["type_voiture"][1])
        ui.input().bind_value(valeurs, "type_voiture")
        _libelle("Date facture")
        _lecture(date_courte(reservation["date_facture"]) or "—")
        _libelle("N° facture")
        if reservation["numero_facture"]:
            ui.button(str(reservation["numero_facture"]), on_click=consulter_facture).props(
                "flat dense no-caps color=primary"
            ).mark("numero-facture")
        else:
            _lecture("—")
    return {"nom": nom, "pays": pays, "identite": identite}


def _onglets_contacts(valeurs: dict) -> dict[str, ui.element]:
    ouvert = "notes" if valeurs["notes"] else "contacts"
    with ui.column().classes("w-full gap-0 border border-slate-200 rounded-lg overflow-hidden"):
        with (
            ui.tabs(value=ouvert)
            .props("dense align=left no-caps inline-label active-color=primary indicator-color=primary")
            .classes("w-full bg-slate-50 text-ardoise border-b border-slate-200") as onglets
        ):
            ui.tab("contacts", "Contacts")
            pastilles = {cle: ui.tab(cle, CHAMPS_FICHE[cle][1]) for cle in ONGLETS_TEXTE}
        with ui.tab_panels(onglets, value=ouvert, animated=False).classes("w-full"):
            with ui.tab_panel("contacts").classes("p-4"):
                with ui.grid().classes("w-full gap-x-4 gap-y-2 items-start").style("grid-template-columns: 6rem 1fr"):
                    _libelle(CHAMPS_FICHE["telephone"][1])
                    telephone = ui.input().bind_value(valeurs, "telephone").mark("telephone-client")
                    _libelle(CHAMPS_FICHE["email"][1])
                    email = ui.input().bind_value(valeurs, "email").mark("email-client")
                    _libelle(CHAMPS_FICHE["adresse"][1])
                    adresse = ui.textarea().bind_value(valeurs, "adresse").props("rows=4").mark("adresse-client")
            zones: dict[str, ui.textarea] = {}
            for cle in ONGLETS_TEXTE:
                with ui.tab_panel(cle).classes("p-3"):
                    zones[cle] = (
                        ui.textarea()
                        .bind_value(valeurs, cle)
                        .props("rows=12")
                        .classes("w-full")
                        .on_value_change(lambda evenement, onglet=pastilles[cle]: _pastille(onglet, evenement.value))
                    )
                _pastille(pastilles[cle], valeurs[cle])
            zones["notes_client"].mark("notes-client")
    return {"telephone": telephone, "email": email, "adresse": adresse, "notes_client": zones["notes_client"]}


def _pastille(onglet: ui.tab, texte: str | None) -> None:
    onglet.props.set_optional("alert", "accent" if (texte or "").strip() else None)


def _libelle(texte: str) -> None:
    ui.label(texte).classes("text-sm text-ardoise leading-10")


def _lecture(texte: str) -> None:
    ui.label(texte).classes("h-10 flex items-center px-3 rounded bg-slate-50 text-sm text-slate-700 tabular-nums")


def _th(texte: str, classes: str, **fusion: int) -> None:
    with ui.element("th").classes(f"{TH} {classes}") as cellule:
        ui.label(texte)
    cellule.props.update(fusion)


def _td(texte: str, classes: str) -> None:
    with ui.element("td").classes(f"{TD} {classes}"):
        ui.label(texte)


def _rangee_vide(texte: str, largeur: int) -> None:
    with ui.element("tr"), ui.element("td").classes(f"{TD} text-center text-ardoise").props(f"colspan={largeur}"):
        ui.label(texte)


def _tableau_lignes() -> tuple[ui.element, ui.element, ui.element]:
    with ui.element("table").classes("w-full text-sm border-collapse"):
        with ui.element("thead"):
            haut = ui.element("tr")
            bas = ui.element("tr")
        debut = 0
        for titre, nombre in GROUPES_LIGNES:
            colonnes = COLONNES_LIGNES[debut : debut + nombre]
            debut += nombre
            if titre is None:
                with haut:
                    for libelle, _, classes in colonnes:
                        _th(libelle, f"{classes} align-bottom", rowspan=2)
                continue
            with haut:
                _th(titre, "text-center border-x py-1!", colspan=nombre)
            with bas:
                for libelle, _, classes in colonnes:
                    _th(libelle, classes)
        persiste = ui.element("tbody")
        brouillon = ui.element("tbody")
        pied = ui.element("tbody")
    return persiste, brouillon, pied


def _entete_ponctuel(cle: str, libelle: str, classes: str) -> None:
    with ui.element("th").classes(f"{TH} {classes}").mark(f"entete-ponctuel|{cle}"):
        ui.label(libelle)


def _entete_date_ponctuelle(jour: date, aujourd_hui: date) -> None:
    courant = jour == aujourd_hui
    fond = "bg-primary-pale text-primary" if courant else "bg-slate-50 text-ardoise"
    with (
        ui.element("th")
        .classes(f"px-2 py-1 border-b border-slate-200 text-center whitespace-nowrap {fond}")
        .mark(f"entete-ponctuel|{jour.isoformat()}")
    ):
        with ui.column().classes("items-center gap-0"):
            ui.label(f"{JOURS[jour.weekday()][:3]}.").classes("text-[11px] uppercase tracking-wide")
            ui.label(f"{jour:%d/%m}").classes("text-sm font-semibold tabular-nums leading-tight")


def _alerte_ponctuelle(messages: list[str]) -> None:
    with (
        ui.row()
        .classes("w-full items-start gap-3 px-4 py-3 bg-warning-soft text-warning")
        .mark("alerte-ponctuelle")
    ):
        ui.icon("error", size="1.25rem").classes("mt-0.5")
        with ui.column().classes("gap-1"):
            ui.label("Cette note ne correspond plus aux séjours.").classes("text-sm font-medium")
            for message in messages:
                ui.label(message).classes("text-sm")


def _note_illisible(note: str | None) -> None:
    with ui.column().classes("w-full gap-2 px-4 py-4").mark("note-illisible"):
        ui.label("La note interne est illisible. Aucune modification ne sera enregistrée.").classes(
            "text-sm text-negative"
        )
        ui.textarea(value=note or "").props("readonly").classes("w-full")


def _remplir_persiste(
    corps: ui.element,
    lignes: list[dict],
    modifier: Callable[[dict], Awaitable[None]],
    montrer_vide: bool,
) -> None:
    corps.clear()
    with corps:
        for ligne in lignes:
            with (
                ui.element("tr")
                .classes("cursor-pointer hover:bg-primary-pale")
                .on("click", lambda ligne=ligne: modifier(ligne))
                .mark(f"ligne-sejour-{ligne['id']}")
            ):
                for _, rendu, classes in COLONNES_LIGNES:
                    _td(rendu(ligne), classes)
        if not lignes and montrer_vide:
            _rangee_vide("Aucune ligne de séjour pour l'instant.", len(COLONNES_LIGNES))


def _lien_ajout(ajouter: Callable[[], Awaitable[None]]) -> None:
    with ui.element("tr").classes("cursor-pointer hover:bg-primary-pale").on("click", ajouter):
        with ui.element("td").classes(f"{TD} text-primary font-medium").props(f"colspan={len(COLONNES_LIGNES)}"):
            with ui.row().classes("items-center gap-1"):
                ui.icon("add", size="1.1rem")
                ui.label("Ajouter une nouvelle ligne").on("click", ajouter)


def _boutons_brouillon(
    enregistrer: Callable[[], Awaitable[None]], annuler: Callable[[], None]
) -> None:
    with ui.element("tr"):
        with ui.element("td").classes("px-3 py-1 border-b border-slate-100").props(f"colspan={len(COLONNES_LIGNES)}"):
            with ui.row().classes("items-center gap-2"):
                ui.button("Enregistrer", on_click=enregistrer)
                ui.button("Annuler", on_click=annuler).props("flat color=ardoise")


def _tableau_consommations(
    lignes: list[dict],
    enregistrer: Callable[[dict, int, int, date], Awaitable[bool]],
    occupee: Callable[[], bool],
) -> None:
    with ui.element("table").classes("w-full text-sm border-collapse"):
        with ui.element("thead"), ui.element("tr"):
            for titre, classes in COLONNES_CONSOMMATIONS:
                _th(titre, classes)
        with ui.element("tbody"):
            if not lignes:
                _rangee_vide("Aucune consommation.", len(COLONNES_CONSOMMATIONS))
            for ligne in lignes:
                _rangee_consommation(ligne, enregistrer, occupee)


def _rangee_consommation(
    ligne: dict,
    enregistrer: Callable[[dict, int, int, date], Awaitable[bool]],
    occupee: Callable[[], bool],
) -> None:
    identifiant = ligne["id"]
    with ui.element("tr").mark(f"ligne-consommation-{identifiant}"):
        with _cellule_saisie():
            date_ligne = (
                _champ_date("").props(PROPS_SAISIE).classes("w-36").mark(f"date-ligne-{identifiant}")
            )
            date_ligne.set_value(date_courte(heure_locale(ligne["date"])))
        with ui.element("td").classes(f"{TD} {A_GAUCHE} align-middle"):
            ui.label(ligne["libelle"]).mark(f"libelle-ligne-{identifiant}")
        with _cellule_saisie():
            quantite = (
                ui.number(value=ligne["quantite"], min=1, precision=0, format="%d")
                .props(f"{PROPS_SAISIE} input-class=text-right")
                .classes("w-16")
                .mark(f"quantite-ligne-{identifiant}")
            )
        with _cellule_saisie():
            prix = (
                _champ_euros("", _euros(ligne["prix_unitaire_centimes"]))
                .props(f"{PROPS_SAISIE} input-class=text-right")
                .classes("w-28")
                .mark(f"prix-ligne-{identifiant}")
            )
        with ui.element("td").classes(f"{TD} {A_DROITE} align-middle font-semibold"):
            montant = ui.label(format_euros(ligne["montant"])).mark(f"montant-ligne-{identifiant}")

    def afficher_montant() -> None:
        quantite_saisie = _entier_positif(quantite.value)
        prix_accepte = _prix_saisi(prix.value)
        montant.set_text(
            "—" if quantite_saisie is None or prix_accepte is None else format_euros(quantite_saisie * prix_accepte)
        )

    async def memoriser(ignorer_date_incomplete: bool) -> None:
        if occupee():
            return
        quantite_saisie = _entier_positif(quantite.value)
        prix_accepte = _prix_saisi(prix.value)
        jour = _lire_date(date_ligne.value)
        if quantite_saisie is None:
            ui.notify("La quantité doit être un entier supérieur à 0", type="warning")
            return
        if prix_accepte is None:
            ui.notify("Indiquez le prix unitaire", type="warning")
            return
        if jour is None:
            if ignorer_date_incomplete:
                return
            ui.notify("Indiquez la date", type="warning")
            return
        if (
            quantite_saisie == ligne["quantite"]
            and prix_accepte == ligne["prix_unitaire_centimes"]
            and jour == heure_locale(ligne["date"]).date()
        ):
            return
        for champ in (date_ligne, quantite, prix):
            champ.disable()
        if not await enregistrer(ligne, quantite_saisie, prix_accepte, jour):
            for champ in (date_ligne, quantite, prix):
                champ.enable()

    async def sortir() -> None:
        await memoriser(False)

    async def saisir_date() -> None:
        await memoriser(True)

    quantite.on("blur", sortir).on("keydown.enter", sortir).on_value_change(lambda _: afficher_montant())
    prix.on("blur", sortir).on("keydown.enter", sortir).on_value_change(lambda _: afficher_montant())
    date_ligne.on("blur", sortir).on("keydown.enter", sortir).on_value_change(saisir_date)


def _tableau(colonnes: tuple[tuple[str, str], ...], rangees: list[list[str]], vide: str) -> None:
    with ui.element("table").classes("w-full text-sm border-collapse"):
        with ui.element("thead"), ui.element("tr"):
            for titre, classes in colonnes:
                _th(titre, classes)
        with ui.element("tbody"):
            for rangee in rangees:
                with ui.element("tr").classes("hover:bg-slate-50"):
                    for (_, classes), texte in zip(colonnes, rangee, strict=True):
                        _td(texte, classes)
            if not rangees:
                _rangee_vide(vide, len(colonnes))


def _barre_saisie(haut: bool = False) -> ui.row:
    bordure = "border-b" if haut else ""
    return ui.row().classes(f"w-full items-start gap-2 px-4 py-3 bg-slate-50 border-slate-200 no-wrap {bordure}")


def _totaux(totaux: Totaux) -> None:
    couleur = "negative" if totaux.solde > 0 else "positive" if totaux.solde == 0 else "warning"
    with ui.row().classes(
        "w-full justify-end items-center gap-8 px-6 py-3 border-b border-slate-200 bg-slate-50 no-wrap"
    ):
        _montant("Hébergement", totaux.hebergement)
        _montant("Taxe de séjour", totaux.taxe_sejour)
        _montant("Consommations", totaux.consommations)
        ui.element("div").classes("w-px self-stretch bg-slate-200")
        _montant("Total TTC", totaux.total, "text-lg font-semibold")
        _montant("Réglé", totaux.regle)
        with ui.column().classes(f"items-end gap-0 rounded-md px-3 py-1 bg-{couleur}-soft text-{couleur}"):
            ui.label("Solde").classes("text-xs")
            ui.label(format_euros(totaux.solde)).classes("text-lg font-semibold tabular-nums")


def _montant(libelle: str, montant: int, classes: str = "text-base") -> None:
    with ui.column().classes("items-end gap-0"):
        ui.label(libelle).classes("text-xs text-ardoise")
        ui.label(format_euros(montant)).classes(f"{classes} tabular-nums")


def _confirmation(titre: str, texte: str, action: str, sur_action: Callable[[], Awaitable[None]]) -> ui.dialog:
    async def executer() -> None:
        dialogue.close()
        await sur_action()

    with ui.dialog() as dialogue, ui.card().classes("w-[28rem] gap-3 p-5"):
        ui.label(titre).classes("text-base font-semibold")
        ui.label(texte).classes("text-sm text-ardoise")
        with ui.row().classes("w-full justify-end gap-2 pt-2"):
            ui.button("Retour", on_click=dialogue.close).props("flat color=ardoise")
            ui.button(action, on_click=executer).props("color=negative")
    return dialogue


def _champ_euros(libelle: str, valeur: float | None = None) -> ui.number:
    champ = ui.number(libelle, value=valeur, min=0, step=0.01, precision=2, format="%.2f")
    champ.props["suffix"] = "€"
    return champ


def _champ_date(libelle: str) -> ui.date_input:
    champ = ui.date_input(libelle)
    champ.picker.props["mask"] = "DD/MM/YYYY"
    return champ


def _euros(montant: int) -> float:
    return montant / 100


def _prix_saisi(valeur: float | None) -> int | None:
    if valeur is None:
        return None
    try:
        return centimes(valeur)
    except (ArithmeticError, ValueError):
        return None


def _entier_positif(valeur: object) -> int | None:
    if isinstance(valeur, bool) or valeur is None:
        return None
    if isinstance(valeur, int):
        return valeur if valeur > 0 else None
    if isinstance(valeur, float) and valeur.is_integer():
        entier = int(valeur)
        return entier if entier > 0 else None
    return None


def _lire_date(texte: str | None) -> date | None:
    try:
        return datetime.strptime(texte or "", "%d/%m/%Y").date()
    except ValueError:
        return None


def _catalogue_chambres() -> tuple[dict[int, str], dict[int, str | None]]:
    chambres = lister_chambres()
    return options_chambres(), {chambre["id"]: chambre["type_chambre"] for chambre in chambres}


def _ajuster_depart(ligne: BrouillonLigne) -> None:
    debut, fin = _lire_date(ligne.arrivee.value), _lire_date(ligne.depart.value)
    if debut and (fin is None or fin <= debut):
        ligne.depart.value = f"{debut + timedelta(days=1):%d/%m/%Y}"


def _mettre_a_jour_brouillon(ligne: BrouillonLigne) -> None:
    ligne.libelle_type.set_text(ligne.types_chambres.get(ligne.chambre.value) or "—")
    debut, fin = _lire_date(ligne.arrivee.value), _lire_date(ligne.depart.value)
    if debut is None or fin is None or fin <= debut:
        ligne.libelle_nuits.set_text("—")
        ligne.libelle_taxe.set_text("—")
        ligne.libelle_montant.set_text("—")
        return
    nombre = nuits(debut, fin)
    ligne.libelle_nuits.set_text(str(nombre))
    ligne.libelle_taxe.set_text(format_euros(taxe_sejour(int(ligne.adultes.value or 0), nombre)))
    ligne.libelle_montant.set_text(
        format_euros(montant_ligne(centimes(ligne.prix.value or 0), nombre))
    )


def _cellule_saisie() -> ui.element:
    return ui.element("td").classes("px-1 py-0.5 border-b border-slate-100 align-middle")


def _etiquette_colonne(classes: str) -> ui.label:
    with ui.element("td").classes(f"{TD} {classes} align-middle"):
        return ui.label("—")


def _monter_brouillon(
    corps: ui.element,
    options: dict[int, str],
    types_chambres: dict[int, str | None],
    debut: date,
    fin: date,
) -> BrouillonLigne:
    corps.clear()
    with corps, ui.element("tr").classes("ligne-ouverte"):
        libelle_type = _etiquette_colonne(A_GAUCHE)
        with _cellule_saisie():
            with ui.row().classes("no-wrap items-center gap-1"):
                chambre = ui.select(options, with_input=True).props(PROPS_SAISIE).classes("w-40")
                nom = ui.input(placeholder="Nom").props(PROPS_SAISIE).classes("w-32")
        libelle_nuits = _etiquette_colonne(A_DROITE)
        with _cellule_saisie():
            arrivee = _champ_date("").props(PROPS_SAISIE).classes("w-28")
        with _cellule_saisie():
            depart = _champ_date("").props(PROPS_SAISIE).classes("w-28")
        with _cellule_saisie():
            prix = _champ_euros("", _euros(DEFAUTS_LIGNE["prix_nuit_centimes"])).props(PROPS_SAISIE).classes("w-24")
        with _cellule_saisie():
            adultes = (
                ui.number(value=DEFAUTS_LIGNE["adultes"], min=0, precision=0, format="%d")
                .props(PROPS_SAISIE)
                .classes("w-14")
            )
        with _cellule_saisie():
            enfants = (
                ui.number(value=DEFAUTS_LIGNE["enfants"], min=0, precision=0, format="%d")
                .props(PROPS_SAISIE)
                .classes("w-14")
            )
        libelle_taxe = _etiquette_colonne(A_DROITE)
        libelle_montant = _etiquette_colonne(f"{A_DROITE} font-semibold")
    ligne = BrouillonLigne(
        chambre=chambre,
        nom=nom,
        arrivee=arrivee,
        depart=depart,
        adultes=adultes,
        enfants=enfants,
        prix=prix,
        options=options,
        types_chambres=types_chambres,
        libelle_type=libelle_type,
        libelle_nuits=libelle_nuits,
        libelle_taxe=libelle_taxe,
        libelle_montant=libelle_montant,
    )

    def sur_champs() -> None:
        _mettre_a_jour_brouillon(ligne)

    def sur_arrivee() -> None:
        _ajuster_depart(ligne)
        _mettre_a_jour_brouillon(ligne)

    depart.value = f"{fin:%d/%m/%Y}"
    arrivee.value = f"{debut:%d/%m/%Y}"
    _ajuster_depart(ligne)
    _mettre_a_jour_brouillon(ligne)
    chambre.on_value_change(sur_champs)
    arrivee.on_value_change(sur_arrivee)
    depart.on_value_change(sur_champs)
    adultes.on_value_change(sur_champs)
    prix.on_value_change(sur_champs)
    return ligne


def _dialogue_clients(appliquer: Callable[[dict], None]) -> Callable[[str], None]:
    generation = 0
    creation_en_cours = False

    with ui.dialog() as dialogue, ui.card().classes("w-[32rem] gap-3 p-5"):
        ui.label("Choisir un client").classes("text-base font-semibold")
        with ui.row().classes("w-full items-center no-wrap gap-2"):
            recherche = (
                ui.input(placeholder="Rechercher un client")
                .props("clearable autofocus")
                .classes("flex-1")
                .mark("recherche-client")
            )
            bouton_plus = ui.button("+").props("flat").classes("text-lg min-w-10 px-3")
            bouton_plus.tooltip("Créer ce client")
            bouton_plus.set_enabled(False)
            bouton_plus.mark("creer-client")
        liste = ui.column().classes("w-full gap-0 max-h-80 overflow-y-auto")

    def autoriser() -> None:
        bouton_plus.set_enabled(bool((recherche.value or "").strip()) and not creation_en_cours)

    def choisir(client: dict) -> None:
        dialogue.close()
        appliquer(client)

    def afficher(clients: list[dict]) -> None:
        liste.clear()
        with liste:
            if not clients:
                ui.label("Aucun client ne correspond").classes("text-sm text-ardoise px-1 py-2")
                return
            for client in clients:
                (
                    ui.button(libelle_client(client), on_click=lambda choisi=client: choisir(choisi))
                    .props("flat align=left")
                    .classes("w-full justify-start font-normal")
                    .mark(f"resultat-client-{client['id']}")
                )

    async def rafraichir() -> None:
        nonlocal generation
        generation += 1
        courant = generation
        texte = recherche.value or ""
        trouves = await run.io_bound(rechercher_clients, texte)
        if courant != generation or liste.is_deleted:
            return
        afficher(trouves)
        autoriser()

    async def creer() -> None:
        nonlocal creation_en_cours
        nom = (recherche.value or "").strip()
        if not nom or creation_en_cours:
            return
        creation_en_cours = True
        bouton_plus.set_enabled(False)
        try:
            nouveau_id = await run.io_bound(creer_client, nom)
            client = await run.io_bound(lire_client, nouveau_id)
        except Exception:
            logger.exception("Création du client impossible")
            creation_en_cours = False
            autoriser()
            ui.notify("Le client n'a pas pu être créé", type="warning")
            return
        creation_en_cours = False
        if client is None:
            autoriser()
            ui.notify("Le client n'a pas pu être créé", type="warning")
            return
        dialogue.close()
        ui.notify("Client créé", type="positive")
        appliquer(client)

    def ouvrir(texte: str = "") -> None:
        dialogue.open()
        if (recherche.value or "") != texte:
            recherche.set_value(texte)
            return
        autoriser()
        background_tasks.create(rafraichir(), context=liste)

    recherche.on_value_change(autoriser)
    recherche.on_value_change(rafraichir)
    bouton_plus.on_click(creer)
    return ouvrir


def _dialogue_ligne(
    user_id: int | None, apres: Callable[[], Awaitable[None]]
) -> Callable[[dict], Awaitable[None]]:
    options: dict[int, str] = {}
    sejour_id: int | None = None
    suppression_armee = False

    def apercu_a_jour() -> None:
        debut, fin = _lire_date(arrivee.value), _lire_date(depart.value)
        if debut is None or fin is None or fin <= debut:
            apercu.set_text("Le départ doit être après l'arrivée.")
            return
        nombre = nuits(debut, fin)
        montant = montant_ligne(centimes(prix.value or 0), nombre)
        taxe = taxe_sejour(int(adultes.value or 0), nombre)
        apercu.set_text(
            f"{nombre} nuit{'s' if nombre > 1 else ''} · montant {format_euros(montant)}"
            f" · taxe de séjour {format_euros(taxe)}"
        )

    def arrivee_changee() -> None:
        debut, fin = _lire_date(arrivee.value), _lire_date(depart.value)
        if debut and (fin is None or fin <= debut):
            depart.value = f"{debut + timedelta(days=1):%d/%m/%Y}"
        apercu_a_jour()

    async def enregistrer() -> None:
        debut, fin = _lire_date(arrivee.value), _lire_date(depart.value)
        if chambre.value is None or debut is None or fin is None:
            ui.notify("Choisissez la chambre et les dates d'arrivée et de départ", type="warning")
            return
        champs = {
            "chambre_id": chambre.value,
            "date_debut": debut,
            "date_fin": fin,
            "adultes": int(adultes.value or 0),
            "enfants": int(enfants.value or 0),
            "prix_nuit_centimes": centimes(prix.value or 0),
            "nom_client": nom.value,
            "user_id": user_id,
        }
        try:
            await run.io_bound(modifier_sejour, sejour_id, **champs)
        except ChambreOccupee as erreur:
            ui.notify(str(erreur), type="negative")
            return
        except SejourInvalide as erreur:
            ui.notify(str(erreur), type="warning")
            return
        dialogue.close()
        ui.notify("Ligne modifiée", type="positive")
        await apres()

    async def supprimer() -> None:
        nonlocal suppression_armee
        if not suppression_armee:
            suppression_armee = True
            bouton_supprimer.set_text("Confirmer la suppression")
            return
        await run.io_bound(supprimer_sejour, sejour_id, user_id)
        dialogue.close()
        ui.notify("Ligne supprimée", type="positive")
        await apres()

    with ui.dialog() as dialogue, ui.card().classes("w-[34rem] gap-4 p-5"):
        titre = ui.label().classes("text-base font-semibold")
        chambre = ui.select({}, label="Chambre", with_input=True).classes("w-full")
        with ui.grid(columns=2).classes("w-full gap-3"):
            arrivee = _champ_date("Arrivée").on_value_change(arrivee_changee)
            depart = _champ_date("Départ").on_value_change(apercu_a_jour).mark("depart-ligne")
            adultes = ui.number("Adultes", min=0, precision=0, format="%d").on_value_change(apercu_a_jour)
            enfants = ui.number("Enfants", min=0, precision=0, format="%d")
            prix = _champ_euros("Prix TTC/nuit").on_value_change(apercu_a_jour)
        nom = ui.input("Nom sur le séjour, si différent du client").classes("w-full")
        apercu = ui.label().classes("text-sm text-ardoise tabular-nums")
        with ui.row().classes("w-full items-center gap-2 pt-1"):
            bouton_supprimer = ui.button("Supprimer la ligne", icon="delete", on_click=supprimer).props(
                "flat color=negative"
            )
            ui.space()
            ui.button("Annuler", on_click=dialogue.close).props("flat color=ardoise")
            ui.button("Enregistrer", on_click=enregistrer).mark("enregistrer-ligne")

    async def ouvrir(ligne: dict) -> None:
        nonlocal options, sejour_id, suppression_armee
        if not options:
            options = await run.io_bound(options_chambres)
        if not options:
            ui.notify("Ajoutez d'abord une chambre", type="warning")
            return
        sejour_id = ligne["id"]
        suppression_armee = False
        titre.set_text(f"Ligne de séjour · chambre {ligne['chambre_nom']}")
        chambre.set_options(options, value=ligne["chambre_id"])
        arrivee.value = f"{ligne['date_debut']:%d/%m/%Y}"
        depart.value = f"{ligne['date_fin']:%d/%m/%Y}"
        adultes.value = ligne["adultes"]
        enfants.value = ligne["enfants"]
        prix.value = _euros(ligne["prix_nuit_centimes"])
        nom.value = ligne["nom_client"] or ""
        bouton_supprimer.set_text("Supprimer la ligne")
        apercu_a_jour()
        dialogue.open()

    return ouvrir
