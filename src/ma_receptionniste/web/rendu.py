import os
from datetime import date
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ma_receptionniste.affichage import date_courte, date_heure, date_longue, initiales, saisie_euros
from ma_receptionniste.consultations import MODE_REGLEMENT_LABEL, STATUT_SEJOUR
from ma_receptionniste.facturation import format_euros
from ma_receptionniste.models import ModeReglement
from ma_receptionniste.web.listes import CONSOMMATIONS_COURANTES, PARTENAIRES, PAYS_COURANTS, TYPES_CHAMBRES

DOSSIER = Path(__file__).parent
templates = Jinja2Templates(directory=str(DOSSIER / "templates"))
templates.env.filters["euros"] = format_euros
templates.env.filters["date_courte"] = date_courte
templates.env.filters["date_heure"] = date_heure
templates.env.filters["date_longue"] = date_longue
templates.env.filters["saisie"] = saisie_euros
templates.env.globals["modes"] = list(MODE_REGLEMENT_LABEL.items())
templates.env.globals["statuts"] = STATUT_SEJOUR
templates.env.globals["pays_courants"] = PAYS_COURANTS
templates.env.globals["partenaires"] = PARTENAIRES
templates.env.globals["consommations_courantes"] = CONSOMMATIONS_COURANTES
templates.env.globals["types_chambres"] = TYPES_CHAMBRES
templates.env.auto_reload = True


def secret() -> str:
    return os.environ.get("STORAGE_SECRET", "dev-secret-a-changer-en-production")


def hx(request: Request) -> bool:
    return request.headers.get("hx-request") == "true"


def cible(request: Request) -> str:
    return request.headers.get("hx-target", "").removeprefix("#")


def identifiant(request: Request) -> int | None:
    return request.session.get("user_id")


def memoriser(request: Request, texte: str, type_: str) -> None:
    request.session["flash"] = {"texte": texte, "type": type_}


def _entrees(ouverte: int | None) -> tuple[dict, ...]:
    return (
        {"href": "/dashboard", "libelle": "Dashboard", "icone": "dashboard", "cle": "/dashboard"},
        {"href": "/", "libelle": "Planning", "icone": "calendar_month", "cle": "/"},
        {"href": "/reservations", "libelle": "Réservations", "icone": "book_online", "cle": "/reservations"},
        {
            "href": f"/reservations/{ouverte}" if ouverte else None,
            "libelle": "Détail Réservation",
            "icone": "description",
            "cle": "detail",
        },
        {"href": "/clients", "libelle": "Clients", "icone": "people", "cle": "/clients"},
        {"href": "/chambres", "libelle": "Chambres", "icone": "bed", "cle": "/chambres"},
        {"href": "/parametres", "libelle": "Paramètres", "icone": "settings", "cle": "/parametres"},
    )


def commun(request: Request) -> dict:
    nom = request.session.get("nom", "")
    return {
        "nom": nom,
        "initiales": initiales(nom),
        "reservation_ouverte": request.session.get("reservation_ouverte"),
        "aujourdhui": date_longue(date.today()),
        "entrees": _entrees(request.session.get("reservation_ouverte")),
    }


def page(request: Request, nom: str, contexte: dict, status: int = 200):
    donnees = commun(request)
    donnees["flash"] = request.session.pop("flash", None)
    donnees.update(contexte)
    return templates.TemplateResponse(request, nom, donnees, status_code=status)


def rendre(nom: str, **contexte) -> str:
    return templates.get_template(nom).render(**contexte)


def fragments(morceaux: list[str], toast: dict | None = None) -> HTMLResponse:
    # Les boutons demandent hx-swap="none" : seul le hors-bande met la page à jour.
    corps = [rendre("partials/toasts.html", flash=toast, oob=True), *morceaux]
    return HTMLResponse("".join(corps))


def rediriger(request: Request, url: str, toast: dict | None = None):
    if toast:
        memoriser(request, toast["texte"], toast["type"])
    if hx(request):
        return HTMLResponse("", status_code=204, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)


def message(texte: str, type_: str) -> dict:
    return {"texte": texte, "type": type_}


def _libelle_mode(mode) -> str:
    return MODE_REGLEMENT_LABEL[ModeReglement(str(mode))]


templates.env.filters["libelle_mode"] = _libelle_mode
