from datetime import UTC, date, datetime

from nicegui import app, ui

COULEURS = {
    "primary": "#1f4e5f",
    "secondary": "#7c6fb0",
    "accent": "#c08a3e",
    "positive": "#2f855a",
    "negative": "#c53030",
    "warning": "#b7791f",
    "ardoise": "#64748b",
    "fond": "#f5f7f9",
    "primary_soft": "#e4eef1",
    "primary_pale": "#f3f8f9",
    "secondary_soft": "#eeecf7",
    "accent_soft": "#f7efe3",
    "positive_soft": "#e6f2eb",
    "negative_soft": "#fbe9e9",
    "warning_soft": "#f8f0e0",
    "ardoise_soft": "#eef1f5",
}

# Pas de CDN : le poste de réception peut être hors ligne, on s'en tient aux polices du système.
CSS = """
body { font-family: "Inter", "Segoe UI", system-ui, sans-serif; font-size: 14px; color: #1e293b; }
.q-table--dense .q-table th, .q-table--dense .q-table td { height: 34px; padding: 4px 10px; }
.q-table th { font-weight: 600; color: #64748b; font-size: 12px; }
.q-table td { font-variant-numeric: tabular-nums; }
"""

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


def appliquer_theme() -> None:
    """À appeler une fois avant ui.run : default_props modifie la classe, donc toutes les pages."""
    app.colors(**COULEURS)
    ui.add_css(CSS, shared=True)
    for champ in (ui.input, ui.number, ui.textarea, ui.date_input):
        champ.default_props("dense outlined")
    ui.select.default_props("dense outlined options-dense")
    ui.button.default_props("unelevated no-caps")


def date_courte(jour: date | None) -> str:
    return jour.strftime("%d/%m/%Y") if jour else ""


def heure_locale(moment: datetime) -> datetime:
    """SQLite rend les horodatages sans fuseau, et l'application les écrit en UTC."""
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).astimezone()


def date_heure(moment: datetime) -> str:
    return f"{heure_locale(moment):%d/%m/%Y %H:%M}"


def date_longue(jour: date) -> str:
    return f"{JOURS[jour.weekday()]} {jour.day} {MOIS[jour.month - 1]} {jour.year}"
