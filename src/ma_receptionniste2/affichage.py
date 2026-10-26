from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


def date_fr(valeur: date | None) -> str:
    if valeur is None:
        return ""
    return valeur.strftime("%d/%m/%Y")


def instant_fr(valeur: datetime | None) -> str:
    if valeur is None:
        return ""
    # SQLite rend un datetime naïf. On l'a écrit en UTC.
    if valeur.tzinfo is None:
        valeur = valeur.replace(tzinfo=UTC)
    return valeur.astimezone(PARIS).strftime("%d/%m/%Y %H:%M")
