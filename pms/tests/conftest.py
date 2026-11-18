import re

import pytest
from fastapi.testclient import TestClient
from hotel_pms.app import create_app
from hotel_pms.models import Sejour
from sqlmodel import Session, select


@pytest.fixture
def client(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path}/pms.db", secret="test-secret")
    with TestClient(app) as test_client:
        yield test_client


def login(client) -> None:
    reponse = client.post(
        "/login",
        data={"identifiant": "reception", "password": "reception"},
        follow_redirects=False,
    )
    assert reponse.status_code == 303, reponse.text


def jeton(html: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match, html[:400]
    return match.group(1)


def id_monnier(app) -> int:
    with Session(app.state.engine) as session:
        sejour = session.exec(select(Sejour).where(Sejour.nom == "Monnier Christophe")).one()
        return sejour.id or 0
