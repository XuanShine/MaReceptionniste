import pytest
from sqlmodel import Session, SQLModel, create_engine

from ma_receptionniste.auth import (
    EmailDejaUtilise,
    authenticate,
    hash_password,
    register_user,
    safe_redirect,
    verify_password,
)
from ma_receptionniste.models import Role


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_hash_password() -> None:
    h = hash_password("motdepasse")
    assert "motdepasse" not in h
    assert verify_password("motdepasse", h)
    assert not verify_password("autre", h)
    assert hash_password("motdepasse") != h


def test_register_et_authenticate(session: Session) -> None:
    user = register_user(session, "  Alice@Example.com ", "Alice", "motdepasse")
    assert user.email == "alice@example.com"
    assert user.role == Role.receptionniste

    assert authenticate(session, "ALICE@example.com", "motdepasse").id == user.id
    assert authenticate(session, "alice@example.com", "mauvais") is None
    assert authenticate(session, "inconnu@example.com", "motdepasse") is None


def test_register_email_deja_utilise(session: Session) -> None:
    register_user(session, "alice@example.com", "Alice", "motdepasse")
    with pytest.raises(EmailDejaUtilise):
        register_user(session, "Alice@example.com", "Alice 2", "motdepasse")


@pytest.mark.parametrize(
    ("target", "expected"),
    [("/clients", "/clients"), (None, "/"), ("", "/"), ("https://evil.com", "/"), ("//evil.com", "/")],
)
def test_safe_redirect(target: str | None, expected: str) -> None:
    assert safe_redirect(target) == expected
