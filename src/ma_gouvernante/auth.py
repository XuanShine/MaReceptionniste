import hashlib
import hmac
import secrets

from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import app
from sqlmodel import Session, select
from starlette.middleware.base import BaseHTTPMiddleware

from ma_gouvernante.db import get_session
from ma_gouvernante.droits import Refus
from ma_gouvernante.models import Role, User

PUBLIC_ROUTES = {"/login"}
MOT_DE_PASSE_INITIAL = "panorama"

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1

COMPTES = (
    ("admin@hotel-panorama.fr", "Admin", Role.admin),
    ("reception@hotel-panorama.fr", "Réceptionniste", Role.receptionniste),
    ("menage@hotel-panorama.fr", "Femme de chambre", Role.femme_de_chambre),
    ("technique@hotel-panorama.fr", "Technicien", Role.technicien),
)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algo, n, r, p, salt, digest = password_hash.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
    return hmac.compare_digest(candidate, bytes.fromhex(digest))


def normalize_email(email: str) -> str:
    return email.strip().lower()


def assurer_comptes() -> None:
    with get_session() as session:
        for email, nom, role in COMPTES:
            email = normalize_email(email)
            if session.exec(select(User).where(User.email == email)).first():
                continue
            session.add(User(email=email, nom=nom, password_hash=hash_password(MOT_DE_PASSE_INITIAL), role=role))
        session.commit()


def authenticate(email: str, password: str) -> dict | None:
    with get_session() as session:
        user = session.exec(select(User).where(User.email == normalize_email(email))).first()
        if user is None or not verify_password(password, user.password_hash):
            return None
        return {"id": user.id, "email": user.email, "nom": user.nom, "role": Role(user.role)}


def charger_utilisateur(user_id: int) -> dict | None:
    with get_session() as session:
        user = session.get(User, user_id)
        if user is None:
            return None
        return {"id": user.id, "email": user.email, "nom": user.nom, "role": Role(user.role)}


def utilisateur(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise Refus("session")
    return user


def logout_user() -> None:
    app.storage.user.clear()


def safe_redirect(target: str | None) -> str:
    if not target or not target.startswith("/") or target.startswith("//"):
        return "/"
    return target


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if "user_id" not in app.storage.user and path not in PUBLIC_ROUTES and not path.startswith("/_nicegui"):
            return RedirectResponse(f"/login?redirect_to={path}")
        return await call_next(request)
