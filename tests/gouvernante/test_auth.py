import pytest
from sqlmodel import Session, select

from ma_gouvernante.auth import assurer_comptes, authenticate
from ma_gouvernante.db import engine
from ma_gouvernante.models import Role, User

COMPTES = (
    ("admin@hotel-panorama.fr", Role.admin),
    ("reception@hotel-panorama.fr", Role.receptionniste),
    ("menage@hotel-panorama.fr", Role.femme_de_chambre),
    ("technique@hotel-panorama.fr", Role.technicien),
)


def test_assurer_comptes_une_seconde_fois() -> None:
    assurer_comptes()
    premiers = {email: authenticate(email, "panorama")["id"] for email, _role in COMPTES}
    assurer_comptes()
    seconds = {email: authenticate(email, "panorama")["id"] for email, _role in COMPTES}
    assert premiers == seconds
    with Session(engine) as session:
        assert len(session.exec(select(User)).all()) == 4


def test_mauvais_mot_de_passe() -> None:
    assurer_comptes()
    assert authenticate("admin@hotel-panorama.fr", "autre") is None
    assert authenticate("inconnu@hotel-panorama.fr", "panorama") is None


@pytest.mark.parametrize(("email", "role"), COMPTES)
def test_role_de_chaque_email(email: str, role: Role) -> None:
    assurer_comptes()
    utilisateur = authenticate(email, "panorama")
    assert utilisateur is not None
    assert utilisateur["role"] == role
