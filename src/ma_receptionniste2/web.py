import hmac
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from ma_receptionniste2.affichage import date_fr, instant_fr
from ma_receptionniste2.models import User

RACINE = Path(__file__).resolve().parent
LIENS = (
    ("/", "Planning"),
    ("/chambres", "Chambres"),
    ("/clients", "Clients"),
    ("/reservations", "Réservations"),
)

templates = Jinja2Templates(directory=str(RACINE / "templates"))
templates.env.trim_blocks = True
templates.env.lstrip_blocks = True
templates.env.filters["date_fr"] = date_fr
templates.env.filters["instant_fr"] = instant_fr
templates.env.globals["liens"] = LIENS


class VersPage(Exception):
    def __init__(self, url: str) -> None:
        self.url = url


class JetonInvalide(Exception):
    pass


def assurer_jeton(request: Request) -> str:
    jeton = request.session.get("csrf")
    if not isinstance(jeton, str) or not jeton:
        jeton = secrets.token_urlsafe(32)
        request.session["csrf"] = jeton
    return jeton


def jeton_valide(attendu: object, fourni: str) -> bool:
    if not isinstance(attendu, str) or len(attendu) != len(fourni):
        return False
    return hmac.compare_digest(attendu, fourni)


def exiger_jeton(request: Request, csrf: str) -> None:
    if not jeton_valide(request.session.get("csrf"), csrf):
        raise JetonInvalide


def session_db(request: Request) -> Iterator[Session]:
    # La transaction se ferme après la vue. Le gabarit est donc rendu dans la vue.
    with Session(request.app.state.engine, expire_on_commit=False) as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        else:
            session.commit()


SessionDB = Annotated[Session, Depends(session_db)]


def url_login(request: Request) -> str:
    chemin = request.url.path
    if request.url.query:
        chemin = f"{chemin}?{request.url.query}"
    return "/login?redirect_to=" + quote(chemin, safe="")


def exiger(request: Request, session: SessionDB) -> User:
    user_id = request.session.get("user_id")
    user = session.get(User, user_id) if isinstance(user_id, int) else None
    if user is None:
        request.session.pop("user_id", None)
        raise VersPage(url_login(request))
    return user


Utilisateur = Annotated[User, Depends(exiger)]


def socle(request: Request, user: User | None = None, **extra) -> dict:
    return {
        "nom_utilisateur": user.nom if user else "",
        "actif": extra.pop("actif", request.url.path),
        **extra,
    }


def html(request: Request, nom: str, contexte: dict, statut: int = 200) -> HTMLResponse:
    # Le gabarit est rendu ici, pendant que la transaction est encore ouverte.
    corps = templates.get_template(nom).render({**contexte, "csrf": assurer_jeton(request)})
    return HTMLResponse(corps, status_code=statut, headers={"Cache-Control": "no-store"})


def repondre(
    request: Request,
    *,
    page: str,
    fragment: str,
    contexte: dict,
    redirection: str | None = None,
) -> Response:
    # Sans HTMX, la réponse est une page entière. Avec HTMX, c'est le fragment.
    if redirection:
        if request.headers.get("hx-request"):
            return Response(status_code=204, headers={"HX-Redirect": redirection, "Cache-Control": "no-store"})
        return RedirectResponse(redirection, status_code=303, headers={"Cache-Control": "no-store"})
    nom = fragment if request.headers.get("hx-request") else page
    return html(request, nom, contexte)


def page_simple(request: Request, *, titre: str, message: str, href: str, lien: str, statut: int) -> HTMLResponse:
    contexte = {"titre": titre, "message": message, "href": href, "lien": lien, "nom_utilisateur": "", "actif": ""}
    if request.headers.get("hx-request"):
        # Le fragment remplace la page, le gabarit complet irait s'imbriquer dans la cible du formulaire.
        reponse = html(request, "_message.html", contexte, statut=statut)
        reponse.headers["HX-Retarget"] = "body"
        reponse.headers["HX-Reswap"] = "innerHTML"
        return reponse
    return html(request, "simple.html", contexte, statut=statut)
