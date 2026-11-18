"""Parcours de facturation : saisie, aperçu, émission, consultation."""

import base64
from functools import partial
from uuid import uuid4

from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from nicegui import app, context, run, ui

from ma_receptionniste.facturation import (
    TAUX_TVA_POUR_MILLE,
    ApercuPerime,
    DestinataireFacture,
    EmissionImpossible,
    EnvoiIndisponible,
    IdentiteFacturation,
    PdfIndisponible,
    centimes,
    destinataire_de_sejour,
    email_du_sejour,
    emettre_facture,
    enregistrer_identite,
    libelle_taux,
    lire_facture,
    lire_identite,
    lister_factures,
    numero_sans_archive,
    obtenir_facture_courante,
    preparer_apercu,
)
from ma_receptionniste.facturation_email import envoi_configure, envoyer_facture
from ma_receptionniste.facturation_pdf import generer_pdf, generer_pdf_apercu
from ma_receptionniste.models import FormeJuridique, RegimeTVA

_CHEMIN_PDF = "/factures/{facture_id}.pdf"
LIBELLES_FORME = {
    FormeJuridique.ei: "Entrepreneur individuel",
    FormeJuridique.eurl: "EURL",
    FormeJuridique.sarl: "SARL",
    FormeJuridique.sasu: "SASU",
    FormeJuridique.sas: "SAS",
    FormeJuridique.sa: "SA",
    FormeJuridique.sci: "SCI",
    FormeJuridique.association: "Association",
    FormeJuridique.autre: "Autre",
}
LIBELLES_REGIME = {
    RegimeTVA.assujetti: "Assujetti à la TVA",
    RegimeTVA.franchise: "Franchise en base",
    RegimeTVA.exonere: "Exonéré",
}


def _pdf(facture_id: int):
    """Sert le PDF d'une facture déjà émise. L'accès exige une session, comme le reste de l'application."""
    if app.storage.user.get("user_id") is None:
        return RedirectResponse("/login", status_code=303)
    try:
        chemin = generer_pdf(facture_id)
    except PdfIndisponible as erreur:
        code = 404 if str(erreur) == "Facture introuvable" else 503
        return PlainTextResponse(str(erreur), status_code=code)
    return FileResponse(
        chemin,
        media_type="application/pdf",
        filename=chemin.name,
        content_disposition_type="inline",
    )


def enregistrer_route_pdf() -> None:
    """Enregistre GET /factures/{id}.pdf une seule fois.

    Appelée à l'import et depuis la fiche. Les tests NiceGUI vident les routes
    sans réimporter ce module, le second appel les remet en place.
    """
    if any(getattr(route, "path", None) == _CHEMIN_PDF for route in app.routes):
        return
    app.add_api_route(_CHEMIN_PDF, _pdf, methods=["GET"])


enregistrer_route_pdf()


