from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from nicegui import app, run, ui

from ma_receptionniste.consultations import (
    MODE_REGLEMENT_LABEL,
    STATUT_SEJOUR,
    fiche_sejour,
    lister_chambres,
    options_chambres,
)
from ma_receptionniste.facturation import Totaux, centimes, format_euros, montant_ligne, nuits, taxe_sejour
from ma_receptionniste.models import Client, ModeReglement, Reservation, StatutReservation
from ma_receptionniste.pages.clients import PAYS_COURANTS
from ma_receptionniste.pages.layout import badge, etat_vide, page
from ma_receptionniste.pages.theme import date_courte, date_heure, heure_locale
from ma_receptionniste.saisie import (
    CHAMPS_FICHE,
    FacturationImpossible,
    FicheInvalide,
    ajouter_consommation,
    ajouter_note,
    ajouter_reglement,
    ajouter_sejour,
    annuler_reservation,
    champs_modifies,
    enregistrer_fiche,
    facturer,
    modifier_sejour,
    supprimer_sejour,
)
from ma_receptionniste.sejours import ChambreOccupee, SejourInvalide

PARTENAIRES = ["Booking.com", "Expedia", "Airbnb", "Direct", "Téléphone", "Site web", "Agence de voyage"]
CONSOMMATIONS_COURANTES = ["Petit-déjeuner", "Parking", "Bar", "Mini-bar", "Restaurant", "Blanchisserie"]
ONGLETS_TEXTE = ("notes", "notes_internes", "notes_tempo", "facturation")
ONGLETS_COMPTES = {
    "reservations": "Réservations",
    "consommations": "Consommations",
    "reglements": "Règlements",
    "modifications": "Modifications",
}
DEFAUTS_LIGNE = {"adultes": 1, "enfants": 0, "prix_nuit_centimes": 0, "remise_pct": 0, "nom_client": None}

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
    ("Remise %", lambda ligne: f"{ligne['remise_pct']} %" if ligne["remise_pct"] else "—", A_DROITE),
    ("Adultes", lambda ligne: str(ligne["adultes"]), A_DROITE),
    ("Enfants", lambda ligne: str(ligne["enfants"]), A_DROITE),
    ("Taxe de séjour", lambda ligne: format_euros(ligne["taxe"]), A_DROITE),
    ("Montant", lambda ligne: format_euros(ligne["montant"]), f"{A_DROITE} font-semibold"),
)
GROUPES_LIGNES = ((None, 2), ("Période / Prix", 5), ("Occupation / Taxe", 3), (None, 1))
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
    remise: ui.number
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
        with page("/reservations", "Fiche séjour"):
            etat_vide(
                "search_off",
                f"La réservation n° {reservation_id} n'existe pas.",
                "Voir les réservations",
                "/reservations",
            )
        return
    user_id = app.storage.user.get("user_id")
    enregistre = _champs(donnees)
    valeurs = {cle: "" if valeur is None else valeur for cle, valeur in enregistre.items()}
    brouillon: BrouillonLigne | None = None
    ajout_en_cours = False
    enregistrement_en_cours = False

    async def recharger() -> None:
        nonlocal donnees
        donnees = await run.io_bound(fiche_sejour, reservation_id)
        for section in (entete, infos, consommations, reglements, historique, totaux, actions):
            section.refresh()
        dessiner_persiste()
        compter()
        montant_reglement.value = _euros(max(donnees["totaux"].solde, 0))

    async def enregistrer_haut() -> list[str] | None:
        nonlocal enregistre
        try:
            libelles = await run.io_bound(enregistrer_fiche, reservation_id, user_id, dict(valeurs))
        except FicheInvalide as erreur:
            ui.notify(str(erreur), type="warning")
            return None
        if libelles:
            await recharger()
            enregistre = _champs(donnees)
        return libelles

    async def confirmer() -> None:
        libelles = await enregistrer_haut()
        if libelles:
            ui.notify("Fiche enregistrée", type="positive")
        elif libelles is not None:
            ui.notify("Aucune modification à enregistrer")

    async def valider() -> None:
        if await enregistrer_haut() is not None:
            ui.navigate.to("/")

    async def partir() -> None:
        ui.navigate.to("/")

    async def abandonner() -> None:
        if champs_modifies(enregistre, valeurs):
            confirmation_abandon.open()
        else:
            await partir()

    async def emettre_facture() -> None:
        deja_emise = donnees["reservation"]["numero_facture"] is not None
        try:
            numero = await run.io_bound(facturer, reservation_id, user_id)
        except FacturationImpossible as erreur:
            ui.notify(str(erreur), type="warning")
            return
        await recharger()
        if deja_emise:
            ui.notify(f"La facture n° {numero} a déjà été émise")
        else:
            ui.notify(f"Facture n° {numero} émise", type="positive")

    async def annuler() -> None:
        await run.io_bound(annuler_reservation, reservation_id, user_id)
        await recharger()
        ui.notify("Réservation annulée", type="warning")

    async def modifier_ligne(ligne: dict) -> None:
        await ouvrir_ligne(ligne)

    async def ajouter_une_consommation() -> None:
        if not (libelle.value or "").strip() or prix_unitaire.value is None:
            ui.notify("Indiquez le libellé et le prix unitaire", type="warning")
            return
        await run.io_bound(
            ajouter_consommation,
            reservation_id,
            libelle.value,
            int(quantite.value or 1),
            centimes(prix_unitaire.value),
            user_id,
        )
        libelle.value = ""
        quantite.value = 1
        prix_unitaire.value = None
        await recharger()
        ui.notify("Consommation ajoutée", type="positive")

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
        _infos(donnees, valeurs)

    @ui.refreshable
    def consommations() -> None:
        _tableau(
            COLONNES_CONSOMMATIONS,
            [
                [
                    date_courte(heure_locale(consommation["date"])),
                    consommation["libelle"],
                    str(consommation["quantite"]),
                    format_euros(consommation["prix_unitaire_centimes"]),
                    format_euros(consommation["montant"]),
                ]
                for consommation in donnees["consommations"]
            ],
            "Aucune consommation.",
        )

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
        ui.button("Facturer", icon="receipt_long", on_click=emettre_facture).props("outline").set_enabled(not annulee)
        ui.button("Annuler la réservation", icon="event_busy", on_click=confirmation_annulation.open).props(
            "outline color=negative"
        ).set_enabled(not annulee)

    def compter() -> None:
        for cle, onglet in onglets_comptes.items():
            onglet.props["label"] = f"{ONGLETS_COMPTES[cle]} ({donnees['compteurs'][cle]})"

    ui.add_body_html(RACCOURCIS)
    ui.on("fiche-confirmer", confirmer)
    ui.on("fiche-abandon", abandonner)

    with page("/reservations", "Fiche séjour"):
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
        with ui.card().props("flat bordered").classes("w-full rounded-lg p-0 gap-0"):
            entete()
            with ui.element("div").classes("w-full grid grid-cols-12 gap-6 px-6 py-5"):
                with ui.column().classes("col-span-5 gap-0"):
                    infos()
                with ui.column().classes("col-span-7 gap-0"):
                    _onglets_contacts(valeurs)

            with ui.column().classes("w-full gap-0 border-t border-slate-200"):
                with (
                    ui.tabs(value="reservations")
                    .props("dense align=left no-caps inline-label active-color=primary indicator-color=primary")
                    .classes("w-full px-3 text-ardoise border-b border-slate-200") as onglets
                ):
                    onglets_comptes = {cle: ui.tab(cle) for cle in ONGLETS_COMPTES}
                    with ui.tab("tickets", "Tickets").props("disable"):
                        ui.tooltip("Non relié à une caisse")
                compter()
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
                            remise = int(brouillon.remise.value or 0)
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
                                    remise,
                                    user_id,
                                )
                            except ChambreOccupee as erreur:
                                ui.notify(str(erreur), type="negative")
                            except SejourInvalide as erreur:
                                ui.notify(str(erreur), type="warning")
                            else:
                                fermer_brouillon()
                                ui.notify("Ligne ajoutée", type="positive")
                                await recharger()
                            finally:
                                enregistrement_en_cours = False

                        dessiner_persiste()
                        dessiner_pied()
                    with ui.tab_panel("consommations").classes("p-0"):
                        consommations()
                        with _barre_saisie():
                            libelle = ui.input("Libellé", autocomplete=CONSOMMATIONS_COURANTES).classes("w-64")
                            quantite = ui.number("Qté", value=1, min=1, precision=0, format="%d").classes("w-24")
                            prix_unitaire = _champ_euros("PU TTC").classes("w-36")
                            ui.button("Ajouter", icon="add", on_click=ajouter_une_consommation)
                    with ui.tab_panel("reglements").classes("p-0"):
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
            totaux()
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


