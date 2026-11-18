"""Environnement Jinja2 et filtres d'affichage."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from hotel_pms.constants import BLOC_LIBELLES, BLOCS, MOYENS_PAIEMENT, ONGLET_LIBELLES, ONGLETS
from hotel_pms.format import date_courte, date_fr, date_longue, dt_fr, euro, pct

TEMPLATES = Path(__file__).resolve().parent / "templates"
STATIC = Path(__file__).resolve().parent / "static"

env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html"]),
)
env.filters["euro"] = euro
env.filters["pct"] = pct
env.filters["date_fr"] = date_fr
env.filters["date_courte"] = date_courte
env.filters["dt_fr"] = dt_fr
env.filters["date_longue"] = date_longue
env.globals["ONGLETS"] = ONGLETS
env.globals["ONGLET_LIBELLES"] = ONGLET_LIBELLES
env.globals["BLOCS"] = BLOCS
env.globals["BLOC_LIBELLES"] = BLOC_LIBELLES
env.globals["MOYENS_PAIEMENT"] = MOYENS_PAIEMENT
