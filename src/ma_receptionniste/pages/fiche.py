from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal

from nicegui import app, run, ui
from sqlalchemy.exc import IntegrityError

from ma_receptionniste.consultations import detail_reservation, lister_clients, options_chambres
from ma_receptionniste.dossier import (
    DossierInvalide,
    DossierSaisi,
    compte_fiche,
    euros,
    jour_fr,
    lire_montant,
    nombre_nuits,
    pourcent,
)
from ma_receptionniste.pages.layout import cadre
from ma_receptionniste.saisie import (
    ajouter_note,
    ajouter_sejour,
    modifier_sejour,
    noter_consommation,
    noter_reglement,
    noter_ticket,
    sauver_dossier,
)
from ma_receptionniste.sejours import ChambreOccupee, SejourInvalide

ETATS = {
    "en_cours": "En cours",
    "option": "Option",
    "parti": "Parti",
    "annulee": "Annulée",
}
MODES = ["CB", "Espèces", "Virement", "Prépayé", "Autre"]
DENSE = "dense outlined hide-bottom-space"
MASQUE_DATE = f'{DENSE} mask="##/##/####"'


def _lire_date(valeur: object) -> date | None:
    if not isinstance(valeur, str):
        return None
    texte = valeur.strip()
    if not texte or set(texte) <= set("_/ "):
        return None
    for forme in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texte, forme).date()
        except ValueError:
            continue
    return None


def _afficher_date(valeur: date | None) -> str:
    return jour_fr(valeur) if valeur else ""


@contextmanager
def _champ(libelle: str):
    with ui.row().classes("items-center w-full gap-2 flex-nowrap"):
        ui.label(libelle).classes("fiche-libelle")
        with ui.column().classes("flex-grow min-w-0 gap-0"):
            yield


def _texte(valeur: str = ""):
    return ui.input(value=valeur).props(DENSE).classes("w-full")


def _date_saisie(valeur: date | None):
    return ui.input(value=_afficher_date(valeur)).props(MASQUE_DATE).classes("w-full")


def _date_courte(libelle: str, valeur: date):
    return ui.input(libelle, value=_afficher_date(valeur)).props(MASQUE_DATE).classes("w-32")


def _montant_saisi(valeur: object) -> str:
    if valeur is None:
        return ""
    return euros(Decimal(valeur))


def _remise_saisie(valeur: object) -> str:
    if valeur is None:
        return "0"
    nombre = Decimal(valeur)
    if nombre == nombre.to_integral():
        return str(int(nombre))
    return euros(nombre)


def _ligne_cliquee(args: object) -> dict | None:
    if isinstance(args, dict) and "id" in args:
        return args
    if isinstance(args, (list, tuple)):
        for item in args:
            if isinstance(item, dict) and "id" in item:
                return item
    return None


@ui.page("/reservations/{reservation_id}")
async def fiche(reservation_id: int) -> None:
    detail = await run.io_bound(detail_reservation, reservation_id)
    chambres = await run.io_bound(options_chambres)
    clients = await run.io_bound(lister_clients)
    with cadre("/reservations"):
        if detail is None:
            ui.label("Réservation introuvable")
            return
        await _dossier(reservation_id, detail, chambres, clients)