def _champs(fiche: dict) -> dict:
    sources = {Client: fiche["client"], Reservation: fiche["reservation"]}
    return {cle: sources[modele][cle] for cle, (modele, _) in CHAMPS_FICHE.items()}


def _entete(fiche: dict, retour: Callable[[], Awaitable[None]]) -> None:
    statut = STATUT_SEJOUR[fiche["statut_sejour"]]
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
                ui.label(fiche["client"]["nom_complet"]).classes("text-2xl font-semibold leading-tight")
                badge(statut.libelle, statut.couleur)
            ui.label(" · ".join(details)).classes("text-sm text-ardoise")
        ui.space()
        ui.button("Planning", icon="arrow_back", on_click=retour).props("flat color=ardoise")


def _infos(fiche: dict, valeurs: dict) -> None:
    client, reservation = fiche["client"], fiche["reservation"]
    statut = STATUT_SEJOUR[fiche["statut_sejour"]]
    with ui.grid().classes("w-full gap-x-4 gap-y-2 items-center").style("grid-template-columns: 7rem 1fr"):
        _libelle("Nom")
        with ui.row().classes("w-full gap-2 no-wrap"):
            ui.input(placeholder="Nom").bind_value(valeurs, "nom").classes("flex-1")
            ui.input(placeholder="Prénom").bind_value(valeurs, "prenom").classes("flex-1")
        _libelle("Client")
        _lecture(f"{client['nom_complet']} · n° {client['id']}")
        _libelle(CHAMPS_FICHE["pays"][1])
        ui.input(autocomplete=PAYS_COURANTS).bind_value(valeurs, "pays")
        _libelle(CHAMPS_FICHE["partenaire"][1])
        ui.input(autocomplete=PARTENAIRES).bind_value(valeurs, "partenaire")
        _libelle("Statut")
        with ui.row().classes("h-10 items-center gap-4"):
            badge(statut.libelle, statut.couleur)
            ui.checkbox(CHAMPS_FICHE["traitee"][1]).bind_value(valeurs, "traitee").props("dense")
        _libelle(CHAMPS_FICHE["type_voiture"][1])
        ui.input().bind_value(valeurs, "type_voiture")
        _libelle("Date facture")
        _lecture(date_courte(reservation["date_facture"]) or "—")
        _libelle("N° facture")
        _lecture(str(reservation["numero_facture"] or "—"))