async def carte_identite_hotel() -> None:
    """Carte « Informations de facturation de l'hôtel » sur la page Paramètres.

    L'enregistrement accepte une fiche incomplète. L'émission d'une facture,
    elle, refuse tant qu'une mention obligatoire manque.
    """
    identite = await run.io_bound(lire_identite)
    valeurs = {
        "nom_commercial": identite.nom_commercial or "",
        "denomination": identite.denomination or "",
        "forme": None if identite.forme_juridique is None else identite.forme_juridique.value,
        "capital": None if identite.capital_centimes is None else identite.capital_centimes / 100,
        "adresse_siege": identite.adresse_siege or "",
        "adresse_facturation": identite.adresse_facturation or "",
        "siren": identite.siren or "",
        "siret": identite.siret or "",
        "immatriculation": identite.immatriculation or "",
        "numero_tva": identite.numero_tva or "",
        "regime": None if identite.regime_tva is None else identite.regime_tva.value,
        "taux": identite.taux_hebergement_pour_mille,
        "delai": identite.delai_paiement_jours,
        "conditions": identite.conditions_paiement or "",
        "escompte": identite.escompte or "",
        "penalites": identite.penalites or "",
    }

    champs: dict = {}

    async def enregistrer() -> None:
        for cle, element in champs.items():
            valeurs[cle] = element.value
        try:
            await run.io_bound(enregistrer_identite, _identite_saisie(valeurs))
        except EmissionImpossible as erreur:
            ui.notify(str(erreur), type="warning")
            return
        ui.notify("Informations de facturation enregistrées", type="positive")

    with ui.card().props("flat bordered").classes("w-full rounded-lg px-4 py-3 gap-3"):
        ui.label("Informations de facturation de l'hôtel").classes("text-sm font-semibold")
        ui.label(
            "La fiche peut être remplie en plusieurs fois. "
            "L'émission reste bloquée tant qu'une mention obligatoire manque."
        ).classes("text-sm text-ardoise")
        with ui.grid(columns=2).classes("w-full gap-3"):
            champs["nom_commercial"] = ui.input("Nom commercial").bind_value(valeurs, "nom_commercial").mark(
                "nom-commercial"
            )
            champs["denomination"] = ui.input("Dénomination sociale").bind_value(valeurs, "denomination").mark(
                "denomination-hotel"
            )
            champs["forme"] = (
                ui.select(
                    {None: "—", **{forme.value: libelle for forme, libelle in LIBELLES_FORME.items()}},
                    label="Forme juridique",
                    value=valeurs["forme"],
                )
                .bind_value(valeurs, "forme")
                .mark("forme-juridique")
            )
            champs["capital"] = (
                ui.number("Capital (€)", value=valeurs["capital"], min=0, precision=2, step=0.01)
                .bind_value(valeurs, "capital")
                .mark("capital-hotel")
            )
            champs["adresse_siege"] = ui.textarea("Adresse du siège").props("rows=3").classes("col-span-2")
            champs["adresse_siege"].bind_value(valeurs, "adresse_siege")
            champs["adresse_facturation"] = (
                ui.textarea("Adresse de facturation si elle est différente")
                .bind_value(valeurs, "adresse_facturation")
                .props("rows=2")
                .classes("col-span-2")
            )
            champs["siren"] = ui.input("SIREN").bind_value(valeurs, "siren").mark("siren-hotel")
            champs["siret"] = ui.input("SIRET").bind_value(valeurs, "siret")
            champs["immatriculation"] = (
                ui.input("Immatriculation").bind_value(valeurs, "immatriculation").classes("col-span-2")
            )
            champs["numero_tva"] = ui.input("Numéro de TVA").bind_value(valeurs, "numero_tva")
            champs["regime"] = (
                ui.select(
                    {None: "—", **{regime.value: libelle for regime, libelle in LIBELLES_REGIME.items()}},
                    label="Régime de TVA",
                    value=valeurs["regime"],
                )
                .bind_value(valeurs, "regime")
                .mark("regime-tva")
            )
            champs["taux"] = ui.select(
                {taux: libelle_taux(taux) for taux in TAUX_TVA_POUR_MILLE},
                label="TVA hébergement",
                value=valeurs["taux"],
            ).bind_value(valeurs, "taux")
            champs["delai"] = ui.number(
                "Délai de paiement (jours)", value=valeurs["delai"], min=0, precision=0
            ).bind_value(valeurs, "delai")
            champs["conditions"] = (
                ui.textarea("Conditions de paiement")
                .bind_value(valeurs, "conditions")
                .props("rows=2")
                .classes("col-span-2")
            )
            champs["escompte"] = ui.input("Escompte").bind_value(valeurs, "escompte")
            champs["penalites"] = ui.textarea("Pénalités").bind_value(valeurs, "penalites").props("rows=2")
        ui.button("Enregistrer les informations de facturation", on_click=enregistrer).mark("enregistrer-identite")


async def ouvrir_facturation(sejour_id: int, *, user_id: int | None, apres) -> None:
    """Point d'entrée du bouton Facturer sur la fiche séjour.

    Une facture courante ouvre sa consultation. Un ancien numéro sans PDF
    ouvre un message. Sinon le formulaire de saisie s'ouvre.
    ``sejour_id`` est l'identifiant de la réservation. ``apres`` recharge la fiche.
    """
    courante = await run.io_bound(obtenir_facture_courante, sejour_id)
    if courante is not None:
        await afficher_facture(courante.id, apres=apres)
        return
    heritage = await run.io_bound(numero_sans_archive, sejour_id)
    if heritage is not None:
        _dialogue_sans_archive(heritage.numero, heritage.date_facture)
        return
    await ouvrir_dialogue_facturation(sejour_id, user_id=user_id, apres=apres)


