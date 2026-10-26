import hashlib
import hmac
import secrets

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ma_receptionniste2.models import User

MIN_PASSWORD_LENGTH = 4
MAX_PASSWORD_LENGTH = 128

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


class EmailDejaUtilise(ValueError):
    pass


class IdentifiantsRefuses(ValueError):
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


def safe_redirect(target: str | None) -> str:
    if not target or not target.startswith("/") or target.startswith("//"):
        return "/"
    if any(caractere in target for caractere in "\\\r\n\t"):
        return "/"
    return target


def inscrire(session: Session, email: str, nom: str, password: str) -> User:
    email = normalize_email(email)
    if session.exec(select(User).where(User.email == email)).first():
        raise EmailDejaUtilise(email)
    user = User(email=email, nom=nom.strip(), password_hash=hash_password(password))
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise EmailDejaUtilise(email) from None
    return user


def authentifier(session: Session, email: str, password: str) -> User:
    user = session.exec(select(User).where(User.email == normalize_email(email))).first()
    if user is None or not verify_password(password, user.password_hash):
        raise IdentifiantsRefuses
    return user


def message_inscription(nom: str, email: str, password: str, confirmation: str) -> str | None:
    if not nom.strip() or not email.strip() or not password:
        return "Tous les champs sont obligatoires"
    if "@" not in email or len(email) > 200:
        return "Email invalide"
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Le mot de passe doit faire au moins {MIN_PASSWORD_LENGTH} caractères"
    if len(password) > MAX_PASSWORD_LENGTH:
        return "Le mot de passe est trop long"
    if password != confirmation:
        return "Les mots de passe ne correspondent pas"
    return None
