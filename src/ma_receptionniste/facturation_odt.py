"""Contexte du modèle ODT et rendu du document. Aucun calcul de taxe ici."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from ma_receptionniste.facturation import ApercuFacture, Facture

AVERTISSEMENT_APERCU = "Aperçu — facture non émise"
ACOMPTES = "Acomptes déjà facturés : aucun."


class LigneODT(TypedDict):
    libelle: str
    periode: str
    quantite: str
    prix_unitaire_ht: str
    tva: str
    ht: str
    ttc: str
    remise: str


class ReglementODT(TypedDict):
    date: str
    libelle: str
    montant: str


class VentilationODT(TypedDict):
    taux: str
    base_ht: str
    montant: str


class ContexteFactureODT(TypedDict):
    hotel: dict[str, str]
    facture: dict[str, str]
    client: dict[str, str]
    sejour: dict[str, str]
    chambres: list[LigneODT]
    consommations: list[LigneODT]
    reglements: list[ReglementODT]
    acomptes: str
    ventilations: list[VentilationODT]
    totaux: dict[str, str]
    conditions: dict[str, str]
    mentions: list[str]
    message_remerciement: str


def chemin_modele() -> Path:
    """Modèle livré avec le paquet, sinon celui du dépôt. Indépendant du répertoire courant."""
    voisin = Path(__file__).resolve().parent / "facture_hotel.odt"
    if voisin.is_file():
        return voisin
    return Path(__file__).resolve().parents[2] / "templates" / "factures" / "facture_hotel.odt"


def contexte_apercu(apercu: ApercuFacture) -> ContexteFactureODT:
    return _contexte(
        apercu.identite,
        apercu.destinataire,
        apercu.lignes,
        apercu.reglements,
        apercu.totaux,
        apercu.date_prestation,
        apercu.remplace_numero,
        apercu.remplace_date,
        numero="",
        emission="",
        echeance=None,
        avertissement=AVERTISSEMENT_APERCU,
    )


def contexte_facture(facture: Facture) -> ContexteFactureODT:
    return _contexte(
        facture.identite,
        facture.destinataire,
        facture.lignes,
        facture.reglements,
        facture.totaux,
        facture.date_prestation,
        facture.remplace_numero,
        facture.remplace_date,
        numero=str(facture.numero),
        emission=f"{facture.date_emission:%d/%m/%Y}",
        echeance=facture.date_echeance,
        avertissement="",
    )


def rendre_odt(contexte: ContexteFactureODT, destination: Path, modele: Path | None = None) -> Path:
    """Remplit le modèle. Les montants sont déjà formatés. Un champ omis est une erreur."""
    from ma_receptionniste.facturation import PdfIndisponible

    try:
        from jinja2 import Environment, StrictUndefined
        from python_odt_template import ODTTemplate
        from python_odt_template.jinja import finalize_value, get_odt_renderer
    except ImportError as erreur:
        raise PdfIndisponible("Le moteur de modèle ODT n'est pas installé.") from erreur
    source = modele or chemin_modele()
    if not source.is_file():
        raise PdfIndisponible("Le modèle de facture est introuvable.")
    try:
        environnement = Environment(undefined=StrictUndefined, autoescape=True, finalize=finalize_value)
        moteur = get_odt_renderer(media_path=source.parent, env=environnement)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with ODTTemplate(source) as template:
            moteur.render(template, context=dict(contexte))
            template.pack(destination)
    except PdfIndisponible:
        raise
    except Exception as erreur:
        raise PdfIndisponible("Le modèle de facture n'a pas pu être rempli.") from erreur
    return destination


def convertir_pdf(odt: Path, dossier_sortie: Path) -> Path:
    """Convertit un ODT en PDF avec un profil LibreOffice isolé. Aucun shell."""
    from ma_receptionniste.facturation import PdfIndisponible

    binaire = shutil.which("libreoffice") or shutil.which("soffice")
    if binaire is None:
        raise PdfIndisponible("LibreOffice est introuvable. Il est nécessaire pour produire le PDF.")
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    profil = Path(tempfile.mkdtemp(prefix="lo-facture-"))
    try:
        try:
            resultat = subprocess.run(
                [
                    binaire,
                    f"-env:UserInstallation=file://{profil}",
                    "--headless",
                    "--norestore",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(dossier_sortie),
                    str(odt),
                ],
                check=False,
                timeout=45,
                capture_output=True,
            )
        except subprocess.TimeoutExpired as erreur:
            raise PdfIndisponible("La conversion PDF a dépassé le délai.") from erreur
    finally:
        shutil.rmtree(profil, ignore_errors=True)
    produit = dossier_sortie / f"{odt.stem}.pdf"
    if resultat.returncode != 0 or not produit.is_file() or not produit.read_bytes().startswith(b"%PDF"):
        raise PdfIndisponible("La conversion PDF a échoué.")
    return produit


def _contexte(
    identite,
    destinataire,
    lignes,
    reglements,
    totaux,
    prestation,
    remplace_numero,
    remplace_date,
    *,
    numero: str,
    emission: str,
    echeance,
    avertissement: str,
) -> ContexteFactureODT:
    from ma_receptionniste.facturation import (
        FORMES_AVEC_CAPITAL,
        LIBELLE_FORME,
        LIBELLE_NATURE,
        LIBELLES_MODE,
        MENTION_40,
        CategorieLigne,
        RegimeTVA,
        TypeDestinataire,
        format_euros,
        libelle_taux,
        nuits,
    )

    chambres = [ligne for ligne in lignes if ligne.categorie is CategorieLigne.chambre]
    extras = [ligne for ligne in lignes if ligne.categorie is CategorieLigne.consommation]
    debuts = [ligne.periode_debut for ligne in chambres if ligne.periode_debut]
    fins = [ligne.periode_fin for ligne in chambres if ligne.periode_fin]
    if debuts and fins:
        periode = _periode(min(debuts), max(fins), nuits)
    elif prestation is not None:
        periode = f"{prestation:%d/%m/%Y}"
    else:
        periode = ""
    return {
        "hotel": _hotel(identite, FORMES_AVEC_CAPITAL, LIBELLE_FORME, RegimeTVA, format_euros),
        "facture": {
            "numero": numero,
            "date_emission": emission,
            "date_prestation": "" if prestation is None else f"{prestation:%d/%m/%Y}",
            "remplacement": _remplacement(remplace_numero, remplace_date),
            "avertissement": avertissement,
        },
        "client": {
            "nom": destinataire.nom or "",
            "adresse": destinataire.adresse or "",
            "complements": _complements(destinataire),
        },
        "sejour": {
            "reference": " · ".join(ligne.libelle for ligne in chambres),
            "periode": periode,
        },
        "chambres": [_ligne(ligne, _periode_ligne(ligne), format_euros, libelle_taux) for ligne in chambres],
        "consommations": [_ligne(ligne, "", format_euros, libelle_taux) for ligne in extras],
        "reglements": [
            {
                "date": f"{reglement.date:%d/%m/%Y}",
                "libelle": (
                    f"{LIBELLES_MODE.get(reglement.mode, reglement.mode)} · {LIBELLE_NATURE[reglement.nature]}"
                ),
                "montant": format_euros(reglement.montant_centimes),
            }
            for reglement in reglements
        ],
        "acomptes": ACOMPTES,
        "ventilations": [
            {
                "taux": libelle_taux(ventilation.taux_tva_pour_mille),
                "base_ht": format_euros(ventilation.base_ht_centimes),
                "montant": format_euros(ventilation.montant_tva_centimes),
            }
            for ventilation in totaux.ventilations
        ],
        "totaux": {
            "ht": format_euros(totaux.total_ht_centimes),
            "tva": format_euros(totaux.total_tva_centimes),
            "prestations_ttc": format_euros(totaux.total_prestations_ttc_centimes),
            "taxe_sejour": format_euros(totaux.taxe_sejour_centimes),
            "a_payer": format_euros(totaux.total_a_payer_centimes),
            "regle": format_euros(totaux.montant_regle_centimes),
            "solde": format_euros(totaux.solde_centimes),
        },
        "conditions": {
            "echeance": _echeance(identite, emission, echeance),
            "escompte": f"Escompte : {identite.escompte}." if identite.escompte else "Escompte : néant.",
            "penalites": identite.penalites or "",
            "mention_tva": _mention_tva(identite, RegimeTVA),
        },
        "mentions": _mentions(identite, destinataire, MENTION_40, TypeDestinataire),
        "message_remerciement": _remerciement(identite),
    }


def _hotel(identite, formes_capital, libelles_forme, regime_tva, format_euros) -> dict[str, str]:
    forme = ""
    if identite.forme_juridique is not None:
        forme = libelles_forme[identite.forme_juridique]
        if identite.forme_juridique in formes_capital and identite.capital_centimes is not None:
            forme = f"{forme} au capital de {format_euros(identite.capital_centimes)}"
    identifiants = " · ".join(
        morceau
        for morceau in (
            f"SIREN {identite.siren}" if identite.siren else "",
            f"SIRET {identite.siret}" if identite.siret else "",
        )
        if morceau
    )
    immatriculation = [identite.immatriculation or ""]
    if identite.regime_tva is regime_tva.assujetti and identite.numero_tva:
        immatriculation.append(f"TVA {identite.numero_tva}")
    return {
        "nom_commercial": identite.nom_commercial or "",
        "denomination": identite.denomination or "",
        "forme_capital": forme,
        "adresse_siege": identite.adresse_siege or "",
        "adresse_facturation": identite.adresse_facturation or "",
        "identifiants": identifiants,
        "immatriculation_tva": " · ".join(morceau for morceau in immatriculation if morceau),
        "contact": "",
    }


def _complements(destinataire) -> str:
    lignes = []
    if destinataire.adresse_facturation:
        lignes.append(f"Adresse de facturation : {destinataire.adresse_facturation}")
    if destinataire.siren:
        lignes.append(f"SIREN {destinataire.siren}")
    if destinataire.numero_tva:
        lignes.append(f"TVA {destinataire.numero_tva}")
    if destinataire.reference_commande:
        lignes.append(f"Commande {destinataire.reference_commande}")
    return "\n".join(lignes)


def _ligne(ligne, periode: str, format_euros, libelle_taux) -> LigneODT:
    return {
        "libelle": ligne.libelle,
        "periode": periode,
        "quantite": str(ligne.quantite),
        "prix_unitaire_ht": format_euros(ligne.prix_unitaire_ht_centimes),
        "tva": libelle_taux(ligne.taux_tva_pour_mille),
        "ht": format_euros(ligne.montant_ht_centimes),
        "ttc": format_euros(ligne.montant_ttc_centimes),
        "remise": "" if not ligne.remise_centimes else f"Remise {format_euros(ligne.remise_centimes)}",
    }


def _periode_ligne(ligne) -> str:
    from ma_receptionniste.facturation import nuits

    if ligne.periode_debut and ligne.periode_fin:
        return _periode(ligne.periode_debut, ligne.periode_fin, nuits)
    return ""


def _periode(debut, fin, nuits) -> str:
    compte = nuits(debut, fin)
    mot = "nuit" if compte == 1 else "nuits"
    return f"Du {debut:%d/%m/%Y} au {fin:%d/%m/%Y} · {compte} {mot}"


def _remplacement(numero, jour) -> str:
    if numero is None:
        return ""
    if jour is None:
        return f"Annule et remplace la facture n° {numero}"
    return f"Annule et remplace la facture n° {numero} du {jour:%d/%m/%Y}"


def _echeance(identite, emission: str, echeance) -> str:
    if identite.delai_paiement_jours == 0:
        return "Échéance : à réception."
    if not emission or echeance is None:
        return f"Échéance : {identite.delai_paiement_jours} jours après l'émission."
    return f"Échéance : {echeance:%d/%m/%Y} ({identite.delai_paiement_jours} jours)."


def _mention_tva(identite, regime_tva) -> str:
    if identite.regime_tva is regime_tva.franchise:
        return "TVA non applicable, article 293 B du CGI"
    if identite.regime_tva is regime_tva.exonere:
        return "Exonération de TVA"
    return ""


def _mentions(identite, destinataire, mention_40: str, type_destinataire) -> list[str]:
    if destinataire.type is not type_destinataire.professionnel:
        return []
    if mention_40 in (identite.penalites or ""):
        return []
    return [f"En cas de retard de paiement : pénalités au taux légal et {mention_40}."]


def _remerciement(identite) -> str:
    nom = identite.nom_commercial or identite.denomination or "l'hôtel"
    return f"Merci pour votre séjour à {nom}.\nAu plaisir de vous accueillir à nouveau."
