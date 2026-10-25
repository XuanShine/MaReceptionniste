from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import app
from starlette.middleware.base import BaseHTTPMiddleware

from ma_gouvernante.menage import Acteur
from ma_receptionniste.db import get_session
from ma_receptionniste.models import Role, User

PUBLIC_ROUTES = {"/login", "/register"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if "user_id" not in app.storage.user and path not in PUBLIC_ROUTES and not path.startswith("/_nicegui"):
            return RedirectResponse(f"/login?redirect_to={path}")
        return await call_next(request)


def acteur_courant() -> Acteur | None:
    user_id = app.storage.user.get("user_id")
    if user_id is None:
        return None
    with get_session() as session:
        user = session.get(User, user_id)
        if user is None:
            return None
        try:
            role = Role(user.role)
        except ValueError:
            return None
        return Acteur(id=user.id, nom=user.nom, role=role)