async def ouvrir_dialogue_facturation(
    sejour_id: int,
    *,
    remplace_id: int | None = None,
    user_id: int | None = None,
    apres=None,
) -> None:
    """Ouvre le formulaire « Facturation client », puis l'aperçu.

    Le champ est prérempli par la facturation du séjour, sinon par le nom de
    l'occupant. ``remplace_id`` indique la facture qu'une validation remplacera.
    """
    try:
        suggestion = await run.io_bound(destinataire_de_sejour, sejour_id)
    except EmissionImpossible as erreur:
        ui.notify(str(erreur), type="warning")
        return
    _dialogues(sejour_id, suggestion, remplace_id, user_id, apres)


async def afficher_facture(facture_id: int, *, apres=None) -> None:
    """Charge une facture émise et ouvre sa fenêtre de consultation."""
    facture = await run.io_bound(lire_facture, facture_id)
    if facture is None:
        ui.notify("Facture introuvable", type="warning")
        return
    try:
        await run.io_bound(generer_pdf, facture_id)
        erreur_pdf = None
    except PdfIndisponible as erreur:
        if str(erreur) == "Facture introuvable":
            ui.notify(str(erreur), type="warning")
            return
        erreur_pdf = str(erreur)
    historique = await run.io_bound(lister_factures, facture.sejour_id)
    email = await run.io_bound(email_du_sejour, facture.sejour_id)
    configure = envoi_configure()
    user_id = app.storage.user.get("user_id")
    page = context.client

    with page.layout:
        _contenu_facture(facture, historique, email, configure, user_id, apres, erreur_pdf)


def _contenu_facture(
    facture, historique, email: str, configure: bool, user_id: int | None, apres, erreur_pdf: str | None
) -> None:
    """Fenêtre d'une facture émise. Le corps est le PDF archivé, pas une liste de textes.

    Le bouton d'envoi reste inactif tant que l'e-mail n'est pas configuré.
    « Annule et remplace » n'apparaît que sur la facture courante.
    """
    with ui.dialog().props("persistent") as dialogue, ui.card().classes("w-full max-w-3xl gap-3"):
        ui.label(f"Facture n° {facture.numero}").classes("text-lg font-semibold")
        with ui.row().classes("w-full gap-2 flex-wrap"):
            for version in historique:
                ui.button(
                    f"n° {version.numero}",
                    on_click=partial(_rouvrir, dialogue, version.id, apres),
                ).props("outline dense" if version.id != facture.id else "dense")
        colonne = ui.column().classes("w-full")
        if erreur_pdf:
            ui.label(f"La facture n° {facture.numero} est enregistrée. {erreur_pdf}").classes("text-sm")
            ui.button(
                "Produire le PDF",
                on_click=lambda: _reessayer_pdf(colonne, facture.id),
            ).props("outline").mark("reessayer-pdf")
        else:
            _afficher_pdf(colonne, f"/factures/{facture.id}.pdf")
        if not facture.courante:
            ui.label("Cette version est conservée.").classes("text-sm text-ardoise")
        with ui.row().classes("w-full items-end gap-2"):
            ui.button("Imprimer", icon="print", on_click=lambda: _imprimer(facture.id)).mark("imprimer-facture")
            champ = ui.input("Email", value=email).classes("flex-1").mark("email-facture")
            bouton = ui.button("Envoyer par email", on_click=lambda: _envoyer(facture.id, champ)).mark(
                "envoyer-facture"
            )
            if not configure:
                bouton.disable()
                ui.label("L'envoi par email n'est pas configuré").classes("text-sm text-ardoise")
        with ui.row().classes("w-full justify-end"):
            if facture.courante:
                ui.button(
                    "Annule et remplace",
                    on_click=lambda: _remplacer(dialogue, facture.sejour_id, facture.id, user_id, apres),
                ).props("outline").mark("annule-remplace")
            ui.button("Fermer", on_click=dialogue.delete).props("flat")
    dialogue.open()


