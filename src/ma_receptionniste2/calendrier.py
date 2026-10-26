from datetime import date, timedelta

JOURS = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")
MOIS = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")


def lundi_de(jour: date) -> date:
    return jour - timedelta(days=jour.weekday())


def lire_lundi(valeur: str | None, aujourd_hui: date) -> date:
    if not valeur:
        return lundi_de(aujourd_hui)
    try:
        jour = date.fromisoformat(valeur)
    except ValueError:
        return lundi_de(aujourd_hui)
    return lundi_de(jour)


def titre_semaine(lundi: date) -> str:
    dimanche = lundi + timedelta(days=6)
    if lundi.month == dimanche.month and lundi.year == dimanche.year:
        return f"{lundi.day} au {dimanche.day} {MOIS[lundi.month - 1]} {lundi.year}"
    if lundi.year == dimanche.year:
        return f"{lundi.day} {MOIS[lundi.month - 1]} au {dimanche.day} {MOIS[dimanche.month - 1]} {dimanche.year}"
    return (
        f"{lundi.day} {MOIS[lundi.month - 1]} {lundi.year} au {dimanche.day} {MOIS[dimanche.month - 1]} {dimanche.year}"
    )


def lire_date(valeur: str) -> date | None:
    if not valeur:
        return None
    try:
        return date.fromisoformat(valeur)
    except ValueError:
        return None
