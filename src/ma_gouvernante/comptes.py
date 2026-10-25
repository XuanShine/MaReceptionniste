from sqlmodel import Session, select

from ma_receptionniste.auth import hash_password
from ma_receptionniste.db import create_db_and_tables, get_session
from ma_receptionniste.models import Role, User

MOT_DE_PASSE = "panorama"
COMPTES = (
    ("admin@hotel-panorama.fr", "Admin", Role.admin),
    ("reception@hotel-panorama.fr", "Réception", Role.receptionniste),
    ("femme@hotel-panorama.fr", "Camille", Role.femme_de_chambre),
)


def assurer_comptes(session: Session) -> None:
    for email, nom, role in COMPTES:
        if session.exec(select(User).where(User.email == email)).first():
            continue
        session.add(User(email=email, nom=nom, password_hash=hash_password(MOT_DE_PASSE), role=role))
    session.commit()


def demarrer() -> None:
    create_db_and_tables()
    with get_session() as session:
        assurer_comptes(session)
