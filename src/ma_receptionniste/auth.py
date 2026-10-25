import hashlib
import hmac
import secrets

from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import app
from sqlmodel import Session, select
from starlette.middleware.base import BaseHTTPMiddleware

from ma_receptionniste.db import get_session
from ma_receptionniste.models import Role, User

PUBLIC_ROUTES = {"/login", "/register"}
MIN_PASSWORD_LENGTH = 4

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


class EmailDejaUtilise(ValueError):
    pass


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


def register_user(
    session: Session,
    email: str,
    nom: str,
    password: str,
    role: Role = Role.receptionniste,
) -> User:
    email = normalize_email(email)
    if session.exec(select(User).where(User.email == email)).first():
        raise EmailDejaUtilise(email)
    user = User(email=email, nom=nom.strip(), password_hash=hash_password(password), role=role)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate(session: Session, email: str, password: str) -> User | None:
    user = session.exec(select(User).where(User.email == normalize_email(email))).first()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def login_user(user: User) -> None:
    app.storage.user.update(user_id=user.id, nom=user.nom)


def logout_user() -> None:
    app.storage.user.clear()


def current_user() -> User | None:
    user_id = app.storage.user.get("user_id")
    if user_id is None:
        return None
    with get_session() as session:
        return session.get(User, user_id)


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