def _dialogues(
    sejour_id: int,
    suggestion: DestinataireFacture,
    remplace_id: int | None,
    user_id: int | None,
    apres,
) -> None:
    """Deux fenêtres. La saisie du nom, puis l'aperçu qui n'écrit encore rien.

    Les deux dialogues sont posés sur la page, pas dans la zone qui se
    reconstruit. Le rechargement de la fiche ne les détruit donc pas.
    """
    saisie = {"nom": suggestion.nom}
    etat: dict = {"apercu": None, "cle": None, "en_cours": False}
    page = context.client
    champs: dict = {}

    with page.layout, ui.dialog().props("persistent") as dialogue_nom, ui.card().classes("w-full max-w-lg gap-3"):
        champs["nom"] = ui.input("Facturation client").bind_value(saisie, "nom").classes("w-full").mark("nom-facture")
        with ui.row().classes("w-full justify-end"):
            ui.button("Retour", on_click=lambda: _fermer_saisie(dialogue_nom, dialogue_apercu)).props("flat").mark(
                "retour-nom"
            )
            bouton_apercu = ui.button("Aperçu", on_click=lambda: vers_apercu()).mark("apercu-facture")

    with (
        page.layout,
        ui.dialog().props("persistent").mark("dialogue-apercu") as dialogue_apercu,
        ui.card().classes("w-full max-w-3xl gap-3"),
    ):
        colonne = ui.column().classes("w-full max-h-96 overflow-y-auto")
        with ui.row().classes("w-full justify-end"):
            ui.button("Retour", on_click=lambda: _retour(dialogue_apercu, dialogue_nom)).props("flat").mark(
                "retour-apercu"
            )
            ui.button("Enregistrer", on_click=lambda: enregistrer()).mark("enregistrer-facture")

    def _destinataire() -> DestinataireFacture:
        """Reprend le nom saisi. L'adresse et le type viennent de la fiche client."""
        return DestinataireFacture(
            type=suggestion.type,
            nom=saisie["nom"] or "",
            adresse=suggestion.adresse,
            adresse_facturation=suggestion.adresse_facturation,
            siren=suggestion.siren,
            numero_tva=suggestion.numero_tva,
            reference_commande=suggestion.reference_commande,
        )

    async def vers_apercu() -> None:
        """Produit le PDF d'aperçu et l'affiche. Aucune facture n'est enregistrée."""
        if etat["en_cours"]:
            return
        etat["en_cours"] = True
        bouton_apercu.disable()
        for cle, element in champs.items():
            saisie[cle] = element.value
        try:
            apercu = await run.io_bound(
                partial(preparer_apercu, sejour_id, _destinataire(), remplace_id=remplace_id)
            )
            pdf = await run.io_bound(generer_pdf_apercu, apercu)
        except EmissionImpossible as erreur:
            ui.notify(str(erreur), type="warning")
            return
        finally:
            etat["en_cours"] = False
            bouton_apercu.enable()
        etat["apercu"] = apercu
        etat["cle"] = uuid4()
        _afficher_pdf(colonne, "data:application/pdf;base64," + base64.b64encode(pdf).decode())
        dialogue_nom.close()
        dialogue_apercu.open()

    async def enregistrer() -> None:
        """Émet la facture de l'aperçu affiché, puis ouvre sa consultation.

        Un second clic pendant l'émission est ignoré. Si le PDF échoue après
        l'enregistrement, la facture existe déjà et la consultation s'ouvre quand même.
        """
        if etat["en_cours"] or etat["apercu"] is None:
            return
        etat["en_cours"] = True
        try:
            facture = await run.io_bound(partial(emettre_facture, etat["apercu"], etat["cle"], user_id=user_id))
        except ApercuPerime as erreur:
            ui.notify(str(erreur), type="warning")
            return
        except PdfIndisponible as erreur:
            ui.notify(str(erreur), type="warning")
            courante = await run.io_bound(obtenir_facture_courante, sejour_id)
            dialogue_apercu.close()
            if apres is not None:
                await apres()
            if courante is not None:
                with page.layout:
                    _fermer_saisie(dialogue_nom, dialogue_apercu)
                    await afficher_facture(courante.id, apres=apres)
            return
        except EmissionImpossible as erreur:
            ui.notify(str(erreur), type="warning")
            return
        finally:
            etat["en_cours"] = False
        dialogue_apercu.close()
        if apres is not None:
            await apres()
        with page.layout:
            _fermer_saisie(dialogue_nom, dialogue_apercu)
            await afficher_facture(facture.id, apres=apres)

    dialogue_nom.open()


def _fermer_saisie(dialogue_nom, dialogue_apercu) -> None:
    """Ferme la saisie et l'aperçu, et retire les deux fenêtres de la page."""
    dialogue_apercu.delete()
    dialogue_nom.delete()


def _retour(dialogue_apercu, dialogue_nom) -> None:
    """Revient de l'aperçu vers la saisie. Le nom tapé est conservé."""
    dialogue_apercu.close()
    dialogue_nom.open()


