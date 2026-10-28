"""Mots de passe (pbkdf2) et authentification par identifiant."""

import hashlib
import secrets

from sqlmodel import Session, select

from hotel_pms.models import User

ITERATIONS = 120_000


class AuthRequise(Exception):
    """Session absente ou utilisateur supprimé."""


def hasher_mot_de_passe(mot_de_passe: str) -> str:
    if not isinstance(mot_de_passe, str) or not mot_de_passe or len(mot_de_passe) > 128:
        raise ValueError("Mot de passe invalide")
    sel = secrets.token_hex(16)
    empreinte = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode(), sel.encode(), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${sel}${empreinte}"


_HASH_FICTIF = hasher_mot_de_passe("mot-de-passe-inexistant")


def verifier_mot_de_passe(mot_de_passe: str, stocke: str) -> bool:
    if not isinstance(mot_de_passe, str) or len(mot_de_passe) > 128:
        mot_de_passe = "x"
        stocke = _HASH_FICTIF
    try:
        algo, iterations, sel, empreinte = stocke.split("$")
        if algo != "pbkdf2_sha256":
            return False
        calcule = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode(), sel.encode(), int(iterations)).hex()
    except (TypeError, ValueError):
        return False
    return secrets.compare_digest(calcule, empreinte)


def authentifier(session: Session, identifiant: str, mot_de_passe: str) -> User | None:
    cle = identifiant.strip().lower()
    user = session.exec(select(User).where(User.identifiant == cle)).first()
    stocke = user.password_hash if user else _HASH_FICTIF
    if not verifier_mot_de_passe(mot_de_passe, stocke) or user is None:
        return None
    return user
