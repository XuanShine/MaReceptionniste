"""L'argent d'un séjour, en centimes entiers. Fonctions pures : ni session, ni float."""

import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from ma_receptionniste.models import Consommation, Reglement, Sejour

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


def montant_ligne(prix_nuit_centimes: int, nuits: int, remise_pct: int) -> int:
    """Arrondi au centime le plus proche, le demi-centime monte."""
    return (prix_nuit_centimes * nuits * (100 - remise_pct) + 50) // 100


def taxe_sejour(adultes: int, nuits: int) -> int:
    """Les mineurs sont exonérés : seuls les adultes paient, par nuit."""
    return adultes * nuits * TAXE_SEJOUR_CENTIMES


def montant_sejour(sejour: Sejour) -> int:
    return montant_ligne(sejour.prix_nuit_centimes, nuits(sejour.date_debut, sejour.date_fin), sejour.remise_pct)


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
