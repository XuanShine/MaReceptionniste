"""Session de base, jeton de formulaire, rendu des pages."""

import secrets
from contextlib import contextmanager

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from hotel_pms.auth import AuthRequise
from hotel_pms.models import User
from hotel_pms.templating import env


def assurer_csrf(request: Request) -> str:
    jeton = request.session.get("csrf")
    if not jeton:
        jeton = secrets.token_urlsafe(32)
        request.session["csrf"] = jeton
    return jeton


def verifier_csrf(request: Request, jeton: str) -> None:
    attendu = str(request.session.get("csrf") or "")
    if not attendu or not secrets.compare_digest(attendu, str(jeton or "")):
        raise HTTPException(status_code=400, detail="Jeton invalide")


def flash(request: Request, message: str) -> None:
    request.session["flash"] = message


def est_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


@contextmanager
def ouvrir(request: Request):
    with Session(request.app.state.engine) as session:
        yield session


def _utilisateur(request: Request, session: Session) -> User:
    user_id = request.session.get("user_id")
    user = session.get(User, user_id) if user_id else None
    if user is None:
        request.session.clear()
        raise AuthRequise()
    return user


def rendre(
    request: Request,
    template: str,
    *,
    session: Session,
    actif: str,
    status: int = 200,
    **contexte,
) -> HTMLResponse:
    contexte["request"] = request
    contexte["user"] = _utilisateur(request, session)
    contexte["actif"] = actif
    contexte["sejour_actif_id"] = request.session.get("sejour_id")
    contexte["csrf"] = assurer_csrf(request)
    contexte["flash"] = request.session.pop("flash", None)
    return HTMLResponse(env.get_template(template).render(contexte), status_code=status)


def fragment(request: Request, template: str, *, status: int = 200, **contexte) -> HTMLResponse:
    contexte["request"] = request
    contexte["csrf"] = assurer_csrf(request)
    return HTMLResponse(env.get_template(template).render(contexte), status_code=status)
