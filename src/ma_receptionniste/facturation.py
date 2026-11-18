"""L'argent d'un séjour, en centimes entiers, et l'émission d'une facture figée.

Les prix saisis sur le séjour sont TTC. Le HT et la TVA d'une ligne en sont dérivés
une seule fois, à l'aperçu, puis copiés. `sejour_id` désigne la réservation :
la fiche séjour facture la réservation, pas une ligne de chambre.
"""

import hashlib
import json
import os
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import func, select

from ma_receptionniste.db import get_session
from ma_receptionniste.models import (
    CategorieLigne,
    Chambre,
    Consommation,
    FormeJuridique,
    Historique,
    NatureReglement,
    RegimeTVA,
    Reglement,
    Reservation,
    Sejour,
    StatutReservation,
    TypeDestinataire,
)
from ma_receptionniste.models import (
    Facture as FactureTable,
)
from ma_receptionniste.models import (
    IdentiteFacturation as IdentiteTable,
)
from ma_receptionniste.models import (
    LigneFacture as LigneTable,
)
from ma_receptionniste.models import (
    ReglementFacture as ReglementTable,
)
from ma_receptionniste.models import (
    VentilationTVA as VentilationTable,
)

# Taux français, en millièmes. 100 = 10 %.
TAUX_TVA_POUR_MILLE = (0, 21, 55, 100, 200)
TAUX_TVA_DEFAUT = 100
FORMES_AVEC_CAPITAL = frozenset(
    {FormeJuridique.eurl, FormeJuridique.sarl, FormeJuridique.sasu, FormeJuridique.sas, FormeJuridique.sa}
)
LIBELLE_FORME = {
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
LIBELLES_MODE = {
    "especes": "Espèces",
    "carte": "Carte bancaire",
    "virement": "Virement",
    "cheque": "Chèque",
    "ota": "OTA (prépayé)",
}
LIBELLE_NATURE = {
    NatureReglement.paiement: "Paiement",
    NatureReglement.remboursement: "Remboursement",
}
MENTION_40 = "indemnité forfaitaire de recouvrement de 40 €"

TAXE_SEJOUR_CENTIMES = int(os.environ.get("TAXE_SEJOUR_CENTIMES", "200"))

_ESPACE_FINE = "\u202f"
_ESPACE_INSECABLE = "\u00a0"


@dataclass(frozen=True)
class Totaux:
    hebergement: int
    taxe_sejour: int
    consommations: int
    total: int
    regle: int
    solde: int


def nuits(debut: date, fin: date) -> int:
    """date_fin est le matin du départ : elle ne compte pas."""
    return (fin - debut).days


def montant_ligne(prix_nuit_centimes: int, nuits: int) -> int:
    return prix_nuit_centimes * nuits


def taxe_sejour(adultes: int, nuits: int) -> int:
    """Les mineurs sont exonérés : seuls les adultes paient, par nuit."""
    return adultes * nuits * TAXE_SEJOUR_CENTIMES


def montant_sejour(sejour: Sejour) -> int:
    return montant_ligne(sejour.prix_nuit_centimes, nuits(sejour.date_debut, sejour.date_fin))


def taxe_du_sejour(sejour: Sejour) -> int:
    return taxe_sejour(sejour.adultes, nuits(sejour.date_debut, sejour.date_fin))


def montant_consommation(consommation: Consommation) -> int:
    return consommation.quantite * consommation.prix_unitaire_centimes


def totaux(lignes: Iterable[Sejour], consommations: Iterable[Consommation], reglements: Iterable[Reglement]) -> Totaux:
    lignes = list(lignes)
    hebergement = sum(montant_sejour(ligne) for ligne in lignes)
    taxe = sum(taxe_du_sejour(ligne) for ligne in lignes)
    extras = sum(montant_consommation(consommation) for consommation in consommations)
    total = hebergement + taxe + extras
    regle = sum(reglement.montant_centimes for reglement in reglements)
    return Totaux(
        hebergement=hebergement,
        taxe_sejour=taxe,
        consommations=extras,
        total=total,
        regle=regle,
        solde=total - regle,
    )


def format_euros(centimes: int) -> str:
    signe = "-" if centimes < 0 else ""
    euros, reste = divmod(abs(centimes), 100)
    milliers = f"{euros:,}".replace(",", _ESPACE_FINE)
    return f"{signe}{milliers},{reste:02d}{_ESPACE_INSECABLE}€"


def centimes(euros: float | int | str) -> int:
    """Convertit une saisie en euros (champ numérique) sans passer par l'arrondi binaire d'un float."""
    return int((Decimal(str(euros)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def libelle_taux(taux_pour_mille: int) -> str:
    entier, dixieme = divmod(taux_pour_mille, 10)
    texte = f"{entier},{dixieme}" if dixieme else str(entier)
    return f"{texte}{_ESPACE_FINE}%"


class EmissionImpossible(ValueError):
    """L'aperçu ou l'émission est refusé."""


class MentionsManquantes(EmissionImpossible):
    def __init__(self, mentions: Sequence[str]) -> None:
        self.mentions = tuple(mentions)
        super().__init__("Mention obligatoire manquante : " + ", ".join(self.mentions))


class ApercuPerime(EmissionImpossible):
    def __init__(self) -> None:
        super().__init__("Les données ont changé depuis l'aperçu. Affichez un nouvel aperçu avant d'enregistrer.")


class RemplacementInterdit(EmissionImpossible):
    """Un avoir serait nécessaire. Ce parcours n'existe pas."""


class PdfIndisponible(EmissionImpossible):
    def __init__(self, message: str = "La facture est enregistrée, mais le PDF n'a pas pu être produit.") -> None:
        super().__init__(message)


class EnvoiIndisponible(EmissionImpossible):
    pass


@dataclass(frozen=True)
class IdentiteFacturation:
    nom_commercial: str | None
    denomination: str | None
    forme_juridique: FormeJuridique | None
    capital_centimes: int | None
    adresse_siege: str | None
    adresse_facturation: str | None
    siren: str | None
    siret: str | None
    immatriculation: str | None
    numero_tva: str | None
    regime_tva: RegimeTVA | None
    taux_hebergement_pour_mille: int
    delai_paiement_jours: int
    conditions_paiement: str | None
    escompte: str | None
    penalites: str | None


@dataclass(frozen=True)
class DestinataireFacture:
    type: TypeDestinataire
    nom: str
    adresse: str
    adresse_facturation: str | None
    siren: str | None
    numero_tva: str | None
    reference_commande: str | None


@dataclass(frozen=True)
class LigneFacture:
    categorie: CategorieLigne
    libelle: str
    periode_debut: date | None
    periode_fin: date | None
    quantite: int
    prix_unitaire_ht_centimes: int
    prix_unitaire_ttc_centimes: int
    remise_centimes: int
    taux_tva_pour_mille: int
    montant_ht_centimes: int
    montant_tva_centimes: int
    montant_ttc_centimes: int


@dataclass(frozen=True)
class VentilationTVA:
    taux_tva_pour_mille: int
    base_ht_centimes: int
    montant_tva_centimes: int


@dataclass(frozen=True)
class ReglementConstate:
    date: date
    mode: str
    montant_centimes: int
    nature: NatureReglement


@dataclass(frozen=True)
class TotauxFacture:
    ventilations: tuple[VentilationTVA, ...]
    total_ht_centimes: int
    total_tva_centimes: int
    total_prestations_ttc_centimes: int
    taxe_sejour_centimes: int
    total_a_payer_centimes: int
    montant_regle_centimes: int
    solde_centimes: int


@dataclass(frozen=True)
class ApercuFacture:
    sejour_id: int
    destinataire: DestinataireFacture
    identite: IdentiteFacturation
    lignes: tuple[LigneFacture, ...]
    reglements: tuple[ReglementConstate, ...]
    totaux: TotauxFacture
    date_prestation: date | None
    remplace_id: int | None
    remplace_numero: int | None
    remplace_date: date | None
    empreinte: str


@dataclass(frozen=True)
class Facture:
    id: int
    sejour_id: int
    numero: int
    date_emission: date
    date_prestation: date | None
    date_echeance: date
    courante: bool
    destinataire: DestinataireFacture
    identite: IdentiteFacturation
    lignes: tuple[LigneFacture, ...]
    reglements: tuple[ReglementConstate, ...]
    totaux: TotauxFacture
    remplace_id: int | None
    remplace_numero: int | None
    remplace_date: date | None
    pdf_empreinte: str | None


@dataclass(frozen=True)
class NumeroSansArchive:
    sejour_id: int
    numero: int
    date_facture: date | None


def identite_vide() -> IdentiteFacturation:
    return IdentiteFacturation(
        nom_commercial=None,
        denomination=None,
        forme_juridique=None,
        capital_centimes=None,
        adresse_siege=None,
        adresse_facturation=None,
        siren=None,
        siret=None,
        immatriculation=None,
        numero_tva=None,
        regime_tva=None,
        taux_hebergement_pour_mille=TAUX_TVA_DEFAUT,
        delai_paiement_jours=0,
        conditions_paiement=None,
        escompte=None,
        penalites=None,
    )


def ht_depuis_ttc(ttc_centimes: int, taux_pour_mille: int) -> int:
    """Le prix commercial est TTC. Le HT est arrondi au centime, half-up."""
    if taux_pour_mille == 0:
        return ttc_centimes
    ht = Decimal(ttc_centimes) * Decimal(1000) / Decimal(1000 + taux_pour_mille)
    return int(ht.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def ligne_ttc(
    categorie: CategorieLigne,
    libelle: str,
    quantite: int,
    prix_unitaire_ttc_centimes: int,
    taux_tva_pour_mille: int,
    *,
    periode_debut: date | None = None,
    periode_fin: date | None = None,
    remise_centimes: int = 0,
) -> LigneFacture:
    if isinstance(quantite, bool) or not isinstance(quantite, int) or quantite <= 0:
        raise EmissionImpossible("La quantité doit être un entier supérieur à 0")
    if isinstance(prix_unitaire_ttc_centimes, bool) or not isinstance(prix_unitaire_ttc_centimes, int):
        raise EmissionImpossible("Le prix doit être un entier de centimes")
    if prix_unitaire_ttc_centimes < 0 or remise_centimes < 0:
        raise EmissionImpossible("Un montant de facture ne peut pas être négatif")
    if taux_tva_pour_mille not in TAUX_TVA_POUR_MILLE:
        raise EmissionImpossible("Le taux de TVA n'est pas reconnu")
    montant_ttc = quantite * prix_unitaire_ttc_centimes - remise_centimes
    if montant_ttc < 0:
        raise EmissionImpossible("La remise dépasse le montant de la ligne")
    montant_ht = ht_depuis_ttc(montant_ttc, taux_tva_pour_mille)
    return LigneFacture(
        categorie=categorie,
        libelle=libelle,
        periode_debut=periode_debut,
        periode_fin=periode_fin,
        quantite=quantite,
        prix_unitaire_ht_centimes=ht_depuis_ttc(prix_unitaire_ttc_centimes, taux_tva_pour_mille),
        prix_unitaire_ttc_centimes=prix_unitaire_ttc_centimes,
        remise_centimes=remise_centimes,
        taux_tva_pour_mille=taux_tva_pour_mille,
        montant_ht_centimes=montant_ht,
        montant_tva_centimes=montant_ttc - montant_ht,
        montant_ttc_centimes=montant_ttc,
    )


def calculer_totaux(lignes: Sequence[LigneFacture]) -> TotauxFacture:
    bases: dict[int, list[int]] = {}
    for ligne in lignes:
        base, tva = bases.setdefault(ligne.taux_tva_pour_mille, [0, 0])
        bases[ligne.taux_tva_pour_mille] = [base + ligne.montant_ht_centimes, tva + ligne.montant_tva_centimes]
    ventilations = tuple(
        VentilationTVA(taux, montants[0], montants[1]) for taux, montants in sorted(bases.items())
    )
    total_ht = sum(ventilation.base_ht_centimes for ventilation in ventilations)
    total_tva = sum(ventilation.montant_tva_centimes for ventilation in ventilations)
    prestations = sum(ligne.montant_ttc_centimes for ligne in lignes)
    return TotauxFacture(
        ventilations=ventilations,
        total_ht_centimes=total_ht,
        total_tva_centimes=total_tva,
        total_prestations_ttc_centimes=prestations,
        taxe_sejour_centimes=0,
        total_a_payer_centimes=prestations,
        montant_regle_centimes=0,
        solde_centimes=prestations,
    )


def appliquer_taxe_et_reglements(
    totaux_lignes: TotauxFacture, taxe_sejour_centimes: int, reglements: Sequence[ReglementConstate]
) -> TotauxFacture:
    """La taxe de séjour reste hors base de TVA. Elle s'ajoute après les prestations."""
    regle = sum(reglement.montant_centimes for reglement in reglements)
    a_payer = totaux_lignes.total_prestations_ttc_centimes + taxe_sejour_centimes
    return replace(
        totaux_lignes,
        taxe_sejour_centimes=taxe_sejour_centimes,
        total_a_payer_centimes=a_payer,
        montant_regle_centimes=regle,
        solde_centimes=a_payer - regle,
    )


def normaliser_identite(identite: IdentiteFacturation) -> IdentiteFacturation:
    return replace(
        identite,
        nom_commercial=_vide(identite.nom_commercial),
        denomination=_vide(identite.denomination),
        adresse_siege=_vide(identite.adresse_siege),
        adresse_facturation=_vide(identite.adresse_facturation),
        siren=_code(identite.siren),
        siret=_code(identite.siret),
        immatriculation=_vide(identite.immatriculation),
        numero_tva=_tva(identite.numero_tva),
        conditions_paiement=_vide(identite.conditions_paiement),
        escompte=_vide(identite.escompte),
        penalites=_vide(identite.penalites),
    )


def normaliser_destinataire(destinataire: DestinataireFacture) -> DestinataireFacture:
    return replace(
        destinataire,
        nom=_vide(destinataire.nom) or "",
        adresse=_vide(destinataire.adresse) or "",
        adresse_facturation=_vide(destinataire.adresse_facturation),
        siren=_code(destinataire.siren),
        numero_tva=_tva(destinataire.numero_tva),
        reference_commande=_vide(destinataire.reference_commande),
    )


def valider_identite_facturation(identite: IdentiteFacturation) -> None:
    propre = normaliser_identite(identite)
    _verifier_format_identite(propre)
    mentions: list[str] = []
    if not propre.denomination:
        mentions.append("dénomination sociale")
    if propre.forme_juridique is None:
        mentions.append("forme juridique")
    if not propre.adresse_siege:
        mentions.append("adresse du siège")
    if not propre.siren and not propre.siret:
        mentions.append("SIREN ou SIRET")
    if propre.forme_juridique is not FormeJuridique.association and not propre.immatriculation:
        mentions.append("immatriculation")
    if propre.forme_juridique in FORMES_AVEC_CAPITAL and propre.capital_centimes is None:
        mentions.append("capital social")
    if propre.regime_tva is None:
        mentions.append("régime de TVA")
    elif propre.regime_tva is RegimeTVA.assujetti and not propre.numero_tva:
        mentions.append("numéro de TVA")
    if mentions:
        raise MentionsManquantes(mentions)


def lire_identite() -> IdentiteFacturation:
    with get_session() as session:
        return _identite_de_session(session)


def enregistrer_identite(identite: IdentiteFacturation) -> None:
    propre = normaliser_identite(identite)
    _verifier_format_identite(propre)
    with get_session() as session:
        ligne = session.get(IdentiteTable, 1)
        if ligne is None:
            ligne = IdentiteTable(id=1)
        _copier_identite(ligne, propre)
        session.add(ligne)
        session.commit()


def email_du_sejour(sejour_id: int) -> str:
    with get_session() as session:
        reservation = session.get(Reservation, sejour_id)
        if reservation is None or not reservation.client.email:
            return ""
        return reservation.client.email


def destinataire_de_sejour(sejour_id: int) -> DestinataireFacture:
    with get_session() as session:
        reservation = session.get(Reservation, sejour_id)
        if reservation is None:
            raise EmissionImpossible("Réservation introuvable")
        nom = (reservation.facturation or "").strip() or (reservation.nom_occupant or "").strip()
        return DestinataireFacture(
            type=TypeDestinataire.particulier,
            nom=(nom or "").strip(),
            adresse=(reservation.client.adresse or "").strip(),
            adresse_facturation=None,
            siren=None,
            numero_tva=None,
            reference_commande=None,
        )


def preparer_apercu(
    sejour_id: int,
    destinataire: DestinataireFacture,
    *,
    remplace_id: int | None = None,
) -> ApercuFacture:
    with get_session() as session:
        reservation = _charger(session, sejour_id)
        if reservation is None:
            raise EmissionImpossible("Réservation introuvable")
        return _composer(session, reservation, destinataire, remplace_id)


def emettre_facture(apercu: ApercuFacture, cle_idempotence: UUID, *, user_id: int | None = None) -> Facture:
    if not isinstance(cle_idempotence, UUID):
        raise EmissionImpossible("La clé d'idempotence n'est pas un UUID")
    valider_identite_facturation(apercu.identite)
    try:
        facture_id = _inserer(apercu, cle_idempotence, user_id)
    except IntegrityError:
        facture_id = _facture_deja_posee(apercu.sejour_id, cle_idempotence, apercu.remplace_id)
    try:
        from ma_receptionniste.facturation_pdf import generer_pdf

        generer_pdf(facture_id)
    except PdfIndisponible:
        raise
    except Exception as erreur:
        raise PdfIndisponible() from erreur
    facture = lire_facture(facture_id)
    if facture is None:
        raise EmissionImpossible("La facture enregistrée est introuvable")
    return facture


def obtenir_facture_courante(sejour_id: int) -> Facture | None:
    with get_session() as session:
        ligne = _courante(session, sejour_id)
        return None if ligne is None else _vue(ligne)


def lister_factures(sejour_id: int) -> list[Facture]:
    with get_session() as session:
        lignes = session.exec(
            select(FactureTable)
            .where(FactureTable.reservation_id == sejour_id)
            .options(*_chargement_facture())
            .order_by(FactureTable.numero)
        ).all()
        return [_vue(ligne) for ligne in lignes]


def lire_facture(facture_id: int) -> Facture | None:
    with get_session() as session:
        ligne = session.exec(
            select(FactureTable).where(FactureTable.id == facture_id).options(*_chargement_facture())
        ).first()
        return None if ligne is None else _vue(ligne)


def numero_sans_archive(sejour_id: int) -> NumeroSansArchive | None:
    with get_session() as session:
        if _courante(session, sejour_id) is not None:
            return None
        reservation = session.get(Reservation, sejour_id)
        if reservation is None or reservation.numero_facture is None:
            return None
        if session.exec(select(FactureTable.id).where(FactureTable.reservation_id == sejour_id)).first():
            return None
        return NumeroSansArchive(sejour_id, reservation.numero_facture, reservation.date_facture)


def contenu_apercu(apercu: ApercuFacture) -> tuple[str, ...]:
    return _contenu(
        apercu.identite,
        apercu.destinataire,
        apercu.lignes,
        apercu.reglements,
        apercu.totaux,
        apercu.date_prestation,
        apercu.remplace_numero,
        apercu.remplace_date,
        numero=None,
        emission=None,
        echeance=None,
    )


def contenu_facture(facture: Facture) -> tuple[str, ...]:
    return _contenu(
        facture.identite,
        facture.destinataire,
        facture.lignes,
        facture.reglements,
        facture.totaux,
        facture.date_prestation,
        facture.remplace_numero,
        facture.remplace_date,
        numero=facture.numero,
        emission=facture.date_emission,
        echeance=facture.date_echeance,
    )


def _contenu(
    identite: IdentiteFacturation,
    destinataire: DestinataireFacture,
    lignes: Sequence[LigneFacture],
    reglements: Sequence[ReglementConstate],
    totaux_facture: TotauxFacture,
    prestation: date | None,
    remplace_numero: int | None,
    remplace_date: date | None,
    *,
    numero: int | None,
    emission: date | None,
    echeance: date | None,
) -> tuple[str, ...]:
    texte: list[str] = []
    if numero is None:
        texte.append("Aperçu — facture non émise")
        texte.append("Numéro : non attribué")
        texte.append("Date d'émission : non attribuée")
    else:
        texte.append(f"Facture n° {numero}")
        texte.append(f"Date d'émission : {emission:%d/%m/%Y}")
    if remplace_numero is not None and remplace_date is not None:
        texte.append(f"Annule et remplace la facture n° {remplace_numero} du {remplace_date:%d/%m/%Y}")
    elif remplace_numero is not None:
        texte.append(f"Annule et remplace la facture n° {remplace_numero}")
    if prestation is not None:
        texte.append(f"Date de prestation : {prestation:%d/%m/%Y}")
    texte.extend(_lignes_hotel(identite))
    texte.append(destinataire.nom)
    texte.append(destinataire.adresse)
    if destinataire.adresse_facturation:
        texte.append(f"Adresse de facturation : {destinataire.adresse_facturation}")
    if destinataire.type is TypeDestinataire.professionnel:
        if destinataire.siren:
            texte.append(f"SIREN client {destinataire.siren}")
        if destinataire.numero_tva:
            texte.append(f"TVA client {destinataire.numero_tva}")
        if destinataire.reference_commande:
            texte.append(f"Bon de commande {destinataire.reference_commande}")
    chambres = [ligne for ligne in lignes if ligne.categorie is CategorieLigne.chambre]
    extras = [ligne for ligne in lignes if ligne.categorie is CategorieLigne.consommation]
    if chambres:
        texte.append("1. Chambres")
        texte.extend(_texte_ligne(ligne) for ligne in chambres)
    if extras:
        texte.append("2. Consommations")
        texte.extend(_texte_ligne(ligne) for ligne in extras)
    texte.append("3. Règlements")
    texte.append("Acomptes déjà facturés : aucun.")
    if reglements:
        texte.extend(
            f"{reglement.date:%d/%m/%Y} — {LIBELLES_MODE.get(reglement.mode, reglement.mode)} — "
            f"{LIBELLE_NATURE[reglement.nature]} — {format_euros(reglement.montant_centimes)}"
            for reglement in reglements
        )
    else:
        texte.append("Aucun règlement.")
    for ventilation in totaux_facture.ventilations:
        texte.append(
            f"Base HT {libelle_taux(ventilation.taux_tva_pour_mille)} : "
            f"{format_euros(ventilation.base_ht_centimes)}, TVA {format_euros(ventilation.montant_tva_centimes)}"
        )
    texte.append(f"Total HT : {format_euros(totaux_facture.total_ht_centimes)}")
    texte.append(f"Total TVA : {format_euros(totaux_facture.total_tva_centimes)}")
    texte.append(f"Total TTC des prestations : {format_euros(totaux_facture.total_prestations_ttc_centimes)}")
    if totaux_facture.taxe_sejour_centimes:
        texte.append(f"Taxe de séjour (hors base TVA) : {format_euros(totaux_facture.taxe_sejour_centimes)}")
    texte.append(f"Total à payer : {format_euros(totaux_facture.total_a_payer_centimes)}")
    texte.append(f"Montant réglé : {format_euros(totaux_facture.montant_regle_centimes)}")
    texte.append(f"Solde : {format_euros(totaux_facture.solde_centimes)}")
    if emission is None:
        if identite.delai_paiement_jours == 0:
            texte.append("Échéance : à réception.")
        else:
            texte.append(f"Échéance : {identite.delai_paiement_jours} jours après l'émission.")
    elif identite.delai_paiement_jours == 0:
        texte.append("Échéance : à réception.")
    else:
        texte.append(f"Échéance : {echeance:%d/%m/%Y} ({identite.delai_paiement_jours} jours).")
    texte.append(f"Escompte : {identite.escompte}." if identite.escompte else "Escompte : néant.")
    if identite.conditions_paiement:
        texte.append(identite.conditions_paiement)
    if destinataire.type is TypeDestinataire.professionnel:
        if identite.penalites:
            texte.append(identite.penalites)
        if MENTION_40 not in (identite.penalites or ""):
            texte.append(f"En cas de retard de paiement : pénalités au taux légal et {MENTION_40}.")
    return tuple(texte)


def _texte_ligne(ligne: LigneFacture) -> str:
    texte = (
        f"{ligne.libelle} : quantité {ligne.quantite}, "
        f"prix unitaire {format_euros(ligne.prix_unitaire_ht_centimes)} HT, "
        f"TVA {libelle_taux(ligne.taux_tva_pour_mille)}, "
        f"{format_euros(ligne.montant_ht_centimes)} HT, {format_euros(ligne.montant_ttc_centimes)} TTC"
    )
    if ligne.remise_centimes:
        texte += f", remise {format_euros(ligne.remise_centimes)}"
    if ligne.categorie is CategorieLigne.chambre and ligne.periode_debut and ligne.periode_fin:
        texte += f", du {ligne.periode_debut:%d/%m/%Y} au {ligne.periode_fin:%d/%m/%Y}"
    return texte


def _lignes_hotel(identite: IdentiteFacturation) -> list[str]:
    lignes: list[str] = []
    if identite.nom_commercial:
        lignes.append(identite.nom_commercial)
    if identite.denomination:
        lignes.append(identite.denomination)
    if identite.forme_juridique is not None:
        forme = LIBELLE_FORME[identite.forme_juridique]
        if identite.forme_juridique in FORMES_AVEC_CAPITAL and identite.capital_centimes is not None:
            forme = f"{forme} au capital de {format_euros(identite.capital_centimes)}"
        lignes.append(forme)
    if identite.adresse_siege:
        lignes.append(identite.adresse_siege)
    if identite.adresse_facturation:
        lignes.append(f"Adresse de facturation : {identite.adresse_facturation}")
    if identite.siren:
        lignes.append(f"SIREN {identite.siren}")
    if identite.siret:
        lignes.append(f"SIRET {identite.siret}")
    if identite.immatriculation:
        lignes.append(identite.immatriculation)
    if identite.regime_tva is RegimeTVA.assujetti and identite.numero_tva:
        lignes.append(f"N° TVA {identite.numero_tva}")
    elif identite.regime_tva is RegimeTVA.franchise:
        lignes.append("TVA non applicable, article 293 B du CGI")
    elif identite.regime_tva is RegimeTVA.exonere:
        lignes.append("Exonération de TVA")
    return lignes


def _verifier_format_identite(identite: IdentiteFacturation) -> None:
    if identite.siren and not _siren_valide(identite.siren):
        raise EmissionImpossible("Le SIREN doit comporter 9 chiffres")
    if identite.siret and not _siret_valide(identite.siret):
        raise EmissionImpossible("Le SIRET doit comporter 14 chiffres")
    if identite.siren and identite.siret and not identite.siret.startswith(identite.siren):
        raise EmissionImpossible("Le SIRET ne correspond pas au SIREN")
    if identite.numero_tva and not _tva_valide(identite.numero_tva):
        raise EmissionImpossible("Le numéro de TVA n'est pas reconnu")
    if identite.taux_hebergement_pour_mille not in TAUX_TVA_POUR_MILLE:
        raise EmissionImpossible("Le taux de TVA de l'hébergement n'est pas reconnu")
    if isinstance(identite.delai_paiement_jours, bool) or identite.delai_paiement_jours < 0:
        raise EmissionImpossible("Le délai de paiement ne peut pas être négatif")
    if identite.capital_centimes is not None and identite.capital_centimes < 0:
        raise EmissionImpossible("Le capital ne peut pas être négatif")


def _composer(
    session, reservation: Reservation, destinataire: DestinataireFacture, remplace_id: int | None
) -> ApercuFacture:
    if reservation.statut == StatutReservation.annulee:
        raise EmissionImpossible("Une réservation annulée ne peut pas être facturée")
    identite = _identite_de_session(session)
    valider_identite_facturation(identite)
    destinataire = normaliser_destinataire(destinataire)
    courante = _courante(session, reservation.id)
    remplace_numero = None
    remplace_date = None
    if remplace_id is None:
        if courante is not None or reservation.numero_facture is not None:
            raise EmissionImpossible("Une facture est déjà émise pour ce séjour")
    else:
        _controler_remplacement(session, reservation, courante, remplace_id)
        ancienne = session.get(FactureTable, remplace_id)
        remplace_numero = ancienne.numero
        remplace_date = ancienne.date_emission
    lignes = tuple(_lignes_sejour(reservation, identite.taux_hebergement_pour_mille))
    reglements = tuple(_reglements_sejour(reservation))
    taxe = sum(taxe_du_sejour(sejour) for sejour in reservation.sejours)
    totaux_facture = appliquer_taxe_et_reglements(calculer_totaux(lignes), taxe, reglements)
    dates = [sejour.date_debut for sejour in reservation.sejours]
    apercu = ApercuFacture(
        sejour_id=reservation.id,
        destinataire=destinataire,
        identite=identite,
        lignes=lignes,
        reglements=reglements,
        totaux=totaux_facture,
        date_prestation=min(dates) if dates else None,
        remplace_id=remplace_id,
        remplace_numero=remplace_numero,
        remplace_date=remplace_date,
        empreinte="",
    )
    return replace(apercu, empreinte=_empreinte(apercu))


def _inserer(apercu: ApercuFacture, cle: UUID, user_id: int | None) -> int:
    with get_session() as session:
        _verrouiller_compteur(session)
        existante = session.exec(select(FactureTable).where(FactureTable.cle_idempotence == str(cle))).first()
        if existante is not None:
            session.commit()
            return existante.id
        reservation = _charger(session, apercu.sejour_id)
        if reservation is None:
            raise EmissionImpossible("Réservation introuvable")
        frais = _composer(session, reservation, apercu.destinataire, apercu.remplace_id)
        if frais.empreinte != apercu.empreinte:
            raise ApercuPerime()
        _controler_date(session, date.today())
        numero = _numero_suivant(session)
        emission = date.today()
        echeance = emission + timedelta(days=frais.identite.delai_paiement_jours)
        ancienne = _courante(session, reservation.id) if frais.remplace_id is not None else None
        if ancienne is not None:
            ancienne.courante = False
            session.add(ancienne)
            session.flush()
        ligne = _table_depuis_apercu(frais, numero, cle, emission, echeance)
        session.add(ligne)
        session.flush()
        _ajouter_details(session, ligne.id, frais)
        reservation.facturation = frais.destinataire.nom
        reservation.numero_facture = numero
        reservation.date_facture = emission
        session.add(reservation)
        description = f"Facture n° {numero} émise"
        if frais.remplace_numero is not None:
            description += f" en remplacement de la facture n° {frais.remplace_numero}"
        session.add(
            Historique(
                reservation_id=reservation.id,
                user_id=user_id,
                description=description,
                date=datetime.now(UTC),
            )
        )
        session.commit()
        return ligne.id


def _facture_deja_posee(sejour_id: int, cle: UUID, remplace_id: int | None) -> int:
    with get_session() as session:
        existante = session.exec(select(FactureTable).where(FactureTable.cle_idempotence == str(cle))).first()
        if existante is not None:
            return existante.id
        courante = _courante(session, sejour_id)
        if courante is not None and remplace_id is not None and courante.remplace_id == remplace_id:
            return courante.id
        if courante is not None and remplace_id is None:
            raise EmissionImpossible("Une facture est déjà émise pour ce séjour")
    raise EmissionImpossible("Le numéro de facture n'a pas pu être attribué")


def _controler_remplacement(session, reservation: Reservation, courante: FactureTable | None, remplace_id: int) -> None:
    ancienne = session.get(FactureTable, remplace_id)
    if ancienne is None or ancienne.reservation_id != reservation.id:
        raise RemplacementInterdit("La facture à remplacer est introuvable")
    if courante is None or courante.id != remplace_id:
        raise RemplacementInterdit("Une facture plus récente existe déjà")
    live = sum(reglement.montant_centimes for reglement in reservation.reglements)
    if live == 0 and ancienne.montant_regle_centimes == 0:
        return
    if live >= ancienne.total_a_payer_centimes or ancienne.montant_regle_centimes >= ancienne.total_a_payer_centimes:
        raise RemplacementInterdit(
            "Cette facture est déjà réglée. Un avoir serait nécessaire, et ce parcours n'est pas disponible."
        )
    raise RemplacementInterdit(
        "Cette facture est partiellement réglée. Un avoir serait nécessaire, et ce parcours n'est pas disponible."
    )


def _controler_date(session, jour: date) -> None:
    derniere_facture = session.exec(select(func.max(FactureTable.date_emission))).one()
    derniere_legacy = session.exec(select(func.max(Reservation.date_facture))).one()
    dates = [valeur for valeur in (derniere_facture, derniere_legacy) if valeur is not None]
    if dates and jour < max(dates):
        raise EmissionImpossible(
            f"La date d'émission {jour:%d/%m/%Y} serait antérieure à une facture déjà numérotée."
        )


def _verrouiller_compteur(session) -> None:
    connexion = session.connection()
    connexion.execute(
        text(
            "INSERT INTO compteur_facture (id, dernier_numero) "
            "SELECT 1, 0 WHERE NOT EXISTS (SELECT 1 FROM compteur_facture WHERE id = 1)"
        )
    )
    connexion.execute(text("UPDATE compteur_facture SET dernier_numero = dernier_numero WHERE id = 1"))


def _numero_suivant(session) -> int:
    resultat = session.connection().execute(
        text(
            """
            UPDATE compteur_facture
            SET dernier_numero = (
                MAX(
                    dernier_numero,
                    COALESCE((SELECT MAX(numero) FROM facture), 0),
                    COALESCE((SELECT MAX(numero_facture) FROM reservation), 0)
                ) + 1
            )
            WHERE id = 1
            RETURNING dernier_numero
            """
        )
    )
    return int(resultat.scalar_one())


def _lignes_sejour(reservation: Reservation, taux_hebergement: int) -> list[LigneFacture]:
    lignes: list[LigneFacture] = []
    for sejour in sorted(reservation.sejours, key=lambda item: (item.date_debut, item.id or 0)):
        quantite = nuits(sejour.date_debut, sejour.date_fin)
        if quantite <= 0:
            continue
        type_nom = sejour.chambre.type_de_chambre.libelle if sejour.chambre.type_de_chambre else None
        libelle = f"Chambre {sejour.chambre.nom}"
        if type_nom and type_nom != sejour.chambre.nom:
            libelle = f"{libelle} — {type_nom}"
        lignes.append(
            ligne_ttc(
                CategorieLigne.chambre,
                libelle,
                quantite,
                sejour.prix_nuit_centimes,
                taux_hebergement,
                periode_debut=sejour.date_debut,
                periode_fin=sejour.date_fin,
            )
        )
    for consommation in sorted(reservation.consommations, key=lambda item: (item.date, item.id or 0)):
        lignes.append(
            ligne_ttc(
                CategorieLigne.consommation,
                consommation.libelle,
                consommation.quantite,
                consommation.prix_unitaire_centimes,
                consommation.taux_tva_pour_mille,
                periode_debut=_jour(consommation.date),
            )
        )
    return lignes


def _reglements_sejour(reservation: Reservation) -> list[ReglementConstate]:
    constates = []
    for reglement in sorted(reservation.reglements, key=lambda item: (item.date, item.id or 0)):
        nature = NatureReglement.remboursement if reglement.montant_centimes < 0 else NatureReglement.paiement
        constates.append(
            ReglementConstate(
                date=_jour(reglement.date),
                mode=str(reglement.mode),
                montant_centimes=reglement.montant_centimes,
                nature=nature,
            )
        )
    return constates


def _table_depuis_apercu(apercu: ApercuFacture, numero: int, cle: UUID, emission: date, echeance: date) -> FactureTable:
    identite = apercu.identite
    destinataire = apercu.destinataire
    totaux_facture = apercu.totaux
    return FactureTable(
        reservation_id=apercu.sejour_id,
        numero=numero,
        cle_idempotence=str(cle),
        courante=True,
        remplace_id=apercu.remplace_id,
        date_emission=emission,
        date_prestation=apercu.date_prestation,
        date_echeance=echeance,
        nom_facture=destinataire.nom,
        destinataire_type=destinataire.type,
        destinataire_nom=destinataire.nom,
        destinataire_adresse=destinataire.adresse,
        destinataire_adresse_facturation=destinataire.adresse_facturation,
        destinataire_siren=destinataire.siren,
        destinataire_tva=destinataire.numero_tva,
        reference_commande=destinataire.reference_commande,
        hotel_nom_commercial=identite.nom_commercial,
        hotel_denomination=identite.denomination,
        hotel_forme_juridique=identite.forme_juridique,
        hotel_capital_centimes=identite.capital_centimes,
        hotel_adresse_siege=identite.adresse_siege,
        hotel_adresse_facturation=identite.adresse_facturation,
        hotel_siren=identite.siren,
        hotel_siret=identite.siret,
        hotel_immatriculation=identite.immatriculation,
        hotel_numero_tva=identite.numero_tva,
        hotel_regime_tva=identite.regime_tva,
        hotel_taux_hebergement_pour_mille=identite.taux_hebergement_pour_mille,
        hotel_delai_paiement_jours=identite.delai_paiement_jours,
        hotel_conditions_paiement=identite.conditions_paiement,
        hotel_escompte=identite.escompte,
        hotel_penalites=identite.penalites,
        taxe_sejour_centimes=totaux_facture.taxe_sejour_centimes,
        total_ht_centimes=totaux_facture.total_ht_centimes,
        total_tva_centimes=totaux_facture.total_tva_centimes,
        total_prestations_ttc_centimes=totaux_facture.total_prestations_ttc_centimes,
        total_a_payer_centimes=totaux_facture.total_a_payer_centimes,
        montant_regle_centimes=totaux_facture.montant_regle_centimes,
        solde_centimes=totaux_facture.solde_centimes,
        remplace_numero=apercu.remplace_numero,
        remplace_date=apercu.remplace_date,
    )


def _ajouter_details(session, facture_id: int, apercu: ApercuFacture) -> None:
    for ordre, ligne in enumerate(apercu.lignes):
        session.add(
            LigneTable(
                facture_id=facture_id,
                ordre=ordre,
                categorie=ligne.categorie,
                libelle=ligne.libelle,
                periode_debut=ligne.periode_debut,
                periode_fin=ligne.periode_fin,
                quantite=ligne.quantite,
                prix_unitaire_ht_centimes=ligne.prix_unitaire_ht_centimes,
                prix_unitaire_ttc_centimes=ligne.prix_unitaire_ttc_centimes,
                remise_centimes=ligne.remise_centimes,
                taux_tva_pour_mille=ligne.taux_tva_pour_mille,
                montant_ht_centimes=ligne.montant_ht_centimes,
                montant_tva_centimes=ligne.montant_tva_centimes,
                montant_ttc_centimes=ligne.montant_ttc_centimes,
            )
        )
    for ventilation in apercu.totaux.ventilations:
        session.add(
            VentilationTable(
                facture_id=facture_id,
                taux_tva_pour_mille=ventilation.taux_tva_pour_mille,
                base_ht_centimes=ventilation.base_ht_centimes,
                montant_tva_centimes=ventilation.montant_tva_centimes,
            )
        )
    for reglement in apercu.reglements:
        session.add(
            ReglementTable(
                facture_id=facture_id,
                date_reglement=reglement.date,
                mode=reglement.mode,
                montant_centimes=reglement.montant_centimes,
                nature=reglement.nature,
            )
        )


def _vue(ligne: FactureTable) -> Facture:
    identite = IdentiteFacturation(
        nom_commercial=ligne.hotel_nom_commercial,
        denomination=ligne.hotel_denomination,
        forme_juridique=(
            None if ligne.hotel_forme_juridique is None else FormeJuridique(str(ligne.hotel_forme_juridique))
        ),
        capital_centimes=ligne.hotel_capital_centimes,
        adresse_siege=ligne.hotel_adresse_siege,
        adresse_facturation=ligne.hotel_adresse_facturation,
        siren=ligne.hotel_siren,
        siret=ligne.hotel_siret,
        immatriculation=ligne.hotel_immatriculation,
        numero_tva=ligne.hotel_numero_tva,
        regime_tva=None if ligne.hotel_regime_tva is None else RegimeTVA(str(ligne.hotel_regime_tva)),
        taux_hebergement_pour_mille=ligne.hotel_taux_hebergement_pour_mille,
        delai_paiement_jours=ligne.hotel_delai_paiement_jours,
        conditions_paiement=ligne.hotel_conditions_paiement,
        escompte=ligne.hotel_escompte,
        penalites=ligne.hotel_penalites,
    )
    destinataire = DestinataireFacture(
        type=TypeDestinataire(str(ligne.destinataire_type)),
        nom=ligne.destinataire_nom,
        adresse=ligne.destinataire_adresse,
        adresse_facturation=ligne.destinataire_adresse_facturation,
        siren=ligne.destinataire_siren,
        numero_tva=ligne.destinataire_tva,
        reference_commande=ligne.reference_commande,
    )
    lignes = tuple(
        LigneFacture(
            categorie=CategorieLigne(str(item.categorie)),
            libelle=item.libelle,
            periode_debut=item.periode_debut,
            periode_fin=item.periode_fin,
            quantite=item.quantite,
            prix_unitaire_ht_centimes=item.prix_unitaire_ht_centimes,
            prix_unitaire_ttc_centimes=item.prix_unitaire_ttc_centimes,
            remise_centimes=item.remise_centimes,
            taux_tva_pour_mille=item.taux_tva_pour_mille,
            montant_ht_centimes=item.montant_ht_centimes,
            montant_tva_centimes=item.montant_tva_centimes,
            montant_ttc_centimes=item.montant_ttc_centimes,
        )
        for item in sorted(ligne.lignes, key=lambda item: item.ordre)
    )
    reglements = tuple(
        ReglementConstate(
            date=item.date_reglement,
            mode=item.mode,
            montant_centimes=item.montant_centimes,
            nature=NatureReglement(str(item.nature)),
        )
        for item in sorted(ligne.reglements_figes, key=lambda item: (item.date_reglement, item.id or 0))
    )
    ventilations = tuple(
        VentilationTVA(item.taux_tva_pour_mille, item.base_ht_centimes, item.montant_tva_centimes)
        for item in sorted(ligne.ventilations, key=lambda item: item.taux_tva_pour_mille)
    )
    return Facture(
        id=ligne.id,
        sejour_id=ligne.reservation_id,
        numero=ligne.numero,
        date_emission=ligne.date_emission,
        date_prestation=ligne.date_prestation,
        date_echeance=ligne.date_echeance,
        courante=bool(ligne.courante),
        destinataire=destinataire,
        identite=identite,
        lignes=lignes,
        reglements=reglements,
        totaux=TotauxFacture(
            ventilations=ventilations,
            total_ht_centimes=ligne.total_ht_centimes,
            total_tva_centimes=ligne.total_tva_centimes,
            total_prestations_ttc_centimes=ligne.total_prestations_ttc_centimes,
            taxe_sejour_centimes=ligne.taxe_sejour_centimes,
            total_a_payer_centimes=ligne.total_a_payer_centimes,
            montant_regle_centimes=ligne.montant_regle_centimes,
            solde_centimes=ligne.solde_centimes,
        ),
        remplace_id=ligne.remplace_id,
        remplace_numero=ligne.remplace_numero,
        remplace_date=ligne.remplace_date,
        pdf_empreinte=ligne.pdf_empreinte,
    )


def _identite_de_session(session) -> IdentiteFacturation:
    ligne = session.get(IdentiteTable, 1)
    if ligne is None:
        return identite_vide()
    return IdentiteFacturation(
        nom_commercial=ligne.nom_commercial,
        denomination=ligne.denomination,
        forme_juridique=None if ligne.forme_juridique is None else FormeJuridique(str(ligne.forme_juridique)),
        capital_centimes=ligne.capital_centimes,
        adresse_siege=ligne.adresse_siege,
        adresse_facturation=ligne.adresse_facturation,
        siren=ligne.siren,
        siret=ligne.siret,
        immatriculation=ligne.immatriculation,
        numero_tva=ligne.numero_tva,
        regime_tva=None if ligne.regime_tva is None else RegimeTVA(str(ligne.regime_tva)),
        taux_hebergement_pour_mille=ligne.taux_hebergement_pour_mille,
        delai_paiement_jours=ligne.delai_paiement_jours,
        conditions_paiement=ligne.conditions_paiement,
        escompte=ligne.escompte,
        penalites=ligne.penalites,
    )


def _copier_identite(ligne: IdentiteTable, identite: IdentiteFacturation) -> None:
    ligne.nom_commercial = identite.nom_commercial
    ligne.denomination = identite.denomination
    ligne.forme_juridique = identite.forme_juridique
    ligne.capital_centimes = identite.capital_centimes
    ligne.adresse_siege = identite.adresse_siege
    ligne.adresse_facturation = identite.adresse_facturation
    ligne.siren = identite.siren
    ligne.siret = identite.siret
    ligne.immatriculation = identite.immatriculation
    ligne.numero_tva = identite.numero_tva
    ligne.regime_tva = identite.regime_tva
    ligne.taux_hebergement_pour_mille = identite.taux_hebergement_pour_mille
    ligne.delai_paiement_jours = identite.delai_paiement_jours
    ligne.conditions_paiement = identite.conditions_paiement
    ligne.escompte = identite.escompte
    ligne.penalites = identite.penalites


def _charger(session, sejour_id: int) -> Reservation | None:
    return session.exec(
        select(Reservation)
        .where(Reservation.id == sejour_id)
        .options(
            selectinload(Reservation.client),
            selectinload(Reservation.sejours).selectinload(Sejour.chambre).selectinload(Chambre.type_de_chambre),
            selectinload(Reservation.consommations),
            selectinload(Reservation.reglements),
        )
    ).first()


def _chargement_facture():
    return (
        selectinload(FactureTable.lignes),
        selectinload(FactureTable.ventilations),
        selectinload(FactureTable.reglements_figes),
    )


def _courante(session, sejour_id: int) -> FactureTable | None:
    return session.exec(
        select(FactureTable)
        .where(FactureTable.reservation_id == sejour_id, FactureTable.courante.is_(True))
        .options(*_chargement_facture())
    ).first()


def _empreinte(apercu: ApercuFacture) -> str:
    brut = asdict(apercu)
    brut.pop("empreinte")
    payload = json.dumps(_primitif(brut), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _primitif(valeur):
    if isinstance(valeur, dict):
        return {cle: _primitif(item) for cle, item in valeur.items()}
    if isinstance(valeur, list | tuple):
        return [_primitif(item) for item in valeur]
    if isinstance(valeur, date):
        return valeur.isoformat()
    if isinstance(valeur, FormeJuridique | RegimeTVA | TypeDestinataire | CategorieLigne | NatureReglement):
        return valeur.value
    return valeur


def _jour(moment: datetime) -> date:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone().date()


def _vide(valeur: str | None) -> str | None:
    if valeur is None:
        return None
    texte = valeur.strip()
    return texte or None


def _code(valeur: str | None) -> str | None:
    texte = _vide(valeur)
    if texte is None:
        return None
    return texte.replace(" ", "")


def _tva(valeur: str | None) -> str | None:
    texte = _code(valeur)
    return None if texte is None else texte.upper()


def _siren_valide(valeur: str) -> bool:
    return len(valeur) == 9 and valeur.isdigit()


def _siret_valide(valeur: str) -> bool:
    return len(valeur) == 14 and valeur.isdigit()


def _tva_valide(valeur: str) -> bool:
    return len(valeur) == 13 and valeur.startswith("FR") and valeur[2:].isalnum()
