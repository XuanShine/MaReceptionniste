from collections.abc import Iterator

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from ma_receptionniste.models import Chambre, ChambreChambreVirtuelle, ChambreVirtuelle, Client, TypeChambre


def test_creer_client() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(Client(nom="Dupont", email="dupont@example.com"))
        session.commit()
        client = session.exec(select(Client)).one()

    assert client.id is not None
    assert client.nom == "Dupont"


@pytest.fixture
def base_relations() -> Iterator[Engine]:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def activer_cles_etrangeres(connexion, _enregistrement) -> None:
        connexion.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(TypeChambre(id=1, libelle="Double"))
        session.add_all([Chambre(id=i, nom=f"10{i}", position=i) for i in range(1, 4)])
        session.commit()
        session.add_all(
            [
                ChambreVirtuelle(id=i, type_chambre_id=1, nom_raccourci=f"V{i}", prix_defaut=80, prix_mini=50)
                for i in range(1, 4)
            ]
        )
        session.commit()
    yield engine
    engine.dispose()


def test_relations_chambres_virtuelles_dans_les_deux_sens(base_relations: Engine) -> None:
    with Session(base_relations) as session:
        chambre1, chambre2, chambre3 = [session.get(Chambre, i) for i in range(1, 4)]
        virtuelle1, virtuelle2, virtuelle3 = [session.get(ChambreVirtuelle, i) for i in range(1, 4)]
        assert chambre3.chambres_virtuelles == []
        assert virtuelle3.chambres == []
        chambre1.chambres_virtuelles.extend([virtuelle1, virtuelle2])
        virtuelle1.chambres.append(chambre2)
        session.commit()

    with Session(base_relations) as session:
        assert {v.id for v in session.get(Chambre, 1).chambres_virtuelles} == {1, 2}
        assert {v.id for v in session.get(Chambre, 2).chambres_virtuelles} == {1}
        assert session.get(Chambre, 3).chambres_virtuelles == []
        assert {c.id for c in session.get(ChambreVirtuelle, 1).chambres} == {1, 2}
        assert {c.id for c in session.get(ChambreVirtuelle, 2).chambres} == {1}
        assert session.get(ChambreVirtuelle, 3).chambres == []


def test_liaison_unique_et_cles_etrangeres_actives(base_relations: Engine) -> None:
    with base_relations.connect() as connexion:
        assert connexion.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

    with Session(base_relations) as session:
        session.add(ChambreChambreVirtuelle(chambre_id=1, chambre_virtuelle_id=1))
        session.commit()

    for chambre_id, virtuelle_id in [(1, 1), (999, 1), (1, 999)]:
        with Session(base_relations) as session:
            session.add(ChambreChambreVirtuelle(chambre_id=chambre_id, chambre_virtuelle_id=virtuelle_id))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    with Session(base_relations) as session:
        liens = [(lien.chambre_id, lien.chambre_virtuelle_id) for lien in session.exec(select(ChambreChambreVirtuelle))]
        assert liens == [(1, 1)]


@pytest.mark.parametrize("cote", ["chambre", "virtuelle"])
@pytest.mark.parametrize("mode", ["sql", "orm_charge", "orm_non_charge"])
def test_suppression_en_cascade_des_liaisons(base_relations: Engine, cote: str, mode: str) -> None:
    with Session(base_relations) as session:
        session.add_all(
            [
                ChambreChambreVirtuelle(chambre_id=chambre_id, chambre_virtuelle_id=virtuelle_id)
                for chambre_id, virtuelle_id in [(1, 1), (1, 2), (2, 1), (2, 2)]
            ]
        )
        session.commit()

    if mode == "sql":
        table = "chambre" if cote == "chambre" else "chambre_virtuelle"
        with base_relations.begin() as connexion:
            assert connexion.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            connexion.exec_driver_sql(f"DELETE FROM {table} WHERE id = 1")
    else:
        with Session(base_relations) as session:
            objet = session.get(Chambre if cote == "chambre" else ChambreVirtuelle, 1)
            if mode == "orm_charge":
                assert len(objet.chambres_virtuelles if cote == "chambre" else objet.chambres) == 2
            session.delete(objet)
            session.commit()

    with Session(base_relations) as session:
        assert {c.id for c in session.exec(select(Chambre))} == ({2, 3} if cote == "chambre" else {1, 2, 3})
        assert {v.id for v in session.exec(select(ChambreVirtuelle))} == ({2, 3} if cote == "virtuelle" else {1, 2, 3})
        assert session.get(TypeChambre, 1).libelle == "Double"
        liens = {(lien.chambre_id, lien.chambre_virtuelle_id) for lien in session.exec(select(ChambreChambreVirtuelle))}
        assert liens == ({(2, 1), (2, 2)} if cote == "chambre" else {(1, 2), (2, 2)})