def _onglets_contacts(valeurs: dict) -> None:
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
                    for cle in ("telephone", "email"):
                        _libelle(CHAMPS_FICHE[cle][1])
                        ui.input().bind_value(valeurs, cle)
                    _libelle(CHAMPS_FICHE["adresse"][1])
                    ui.textarea().bind_value(valeurs, "adresse").props("rows=4")
            for cle in ONGLETS_TEXTE:
                with ui.tab_panel(cle).classes("p-3"):
                    ui.textarea().bind_value(valeurs, cle).props("rows=12").classes("w-full").on_value_change(
                        lambda evenement, onglet=pastilles[cle]: _pastille(onglet, evenement.value)
                    )
                _pastille(pastilles[cle], valeurs[cle])


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
        "w-full justify-end items-center gap-8 px-6 py-3 border-t border-slate-200 bg-slate-50 no-wrap"
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
        format_euros(montant_ligne(centimes(ligne.prix.value or 0), nombre, int(ligne.remise.value or 0)))
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
            remise = (
                ui.number(value=DEFAUTS_LIGNE["remise_pct"], min=0, max=100, precision=0, format="%d")
                .props(f"{PROPS_SAISIE} suffix=%")
                .classes("w-16")
            )
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
        remise=remise,
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
    remise.on_value_change(sur_champs)
    return ligne


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
        montant = montant_ligne(centimes(prix.value or 0), nombre, int(remise.value or 0))
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
            "remise_pct": int(remise.value or 0),
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
            depart = _champ_date("Départ").on_value_change(apercu_a_jour)
            adultes = ui.number("Adultes", min=0, precision=0, format="%d").on_value_change(apercu_a_jour)
            enfants = ui.number("Enfants", min=0, precision=0, format="%d")
            prix = _champ_euros("Prix TTC/nuit").on_value_change(apercu_a_jour)
            remise = (
                ui.number("Remise", min=0, max=100, precision=0, format="%d")
                .props("suffix=%")
                .on_value_change(apercu_a_jour)
            )
        nom = ui.input("Nom sur le séjour, si différent du client").classes("w-full")
        apercu = ui.label().classes("text-sm text-ardoise tabular-nums")
        with ui.row().classes("w-full items-center gap-2 pt-1"):
            bouton_supprimer = ui.button("Supprimer la ligne", icon="delete", on_click=supprimer).props(
                "flat color=negative"
            )
            ui.space()
            ui.button("Annuler", on_click=dialogue.close).props("flat color=ardoise")
            ui.button("Enregistrer", on_click=enregistrer)

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
        remise.value = ligne["remise_pct"]
        nom.value = ligne["nom_client"] or ""
        bouton_supprimer.set_text("Supprimer la ligne")
        apercu_a_jour()
        dialogue.open()

    return ouvrir
