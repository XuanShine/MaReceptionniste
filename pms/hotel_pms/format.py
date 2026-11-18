"""Affichage français des montants et des dates, sans dépendre de la locale système."""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)
JOURS_COURTS = ("lu", "ma", "me", "je", "ve", "sa", "di")


def D(valeur) -> Decimal:
    if isinstance(valeur, Decimal):
        return valeur
    if valeur is None:
        return Decimal("0")
    return Decimal(str(valeur))


def euro(valeur) -> str:
    montant = D(valeur).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    signe = "-" if montant < 0 else ""
    entier, fraction = f"{abs(montant):.2f}".split(".")
    groupes: list[str] = []
    while entier:
        groupes.append(entier[-3:])
        entier = entier[:-3]
    return signe + "\u202f".join(reversed(groupes)) + "," + fraction


def pct(valeur) -> str:
    nombre = D(valeur)
    if nombre == nombre.to_integral_value():
        return f"{int(nombre)} %"
    return euro(nombre) + " %"


def date_fr(valeur: date | datetime | None) -> str:
    if valeur is None:
        return ""
    return valeur.strftime("%d/%m/%Y")


def date_courte(valeur: date | None) -> str:
    if valeur is None:
        return ""
    return f"{JOURS_COURTS[valeur.weekday()]} {valeur.strftime('%d/%m')}"


def dt_fr(valeur: datetime | None) -> str:
    if valeur is None:
        return ""
    return valeur.strftime("%d/%m/%Y %H:%M")


def date_longue(valeur: date | None) -> str:
    if valeur is None:
        return ""
    return f"{JOURS[valeur.weekday()]} {valeur.day} {MOIS[valeur.month - 1]} {valeur.year}"
