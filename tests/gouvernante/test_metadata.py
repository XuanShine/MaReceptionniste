from sqlmodel import SQLModel

import ma_gouvernante.models
import ma_receptionniste.models  # noqa: F401
from ma_gouvernante.models import GouvernanteModel


def test_tables_gouvernante_absentes_du_metadata_reception() -> None:
    assert ma_gouvernante.models.GouvernanteModel.metadata is GouvernanteModel.metadata
    assert GouvernanteModel.metadata is not SQLModel.metadata
    noms = set(GouvernanteModel.metadata.tables)
    assert {"user", "chambre", "listemenage", "lignemenage", "signalement", "historique"} <= noms
    assert {"listemenage", "lignemenage", "signalement"}.isdisjoint(SQLModel.metadata.tables)
    tables_reception = list(SQLModel.metadata.tables.values())
    for table in GouvernanteModel.metadata.tables.values():
        assert all(table is not autre for autre in tables_reception)
    assert "role" not in SQLModel.metadata.tables["user"].columns
    assert "type_chambre" in SQLModel.metadata.tables["chambre"].columns
    assert "reservation_id" in SQLModel.metadata.tables["historique"].columns
    assert "liste_id" not in SQLModel.metadata.tables["historique"].columns