def _afficher_pdf(conteneur: ui.column, source: str) -> None:
    """Affiche le PDF dans le dialogue. ``source`` est l'URL archivée ou une URI data locale."""
    conteneur.clear()
    with conteneur:
        (
            ui.element("iframe")
            .props(f'src="{source}"')
            .classes("w-full")
            .style("height: 28rem; border: 0")
            .mark("pdf-facture")
        )


async def _reessayer_pdf(conteneur: ui.column, facture_id: int) -> None:
    """Produit à nouveau le PDF d'une facture déjà émise. N'émet pas une autre facture."""
    try:
        await run.io_bound(generer_pdf, facture_id)
    except PdfIndisponible as erreur:
        ui.notify(str(erreur), type="warning")
        return
    _afficher_pdf(conteneur, f"/factures/{facture_id}.pdf")
    ui.notify("PDF produit", type="positive")


def _imprimer(facture_id: int) -> None:
    """Ouvre le PDF archivé dans un nouvel onglet."""
    ui.run_javascript(f"window.open('/factures/{int(facture_id)}.pdf', '_blank')")


async def _envoyer(facture_id: int, champ) -> None:
    """Envoie la facture à l'adresse saisie. Un échec ne crée pas une nouvelle facture."""
    try:
        await envoyer_facture(facture_id, champ.value or "")
    except EnvoiIndisponible as erreur:
        ui.notify(str(erreur), type="warning")
        return
    ui.notify("Facture envoyée", type="positive")


async def _remplacer(dialogue, sejour_id: int, facture_id: int, user_id: int | None, apres) -> None:
    """Vérifie que le remplacement est possible, puis rouvre le formulaire de saisie.

    La facture d'origine reste en place. Une nouvelle n'existe qu'après Enregistrer.
    """
    page = context.client
    facture = await run.io_bound(lire_facture, facture_id)
    if facture is None:
        return
    try:
        await run.io_bound(partial(preparer_apercu, sejour_id, facture.destinataire, remplace_id=facture_id))
    except EmissionImpossible as erreur:
        ui.notify(str(erreur), type="warning")
        return
    with page.layout:
        await ouvrir_dialogue_facturation(sejour_id, remplace_id=facture_id, user_id=user_id, apres=apres)
    dialogue.delete()


async def _rouvrir(dialogue, facture_id: int, apres) -> None:
    """Affiche une autre version de l'historique et retire la fenêtre précédente."""
    page = context.client
    with page.layout:
        await afficher_facture(facture_id, apres=apres)
    dialogue.delete()


def _dialogue_sans_archive(numero: int, jour) -> None:
    """Ancien numéro de facture sans PDF. Le remplacement est impossible."""
    with context.client.layout, ui.dialog() as dialogue, ui.card().classes("max-w-xl gap-3"):
        ui.label(f"Facture n° {numero}").classes("text-lg font-semibold")
        quand = f" du {jour:%d/%m/%Y}" if jour else ""
        ui.label(
            f"La facture n° {numero}{quand} n'a pas de PDF archivé. "
            "Annule et remplace n'est pas disponible sans cette archive."
        ).classes("text-sm")
        with ui.row().classes("w-full justify-end"):
            ui.button("Fermer", on_click=dialogue.delete).props("flat")
    dialogue.open()


def _identite_saisie(valeurs: dict) -> IdentiteFacturation:
    """Transforme les champs du formulaire hôtel en identité, euros compris en centimes."""
    forme = valeurs["forme"]
    regime = valeurs["regime"]
    capital = valeurs["capital"]
    delai = valeurs["delai"]
    return IdentiteFacturation(
        nom_commercial=valeurs["nom_commercial"],
        denomination=valeurs["denomination"],
        forme_juridique=None if not forme else FormeJuridique(forme),
        capital_centimes=None if capital is None or capital == "" else centimes(capital),
        adresse_siege=valeurs["adresse_siege"],
        adresse_facturation=valeurs["adresse_facturation"],
        siren=valeurs["siren"],
        siret=valeurs["siret"],
        immatriculation=valeurs["immatriculation"],
        numero_tva=valeurs["numero_tva"],
        regime_tva=None if not regime else RegimeTVA(regime),
        taux_hebergement_pour_mille=int(valeurs["taux"]),
        delai_paiement_jours=0 if delai is None or delai == "" else int(delai),
        conditions_paiement=valeurs["conditions"],
        escompte=valeurs["escompte"],
        penalites=valeurs["penalites"],
    )