async def _dossier(reservation_id: int, detail: dict, chambres: dict, clients: list[dict]) -> None:
    aujourd_hui = date.today()
    onglet = {"valeur": "sejours"}
    ajout_ouvert = {"valeur": False}
    pret = {"valeur": False}

    with ui.row().classes("items-center gap-2 w-full"):
        ui.button("Réservations", icon="arrow_back", on_click=lambda: ui.navigate.to("/reservations")).props(
            "flat dense no-caps"
        )
        ui.label("Séjour").classes("texte-discret text-sm")
        titre_nom = ui.label(detail["occupant"]).classes("text-xl font-semibold")
        ui.label(f"#{detail['id']}").classes("texte-discret text-sm")
        ui.badge(detail["etat_label"], color="negative" if detail["etat"] == "annulee" else "primary").props("outline")

    with ui.element("div").classes("fiche-haut w-full"):
        with ui.column().classes("feuille p-3 gap-2"):
            with _champ("Nom"):
                nom = _texte(detail["nom_occupant"] or detail["occupant"])
            with _champ("Client"):
                client_id = (
                    ui.select(options_client_initiales(detail), value=detail["client_id"], with_input=True)
                    .props(DENSE)
                    .classes("w-full")
                )
            with _champ("Pays de nat."):
                pays = _texte(detail["pays"] or "")
            with _champ("Partenaire"):
                partenaire = _texte(detail["partenaire"] or "")
            with ui.row().classes("items-center w-full gap-2 flex-nowrap"):
                ui.label("Statut").classes("fiche-libelle")
                etat = ui.select(ETATS, value=detail["etat"]).props(DENSE).classes("flex-grow min-w-0")
                traite = ui.checkbox("Traité", value=detail["traite"])
            with _champ("Type voiture"):
                voiture = _texte(detail["type_voiture"] or "")
            with _champ("Date facture"):
                date_facture = _date_saisie(detail["date_facture"])
            with _champ("N° facture"):
                numero = _texte(detail["numero_facture"] or "")

        with ui.column().classes("feuille p-2 gap-1 min-w-0"):
            with ui.tabs(value="notes").props("dense no-caps align=left") as onglets_notes:
                ui.tab("contacts", label="Contacts")
                ui.tab("notes", label="Notes")
                ui.tab("internes", label="Notes internes")
                ui.tab("tempo", label="Notes tempo")
                ui.tab("facturation", label="Facturation client")
            with ui.tab_panels(onglets_notes, value="notes", animated=False).classes("w-full"):
                with ui.tab_panel("contacts").classes("p-2"):
                    telephone = ui.input("Téléphone", value=detail["telephone"] or "").props(DENSE).classes("w-full")
                    email = ui.input("Email", value=detail["email"] or "").props(DENSE).classes("w-full")
                    adresse = ui.input("Adresse", value=detail["adresse"] or "").props(DENSE).classes("w-full")
                with ui.tab_panel("notes").classes("p-2"):
                    notes = ui.textarea(value=detail["notes"] or "").props(DENSE).classes("w-full note-zone")
                with ui.tab_panel("internes").classes("p-2"):
                    notes_internes = (
                        ui.textarea(value=detail["notes_internes"] or "").props(DENSE).classes("w-full note-zone")
                    )
                with ui.tab_panel("tempo").classes("p-2"):
                    notes_tempo = (
                        ui.textarea(value=detail["notes_tempo"] or "").props(DENSE).classes("w-full note-zone")
                    )
                with ui.tab_panel("facturation").classes("p-2"):
                    notes_facturation = (
                        ui.textarea(value=detail["notes_facturation"] or "").props(DENSE).classes("w-full note-zone")
                    )

    client_id.set_options({row["id"]: _libelle_client(row) for row in clients}, value=detail["client_id"])

    async def charger_client() -> None:
        if not pret["valeur"]:
            return
        info = next((row for row in clients if row["id"] == client_id.value), None)
        if info is None:
            return
        pays.set_value(info["pays"] or "")
        telephone.set_value(info["telephone"] or "")
        email.set_value(info["email"] or "")
        adresse.set_value(info["adresse"] or "")

    client_id.on_value_change(charger_client)

    def saisi() -> DossierSaisi:
        facture = _lire_date(date_facture.value)
        if date_facture.value and facture is None:
            raise DossierInvalide("Date de facture illisible")
        if client_id.value is None:
            raise DossierInvalide("Choisissez un client")
        return DossierSaisi(
            client_id=int(client_id.value),
            nom_occupant=nom.value,
            pays=pays.value,
            telephone=telephone.value,
            email=email.value,
            adresse=adresse.value,
            partenaire=partenaire.value,
            etat=str(etat.value),
            traite=bool(traite.value),
            type_voiture=voiture.value,
            date_facture=facture,
            numero_facture=numero.value,
            notes=notes.value,
            notes_internes=notes_internes.value,
            notes_tempo=notes_tempo.value,
            notes_facturation=notes_facturation.value,
        )

    async def sauver() -> bool:
        try:
            formulaire = saisi()
        except DossierInvalide as exc:
            ui.notify(str(exc), type="warning")
            return False
        try:
            await run.io_bound(sauver_dossier, reservation_id, formulaire)
        except ChambreOccupee:
            ui.notify("La chambre est déjà occupée sur cette période", type="negative")
            return False
        except DossierInvalide as exc:
            ui.notify(str(exc), type="warning")
            return False
        titre_nom.set_text((nom.value or "").strip() or detail["client"])
        return True

    edit_id: dict[str, int | None] = {"id": None}
    with ui.dialog() as dialogue:
        with ui.card().classes("w-[760px] max-w-full gap-2"):
            ui.label("Modifier la ligne").classes("text-base font-semibold")
            with ui.row().classes("items-end gap-2 flex-wrap"):
                edit_type = ui.input("Type").props(DENSE).classes("w-32")
                edit_chambre = ui.select(chambres, label="Chambre").props(DENSE).classes("w-28")
                edit_debut = ui.input("Début").props(MASQUE_DATE).classes("w-32")
                edit_fin = ui.input("Fin").props(MASQUE_DATE).classes("w-32")
                edit_prix = ui.input("Prix TTC").props(DENSE).classes("w-28")
                edit_remise = ui.input("Remise %").props(DENSE).classes("w-24")
                edit_adultes = ui.number("Adultes", min=0, precision=0).props(DENSE).classes("w-20")
                edit_enfants = ui.number("Enfants", min=0, precision=0).props(DENSE).classes("w-20")
                edit_taxe = ui.input("Taxe de séjour").props(DENSE).classes("w-28")

            async def enregistrer_ligne() -> None:
                if edit_id["id"] is None or edit_chambre.value is None:
                    ui.notify("Chambre obligatoire", type="warning")
                    return
                debut = _lire_date(edit_debut.value)
                fin = _lire_date(edit_fin.value)
                if debut is None or fin is None:
                    ui.notify("Chambre et dates obligatoires", type="warning")
                    return
                try:
                    prix = lire_montant(edit_prix.value)
                    remise = lire_montant(edit_remise.value)
                    taxe = lire_montant(edit_taxe.value)
                except DossierInvalide:
                    ui.notify("Montant illisible", type="warning")
                    return
                try:
                    await run.io_bound(
                        modifier_sejour,
                        edit_id["id"],
                        int(edit_chambre.value),
                        debut,
                        fin,
                        type_produit=edit_type.value,
                        prix_ttc=prix,
                        remise_pct=Decimal("0") if remise is None else remise,
                        adultes=int(edit_adultes.value or 0),
                        enfants=int(edit_enfants.value or 0),
                        taxe_sejour=taxe,
                    )
                except ChambreOccupee:
                    ui.notify("La chambre est déjà occupée sur cette période", type="negative")
                    return
                except SejourInvalide as exc:
                    ui.notify(str(exc), type="warning")
                    return
                dialogue.close()
                await milieu.refresh()
                ui.notify("Ligne mise à jour", type="positive")

            with ui.row().classes("justify-end w-full"):
                ui.button("Fermer", on_click=dialogue.close).props("flat no-caps")
                ui.button("Enregistrer", on_click=enregistrer_ligne).props("unelevated no-caps")

    def ouvrir_ligne(evenement) -> None:
        ligne = _ligne_cliquee(evenement.args)
        if ligne is None:
            return
        edit_id["id"] = ligne["id"]
        edit_type.set_value(ligne["type_produit"])
        edit_chambre.set_value(ligne["chambre_id"])
        edit_debut.set_value(ligne["debut_label"])
        edit_fin.set_value(ligne["fin_label"])
        edit_prix.set_value(ligne["prix_saisi"])
        edit_remise.set_value(ligne["remise_saisie"])
        edit_adultes.set_value(ligne["adultes"])
        edit_enfants.set_value(ligne["enfants"])
        edit_taxe.set_value(ligne["taxe_saisie"])
        dialogue.open()

    @ui.refreshable
    async def milieu() -> None:
        fiche_detail = await run.io_bound(detail_reservation, reservation_id)
        if fiche_detail is None:
            ui.label("Réservation introuvable")
            return
        compte = compte_fiche(fiche_detail["sejours"], fiche_detail["consommations"], fiche_detail["reglements"])
        lignes = [_ligne_tableau(sejour) for sejour in fiche_detail["sejours"]]

        def retenir(evenement) -> None:
            onglet["valeur"] = str(evenement.value)

        with ui.column().classes("feuille w-full p-2 gap-1 min-w-0"):
            with ui.tabs(value=onglet["valeur"], on_change=retenir).props("dense no-caps align=left") as onglets:
                ui.tab("sejours", label=f"Réservations ({len(fiche_detail['sejours'])})")
                ui.tab("consommations", label=f"Consommations ({len(fiche_detail['consommations'])})")
                ui.tab("reglements", label=f"Règlements ({len(fiche_detail['reglements'])})")
                ui.tab("modifications", label=f"Modifications ({len(fiche_detail['modifications'])})")
                ui.tab("tickets", label=f"Tickets ({len(fiche_detail['tickets'])})")
            with ui.tab_panels(onglets, value=onglet["valeur"], animated=False).classes("w-full"):
                with ui.tab_panel("sejours").classes("p-1 gap-2"):
                    _tableau_sejours(lignes, ouvrir_ligne)
                    if not chambres:
                        ui.label("Ajoutez une chambre avant un séjour.").classes("texte-discret")
                        ui.link("Aller aux chambres", "/chambres")
                    elif not ajout_ouvert["valeur"]:
                        ui.button(
                            "Cliquez ici pour ajouter une nouvelle ligne",
                            on_click=lambda: _ouvrir_ajout(True),
                        ).props("flat no-caps dense").classes("w-full ligne-ajout")
                    else:
                        await _formulaire_ligne(reservation_id, chambres, aujourd_hui)
                with ui.tab_panel("consommations").classes("p-2 gap-2"):
                    _tableau_simple(
                        [
                            {
                                "libelle": ligne["libelle"],
                                "quantite": ligne["quantite"],
                                "montant": euros(ligne["montant"]),
                                "jour": jour_fr(ligne["jour"]),
                            }
                            for ligne in fiche_detail["consommations"]
                        ],
                        [
                            {"name": "jour", "label": "Date", "field": "jour", "align": "left"},
                            {"name": "libelle", "label": "Libellé", "field": "libelle", "align": "left"},
                            {"name": "quantite", "label": "Qté", "field": "quantite", "align": "right"},
                            {"name": "montant", "label": "Montant", "field": "montant", "align": "right"},
                        ],
                        "Aucune consommation",
                    )
                    await _formulaire_consommation(reservation_id, aujourd_hui)
                with ui.tab_panel("reglements").classes("p-2 gap-2"):
                    _tableau_simple(
                        [
                            {
                                "jour": jour_fr(ligne["jour"]),
                                "mode": ligne["mode"],
                                "montant": euros(ligne["montant"]),
                                "reference": ligne["reference"] or "",
                            }
                            for ligne in fiche_detail["reglements"]
                        ],
                        [
                            {"name": "jour", "label": "Date", "field": "jour", "align": "left"},
                            {"name": "mode", "label": "Mode", "field": "mode", "align": "left"},
                            {"name": "reference", "label": "Référence", "field": "reference", "align": "left"},
                            {"name": "montant", "label": "Montant", "field": "montant", "align": "right"},
                        ],
                        "Aucun règlement",
                    )
                    await _formulaire_reglement(reservation_id, aujourd_hui)
                with ui.tab_panel("modifications").classes("p-2 gap-2"):
                    if not fiche_detail["modifications"]:
                        ui.label("Aucune modification").classes("texte-discret")
                    for note in fiche_detail["modifications"]:
                        with ui.column().classes("gap-0 py-2 w-full").style("border-bottom: 1px solid #e6dfd2"):
                            auteur = note["auteur"] or "sans auteur"
                            ui.label(f"{note['date'].strftime('%d/%m/%Y %H:%M')} · {auteur}").classes(
                                "text-xs texte-discret"
                            )
                            ui.label(note["description"])
                    await _formulaire_note(reservation_id)
                with ui.tab_panel("tickets").classes("p-2 gap-2"):
                    _tableau_simple(
                        [
                            {
                                "date": note["date"].strftime("%d/%m/%Y %H:%M"),
                                "objet": note["objet"],
                                "detail": note["detail"] or "",
                            }
                            for note in fiche_detail["tickets"]
                        ],
                        [
                            {"name": "date", "label": "Date", "field": "date", "align": "left"},
                            {"name": "objet", "label": "Objet", "field": "objet", "align": "left"},
                            {"name": "detail", "label": "Détail", "field": "detail", "align": "left"},
                        ],
                        "Aucun ticket",
                    )
                    await _formulaire_ticket(reservation_id)

            with ui.column().classes("w-full items-end gap-0 px-2 pb-2"):
                ui.label(f"Taxe de séjour  {euros(compte.taxe)} €").classes("text-base font-semibold")
                ui.label(
                    f"Prix TTC {euros(compte.ttc)} € · Consommations {euros(compte.consommations)} € · "
                    f"Réglé {euros(compte.regle)} € · Reste {euros(compte.reste)} €"
                ).classes("text-sm texte-discret")

    async def _ouvrir_ajout(ouvert: bool) -> None:
        ajout_ouvert["valeur"] = ouvert
        onglet["valeur"] = "sejours"
        await milieu.refresh()

    async def _formulaire_ligne(reservation_id: int, chambres: dict, aujourd_hui: date) -> None:
        with ui.column().classes("w-full gap-2 pt-1"):
            with ui.row().classes("items-end gap-2 flex-wrap"):
                type_produit = ui.input("Type").props(DENSE).classes("w-32")
                chambre = ui.select(chambres, label="Chambre", value=next(iter(chambres))).props(DENSE).classes("w-28")
                with ui.column().classes("gap-0 items-end"):
                    ui.label("Nb. jours").classes("text-xs texte-discret")
                    nuits = ui.label("1").classes("text-sm font-semibold w-10 text-right")
                arrivee = _date_courte("Début", aujourd_hui)
                depart = _date_courte("Fin", aujourd_hui + timedelta(days=1))
                prix = ui.input("Prix TTC").props(DENSE).classes("w-28")
                remise = ui.input("Remise %", value="0").props(DENSE).classes("w-24")
                adultes = ui.number("Adultes", value=1, min=0, precision=0).props(DENSE).classes("w-20")
                enfants = ui.number("Enfants", value=0, min=0, precision=0).props(DENSE).classes("w-20")
                taxe = ui.input("Taxe de séjour").props(DENSE).classes("w-28")

            def maj_nuits() -> None:
                debut = _lire_date(arrivee.value)
                fin = _lire_date(depart.value)
                nuits.set_text(str(nombre_nuits(debut, fin)) if debut and fin and fin > debut else "—")

            arrivee.on_value_change(maj_nuits)
            depart.on_value_change(maj_nuits)
            with ui.row().classes("gap-2"):
                ui.button("Ajouter la ligne", on_click=lambda: poser_ligne()).props("unelevated no-caps dense")
                ui.button("Fermer", on_click=lambda: _ouvrir_ajout(False)).props("flat no-caps dense")

        async def poser_ligne() -> None:
            debut = _lire_date(arrivee.value)
            fin = _lire_date(depart.value)
            if chambre.value is None or debut is None or fin is None:
                ui.notify("Chambre et dates obligatoires", type="warning")
                return
            try:
                prix_ttc = lire_montant(prix.value)
                remise_pct = lire_montant(remise.value)
                taxe_sejour = lire_montant(taxe.value)
            except DossierInvalide:
                ui.notify("Montant illisible", type="warning")
                return
            try:
                await run.io_bound(
                    ajouter_sejour,
                    reservation_id,
                    int(chambre.value),
                    debut,
                    fin,
                    None,
                    type_produit=type_produit.value,
                    prix_ttc=prix_ttc,
                    remise_pct=Decimal("0") if remise_pct is None else remise_pct,
                    adultes=int(adultes.value or 0),
                    enfants=int(enfants.value or 0),
                    taxe_sejour=taxe_sejour,
                )
            except ChambreOccupee:
                ui.notify("La chambre est déjà occupée sur cette période", type="negative")
                return
            except SejourInvalide as exc:
                ui.notify(str(exc), type="warning")
                return
            ajout_ouvert["valeur"] = False
            await milieu.refresh()
            ui.notify("Séjour ajouté", type="positive")

    async def _formulaire_consommation(reservation_id: int, aujourd_hui: date) -> None:
        with ui.row().classes("items-end gap-2"):
            libelle = ui.input("Libellé").props(DENSE).classes("w-48")
            quantite = ui.number("Qté", value=1, min=1, precision=0).props(DENSE).classes("w-20")
            montant = ui.input("Montant").props(DENSE).classes("w-28")
            jour = _date_courte("Date", aujourd_hui)

            async def ajouter() -> None:
                try:
                    valeur = lire_montant(montant.value)
                except DossierInvalide:
                    ui.notify("Montant illisible", type="warning")
                    return
                if valeur is None:
                    ui.notify("Le montant est obligatoire", type="warning")
                    return
                quand = _lire_date(jour.value)
                if quand is None:
                    ui.notify("Date obligatoire", type="warning")
                    return
                try:
                    await run.io_bound(
                        noter_consommation,
                        reservation_id,
                        libelle.value,
                        int(quantite.value or 1),
                        valeur,
                        quand,
                    )
                except DossierInvalide as exc:
                    ui.notify(str(exc), type="warning")
                    return
                onglet["valeur"] = "consommations"
                await milieu.refresh()

            ui.button("Ajouter", on_click=ajouter).props("unelevated no-caps dense")

    async def _formulaire_reglement(reservation_id: int, aujourd_hui: date) -> None:
        with ui.row().classes("items-end gap-2"):
            mode = ui.select(MODES, label="Mode", value="CB").props(DENSE).classes("w-32")
            montant = ui.input("Montant").props(DENSE).classes("w-28")
            reference = ui.input("Référence").props(DENSE).classes("w-40")
            jour = _date_courte("Date", aujourd_hui)

            async def ajouter() -> None:
                try:
                    valeur = lire_montant(montant.value)
                except DossierInvalide:
                    ui.notify("Montant illisible", type="warning")
                    return
                if valeur is None:
                    ui.notify("Le montant est obligatoire", type="warning")
                    return
                quand = _lire_date(jour.value)
                if quand is None:
                    ui.notify("Date obligatoire", type="warning")
                    return
                try:
                    await run.io_bound(
                        noter_reglement,
                        reservation_id,
                        str(mode.value),
                        valeur,
                        quand,
                        reference.value,
                    )
                except DossierInvalide as exc:
                    ui.notify(str(exc), type="warning")
                    return
                onglet["valeur"] = "reglements"
                await milieu.refresh()

            ui.button("Ajouter", on_click=ajouter).props("unelevated no-caps dense")

    async def _formulaire_note(reservation_id: int) -> None:
        with ui.row().classes("items-end gap-2 w-full"):
            description = ui.textarea("Note").props(DENSE).classes("w-96")

            async def noter() -> None:
                if not (description.value or "").strip():
                    ui.notify("La note est vide", type="warning")
                    return
                try:
                    await run.io_bound(
                        ajouter_note,
                        reservation_id,
                        app.storage.user.get("user_id"),
                        description.value,
                    )
                except IntegrityError:
                    ui.notify("Impossible d'enregistrer la note", type="negative")
                    return
                onglet["valeur"] = "modifications"
                await milieu.refresh()
                ui.notify("Note ajoutée", type="positive")

            ui.button("Ajouter la note", on_click=noter).props("unelevated no-caps dense")

    async def _formulaire_ticket(reservation_id: int) -> None:
        with ui.row().classes("items-end gap-2"):
            objet = ui.input("Objet").props(DENSE).classes("w-48")
            detail_ticket = ui.input("Détail").props(DENSE).classes("w-64")

            async def ajouter() -> None:
                try:
                    await run.io_bound(noter_ticket, reservation_id, objet.value, detail_ticket.value)
                except DossierInvalide as exc:
                    ui.notify(str(exc), type="warning")
                    return
                onglet["valeur"] = "tickets"
                await milieu.refresh()

            ui.button("Ajouter", on_click=ajouter).props("unelevated no-caps dense")

    async def confirmer() -> None:
        avant = etat.value
        etat.set_value("en_cours")
        if not await sauver():
            etat.set_value(avant)
            return
        if avant != "en_cours":
            await run.io_bound(
                ajouter_note,
                reservation_id,
                app.storage.user.get("user_id"),
                "Réservation confirmée",
            )
            await milieu.refresh()
        ui.notify("Réservation confirmée", type="positive")

    async def facturer() -> None:
        if not _lire_date(date_facture.value):
            date_facture.set_value(_afficher_date(aujourd_hui))
        if not await sauver():
            return
        if not (numero.value or "").strip():
            ui.notify("Date posée. Indiquez le numéro de facture.", type="warning")
            return
        ui.notify("Facture enregistrée", type="positive")

    async def ok() -> None:
        if await sauver():
            ui.navigate.to("/reservations")

    await milieu()
    pret["valeur"] = True

    with ui.row().classes("barre-actions w-full items-center justify-between px-3 py-2"):
        with ui.row().classes("gap-2"):
            ui.button("Facturer", on_click=facturer).props("outline no-caps")
            ui.button("Confirmer", on_click=confirmer).props("outline no-caps")
        with ui.row().classes("gap-2"):
            ui.button("OK", on_click=ok).props("unelevated no-caps")
            ui.button("Abandon", on_click=lambda: ui.navigate.to("/reservations")).props("flat no-caps")


