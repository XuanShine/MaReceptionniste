"""Connexion et déconnexion."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from hotel_pms.auth import authentifier
from hotel_pms.templating import env
from hotel_pms.web import ouvrir, verifier_csrf

router = APIRouter()


def _page_login(request: Request, erreur: str | None, status: int) -> HTMLResponse:
    html = env.get_template("login.html").render({"request": request, "erreur": erreur})
    return HTMLResponse(html, status_code=status)


@router.get("/login", response_class=HTMLResponse)
def formulaire_login(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=303)
    return _page_login(request, None, 200)


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, identifiant: str = Form(""), password: str = Form("")):
    with ouvrir(request) as session:
        user = authentifier(session, identifiant, password)
        if user is None:
            return _page_login(request, "Identifiant ou mot de passe incorrect.", 401)
        request.session.clear()
        request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/logout")
def logout(request: Request, csrf: str = Form("")):
    verifier_csrf(request, csrf)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
