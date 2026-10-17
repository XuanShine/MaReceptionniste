from sqlmodel import Session, SQLModel, create_engine, select

from ma_receptionniste.models import Client


def test_creer_client() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(Client(nom="Dupont", email="dupont@example.com"))
        session.commit()
        client = session.exec(select(Client)).one()

    assert client.id is not None
    assert client.nom == "Dupont"