def options_client_initiales(detail: dict) -> dict[int, str]:
    return {detail["client_id"]: detail["client"]}


def _libelle_client(row: dict) -> str:
    if row["prenom"]:
        return f"{row['prenom']} {row['nom']}"
    return row["nom"]


def _ligne_tableau(sejour: dict) -> dict:
    return {
        "id": sejour["id"],
        "chambre_id": sejour["chambre_id"],
        "type_produit": sejour["type_produit"] or "",
        "chambre": sejour["chambre_nom"],
        "nuits": sejour["nuits"],
        "debut": sejour["date_debut"].isoformat(),
        "fin": sejour["date_fin"].isoformat(),
        "debut_label": jour_fr(sejour["date_debut"]),
        "fin_label": jour_fr(sejour["date_fin"]),
        "prix": _montant_saisi(sejour["prix_ttc"]),
        "prix_saisi": _montant_saisi(sejour["prix_ttc"]),
        "remise": pourcent(sejour["remise_pct"]),
        "remise_saisie": _remise_saisie(sejour["remise_pct"]),
        "adultes": sejour["adultes"],
        "enfants": sejour["enfants"],
        "taxe": _montant_saisi(sejour["taxe_sejour"]),
        "taxe_saisie": _montant_saisi(sejour["taxe_sejour"]),
    }


