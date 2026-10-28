"""Lecture des nombres et des dates saisis dans les formulaires."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def parser_decimal(brut: str, minimum: Decimal, maximum: Decimal) -> Decimal:
    texte = (brut or "").strip().replace("\u202f", "").replace(" ", "").replace(",", ".")
    if not texte:
        raise ValueError("Nombre manquant")
    try:
        valeur = Decimal(texte)
    except InvalidOperation as exc:
        raise ValueError("Nombre invalide") from exc
    valeur = valeur.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if valeur < minimum or valeur > maximum:
        raise ValueError("Nombre hors limites")
    return valeur


def parser_entier(brut: str, minimum: int, maximum: int) -> int:
    texte = (brut or "").strip()
    try:
        valeur = int(texte)
    except ValueError as exc:
        raise ValueError("Nombre invalide") from exc
    if valeur < minimum or valeur > maximum:
        raise ValueError("Nombre hors limites")
    return valeur


def parser_date(brut: str, obligatoire: bool = False) -> date | None:
    texte = (brut or "").strip()
    if not texte:
        if obligatoire:
            raise ValueError("Date manquante")
        return None
    try:
        return date.fromisoformat(texte)
    except ValueError as exc:
        raise ValueError("Date invalide") from exc


def couper(brut: str, taille: int) -> str:
    return (brut or "").replace("\r\n", "\n").strip()[:taille]
