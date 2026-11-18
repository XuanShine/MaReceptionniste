"""Totaux d'un séjour.

La TVA hébergement est de 10 % sur le prix des lignes après remise.
La taxe de séjour s'ajoute hors TVA, comme sur la fiche legacy.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from hotel_pms.format import D

TAUX_TVA = Decimal("0.10")


@dataclass(frozen=True)
class TotauxSejour:
    total_ttc: Decimal
    total_ht: Decimal
    total_tva: Decimal
    total_taxe: Decimal
    total_general: Decimal
    total_paye: Decimal
    reste: Decimal


def _somme(valeurs) -> Decimal:
    total = Decimal("0.00")
    for valeur in valeurs:
        total += D(valeur)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def prix_net(ligne) -> Decimal:
    brut = D(ligne.prix_ttc)
    remise = D(ligne.remise_pct)
    net = brut * (Decimal("1") - remise / Decimal("100"))
    return net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def totaux_sejour(lignes, reglements) -> TotauxSejour:
    total_ttc = _somme(prix_net(ligne) for ligne in lignes)
    total_taxe = _somme(D(ligne.taxe_sejour) for ligne in lignes)
    total_paye = _somme(D(reglement.montant) for reglement in reglements)
    total_ht = (total_ttc / (Decimal("1") + TAUX_TVA)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_tva = (total_ttc - total_ht).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_general = (total_ttc + total_taxe).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    reste = (total_general - total_paye).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return TotauxSejour(
        total_ttc=total_ttc,
        total_ht=total_ht,
        total_tva=total_tva,
        total_taxe=total_taxe,
        total_general=total_general,
        total_paye=total_paye,
        reste=reste,
    )