def _tableau_sejours(lignes: list[dict], ouvrir) -> None:
    if not lignes:
        ui.label("Aucune ligne").classes("texte-discret px-2")
        return
    table = (
        ui.table(
            columns=[
                {"name": "type_produit", "label": "Type", "field": "type_produit", "align": "left"},
                {"name": "chambre", "label": "Chambre", "field": "chambre", "align": "left"},
                {"name": "nuits", "label": "Nb. jours", "field": "nuits", "align": "right"},
                {"name": "debut_label", "label": "Début", "field": "debut_label", "align": "left"},
                {"name": "fin_label", "label": "Fin", "field": "fin_label", "align": "left"},
                {"name": "prix", "label": "Prix TTC", "field": "prix", "align": "right"},
                {"name": "remise", "label": "Remise %", "field": "remise", "align": "right"},
                {"name": "adultes", "label": "Adultes", "field": "adultes", "align": "right"},
                {"name": "enfants", "label": "Enfants", "field": "enfants", "align": "right"},
                {"name": "taxe", "label": "Taxe de séjour", "field": "taxe", "align": "right"},
            ],
            rows=lignes,
            row_key="id",
            pagination={"rowsPerPage": 0},
        )
        .props("dense flat hide-bottom")
        .classes("w-full fiche-table")
    )
    table.on("rowClick", ouvrir)


def _tableau_simple(rows: list[dict], columns: list[dict], vide: str) -> None:
    if not rows:
        ui.label(vide).classes("texte-discret")
        return
    for index, row in enumerate(rows):
        row["cle"] = index
    ui.table(columns=columns, rows=rows, row_key="cle", pagination={"rowsPerPage": 0}).props(
        "dense flat hide-bottom"
    ).classes("w-full fiche-table")
