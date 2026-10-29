from datetime import UTC, date, datetime

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


def date_courte(jour: date | datetime | None) -> str:
    if jour is None:
        return ""
    if isinstance(jour, datetime):
        jour = heure_locale(jour)
    return f"{jour:%d/%m/%Y}"


def heure_locale(moment: datetime) -> datetime:
    """SQLite rend les horodatages sans fuseau, et l'application les écrit en UTC."""
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).astimezone()


def date_heure(moment: datetime) -> str:
    return f"{heure_locale(moment):%d/%m/%Y %H:%M}"


def date_longue(jour: date) -> str:
    return f"{JOURS[jour.weekday()]} {jour.day} {MOIS[jour.month - 1]} {jour.year}"


def initiales(nom: str) -> str:
    return "".join(mot[0] for mot in nom.split()[:2]).upper() or "?"


def saisie_euros(centimes: int) -> str:
    euros, reste = divmod(max(centimes, 0), 100)
    return f"{euros}.{reste:02d}"
